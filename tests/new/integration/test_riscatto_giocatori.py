"""Riscatto dei giocatori non registrati (ADR-086).

Il percorso intero: il pulsante «Sei tu? Riscatta» nelle pagine pubbliche, la
richiesta che parte da sola dopo l'accesso (con un account nuovo o vecchio),
chi la decide — il creatore, o l'admin per gli storici senza creatore —, cosa
sposta la conferma (iscrizioni, partite, ELO) e cosa non si può chiedere.
"""

from __future__ import annotations

import time
import uuid
from datetime import date, time as ora, timedelta

import pytest
from flask import g

from models import User, db
from models.base import utc_now
from models.competition.models import Gara, Inscription
from models.exceptions import ConflictError, PermissionDeniedError, ValidationError
from models.notification.models import Notification, NotificationType
from models.status_enum import ClaimRequestStatus, Discipline, GaraStatus, MatchStatus
from models.user.claim_request import ClaimRequest
from models.user.claim_service import ClaimService
from models.user.role_enum import UserRole
from models.user.services import UserService
from routes.riscatto import CHIAVE_IN_SOSPESO


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _user(role: str = UserRole.PLAYER.value, **campi) -> User:
    uid = uuid.uuid4().hex[:8]
    campi.setdefault("onboarding_completed", True)
    user = User(
        username=f"rs_{uid}",
        email=f"rs_{uid}@test.com",
        role=role,
        gamification_override=True,
        **campi,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _admin() -> User:
    esistente = User.query.filter_by(role=UserRole.ADMIN.value).first()
    return esistente or _user(UserRole.ADMIN.value)


def _nome() -> tuple[str, str]:
    return "Mario", f"Rossi{uuid.uuid4().hex[:5]}"


def _placeholder(creatore=None) -> User:
    creatore = creatore or _user(UserRole.DIRECTOR.value)
    giocatore = UserService.create_placeholder(*_nome(), creatore)
    db.session.commit()
    return giocatore


def _storico() -> User:
    """Un giocatore non registrato senza creatore, come quelli dello script."""
    giocatore = _user()
    giocatore.is_placeholder = True
    db.session.commit()
    return giocatore


def _client_for(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True
    return client


def _anonimo(app):
    g.pop("_login_user", None)
    return app.test_client()


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
        time=ora(20, 0),
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


def _iscrivi(gara: Gara, user: User) -> Inscription:
    iscrizione = Inscription(gara_id=gara.id, user_id=user.id)
    db.session.add(iscrizione)
    db.session.commit()
    return iscrizione


def _pagina_riscatto(giocatore: User) -> str:
    return f"/giocatori/{giocatore.id}/riscatta"


def _richieste_di(giocatore_id: int):
    return ClaimRequest.query.filter_by(placeholder_id=giocatore_id).all()


# ---------------------------------------------------------------- il pulsante


class TestPulsante:
    def test_l_anonimo_lo_vede_solo_accanto_ai_non_registrati(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        giocatore = _placeholder(direttore)
        vero = _user()
        _iscrivi(gara, giocatore)
        _iscrivi(gara, vero)

        html = _get(_anonimo(app), f"/admin/gara/{gara.id}").get_data(as_text=True)

        # Il componente degli iscritti c'è due volte (mobile e desktop): ogni
        # pulsante deve portare al non registrato, e a nessun altro.
        assert html.count("Sei tu? Riscatta") == html.count(_pagina_riscatto(giocatore))
        assert html.count("Sei tu? Riscatta") >= 1
        assert f"/giocatori/{vero.id}/riscatta" not in html

    def test_non_lo_vede_chi_l_ha_creato(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        _iscrivi(gara, _placeholder(direttore))

        html = _get(_client_for(app, direttore), f"/admin/gara/{gara.id}").get_data(
            as_text=True
        )
        assert "Sei tu? Riscatta" not in html

    def test_sparisce_con_una_richiesta_in_attesa(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        giocatore = _placeholder(direttore)
        _iscrivi(gara, giocatore)
        ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()

        html = _get(_anonimo(app), f"/admin/gara/{gara.id}").get_data(as_text=True)
        assert "Sei tu? Riscatta" not in html

    def test_la_pagina_si_apre_da_anonimo_e_non_crea_niente(self, app):
        giocatore = _placeholder()
        risposta = _get(_anonimo(app), _pagina_riscatto(giocatore))
        assert risposta.status_code == 200
        html = risposta.get_data(as_text=True)
        assert "Crea un account" in html and "accedi" in html
        assert _richieste_di(giocatore.id) == []

    def test_la_pagina_di_un_utente_vero_non_esiste(self, app):
        assert _get(_anonimo(app), _pagina_riscatto(_user())).status_code == 404


# ------------------------------------------------------- il percorso completo


class TestPercorsoDaAnonimo:
    def test_registrazione_e_login_creano_la_richiesta_senza_altri_clic(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder(direttore)
        client = _anonimo(app)

        risposta = _post(
            client, _pagina_riscatto(giocatore), data={"azione": "registrati"}
        )
        assert risposta.status_code == 302
        assert "/auth/register" in risposta.headers["Location"]
        assert _richieste_di(giocatore.id) == []

        uid = uuid.uuid4().hex[:8]
        risposta = _post(
            client,
            risposta.headers["Location"],
            data={
                "username": f"nuovo_{uid}",
                "email": f"nuovo_{uid}@test.com",
                "password": "pw123456",
            },
        )
        assert "/auth/login" in risposta.headers["Location"]
        # Registrarsi non basta: la richiesta nasce con l'accesso.
        assert _richieste_di(giocatore.id) == []

        risposta = _post(
            client,
            "/auth/login",
            data={"username": f"nuovo_{uid}", "password": "pw123456"},
        )

        richieste = _richieste_di(giocatore.id)
        assert len(richieste) == 1
        nuovo = User.query.filter_by(username=f"nuovo_{uid}").one()
        assert richieste[0].claimant_id == nuovo.id
        assert richieste[0].is_pending
        assert risposta.headers["Location"].endswith(f"/riscatti/{richieste[0].id}")
        with client.session_transaction() as sess:
            assert CHIAVE_IN_SOSPESO not in sess
            flash = " ".join(m for _c, m in sess.get("_flashes", []))
        assert direttore.username in flash

    def test_con_un_account_esistente(self, app):
        giocatore = _placeholder()
        vero = _user()
        client = _anonimo(app)

        risposta = _post(client, _pagina_riscatto(giocatore), data={"azione": "accedi"})
        assert "/auth/login" in risposta.headers["Location"]

        _post(
            client,
            "/auth/login",
            data={"username": vero.username, "password": "pw123456"},
        )

        richieste = _richieste_di(giocatore.id)
        assert [r.claimant_id for r in richieste] == [vero.id]

    def test_un_get_a_next_da_solo_non_crea_niente(self, app):
        giocatore = _placeholder()
        vero = _user()
        client = _anonimo(app)
        pagina = _pagina_riscatto(giocatore)

        _get(client, f"/auth/login?next={pagina}")
        risposta = _post(
            client,
            f"/auth/login?next={pagina}",
            data={"username": vero.username, "password": "pw123456", "next": pagina},
        )

        assert _richieste_di(giocatore.id) == []
        assert risposta.headers["Location"].endswith(pagina)

    def test_l_intenzione_scaduta_non_parte(self, app):
        giocatore = _placeholder()
        vero = _user()
        client = _anonimo(app)
        with client.session_transaction() as sess:
            sess[CHIAVE_IN_SOSPESO] = {
                "giocatore": giocatore.id,
                "scade": int(time.time()) - 1,
            }

        _post(
            client,
            "/auth/login",
            data={"username": vero.username, "password": "pw123456"},
        )

        assert _richieste_di(giocatore.id) == []

    def test_il_logout_dimentica_l_intenzione(self, app):
        giocatore = _placeholder()
        vero = _user()
        client = _client_for(app, vero)
        with client.session_transaction() as sess:
            sess[CHIAVE_IN_SOSPESO] = {
                "giocatore": giocatore.id,
                "scade": int(time.time()) + 600,
            }
        _post(client, "/auth/logout")
        with client.session_transaction() as sess:
            assert CHIAVE_IN_SOSPESO not in sess

    def test_l_utente_collegato_la_chiede_con_un_post(self, app):
        giocatore = _placeholder()
        vero = _user()

        risposta = _post(_client_for(app, vero), _pagina_riscatto(giocatore))

        richieste = _richieste_di(giocatore.id)
        assert [r.claimant_id for r in richieste] == [vero.id]
        assert risposta.headers["Location"].endswith(f"/riscatti/{richieste[0].id}")

    def test_il_get_dell_utente_collegato_non_crea_niente(self, app):
        giocatore = _placeholder()
        _get(_client_for(app, _user()), _pagina_riscatto(giocatore))
        assert _richieste_di(giocatore.id) == []


class TestRegistrazioneMandaLaVerifica:
    def test_la_registrazione_spedisce_la_mail_di_verifica(self, app, monkeypatch):
        from models.shared.email_service import EmailService

        spedite = []
        monkeypatch.setattr(
            EmailService,
            "send_verification_email",
            staticmethod(lambda user, token, base: spedite.append(user.email) or True),
        )
        uid = uuid.uuid4().hex[:8]
        _post(
            _anonimo(app),
            "/auth/register",
            data={
                "username": f"ver_{uid}",
                "email": f"ver_{uid}@test.com",
                "password": "pw123456",
            },
        )
        assert spedite == [f"ver_{uid}@test.com"]


# ---------------------------------------------------------------- casi impossibili


class TestCosaNonSiChiede:
    def test_chi_l_ha_creato_non_lo_riscatta(self):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder(direttore)
        with pytest.raises(ValidationError):
            ClaimService.richiedi(giocatore.id, direttore)

    def test_una_sola_richiesta_in_attesa(self):
        giocatore = _placeholder()
        ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()
        with pytest.raises(ConflictError):
            ClaimService.richiedi(giocatore.id, _user())

    def test_dopo_un_rifiuto_si_puo_chiedere_di_nuovo(self):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder(direttore)
        prima = ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()
        ClaimService.reject(prima.id, direttore)
        db.session.commit()

        seconda = ClaimService.richiedi(giocatore.id, _user())
        assert seconda.is_pending

    def test_un_utente_vero_non_si_riscatta(self):
        from models.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            ClaimService.richiedi(_user().id, _user())

    def test_dalla_pagina_un_caso_impossibile_non_fa_niente(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder(direttore)

        risposta = _post(_client_for(app, direttore), _pagina_riscatto(giocatore))

        assert risposta.headers["Location"].endswith(_pagina_riscatto(giocatore))
        assert _richieste_di(giocatore.id) == []

    def test_l_indice_parziale_tiene_una_sola_pending_anche_nel_db(self):
        from sqlalchemy.exc import IntegrityError

        giocatore = _placeholder()
        for _ in range(2):
            db.session.add(
                ClaimRequest(
                    placeholder_id=giocatore.id,
                    claimant_id=_user().id,
                    status=ClaimRequestStatus.PENDING.value,
                )
            )
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()


# ---------------------------------------------------------------- chi decide


class TestChiDecide:
    def test_il_creatore_e_il_destinatario_e_riceve_la_notifica(self):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder(direttore)
        richiesta = ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()

        assert richiesta.recipient_ids == {direttore.id}
        assert (
            Notification.query.filter_by(
                user_id=direttore.id,
                notification_type=NotificationType.CLAIM_REQUEST_RECEIVED,
            ).count()
            == 1
        )

    def test_un_altro_direttore_non_decide(self):
        giocatore = _placeholder()
        richiesta = ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()
        with pytest.raises(PermissionDeniedError):
            ClaimService.approve(richiesta.id, _user(UserRole.DIRECTOR.value))

    def test_lo_storico_lo_approva_solo_l_admin(self):
        admin = _admin()
        giocatore = _storico()
        richiesta = ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()

        assert richiesta.recipient_ids == {admin.id}
        with pytest.raises(PermissionDeniedError):
            ClaimService.approve(richiesta.id, _user(UserRole.DIRECTOR.value))
        ClaimService.approve(richiesta.id, admin)
        db.session.commit()
        assert db.session.get(ClaimRequest, richiesta.id).status == (
            ClaimRequestStatus.APPROVED.value
        )

    def test_l_admin_non_decide_quando_c_e_il_creatore(self):
        admin = _admin()
        richiesta = ClaimService.richiedi(_placeholder().id, _user())
        db.session.commit()
        with pytest.raises(PermissionDeniedError):
            ClaimService.reject(richiesta.id, admin)

    def test_col_creatore_cancellato_decide_l_admin(self):
        admin = _admin()
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder(direttore)
        richiesta = ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()
        direttore.anonymize()
        db.session.commit()

        assert ClaimService.puo_decidere(richiesta, admin)
        ClaimService.reject(richiesta.id, admin)

    def test_la_coda_mostra_le_richieste_al_creatore(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder(direttore)
        chi = _user()
        richiesta = ClaimService.richiedi(giocatore.id, chi)
        db.session.commit()

        html = _get(_client_for(app, direttore), "/riscatti").get_data(as_text=True)
        assert giocatore.username in html
        dettaglio = _get(
            _client_for(app, direttore), f"/riscatti/{richiesta.id}"
        ).get_data(as_text=True)
        # Chi decide vede chi chiede: nome utente, email e se è verificata.
        assert chi.username in dettaglio
        assert chi.email in dettaglio
        assert "Email non ancora verificata" in dettaglio

    def test_un_estraneo_non_legge_la_richiesta(self, app):
        richiesta = ClaimService.richiedi(_placeholder().id, _user())
        db.session.commit()
        risposta = _get(_client_for(app, _user()), f"/riscatti/{richiesta.id}")
        assert risposta.status_code == 404


# ---------------------------------------------------------------- l'esito


def _partita_chiusa(gara: Gara, vincitore: User, perdente: User):
    from models.match.models import Match

    partita = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=vincitore.id,
        player2_id=perdente.id,
        player1_score=5,
        player2_score=2,
        winner_id=vincitore.id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    db.session.add(partita)
    db.session.flush()
    # Senza triangoli è un walkover, e un walkover non muove l'ELO.
    from models.match.models import Rack

    for numero, chi in enumerate([vincitore] * 5 + [perdente] * 2, start=1):
        db.session.add(Rack(match_id=partita.id, rack_number=numero, winner_id=chi.id))
    db.session.commit()
    return partita


class TestApprovazione:
    def test_sposta_iscrizioni_partite_ed_elo(self, app):
        from models.match.models import Match
        from models.rating.models import MatchRatingHistory

        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder(direttore)
        avversario = _user()
        chi = _user()
        gara = _gara(direttore, status=GaraStatus.PLAYING.value)
        iscrizione = _iscrivi(gara, giocatore)
        _iscrivi(gara, avversario)
        partita = _partita_chiusa(gara, giocatore, avversario)
        giocatore_id, partita_id, iscrizione_id = (
            giocatore.id,
            partita.id,
            iscrizione.id,
        )

        richiesta = ClaimService.richiedi(giocatore_id, chi)
        db.session.commit()
        risposta = _post(
            _client_for(app, direttore),
            f"/riscatti/{richiesta.id}/decidi",
            data={"decisione": "approva"},
        )
        assert risposta.status_code == 302

        chi_id, direttore_id, richiesta_id = chi.id, direttore.id, richiesta.id
        # Sessione vuota: come la richiesta successiva, che non ha più il
        # giocatore anonimizzato in memoria.
        db.session.expunge_all()
        assert db.session.get(Match, partita_id).player1_id == chi_id
        assert db.session.get(Inscription, iscrizione_id).user_id == chi_id
        storia = MatchRatingHistory.query.filter_by(match_id=partita_id).all()
        assert storia and chi_id in {s.user_id for s in storia}
        assert giocatore_id not in {s.user_id for s in storia}

        from models.user.claim_service import utente_anche_cancellato

        riscattato = utente_anche_cancellato(giocatore_id)
        assert riscattato is not None and riscattato.is_deleted
        assert riscattato.claimed_at is not None
        fatta = db.session.get(ClaimRequest, richiesta_id)
        assert fatta.status == ClaimRequestStatus.APPROVED.value
        assert fatta.decided_by_id == direttore_id
        # La richiesta continua a dire chi è stato riscattato.
        assert fatta.placeholder_id == giocatore_id
        assert fatta.nome_giocatore.startswith("Mario")
        assert (
            Notification.query.filter_by(
                user_id=chi_id,
                notification_type=NotificationType.CLAIM_REQUEST_PROCESSED,
            ).count()
            == 1
        )

    def test_non_si_riscatta_due_volte(self):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder(direttore)
        richiesta = ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()
        ClaimService.approve(richiesta.id, direttore)
        db.session.commit()
        giocatore_id = giocatore.id
        db.session.expunge_all()
        with pytest.raises(ConflictError):
            ClaimService.richiedi(giocatore_id, _user())

    def test_se_hanno_giocato_contro_si_ferma_e_non_scrive(self):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder(direttore)
        chi = _user()
        gara = _gara(direttore, status=GaraStatus.PLAYING.value)
        _partita_chiusa(gara, giocatore, chi)
        richiesta = ClaimService.richiedi(giocatore.id, chi)
        db.session.commit()
        richiesta_id, giocatore_id = richiesta.id, giocatore.id

        with pytest.raises(ConflictError):
            ClaimService.approve(richiesta_id, direttore)
        db.session.rollback()

        assert db.session.get(ClaimRequest, richiesta_id).is_pending
        assert not db.session.get(User, giocatore_id).is_deleted

    def test_il_rifiuto_lascia_il_giocatore_com_era(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder(direttore)
        chi = _user()
        richiesta = ClaimService.richiedi(giocatore.id, chi)
        db.session.commit()

        _post(
            _client_for(app, direttore),
            f"/riscatti/{richiesta.id}/decidi",
            data={"decisione": "rifiuta"},
        )

        assert db.session.get(ClaimRequest, richiesta.id).status == (
            ClaimRequestStatus.REJECTED.value
        )
        rimasto = db.session.get(User, giocatore.id)
        assert rimasto.is_placeholder and not rimasto.is_deleted
        assert (
            Notification.query.filter_by(
                user_id=chi.id,
                notification_type=NotificationType.CLAIM_REQUEST_PROCESSED,
            ).count()
            == 1
        )


class TestUnioneDaAdminInvariata:
    def test_senza_il_riscatto_un_non_admin_non_unisce(self):
        from models.user.merge_service import UserMergeService

        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder(direttore)
        with pytest.raises(ValidationError):
            UserMergeService.merge_users(giocatore.id, _user().id, direttore.id)

    def test_il_riscatto_non_unisce_un_utente_vero(self):
        from models.user.merge_service import UserMergeService

        direttore = _user(UserRole.DIRECTOR.value)
        with pytest.raises(ValidationError):
            UserMergeService.merge_users(
                _user().id, _user().id, direttore.id, riscatto_approvato=True
            )


# ---------------------------------------------------------------- onboarding


class TestOnboarding:
    def test_chi_si_chiama_come_un_non_registrato_lo_vede(self, app):
        giocatore = _placeholder()
        nuovo = _user(onboarding_completed=False)
        client = _client_for(app, nuovo)

        risposta = _post(
            client,
            "/onboarding",
            data={
                "first_name": "mario",
                "last_name": giocatore.last_name.upper(),
            },
        )
        assert risposta.headers["Location"].endswith("/riscatti/sei-tu")
        html = _get(client, "/riscatti/sei-tu").get_data(as_text=True)
        assert giocatore.username in html
        assert _richieste_di(giocatore.id) == []

    def test_senza_omonimi_si_va_in_dashboard(self, app):
        nuovo = _user(onboarding_completed=False)
        risposta = _post(
            _client_for(app, nuovo),
            "/onboarding",
            data={"first_name": "Nessuno", "last_name": uuid.uuid4().hex},
        )
        assert risposta.headers["Location"].endswith("/dashboard")


# ---------------------------------------------------------------- storici


class TestStorici:
    def test_i_criteri_dello_script(self):
        from models.user.placeholder_storici import candidati_storici, segna
        from models.user.session_models import UserSession

        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        mai_entrato = _user(onboarding_completed=False)
        entrato = _user(onboarding_completed=False)
        attivo = _user(onboarding_completed=False, last_active_at=utc_now())
        senza_gare = _user(onboarding_completed=False)
        for u in (mai_entrato, entrato, attivo):
            _iscrivi(gara, u)
        db.session.add(UserSession(user_id=entrato.id, last_seen_at=utc_now()))
        db.session.commit()

        trovati = {u.id for u in candidati_storici()}
        assert mai_entrato.id in trovati
        assert not trovati & {entrato.id, attivo.id, senza_gare.id, direttore.id}

        segna([db.session.get(User, mai_entrato.id)])
        db.session.commit()
        assert db.session.get(User, mai_entrato.id).is_placeholder
        assert mai_entrato.id not in {u.id for u in candidati_storici()}
