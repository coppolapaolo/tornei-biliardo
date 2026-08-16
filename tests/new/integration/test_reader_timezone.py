"""Ogni orario è nel fuso di **chi legge**, non in quello di Roma (ADR-043).

La piattaforma è pensata anche in inglese, e mostrava tutto in ora italiana con
il fuso scritto a mano dentro tre filtri Jinja. Per un giocatore a Londra ogni
orario era sbagliato di un'ora — e in modo invisibile, perché «21:00» è un
orario plausibile: nessun errore, nessun log, solo un appuntamento mancato.

Il fuso non si chiede: si deduce dal browser e si **salva**. Salvarlo è il
punto: promemoria e notifiche nascono in uno scheduled task, dove nessun
browser esiste, e le caselle di posta non eseguono JavaScript. Quello che non
finisce in colonna, fuori da una pagina non esiste — ed è la parte che questi
test presidiano più delle altre.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

import pytest

from models.user.models import User
from models.user.role_enum import UserRole
from models.user.services import UserService
from utils.jinja import (
    format_date_local,
    format_datetime_input,
    format_datetime_local_text,
    format_time_local,
)
from utils.local_time import (
    FALLBACK_TIMEZONE,
    is_valid_timezone,
    parse_local_datetime,
    resolve_timezone,
    resolve_timezone_for_user_id,
)

#: Un istante d'estate: Roma è UTC+2, Londra UTC+1, New York UTC-4. Tre fusi
#: diversi sullo stesso momento sono l'unico modo di accorgersi di uno scambio.
SUMMER_UTC = datetime(2026, 6, 12, 19, 0)


def _player(db_session, timezone=None) -> User:
    tag = uuid.uuid4().hex[:8]
    user = User(
        username=f"tz_{tag}",
        email=f"tz_{tag}@test.com",
        role=UserRole.PLAYER.value,
        timezone=timezone,
    )
    user.set_password("test123")
    db_session.add(user)
    db_session.commit()
    return user


# ────────────────────────────────────────────────────────────────────────────
# Il fuso: da dove si ricava
# ────────────────────────────────────────────────────────────────────────────


def test_an_invented_timezone_is_refused(db_session):
    """Il nome arriva da un client, e un client può mandare qualunque cosa.

    Scritto in colonna, un fuso inventato farebbe sollevare a ogni pagina che
    mostra un orario — cioè quasi tutte.
    """
    assert not is_valid_timezone("Mars/Olympus_Mons")
    assert not is_valid_timezone("")
    assert not is_valid_timezone(None)
    assert is_valid_timezone("America/New_York")

    user = _player(db_session, timezone="Europe/London")
    assert UserService.remember_timezone(user.id, "Mars/Olympus_Mons") is False
    assert (
        db_session.get(User, user.id).timezone == "Europe/London"
    ), "un fuso inventato non deve cancellare quello buono"


def test_the_timezone_is_written_only_when_it_changes(db_session):
    """La verifica gira a ogni accesso: una UPDATE per pagina sarebbe sprecata."""
    user = _player(db_session, timezone="Europe/Rome")

    assert UserService.remember_timezone(user.id, "Europe/Rome") is False
    assert UserService.remember_timezone(user.id, "America/New_York") is True
    assert db_session.get(User, user.id).timezone == "America/New_York"


def test_without_a_timezone_it_falls_back_to_italy(db_session):
    """NULL vuol dire «mai dedotto», e si comporta come prima del cambiamento."""
    user = _player(db_session, timezone=None)
    assert resolve_timezone(user) is FALLBACK_TIMEZONE
    assert resolve_timezone(None) is FALLBACK_TIMEZONE


# ────────────────────────────────────────────────────────────────────────────
# La lettura
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "timezone,expected",
    [
        ("Europe/Rome", "21:00"),
        ("Europe/London", "20:00"),
        ("America/New_York", "15:00"),
        (None, "21:00"),  # ripiego: ora italiana
    ],
)
def test_the_same_instant_reads_differently_for_each_reader(
    app, db_session, timezone, expected
):
    with app.app_context():
        tz = resolve_timezone(_player(db_session, timezone=timezone))
        assert expected in format_datetime_local_text(SUMMER_UTC, tz=tz)
        assert expected in str(format_time_local(SUMMER_UTC, tz=tz))


#: Mezzanotte è il punto in cui una data smette di essere «solo una data»: lo
#: stesso istante cade in due giorni diversi a seconda di chi guarda.
@pytest.mark.parametrize(
    "instant,timezone,expected",
    [
        # 23:30 UTC: a Roma è già il 13, a New York sono ancora le 19:30 del 12.
        (datetime(2026, 6, 12, 23, 30), "Europe/Rome", "13/06/2026"),
        (datetime(2026, 6, 12, 23, 30), "America/New_York", "12/06/2026"),
        # 01:30 UTC: a Roma è il 12, a New York è ancora l'11.
        (datetime(2026, 6, 12, 1, 30), "Europe/Rome", "12/06/2026"),
        (datetime(2026, 6, 12, 1, 30), "America/New_York", "11/06/2026"),
    ],
)
def test_a_date_near_midnight_is_the_readers_date(
    app, db_session, instant, timezone, expected
):
    """``|date_local`` su un *datetime* deve convertire, non troncare.

    Il filtro faceva ``strftime`` sul naive UTC grezzo: vicino a mezzanotte
    mostrava il giorno sbagliato a chiunque, italiani compresi. Ed è un errore
    che non si vede — «12/06» è una data plausibile.
    """
    with app.app_context():
        tz = resolve_timezone(_player(db_session, timezone=timezone))
        assert expected in str(format_date_local(instant, tz=tz))


def test_a_plain_date_has_nothing_to_convert(app, db_session):
    """Una ``date`` non è un istante: spostarla di fuso la falserebbe.

    La data di una gara è «il 12 giugno» per tutti, non un momento preciso da
    riproiettare — convertirla farebbe comparire l'11 a chi sta a ovest.
    """
    with app.app_context():
        new_york = resolve_timezone(_player(db_session, timezone="America/New_York"))
        assert "12/06/2026" in str(format_date_local(date(2026, 6, 12), tz=new_york))


def test_the_edit_form_is_repopulated_in_the_readers_timezone(app, db_session):
    """Il verso di lettura di un `datetime-local`: stesso fuso della scrittura.

    Se i due divergono, chi riapre un form e salva senza toccare niente sposta
    l'orario di un fuso a ogni giro.
    """
    with app.app_context():
        london = resolve_timezone(_player(db_session, timezone="Europe/London"))
        assert format_datetime_input(SUMMER_UTC, tz=london) == "2026-06-12T20:00"


# ────────────────────────────────────────────────────────────────────────────
# La scrittura
# ────────────────────────────────────────────────────────────────────────────


def test_what_a_reader_types_is_what_that_reader_reads_back(app, db_session):
    """Il giro completo, per un giocatore che non sta in Italia."""
    with app.app_context():
        london = resolve_timezone(_player(db_session, timezone="Europe/London"))

        stored = parse_local_datetime("2026-06-12T20:00", tz=london)
        # Sul DB resta l'istante in UTC, uguale per tutti.
        assert stored == SUMMER_UTC
        # E rileggendolo, l'ora che aveva digitato.
        assert format_datetime_input(stored, tz=london) == "2026-06-12T20:00"


def test_two_readers_typing_the_same_hour_mean_two_different_instants(app, db_session):
    """«Alle 21:00» detto da Roma e da New York non è lo stesso momento.

    È la ragione per cui il fuso deve stare sul dato e non nella formattazione:
    se la scrittura ignorasse il lettore, i due valori finirebbero uguali sul
    DB, e uno dei due giocatori si presenterebbe con sei ore di scarto.
    """
    with app.app_context():
        rome = resolve_timezone(_player(db_session, timezone="Europe/Rome"))
        new_york = resolve_timezone(_player(db_session, timezone="America/New_York"))

        from_rome = parse_local_datetime("2026-06-12T21:00", tz=rome)
        from_new_york = parse_local_datetime("2026-06-12T21:00", tz=new_york)

        assert from_rome != from_new_york
        assert (from_new_york - from_rome).total_seconds() == 6 * 3600


# ────────────────────────────────────────────────────────────────────────────
# Fuori da una pagina: dove il browser non c'è
# ────────────────────────────────────────────────────────────────────────────


def test_a_recipients_timezone_is_reachable_without_a_request(app, db_session):
    """Il caso che giustifica la colonna.

    Uno scheduled task compone il promemoria ore dopo, senza nessuno collegato:
    l'unico modo di sapere il fuso del destinatario è averlo scritto.
    """
    with app.app_context():
        user = _player(db_session, timezone="America/New_York")
        tz = resolve_timezone_for_user_id(user.id)
        assert "15:00" in format_datetime_local_text(SUMMER_UTC, tz=tz)


def test_an_unknown_recipient_does_not_explode(app, db_session):
    """Un id che non esiste più (utente cancellato) vale il ripiego, non un 500."""
    with app.app_context():
        assert resolve_timezone_for_user_id(999_999) is FALLBACK_TIMEZONE


def test_quiet_hours_are_read_on_the_players_own_clock(app, db_session, monkeypatch):
    """Le ore di silenzio le imposta l'utente: valgono nel **suo** fuso.

    Il confronto era scritto a mano su ``Europe/Rome``. Per un giocatore a New
    York la finestra risultava spostata di sei ore: notifiche in piena notte, e
    silenzio a metà pomeriggio — senza niente da vedere né a log né in pagina.
    """
    import models.notification.models as notification_models
    from models.notification.models import NotificationPreference, NotificationType

    with app.app_context():
        player = _player(db_session, timezone="America/New_York")
        preference = NotificationPreference(
            user_id=player.id,
            notification_type=NotificationType.MATCH_PROPOSAL,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(8, 0),
        )
        db_session.add(preference)
        db_session.commit()

        # 11:00 UTC: le 07:00 a New York (dentro la finestra), ma le 13:00 a
        # Roma (fuori) — è la coppia che distingue il fuso giusto da quello
        # scritto a mano.
        monkeypatch.setattr(
            notification_models, "utc_now", lambda: datetime(2026, 6, 12, 11, 0)
        )
        assert preference.is_in_quiet_hours() is True

        # 21:30 UTC: le 17:30 a New York (fuori), le 23:30 a Roma (dentro).
        monkeypatch.setattr(
            notification_models, "utc_now", lambda: datetime(2026, 6, 12, 21, 30)
        )
        assert preference.is_in_quiet_hours() is False


def test_a_match_reminder_speaks_to_each_player_in_their_own_hour(app, db_session):
    """Due giocatori in due fusi, due frasi diverse — non una sola per tutti.

    È il punto in cui «fuso di chi legge» costa qualcosa: il messaggio è testo
    cotto dentro la notifica, quindi va costruito per destinatario.
    """
    from models.individual_match.match_lifecycle_service import MatchLifecycleService
    from models.individual_match.models import IndividualMatch
    from models.notification.models import Notification
    from models.status_enum import MatchStatus

    with app.app_context():
        rome = _player(db_session, timezone="Europe/Rome")
        new_york = _player(db_session, timezone="America/New_York")

        from models.base import utc_now
        from datetime import timedelta

        match = IndividualMatch(
            player1_id=rome.id,
            player2_id=new_york.id,
            scheduled_at=utc_now() + timedelta(hours=2, minutes=30),
            status=MatchStatus.SCHEDULED.value,
            discipline="8_ball",
            distance=5,
        )
        db_session.add(match)
        db_session.commit()

        MatchLifecycleService.send_match_reminders(hours_before=2, window_minutes=60)

        def text_for(user_id: int) -> str:
            note = (
                Notification.query.filter_by(user_id=user_id)
                .order_by(Notification.id.desc())
                .first()
            )
            return note.message if note else ""

        rome_text = text_for(rome.id)
        new_york_text = text_for(new_york.id)

        assert rome_text and new_york_text, "il promemoria non è partito"
        assert (
            rome_text != new_york_text
        ), "stessa frase per due fusi diversi: uno dei due legge l'ora sbagliata"
