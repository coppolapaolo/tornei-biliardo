"""L'avversario di una sfida può essere un giocatore non registrato.

Emendamento del 2026-10-18 all'ADR-085, dalla segnalazione dell'utente: «non
posso prendere il TPA di una mia partita con un altro giocatore che non è
iscritto». Il percorso intero, dalle route:

* l'avvio rapido trova i non registrati e, per direttori e istruttori, ne
  crea uno nuovo con nome e cognome; un giocatore senza ruolo sceglie solo
  quelli che esistono già, l'admin non entra;
* il non registrato non firma e non riceve niente; la sfida si chiude con la
  firma di chi l'ha aperta, *registrata da uno*, e conta solo fra «Tutte»
  (regola del 2026-10-18 sera, che sostituisce l'attesa del riscatto);
* dopo il riscatto chi lo ha riscattato è invitato a rivederla, senza blocchi
  (il resto della revisione in `test_revisione_dopo_il_riscatto.py`).
"""

from __future__ import annotations

import uuid

import pytest
from flask import g

from models import User, db
from models.certificazione import Livello, Vista, livello_di_sfida
from models.individual_match.individual_rack_service import IndividualRackService
from models.individual_match.models import IndividualMatch
from models.individual_match.pending_confirmation import PendingConfirmationService
from models.individual_match.quick_match_service import QuickMatchService
from models.individual_match.scored_match_service import NuovoGiocatore
from models.notification.models import Notification
from models.exceptions import PermissionDeniedError
from models.status_enum import MatchStatus
from models.user.claim_service import ClaimService
from models.user.role_enum import UserRole
from models.user.services import UserService


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"nr_{uid}",
        email=f"nr_{uid}@test.com",
        role=role,
        gamification_override=True,
        onboarding_completed=True,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _istruttore() -> User:
    from models.user.role_enum import GrantableRole
    from models.user.role_grant_service import RoleGrantService

    istruttore = _user()
    admin = User.query.filter_by(role=UserRole.ADMIN.value).first() or _user(
        UserRole.ADMIN.value
    )
    RoleGrantService.grant(istruttore.id, GrantableRole.INSTRUCTOR, admin)
    db.session.commit()
    return istruttore


def _placeholder(creatore: User | None = None) -> User:
    creatore = creatore or _user(UserRole.DIRECTOR.value)
    giocatore = UserService.create_placeholder(
        "Luca", f"Bianchi{uuid.uuid4().hex[:5]}", creatore
    )
    db.session.commit()
    return giocatore


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


def _avvio_con_nuovo(client, nome="Gino", cognome=None):
    return _post(
        client,
        "/match/quick",
        json={
            "opponent_new_first_name": nome,
            "opponent_new_last_name": cognome or f"Verdi{uuid.uuid4().hex[:5]}",
            "match_format": "single",
            "distance": 3,
        },
    )


def _avvio_con(client, avversario: User):
    return _post(
        client,
        "/match/quick",
        json={"opponent_id": avversario.id, "match_format": "single", "distance": 3},
    )


def _alla_distanza(match_id: int, creatore: User, vincitore_id: int) -> IndividualMatch:
    for _ in range(3):
        IndividualRackService.add_rack_for_player(match_id, creatore.id, vincitore_id)
    db.session.commit()
    match = db.session.get(IndividualMatch, match_id)
    assert match is not None
    return match


def _notifiche_di(user_id: int) -> list[Notification]:
    return Notification.query.filter_by(user_id=user_id).all()


