"""La sfida conclusa non si tocca più, e gli avvisi superati si ritirano.

Due difetti trovati dall'utente il 2026-10-18, dopo le PR #714 e #716
(``SPECIFICHE.md``, «Ciclo di vita dei Match», nota del 2026-10-18):

* togliere un triangolo da una sfida **confermata da entrambi** azzerava le
  firme e la lasciava ``CONFIRMED_BY_BOTH``: confermata senza firme, con
  l'ELO globale già mosso. La specifica non prevede correzioni dopo la doppia
  firma, quindi la correzione è **impedita** — dal segnapunti, dal referto
  TPA rimasto aperto, dall'annulla che riapre il referto — e i pulsanti non
  si mostrano;
* riaperto il referto chiuso alla distanza, la richiesta «conferma il
  risultato» già partita restava fra le notifiche dell'avversario. Ogni volta
  che le firme si azzerano, la richiesta ancora da leggere scade; alla nuova
  chiusura ne parte una nuova.
"""

from __future__ import annotations

import uuid

import pytest
from flask import g

from models import User, db
from models.exceptions import ConflictError
from models.individual_match.individual_rack_service import IndividualRackService
from models.individual_match.match_lifecycle_service import MatchLifecycleService
from models.individual_match.models import IndividualMatch
from models.individual_match.quick_match_service import QuickMatchService
from models.individual_match.scored_match_service import ScoredMatchService
from models.notification.models import (
    Notification,
    NotificationStatus,
    NotificationType,
)
from models.status_enum import Discipline, MatchStatus
from models.tpa.services import TpaRefertoService
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService
from models.user.services import UserService

