"""Giocatori non ancora registrati, creati da direttori e istruttori (ADR-085).

Il percorso intero: chi può crearli, come nascono (senza email, con una
password che non vale niente, uno username dal nome), perché non entrano mai
nell'app, cosa non ricevono (notifiche, proposte di sfida, la ricerca degli
avversari) e cosa invece fanno come chiunque (iscriversi a una gara, contare
in classifica, giocare la partita di altri due). Più l'unione con un account
vero, che sarà il riscatto della PR successiva.
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

import pytest
from flask import g

from models import User, db
from models.base import utc_now
from models.competition.models import Gara, Inscription
from models.exceptions import PermissionDeniedError, ValidationError
from models.notification.models import Notification, NotificationType
from models.notification.services import NotificationService
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import PASSWORD_DA_RISCATTARE
from models.user.profile_service import UserProfileService
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService
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
    admin = _user(UserRole.ADMIN.value)
    marco = _user()
    RoleGrantService.grant(marco.id, GrantableRole.INSTRUCTOR, admin)
    db.session.commit()
    return marco


def _nome() -> tuple[str, str]:
    return "Mario", f"Rossi{uuid.uuid4().hex[:5]}"


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


def _gara(director: User, status=GaraStatus.INSCRIPTION.value) -> Gara:
    gara = Gara(
        name=f"Gara {uuid.uuid4().hex[:6]}",
        number=1,
        date=date.today() + timedelta(days=7),
        time=time(20, 0),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        rounds_count=3,
        min_participants=2,
        max_participants=16,
        matchmaking_strategy="random",
        director_id=director.id,
        status=status,
        inscription_start=utc_now() - timedelta(days=1),
        inscription_end=utc_now() + timedelta(days=3),
    )
    db.session.add(gara)
    db.session.commit()
    from models.competition.services import GaraService

    GaraService.add_director(gara.id, director.id, director.id)
    db.session.commit()
    return gara


# ---------------------------------------------------------------- creazione


class TestCreazione:
    def test_il_direttore_lo_crea_senza_email_e_senza_password(self):
        direttore = _user(UserRole.DIRECTOR.value)
        nome, cognome = _nome()

        giocatore = UserService.create_placeholder(nome, cognome, direttore)

        rivisto = db.session.get(User, giocatore.id)
        assert rivisto.is_placeholder is True
        assert rivisto.email is None
        assert rivisto.password_hash == PASSWORD_DA_RISCATTARE
        assert rivisto.created_by_id == direttore.id
        assert rivisto.claimed_at is None
        assert rivisto.onboarding_completed is True
        assert rivisto.is_verified is False
        assert rivisto.is_fittizio is False
        assert rivisto.role == UserRole.PLAYER.value
        # Nome e cognome si leggono decifrati, come per chiunque.
        assert rivisto.first_name == nome
        assert rivisto.last_name == cognome
        assert rivisto.username == f"{nome} {cognome}"

    def test_lo_crea_anche_un_istruttore_e_l_admin(self):
        for autore in (_istruttore(), _user(UserRole.ADMIN.value)):
            nome, cognome = _nome()
            assert UserService.create_placeholder(nome, cognome, autore).is_placeholder

    def test_un_giocatore_qualunque_non_lo_crea(self):
        nome, cognome = _nome()
        with pytest.raises(PermissionDeniedError):
            UserService.create_placeholder(nome, cognome, _user())

    def test_servono_nome_e_cognome(self):
        direttore = _user(UserRole.DIRECTOR.value)
        with pytest.raises(ValidationError):
            UserService.create_placeholder("Mario", "  ", direttore)
        with pytest.raises(ValidationError):
            UserService.create_placeholder("", "Rossi", direttore)

    def test_due_omonimi_hanno_due_username(self):
        direttore = _user(UserRole.DIRECTOR.value)
        nome, cognome = _nome()
        primo = UserService.create_placeholder(nome, cognome, direttore)
        secondo = UserService.create_placeholder(nome, cognome, direttore)
        assert primo.username == f"{nome} {cognome}"
        assert secondo.username == f"{nome} {cognome} (2)"

    def test_lo_username_non_ruba_quello_di_un_utente_vero(self):
        direttore = _user(UserRole.DIRECTOR.value)
        vero = _user()
        nome, cognome = vero.username.split("_")
        giocatore = UserService.create_placeholder(nome, cognome, direttore)
        assert giocatore.username != vero.username


# ---------------------------------------------------------------- niente login


class TestNessunAccesso:
    def test_l_autenticazione_lo_rifiuta_anche_con_una_password(self):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = UserService.create_placeholder(*_nome(), direttore)
        # Anche se qualcuno, per errore, gli impostasse una password vera.
        giocatore.set_password("pw123456")
        db.session.commit()

        assert UserService.authenticate_user(giocatore.username, "pw123456") is None
        assert (
            UserProfileService.authenticate_user(giocatore.username, "pw123456") is None
        )

    def test_la_sessione_non_lo_carica(self):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = UserService.create_placeholder(*_nome(), direttore)
        assert User.from_session_id(giocatore.get_id()) is None

    def test_il_modulo_di_login_non_lo_fa_entrare(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = UserService.create_placeholder(*_nome(), direttore)
        client = app.test_client()
        g.pop("_login_user", None)
        risposta = client.post(
            "/auth/login",
            data={"username": giocatore.username, "password": PASSWORD_DA_RISCATTARE},
        )
        with client.session_transaction() as sess:
            assert "_user_id" not in sess
        assert risposta.status_code in (200, 302)


# ---------------------------------------------------------------- cosa non riceve


class TestCosaNonRiceve:
    def test_nessuna_notifica(self):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = UserService.create_placeholder(*_nome(), direttore)

        esito = NotificationService.create_notification(
            user_id=giocatore.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="Ciao",
            message="Ciao",
        )
        db.session.commit()

        assert esito is None
        assert Notification.query.filter_by(user_id=giocatore.id).count() == 0

    def test_non_riceve_proposte_di_sfida(self):
        from models.individual_match.proposal_service import ProposalService

        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = UserService.create_placeholder(*_nome(), direttore)
        proponente = _user()

        with pytest.raises(ValidationError):
            ProposalService.create_direct_proposal(
                proposer_id=proponente.id,
                invited_user_ids=[giocatore.id],
                location="Sala",
                scheduled_at=utc_now() + timedelta(days=2),
            )

    def test_si_sfida_con_l_avvio_rapido_senza_avvisi(self):
        """Emendamento del 2026-10-18 all'ADR-085: fino a quella data l'avvio
        rapido lo rifiutava (`ConflictError`). Ora lo accetta, e non lo
        avvisa: non ha un account con cui leggere."""
        from models.individual_match.quick_match_service import QuickMatchService

        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = UserService.create_placeholder(*_nome(), direttore)
        partita = QuickMatchService.start(_user().id, giocatore.id)
        db.session.commit()

        assert partita.player2_id == giocatore.id
        assert Notification.query.filter_by(user_id=giocatore.id).count() == 0

    def test_la_ricerca_degli_avversari_non_lo_trova(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        nome, cognome = _nome()
        giocatore = UserService.create_placeholder(nome, cognome, direttore)
        client = _client_for(app, _user())

        risposta = _get(client, f"/match/players/search?q={cognome}")

        assert risposta.status_code == 200
        assert giocatore.id not in [r["id"] for r in risposta.get_json()]

    def test_la_ricerca_della_partita_di_altri_due_lo_trova(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        nome, cognome = _nome()
        giocatore = UserService.create_placeholder(nome, cognome, direttore)
        client = _client_for(app, direttore)

        risposta = _get(client, f"/match/players/search?q={cognome}&ambito=altri_due")

        trovati = {r["id"]: r for r in risposta.get_json()}
        assert giocatore.id in trovati
        assert trovati[giocatore.id]["is_placeholder"] is True


# ---------------------------------------------------------------- gara


class TestIscrizioneDaDirettore:
    def test_il_direttore_crea_e_iscrive_in_un_gesto(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        nome, cognome = _nome()
        client = _client_for(app, direttore)

        risposta = _post(
            client,
            f"/admin/gara/{gara.id}/admin_inscribe_placeholder",
            data={"first_name": nome, "last_name": cognome},
        )

        assert risposta.status_code == 302
        giocatore = User.query.filter_by(username=f"{nome} {cognome}").one()
        assert giocatore.is_placeholder
        assert giocatore.created_by_id == direttore.id
        iscrizione = Inscription.query.filter_by(
            gara_id=gara.id, user_id=giocatore.id
        ).one()
        assert iscrizione.inscribed_by_id == direttore.id
        # Nessuna notifica: non ha un account per leggerla.
        assert Notification.query.filter_by(user_id=giocatore.id).count() == 0

    def test_nella_lista_degli_iscritti_si_vede_che_non_e_registrato(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        nome, cognome = _nome()
        client = _client_for(app, direttore)
        _post(
            client,
            f"/admin/gara/{gara.id}/admin_inscribe_placeholder",
            data={"first_name": nome, "last_name": cognome},
        )

        pagina = _get(client, f"/admin/gara/{gara.id}").get_data(as_text=True)

        assert f"{nome} {cognome}" in pagina
        assert "c7-nonreg" in pagina
        # E il modulo per crearne un altro c'è.
        assert "admin_inscribe_placeholder" in pagina

    def test_un_giocatore_non_crea_iscritti(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        nome, cognome = _nome()
        client = _client_for(app, _user())

        risposta = _post(
            client,
            f"/admin/gara/{gara.id}/admin_inscribe_placeholder",
            data={"first_name": nome, "last_name": cognome},
        )

        assert risposta.status_code in (302, 403)
        assert User.query.filter_by(username=f"{nome} {cognome}").count() == 0

    def test_non_in_una_prova(self, app):
        from models.prova.service import ProvaService

        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        for campo, valore in ProvaService.campi_di_creazione().items():
            setattr(gara, campo, valore)
        db.session.commit()
        nome, cognome = _nome()

        from models.competition.inscription_service import InscriptionService

        with pytest.raises(ValidationError):
            InscriptionService.iscrivi_non_registrato(gara.id, nome, cognome, direttore)


class TestContaInClassifica:
    def test_le_sue_vittorie_entrano_nella_classifica_generale(self, db_session):
        from models.campionato.models import Campionato
        from models.campionato.tournament_service import TournamentService
        from models.classification.gara_classification import (
            RoundClassificationService,
        )
        from models.match.models import Match

        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = UserService.create_placeholder(*_nome(), direttore)
        avversario = _user()
        camp = Campionato(
            name=f"Camp {uuid.uuid4().hex[:6]}",
            campionato_type="amalfi",
            default_classification_system="WINS",
            is_active=True,
            planned_gare_count=1,
            default_rounds_count=1,
        )
        db.session.add(camp)
        db.session.flush()
        gara = Gara(
            campionato_id=camp.id,
            number=1,
            name="Gara 1",
            date=date(2026, 1, 11),
            time=time(18, 0),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            rounds_count=1,
            current_round=1,
            status=GaraStatus.COMPLETED.value,
            classification_system="WINS",
        )
        db.session.add(gara)
        db.session.flush()
        db.session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=giocatore.id,
                player2_id=avversario.id,
                player1_score=5,
                player2_score=2,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
                winner_id=giocatore.id,
            )
        )
        db.session.flush()
        RoundClassificationService.calculate_and_save_round_classification(gara.id, 1)
        db.session.flush()

        righe = TournamentService().calculate_general_classification(camp.id)

        primo = righe[0][1]
        assert primo["user_id"] == giocatore.id
        assert primo["total_matches_won"] == 1
        assert primo["is_placeholder"] is True


# ---------------------------------------------------------------- altri due


class TestPartitaDiAltriDue:
    def test_chi_segna_crea_il_giocatore_dal_modulo(self, app):
        from models.individual_match.models import IndividualMatch

        marco = _istruttore()
        anna = _user()
        nome, cognome = _nome()
        client = _client_for(app, marco)

        risposta = _post(
            client,
            "/match/scored",
            data={
                "player1_id": str(anna.id),
                "player2_new_first_name": nome,
                "player2_new_last_name": cognome,
                "discipline": Discipline.NINE_BALL.value,
                "match_format": "single",
                "distance": "3",
                "is_race_to": "true",
            },
        )

        assert risposta.status_code == 302
        giocatore = User.query.filter_by(username=f"{nome} {cognome}").one()
        assert giocatore.is_placeholder and giocatore.created_by_id == marco.id
        match = IndividualMatch.query.filter_by(scorer_id=marco.id).one()
        assert match.player2_id == giocatore.id
        assert Notification.query.filter_by(user_id=giocatore.id).count() == 0

    def test_per_lui_la_partita_resta_in_attesa(self):
        from models.certificazione import Livello, livello_di_sfida_per
        from models.individual_match.scored_match_service import (
            NuovoGiocatore,
            ScoredMatchService,
        )

        marco = _istruttore()
        anna = _user()
        nome, cognome = _nome()
        match = ScoredMatchService.start(
            marco,
            anna.id,
            NuovoGiocatore(nome, cognome),
            {"discipline": Discipline.NINE_BALL.value, "distance": 3},
        )
        db.session.commit()
        match.player1_confirmed = True
        match.player1_score, match.player2_score = 3, 1
        match.tpa_referto.closed_at = utc_now()
        db.session.commit()

        assert livello_di_sfida_per(match, anna.id) is Livello.CONFERMATA
        assert livello_di_sfida_per(match, match.player2_id) is Livello.IN_ATTESA

    def test_uno_studente_non_puo_creare_giocatori_dal_modulo(self):
        from models.individual_match.scored_match_service import (
            NuovoGiocatore,
            ScoredMatchService,
        )

        with pytest.raises(PermissionDeniedError):
            ScoredMatchService.start(_user(), _user().id, NuovoGiocatore(*_nome()), {})


# ---------------------------------------------------------------- profilo


class TestProfilo:
    def test_il_profilo_dice_che_non_e_registrato(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = UserService.create_placeholder(*_nome(), direttore)
        client = _client_for(app, _user())

        pagina = _get(client, f"/player/profile/{giocatore.id}")

        assert pagina.status_code == 200
        assert "c7-nonreg" in pagina.get_data(as_text=True)


# ---------------------------------------------------------------- unione


class TestUnione:
    def test_un_non_registrato_si_unisce_a_un_account_vero(self):
        from models.match.models import Match

        admin = _user(UserRole.ADMIN.value)
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = UserService.create_placeholder(*_nome(), direttore)
        vero = _user()
        terzo = _user()
        gara = _gara(direttore, status=GaraStatus.PLAYING.value)
        partita = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=giocatore.id,
            player2_id=terzo.id,
            winner_id=giocatore.id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
        )
        db.session.add(partita)
        db.session.commit()
        partita_id, sorgente_id = partita.id, giocatore.id

        UserService.merge_users(sorgente_id, vero.id, admin.id)

        assert db.session.get(Match, partita_id).player1_id == vero.id

    def test_chi_ha_creato_i_non_registrati_li_porta_con_se(self):
        """Se si uniscono due account del creatore, i non registrati che aveva
        creato passano al destinatario: il riscatto li farà confermare a lui."""
        admin = _user(UserRole.ADMIN.value)
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = UserService.create_placeholder(*_nome(), direttore)
        nuovo_account = _user(UserRole.DIRECTOR.value)
        giocatore_id = giocatore.id

        UserService.merge_users(direttore.id, nuovo_account.id, admin.id)

        assert db.session.get(User, giocatore_id).created_by_id == nuovo_account.id