@pytest.mark.integration
class TestCreazioneDallAvvioRapido:
    @pytest.mark.parametrize("ruolo", ["direttore", "istruttore"])
    def test_direttore_e_istruttore_creano_l_avversario(self, app, ruolo):
        creatore = (
            _user(UserRole.DIRECTOR.value) if ruolo == "direttore" else (_istruttore())
        )
        client = _client_for(app, creatore)
        assert "Non ha un account? Aggiungilo" in _get(client, "/match/quick").get_data(
            as_text=True
        )

        risposta = _avvio_con_nuovo(client, "Gino", "Verdi")

        assert risposta.status_code == 200, risposta.get_data(as_text=True)[:300]
        match = db.session.get(IndividualMatch, risposta.get_json()["match_id"])
        assert match is not None
        avversario = match.player2
        assert avversario.is_placeholder
        assert avversario.created_by_id == creatore.id
        assert (avversario.first_name, avversario.last_name) == ("Gino", "Verdi")
        assert match.status == MatchStatus.IN_PROGRESS
        assert match.scorer_id is None
        assert _notifiche_di(avversario.id) == []

    def test_il_giocatore_senza_ruolo_non_crea(self, app):
        giocatore = _user()
        client = _client_for(app, giocatore)
        assert "Non ha un account? Aggiungilo" not in _get(
            client, "/match/quick"
        ).get_data(as_text=True)
        prima = User.query.filter_by(is_placeholder=True).count()

        risposta = _avvio_con_nuovo(client)

        assert risposta.status_code == 403
        assert User.query.filter_by(is_placeholder=True).count() == prima

    def test_il_giocatore_senza_ruolo_sceglie_un_non_registrato_esistente(self, app):
        giocatore = _user()
        esistente = _placeholder()
        client = _client_for(app, giocatore)

        cercati = _get(
            client, f"/match/players/search?ambito=sfida&q={esistente.last_name[:6]}"
        ).get_json()
        assert {"id": esistente.id, "is_placeholder": True}.items() <= next(
            r for r in cercati if r["id"] == esistente.id
        ).items()
        # La ricerca della proposta no: un non registrato non accetta proposte.
        proposta = _get(
            client, f"/match/players/search?q={esistente.last_name[:6]}"
        ).get_json()
        assert esistente.id not in {r["id"] for r in proposta}

        risposta = _avvio_con(client, esistente)

        assert risposta.status_code == 200, risposta.get_data(as_text=True)[:300]
        assert _notifiche_di(esistente.id) == []

    def test_l_admin_non_crea(self, app):
        admin = User.query.filter_by(role=UserRole.ADMIN.value).first() or _user(
            UserRole.ADMIN.value
        )
        assert QuickMatchService.can_create_opponent(admin) is False
        assert _avvio_con_nuovo(_client_for(app, admin)).status_code == 403
        with pytest.raises(PermissionDeniedError):
            QuickMatchService.start(admin.id, NuovoGiocatore("Ada", "Neri"))
        db.session.rollback()

    def test_la_rivincita_con_lui_e_un_avvio_rapido(self, app):
        """«Proponi un'altra data» non c'è: una proposta non gli arriverebbe."""
        creatore = _user(UserRole.DIRECTOR.value)
        client = _client_for(app, creatore)
        match_id = _avvio_con_nuovo(client).get_json()["match_id"]
        match = _alla_distanza(match_id, creatore, creatore.id)

        pagina = _get(client, f"/match/matches/{match_id}").get_data(as_text=True)
        assert "Rigioca adesso" in pagina
        assert "Proponi un&#39;altra data" not in pagina
        risposta = _get(client, f"/match/matches/{match_id}/rematch")
        assert risposta.status_code == 302
        assert (
            f"/match/quick?opponent_id={match.player2_id}"
            in risposta.headers["Location"]
        )