DA_LEGGERE = (NotificationStatus.PENDING, NotificationStatus.SENT)


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"sc_{uid}",
        email=f"sc_{uid}@test.com",
        role=role,
        gamification_override=True,
        onboarding_completed=True,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _client_for(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True
    return client


def _get(client, url, **kw):
    g.pop("_login_user", None)
    return client.get(url, **kw)


def _post(client, url, **kw):
    g.pop("_login_user", None)
    return client.post(url, **kw)


def _sfida(a: User, b: User, **config) -> IndividualMatch:
    impostazioni = {
        "match_format": "single",
        "distance": 2,
        "discipline": Discipline.NINE_BALL.value,
    }
    impostazioni.update(config)
    match = QuickMatchService.start(a.id, b.id, impostazioni)
    db.session.commit()
    return match


def _vinci_un_rack(referto_id: int, user_id: int, seat: int = 1) -> None:
    """Spacca imbucando tutto: nove bilie, rack chiuso."""
    TpaRefertoService.press(referto_id, user_id, f"seat:{seat}")
    TpaRefertoService.press(referto_id, user_id, "1")
    TpaRefertoService.press(referto_id, user_id, "9")
    TpaRefertoService.press(referto_id, user_id, "end")
    db.session.commit()


def _richieste(user_id: int, match_id: int, stati=DA_LEGGERE):
    return Notification.query.filter(
        Notification.user_id == user_id,
        Notification.notification_type == NotificationType.MATCH_RESULT_TO_CONFIRM,
        Notification.action_url == f"/match/matches/{match_id}",
        Notification.status.in_(stati),  # type: ignore[attr-defined]
    ).all()


def _confermata_a_mano(a: User, b: User) -> IndividualMatch:
    """Sfida al 2 segnata col segnapunti: Aldo vince 2-0, firmano tutti e due."""
    match = _sfida(a, b)
    for _ in range(2):
        IndividualRackService.add_rack_for_player(match.id, a.id, a.id)
    MatchLifecycleService.confirm_match_result(match.id, b.id)
    db.session.commit()
    match = db.session.get(IndividualMatch, match.id)
    assert match.status == MatchStatus.CONFIRMED_BY_BOTH
    return match


@pytest.mark.integration
class TestLaSfidaConfermataNonSiTocca:
    def test_il_triangolo_non_si_toglie(self):
        aldo, bruno = _user(), _user()
        match = _confermata_a_mano(aldo, bruno)

        with pytest.raises(ConflictError):
            IndividualRackService.remove_rack_for_player(match.id, aldo.id, aldo.id)
        db.session.rollback()

        match = db.session.get(IndividualMatch, match.id)
        assert match.status == MatchStatus.CONFIRMED_BY_BOTH
        assert (match.player1_score, match.player2_score) == (2, 0)
        assert match.player1_confirmed and match.player2_confirmed
        assert len(match.active_racks()) == 2

    def test_la_route_lo_rifiuta_e_il_pulsante_non_c_e(self, app):
        aldo, bruno = _user(), _user()
        match = _confermata_a_mano(aldo, bruno)
        client = _client_for(app, aldo)

        risposta = _post(
            client,
            f"/match/matches/{match.id}/racks/remove",
            json={"player_id": aldo.id},
        )
        assert risposta.status_code == 400
        assert not risposta.get_json()["success"]
        assert db.session.get(IndividualMatch, match.id).player1_score == 2

        pagina = _get(client, f"/match/matches/{match.id}").get_data(as_text=True)
        assert "c7-board__undo" not in pagina

    def test_in_corso_il_pulsante_c_e(self, app):
        """Il controllo di prima, a rovescio: senza, l'assenza del pulsante
        sulla confermata non direbbe niente."""
        aldo, bruno = _user(), _user()
        match = _sfida(aldo, bruno)
        IndividualRackService.add_rack_for_player(match.id, aldo.id, aldo.id)
        db.session.commit()

        pagina = _get(_client_for(app, aldo), f"/match/matches/{match.id}")
        assert "c7-board__undo" in pagina.get_data(as_text=True)

    def test_il_referto_rimasto_aperto_non_riscrive(self, app):
        """Formato libero: il referto si chiude a mano, e i due possono firmare
        prima. A sfida confermata il referto si rilegge e basta."""
        aldo, bruno = _user(), _user()
        match = _sfida(aldo, bruno, match_format="free")
        referto = TpaRefertoService.open_referto(match.id, aldo.id)
        db.session.commit()
        _vinci_un_rack(referto.id, aldo.id)
        _vinci_un_rack(referto.id, aldo.id, seat=1)
        MatchLifecycleService.confirm_match_result(match.id, aldo.id)
        MatchLifecycleService.confirm_match_result(match.id, bruno.id)
        db.session.commit()
        match = db.session.get(IndividualMatch, match.id)
        assert match.status == MatchStatus.CONFIRMED_BY_BOTH
        referto = TpaRefertoService.get_for_match(match.id)
        assert not referto.is_closed

        for gesto in (
            lambda: TpaRefertoService.undo(referto.id, aldo.id),
            lambda: TpaRefertoService.press(referto.id, aldo.id, "seat:1"),
        ):
            with pytest.raises(ConflictError):
                gesto()
            db.session.rollback()

        match = db.session.get(IndividualMatch, match.id)
        assert match.status == MatchStatus.CONFIRMED_BY_BOTH
        assert (match.player1_score, match.player2_score) == (2, 0)
        stato = TpaRefertoService.describe(referto, viewer_id=aldo.id)
        assert not stato["can_write"] and not stato["can_undo"]

        pagina = _get(_client_for(app, aldo), f"/match/matches/{match.id}/tpa")
        assert "il referto si rilegge, ma non si scrive più" in pagina.get_data(
            as_text=True
        )

    def test_il_referto_chiuso_alla_distanza_non_si_riapre(self, app):
        aldo, bruno = _user(), _user()
        match = _sfida(aldo, bruno)
        referto = TpaRefertoService.open_referto(match.id, aldo.id)
        db.session.commit()
        _vinci_un_rack(referto.id, aldo.id)
        _vinci_un_rack(referto.id, aldo.id, seat=1)
        MatchLifecycleService.confirm_match_result(match.id, bruno.id)
        db.session.commit()
        referto = TpaRefertoService.get_for_match(match.id)
        assert referto.is_closed

        assert not TpaRefertoService.can_undo_closing(referto, aldo.id)
        with pytest.raises(ConflictError):
            TpaRefertoService.undo(referto.id, aldo.id)
        db.session.rollback()
        pagina = _get(_client_for(app, aldo), f"/match/matches/{match.id}/tpa")
        assert "riapri il referto" not in pagina.get_data(as_text=True)

    def test_registrata_da_uno_prima_del_riscatto_si_corregge(self):
        """Contro un non registrato la chiusura è la sola firma di chi segna:
        un triangolo tolto la rimette in corso, come dal referto."""
        marco = _user(UserRole.DIRECTOR.value)
        gino = UserService.create_placeholder("Gino", uuid.uuid4().hex[:6], marco)
        db.session.commit()
        match = _sfida(marco, gino)
        for _ in range(2):
            IndividualRackService.add_rack_for_player(match.id, marco.id, marco.id)
        db.session.commit()
        assert db.session.get(IndividualMatch, match.id).is_recorded_by_one

        IndividualRackService.remove_rack_for_player(match.id, marco.id, marco.id)
        db.session.commit()

        match = db.session.get(IndividualMatch, match.id)
        assert match.status == MatchStatus.IN_PROGRESS
        assert match.recorded_by_id is None and match.player1_score == 1


@pytest.mark.integration
class TestGliAvvisiSuperatiSiRitirano:
    def test_riaprire_il_referto_ritira_la_richiesta(self):
        aldo, bruno = _user(), _user()
        match = _sfida(aldo, bruno)
        referto = TpaRefertoService.open_referto(match.id, aldo.id)
        db.session.commit()
        _vinci_un_rack(referto.id, aldo.id)
        _vinci_un_rack(referto.id, aldo.id, seat=1)
        (vecchia,) = _richieste(bruno.id, match.id)

        TpaRefertoService.undo(referto.id, aldo.id)
        db.session.commit()

        assert db.session.get(Notification, vecchia.id).status == (
            NotificationStatus.EXPIRED
        )
        assert _richieste(bruno.id, match.id) == []

        # Alla nuova chiusura parte la richiesta nuova, una sola: il tavolo
        # ripassato riassegna il triangolo.
        TpaRefertoService.press(referto.id, aldo.id, "end")
        db.session.commit()
        (nuova,) = _richieste(bruno.id, match.id)
        assert nuova.id != vecchia.id

    def test_il_rifiuto_ritira_la_richiesta_di_chi_rifiuta(self):
        aldo, bruno = _user(), _user()
        match = _sfida(aldo, bruno)
        for _ in range(2):
            IndividualRackService.add_rack_for_player(match.id, aldo.id, aldo.id)
        db.session.commit()
        assert len(_richieste(bruno.id, match.id)) == 1

        MatchLifecycleService.reject_match_result(match.id, bruno.id)
        db.session.commit()

        assert _richieste(bruno.id, match.id) == []
        assert (
            len(_richieste(bruno.id, match.id, stati=(NotificationStatus.EXPIRED,)))
            == 1
        )

    def test_il_triangolo_tolto_dal_segnapunti_la_ritira(self):
        aldo, bruno = _user(), _user()
        match = _sfida(aldo, bruno)
        for _ in range(2):
            IndividualRackService.add_rack_for_player(match.id, aldo.id, aldo.id)
        db.session.commit()

        IndividualRackService.remove_rack_for_player(match.id, aldo.id, aldo.id)
        db.session.commit()

        assert _richieste(bruno.id, match.id) == []
        # La partita è di nuovo in corso: l'avviso dell'avvio rapido resta.
        assert (
            Notification.query.filter_by(
                user_id=bruno.id, notification_type=NotificationType.MATCH_ACCEPTED
            )
            .filter(Notification.status.in_(DA_LEGGERE))  # type: ignore[attr-defined]
            .count()
            == 1
        )

    def test_partita_di_altri_due_riaperta_ritira_le_due_richieste(self):
        admin = _user(UserRole.ADMIN.value)
        istruttore = _user()
        RoleGrantService.grant(istruttore.id, GrantableRole.INSTRUCTOR, admin)
        db.session.commit()
        anna, bea = _user(), _user()
        match = ScoredMatchService.start(
            istruttore,
            anna.id,
            bea.id,
            {"discipline": Discipline.NINE_BALL.value, "distance": 2},
        )
        db.session.commit()
        referto = TpaRefertoService.get_for_match(match.id)
        _vinci_un_rack(referto.id, istruttore.id)
        _vinci_un_rack(referto.id, istruttore.id, seat=1)
        assert TpaRefertoService.get_for_match(match.id).is_closed
        assert len(_richieste(anna.id, match.id)) == 1
        assert len(_richieste(bea.id, match.id)) == 1

        TpaRefertoService.undo(referto.id, istruttore.id)
        db.session.commit()

        assert _richieste(anna.id, match.id) == []
        assert _richieste(bea.id, match.id) == []

        TpaRefertoService.press(referto.id, istruttore.id, "end")
        db.session.commit()
        assert len(_richieste(anna.id, match.id)) == 1
        assert len(_richieste(bea.id, match.id)) == 1
