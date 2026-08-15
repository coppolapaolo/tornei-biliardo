"""Unit test dei promemoria match (`MatchLifecycleService.send_match_reminders`).

Il promemoria gira da uno scheduled task che nessuno guarda: se sbaglia
finestra o manda due volte, l'unico a scoprirlo è il giocatore. Qui si fissano
le tre proprietà che lo scheduling orario richiede:

1. la finestra copre l'intero intervallo fra due esecuzioni (nessun buco);
2. una seconda esecuzione non rimanda lo stesso promemoria (nessun doppione,
   anche quando lo scheduler parte in ritardo e le finestre si sovrappongono);
3. l'orario mostrato è quello italiano, non l'UTC salvato sul DB.
"""

import uuid
from datetime import timedelta

import pytest

from models.base import utc_now
from models.individual_match.match_lifecycle_service import MatchLifecycleService
from models.individual_match.models import IndividualMatch
from models.notification.models import Notification, NotificationType
from models.status_enum import MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _make_user(db_session) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"player_{suffix}",
        email=f"player_{suffix}@example.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def players(db_session):
    return _make_user(db_session), _make_user(db_session)


def _make_match(db_session, players, scheduled_at) -> IndividualMatch:
    player1, player2 = players
    match = IndividualMatch(
        player1_id=player1.id,
        player2_id=player2.id,
        scheduled_at=scheduled_at,
        status=MatchStatus.SCHEDULED.value,
        discipline="8_ball",
        distance=5,
    )
    db_session.add(match)
    db_session.commit()
    return match


def _reminders_for(match: IndividualMatch):
    return Notification.query.filter_by(
        notification_type=NotificationType.MATCH_REMINDER,
        action_url=f"/match/matches/{match.id}",
    ).all()


@pytest.mark.parametrize("minutes_into_window", [1, 30, 59])
def test_hourly_window_covers_the_whole_gap_between_runs(
    db_session, players, minutes_into_window
):
    """Con esecuzione oraria la finestra deve essere di 60 minuti.

    Era il guasto vero: `window_minutes=15` con un task che non può girare più
    spesso di un'ora copriva 15 minuti su 60, e tre promemoria su quattro non
    partivano.
    """
    scheduled_at = utc_now() + timedelta(hours=2, minutes=minutes_into_window)
    match = _make_match(db_session, players, scheduled_at)

    reminded = MatchLifecycleService.send_match_reminders()

    assert match.id in reminded
    assert len(_reminders_for(match)) == 2, "una notifica per ciascun giocatore"


def test_match_outside_the_window_is_not_reminded(db_session, players):
    """Il match di domani non deve ricevere il promemoria oggi."""
    match = _make_match(db_session, players, utc_now() + timedelta(hours=26))

    assert MatchLifecycleService.send_match_reminders() == []
    assert _reminders_for(match) == []


def test_second_run_does_not_send_a_duplicate(db_session, players):
    """Idempotenza: due esecuzioni ravvicinate mandano un promemoria solo.

    Gli scheduled task di PythonAnywhere partono "entro qualche minuto"
    dall'orario, quindi finestre contigue in teoria si sovrappongono in
    pratica. Senza il guard il giocatore riceverebbe il doppione.
    """
    match = _make_match(db_session, players, utc_now() + timedelta(hours=2, minutes=30))

    assert MatchLifecycleService.send_match_reminders() == [match.id]
    assert MatchLifecycleService.send_match_reminders() == []
    assert len(_reminders_for(match)) == 2, "nessuna notifica in più al secondo giro"


def test_old_reminder_does_not_block_a_rescheduled_match(db_session, players):
    """Un match spostato in avanti riceve un nuovo promemoria.

    Il guard guarda solo i promemoria abbastanza recenti da riferirsi a un
    match ancora da giocare: altrimenti bloccherebbe per sempre il promemoria
    di una riprogrammazione.
    """
    match = _make_match(db_session, players, utc_now() + timedelta(hours=2, minutes=30))
    MatchLifecycleService.send_match_reminders()

    # Il promemoria appartiene a ieri: il match è stato spostato da allora.
    for notification in _reminders_for(match):
        notification.created_at = utc_now() - timedelta(days=1)
    db_session.commit()

    assert MatchLifecycleService.send_match_reminders() == [match.id]
    assert len(_reminders_for(match)) == 4