@pytest.mark.integration
class TestChiusuraSenzaLaSuaFirma:
    """Regola del 2026-10-18 sera, decisa dall'utente: «quando un match con
    giocatore aggiunto finisce non deve aspettare la conferma da parte del
    giocatore aggiunto». Sostituisce la regola di mezzogiorno (PR #712), in
    cui la sfida restava «in attesa del riscatto»."""

    @pytest.mark.parametrize("vince_il_creatore", [True, False])
    def test_alla_distanza_si_chiude_registrata_da_chi_l_ha_aperta(
        self, app, vince_il_creatore
    ):
        creatore = _user(UserRole.DIRECTOR.value)
        client = _client_for(app, creatore)
        match_id = _avvio_con_nuovo(client).get_json()["match_id"]
        avversario_id = db.session.get(IndividualMatch, match_id).player2_id

        match = _alla_distanza(
            match_id, creatore, creatore.id if vince_il_creatore else avversario_id
        )

        # Chiusa, con la sola firma di chi l'ha aperta — anche se vince lui.
        assert match.status == MatchStatus.CLOSED_UNILATERALLY
        assert match.is_recorded_by_one
        assert match.recorded_by_id == creatore.id
        assert match.player1_confirmed and not match.player2_confirmed
        assert match.winner_id == (creatore.id if vince_il_creatore else avversario_id)
        assert match.ended_at is not None
        assert match.awaiting_confirmation_from_id is None
        # Livello: solo nella vista «Tutte».
        assert livello_di_sfida(match) is Livello.IN_ATTESA
        assert Vista.TUTTE.comprende(livello_di_sfida(match))
        assert not Vista.CONFERMATE.comprende(livello_di_sfida(match))
        assert PendingConfirmationService.pending_for(creatore.id) == []

        # Nessun blocco: si apre subito un'altra sfida, anche con lui.
        altro = _user()
        assert _avvio_con(client, altro).status_code == 200
        assert _avvio_con(client, match.player2).status_code == 200

        # La pagina e l'elenco lo dicono: registrata da te, niente firma attesa.
        pagina = _get(client, f"/match/matches/{match_id}").get_data(as_text=True)
        assert "Registrata da te" in pagina
        assert "Manca la conferma" not in pagina
        assert "In attesa del riscatto" not in pagina
        elenco = _get(client, "/match/matches").get_data(as_text=True)
        assert "Registrata da te" in elenco
        assert _notifiche_di(avversario_id) == []

    def test_conta_per_l_elo_di_tutte_e_non_per_quello_globale(self, app):
        from models.rating.models import MatchRatingHistory, RatingSystem

        creatore = _user(UserRole.DIRECTOR.value)
        match_id = _avvio_con_nuovo(_client_for(app, creatore)).get_json()["match_id"]
        _alla_distanza(match_id, creatore, creatore.id)

        assert MatchRatingHistory.exists_for_individual_match(
            match_id, RatingSystem.ELO_ALL
        )
        assert not MatchRatingHistory.exists_for_individual_match(
            match_id, RatingSystem.ELO_GLOBAL
        )

    def test_formato_libero_si_chiude_con_termina(self, app):
        creatore = _user(UserRole.DIRECTOR.value)
        client = _client_for(app, creatore)
        risposta = _post(
            client,
            "/match/quick",
            json={
                "opponent_new_first_name": "Gino",
                "opponent_new_last_name": f"Libero{uuid.uuid4().hex[:5]}",
                "match_format": "free",
            },
        )
        match_id = risposta.get_json()["match_id"]
        assert db.session.get(IndividualMatch, match_id).distance is None
        IndividualRackService.add_rack_for_player(match_id, creatore.id, creatore.id)
        db.session.commit()

        assert _post(client, f"/match/matches/{match_id}/confirm").status_code in (
            200,
            302,
        )
        match = db.session.get(IndividualMatch, match_id)
        assert match.is_recorded_by_one
        assert match.winner_id == creatore.id

    def test_dashboard_non_la_mostra_fra_le_sfide_in_corso(self, app):
        from models.dashboard.section_builders import DashboardSectionBuilder

        creatore = _user(UserRole.DIRECTOR.value)
        match_id = _avvio_con_nuovo(_client_for(app, creatore)).get_json()["match_id"]
        _alla_distanza(match_id, creatore, creatore.id)

        sezione = DashboardSectionBuilder.build_individual_match_sections(creatore.id)
        assert match_id not in {m.id for m in sezione["sfide_in_corso"]}

    def test_chi_l_ha_registrata_la_ritira(self, app):
        creatore = _user(UserRole.DIRECTOR.value)
        client = _client_for(app, creatore)
        match_id = _avvio_con_nuovo(client).get_json()["match_id"]
        avversario_id = _alla_distanza(match_id, creatore, creatore.id).player2_id
        assert "Ritira la sfida" in _get(client, f"/match/matches/{match_id}").get_data(
            as_text=True
        )

        risposta = _post(client, f"/match/matches/{match_id}/withdraw")

        assert risposta.status_code == 302
        assert db.session.get(IndividualMatch, match_id).status == MatchStatus.CANCELLED
        assert _notifiche_di(avversario_id) == []


@pytest.mark.integration
class TestDopoIlRiscatto:
    def test_chi_ha_riscattato_e_invitato_a_rivedere_e_non_e_bloccato(self, app):
        creatore = _user(UserRole.DIRECTOR.value)
        client = _client_for(app, creatore)
        match_id = _avvio_con_nuovo(client).get_json()["match_id"]
        placeholder_id = _alla_distanza(match_id, creatore, creatore.id).player2_id

        luca = _user()
        richiesta = ClaimService.richiedi(placeholder_id, luca)
        db.session.commit()
        ClaimService.approve(richiesta.id, creatore)
        db.session.commit()

        match = db.session.get(IndividualMatch, match_id)
        assert match.player2_id == luca.id
        # Resta com'è: registrata da uno, In attesa, e aspetta la sua revisione.
        assert match.is_recorded_by_one
        assert livello_di_sfida(match) is Livello.IN_ATTESA
        assert match.awaits_review_from(luca.id)
        # Nessuna firma da dare, quindi nessun blocco.
        assert PendingConfirmationService.pending_for(luca.id) == []
        assert _avvio_con(_client_for(app, luca), _user()).status_code == 200
        # L'invito alla revisione, uno solo.
        inviti = [
            n for n in _notifiche_di(luca.id) if n.action_url == "/match/revisione"
        ]
        assert len(inviti) == 1


@pytest.mark.integration
class TestColRefertoTpa:
    """Il referto si chiude da solo alla distanza (#714): la sfida contro il
    non registrato si chiude con lui, e annullare l'ultimo tocco riapre
    entrambi."""

    def _al_tre_col_referto(self, creatore):
        from models.status_enum import Discipline
        from models.tpa.services import TpaRefertoService

        match = QuickMatchService.start(
            creatore.id,
            NuovoGiocatore("Gino", f"Tpa{uuid.uuid4().hex[:5]}"),
            {
                "match_format": "single",
                "distance": 3,
                "discipline": Discipline.NINE_BALL.value,
            },
        )
        db.session.commit()
        TpaRefertoService.open_referto(match.id, creatore.id)
        db.session.commit()
        for _ in range(3):
            for comando in ("seat:1", "1", "9", "end"):
                referto = TpaRefertoService.get_for_match(match.id)
                assert referto is not None
                if referto.is_closed:
                    break
                TpaRefertoService.press(referto.id, creatore.id, comando)
        db.session.commit()
        sfida = db.session.get(IndividualMatch, match.id)
        assert sfida is not None
        return sfida

    def test_alla_distanza_si_chiudono_referto_e_sfida(self, app):
        from models.tpa.services import TpaRefertoService

        creatore = _user(UserRole.DIRECTOR.value)
        match = self._al_tre_col_referto(creatore)

        referto = TpaRefertoService.get_for_match(match.id)
        assert referto is not None and referto.is_closed
        assert match.is_recorded_by_one
        assert match.recorded_by_id == creatore.id

    def test_annullare_riapre_referto_e_sfida(self, app):
        from models.tpa.services import TpaRefertoService

        creatore = _user(UserRole.DIRECTOR.value)
        match_id = self._al_tre_col_referto(creatore).id
        referto = TpaRefertoService.get_for_match(match_id)
        assert referto is not None
        assert TpaRefertoService.can_undo_closing(referto, creatore.id)

        for _ in range(4):
            sfida = db.session.get(IndividualMatch, match_id)
            if sfida.player1_score < 3:
                break
            TpaRefertoService.undo(referto.id, creatore.id)
            db.session.commit()

        sfida = db.session.get(IndividualMatch, match_id)
        referto = TpaRefertoService.get_for_match(match_id)
        assert referto is not None and not referto.is_closed
        assert sfida.status == MatchStatus.IN_PROGRESS
        assert not sfida.is_recorded_by_one
        assert sfida.winner_id is None