def test_reminder_is_resent_when_the_match_is_rescheduled_soon_after(
    db_session, players
):
    """Riprogrammazione **ravvicinata**: il vecchio promemoria non deve zittire
    quello nuovo.

    Caso distinto da quello sopra, dove il promemoria era di un giorno prima.
    Qui è di appena 40 minuti fa, quindi con una soglia globale
    (``now - stale_after``) risulterebbe ancora valido e il match verrebbe
    saltato: il giocatore resterebbe con l'orario vecchio e nessuna correzione.
    La soglia ancorata a ``scheduled_at`` lo classifica invece come superato.
    """
    match = _make_match(db_session, players, utc_now() + timedelta(hours=2, minutes=30))
    assert MatchLifecycleService.send_match_reminders() == [match.id]

    # Il promemoria è recente (40 minuti), ma si riferisce all'orario vecchio.
    for notification in _reminders_for(match):
        notification.created_at = utc_now() - timedelta(minutes=40)

    # Match spostato in avanti, ma ancora dentro la finestra di questo giro.
    match.scheduled_at = utc_now() + timedelta(hours=2, minutes=50)
    db_session.commit()

    assert MatchLifecycleService.send_match_reminders() == [
        match.id
    ], "il nuovo orario deve produrre un nuovo promemoria"
    assert len(_reminders_for(match)) == 4


def test_non_scheduled_matches_are_skipped(db_session, players):
    """Un match già iniziato o annullato non ha bisogno di promemoria."""
    match = _make_match(db_session, players, utc_now() + timedelta(hours=2, minutes=30))
    match.status = MatchStatus.CANCELLED.value
    db_session.commit()

    assert MatchLifecycleService.send_match_reminders() == []


def test_message_shows_italian_time_not_utc(db_session, players):
    """L'orario nel messaggio è quello che il giocatore legge sull'orologio.

    `scheduled_at` è UTC naive per convenzione di progetto: stampato con
    `strftime` diretto il promemoria annuncerebbe un orario sbagliato di una o
    due ore a seconda dell'ora legale.
    """
    from utils.jinja import format_datetime_local_text

    scheduled_at = utc_now() + timedelta(hours=2, minutes=30)
    match = _make_match(db_session, players, scheduled_at)

    MatchLifecycleService.send_match_reminders()

    expected = format_datetime_local_text(scheduled_at)
    message = _reminders_for(match)[0].message
    assert expected in message, f"atteso l'orario locale {expected} in {message!r}"


def test_match_is_not_counted_when_no_notification_goes_out(db_session, players):
    """Se entrambi hanno disattivato il promemoria, il match non va contato.

    `create_notification` restituisce `None` (senza sollevare) quando la
    preferenza blocca l'invio: contando comunque il match, il riepilogo dello
    scheduled task avrebbe annunciato promemoria mai partiti.
    """
    from models.notification.services import NotificationService

    for player in players:
        NotificationService.set_user_preference(
            user_id=player.id,
            notification_type=NotificationType.MATCH_REMINDER,
            enabled=False,
        )
    match = _make_match(db_session, players, utc_now() + timedelta(hours=2, minutes=30))

    assert MatchLifecycleService.send_match_reminders() == []
    assert _reminders_for(match) == []


def test_match_is_counted_when_only_one_player_is_reachable(db_session, players):
    """Basta un giocatore raggiunto perché il promemoria conti come inviato."""
    from models.notification.services import NotificationService

    NotificationService.set_user_preference(
        user_id=players[0].id,
        notification_type=NotificationType.MATCH_REMINDER,
        enabled=False,
    )
    match = _make_match(db_session, players, utc_now() + timedelta(hours=2, minutes=30))

    assert MatchLifecycleService.send_match_reminders() == [match.id]
    assert len(_reminders_for(match)) == 1


def test_reminder_links_back_to_the_match(db_session, players):
    """`related_entities` lega la notifica al match, non solo via URL."""
    match = _make_match(db_session, players, utc_now() + timedelta(hours=2, minutes=30))

    MatchLifecycleService.send_match_reminders()

    notification = _reminders_for(match)[0]
    assert notification.get_related_entities() == {"individual_match_id": match.id}
