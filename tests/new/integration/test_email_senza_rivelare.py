"""La registrazione non rivela le email; chi ha l'email di un non registrato
lo attiva (ADR-086, emendamento del 2026-10-19).

Prima la registrazione con un indirizzo già presente rispondeva «email già in
uso» — a chiunque, quindi anche a chi voleva solo sapere chi è iscritto — e il
giocatore non registrato con un'email vera restava fuori due volte: non poteva
registrarsi, e il recupero password gli dava una password con cui il login lo
rifiutava comunque.

Ora la pagina risponde sempre come a una registrazione riuscita, e la
differenza la vede solo chi legge quella casella: l'avviso per un account
normale, il link di attivazione per un non registrato. Il link vale anche dal
recupero password.
"""

from __future__ import annotations

import uuid
from datetime import date, time as ora, timedelta

import pytest
from flask import g

from models import User, db
from models.base import utc_now
from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.notification.models import Notification, NotificationType
from models.shared.email_service import EmailService
from models.status_enum import ClaimRequestStatus, Discipline, GaraStatus, MatchStatus
from models.user.attivazione import TOKEN_ATTIVAZIONE
from models.user.claim_request import ClaimRequest
from models.user.claim_service import ClaimService
from models.user.role_enum import UserRole
from models.user.services import UserService
from models.user.tokens import UserToken


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


@pytest.fixture
def posta(monkeypatch):
    """Le email spedite: (destinatario, oggetto, corpo)."""
    spedite: list[tuple[str, str, str]] = []

    def finto_invio(to_email, subject, html_content):
        spedite.append((to_email, subject, html_content))
        return True

    monkeypatch.setattr(EmailService, "send_email", staticmethod(finto_invio))
    return spedite


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _user(role: str = UserRole.PLAYER.value, **campi) -> User:
    uid = _uid()
    campi.setdefault("onboarding_completed", True)
    campi.setdefault("email", f"es_{uid}@test.com")
    user = User(username=f"es_{uid}", role=role, gamification_override=True, **campi)
    user.set_password("pw123456")
    user.is_verified = True
    db.session.add(user)
    db.session.commit()
    return user


def _placeholder_con_email(creatore: User | None = None) -> User:
    """Un non registrato con un'email vera, come gli storici dello script."""
    creatore = creatore or _user(UserRole.DIRECTOR.value)
    giocatore = UserService.create_placeholder("Mario", f"Rossi{_uid()}", creatore)
    giocatore.email = f"mario_{_uid()}@test.com"
    db.session.commit()
    return giocatore


def _partita_giocata(giocatore: User) -> Match:
    direttore = _user(UserRole.DIRECTOR.value)
    avversario = _user()
    gara = Gara(
        name=f"Gara {_uid()}",
        number=1,
        date=date.today() - timedelta(days=7),
        time=ora(20, 0),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        rounds_count=3,
        min_participants=2,
        max_participants=16,
        matchmaking_strategy="random",
        director_id=direttore.id,
        status=GaraStatus.PLAYING.value,
        inscription_start=utc_now() - timedelta(days=10),
        inscription_end=utc_now() - timedelta(days=8),
    )
    db.session.add(gara)
    db.session.flush()
    for persona in (giocatore, avversario):
        db.session.add(Inscription(gara_id=gara.id, user_id=persona.id))
    partita = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=giocatore.id,
        player2_id=avversario.id,
        player1_score=5,
        player2_score=2,
        winner_id=giocatore.id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    db.session.add(partita)
    db.session.commit()
    return partita


def _anonimo(app):
    g.pop("_login_user", None)
    return app.test_client()


def _post(client, url, **kw):
    g.pop("_login_user", None)
    return client.post(url, **kw)


def _registra(app, username: str, email: str, password: str = "pw123456"):
    return _post(
        _anonimo(app),
        "/auth/register",
        data={"username": username, "email": email, "password": password},
    )


def _token(user_id: int, tipo: str = TOKEN_ATTIVAZIONE) -> UserToken | None:
    return (
        UserToken.query.filter_by(user_id=user_id, token_type=tipo)
        .order_by(UserToken.id.desc())
        .first()
    )


def _attiva(app, token: str, username: str, password: str = "nuova_pw1"):
    return _post(
        _anonimo(app),
        f"/auth/attiva/{token}",
        data={
            "username": username,
            "password": password,
            "confirm_password": password,
        },
    )


def _login(app, username: str, password: str):
    client = _anonimo(app)
    risposta = _post(
        client, "/auth/login", data={"username": username, "password": password}
    )
    return client, risposta


def _flash(risposta_client) -> list:
    with risposta_client.session_transaction() as sess:
        return list(sess.get("_flashes", []))


def _risposta_visibile(client, risposta) -> tuple:
    """Ciò che vede chi si registra: codice, destinazione, messaggi."""
    with client.session_transaction() as sess:
        messaggi = [
            (categoria, testo)
            for categoria, testo in sess.get("_flashes", [])
            if categoria != "gamification_event"
        ]
    return risposta.status_code, risposta.location, messaggi


def _registra_e_guarda(app, username: str, email: str) -> tuple:
    client = _anonimo(app)
    risposta = _post(
        client,
        "/auth/register",
        data={"username": username, "email": email, "password": "pw123456"},
    )
    return _risposta_visibile(client, risposta)


# --------------------------------------------------------------- registrazione


class TestRegistrazione:
    def test_email_nuova_crea_l_account_e_manda_la_verifica(self, app, posta):
        uid = _uid()
        risposta = _registra(app, f"nuovo_{uid}", f"nuovo_{uid}@test.com")

        assert risposta.status_code == 302
        assert "/auth/login" in risposta.location
        nuovo = User.query.filter_by(username=f"nuovo_{uid}").one()
        assert not nuovo.is_verified
        assert [destinatario for destinatario, _, _ in posta] == [
            f"nuovo_{uid}@test.com"
        ]
        assert "/auth/verify-email/" in posta[0][2]

    def test_email_di_un_account_la_risposta_e_la_stessa(self, app, posta):
        esistente = _user()
        utenti_prima = User.query.count()

        nuova = _registra_e_guarda(app, f"a_{_uid()}", f"a_{_uid()}@test.com")
        doppia = _registra_e_guarda(app, f"b_{_uid()}", esistente.email)

        assert nuova == doppia, "la pagina dice se l'email esiste già"
        # Il primo ha creato un account, il secondo no.
        assert User.query.count() == utenti_prima + 1

    def test_email_di_un_account_parte_l_avviso(self, app, posta):
        esistente = _user()
        username_tentato = f"intruso_{_uid()}"

        _registra(app, username_tentato, esistente.email.upper())

        assert User.query.filter_by(username=username_tentato).first() is None
        assert len(posta) == 1
        destinatario, oggetto, corpo = posta[0]
        assert destinatario == esistente.email
        assert "registrazione" in oggetto.lower()
        assert "/auth/forgot-password" in corpo
        assert "/auth/login" in corpo
        # Niente link di attivazione, e nessun token creato per lui.
        assert "/auth/attiva/" not in corpo
        assert _token(esistente.id) is None
        # Lo username tentato non finisce nell'email: non serve, ed è un dato
        # di chi ha provato.
        assert username_tentato not in corpo

    def test_username_gia_preso_si_dice_ma_non_dice_l_email(self, app, posta):
        esistente = _user()
        client = _anonimo(app)
        risposta = _post(
            client,
            "/auth/register",
            data={
                "username": esistente.username,
                "email": esistente.email,
                "password": "pw123456",
            },
        )
        assert risposta.status_code == 200
        pagina = risposta.get_data(as_text=True)
        assert esistente.username in pagina
        assert esistente.email not in pagina
        # Il messaggio parla dello username: l'email, che pure è presa, no.
        assert "already exists" in pagina
        assert posta == []

    def test_email_di_un_non_registrato_parte_l_attivazione(self, app, posta):
        giocatore = _placeholder_con_email()
        utenti_prima = User.query.count()

        nuova = _registra_e_guarda(app, f"c_{_uid()}", f"c_{_uid()}@test.com")
        posta.clear()
        doppia = _registra_e_guarda(app, f"d_{_uid()}", giocatore.email)

        assert nuova == doppia
        assert User.query.count() == utenti_prima + 1
        assert len(posta) == 1
        destinatario, oggetto, corpo = posta[0]
        assert destinatario == giocatore.email
        token = _token(giocatore.id)
        assert token is not None and token.is_valid()
        assert f"/auth/attiva/{token.token}" in corpo
        assert "/auth/forgot-password" not in corpo

    def test_email_nella_lingua_di_chi_la_riceve(self, app, posta):
        esistente = _user(language="en")
        _registra(app, f"e_{_uid()}", esistente.email)

        _, oggetto, corpo = posta[0]
        assert "registration" in oggetto.lower() or "sign" in oggetto.lower(), oggetto
        assert "registrar" not in corpo


# ---------------------------------------------------------------- attivazione


class TestAttivazione:
    def test_attivazione_completa_e_login_con_le_partite(self, app, posta):
        giocatore = _placeholder_con_email()
        partita = _partita_giocata(giocatore)
        _registra(app, f"f_{_uid()}", giocatore.email)
        token = _token(giocatore.id)

        nome = f"mario_{_uid()}"
        pagina = _anonimo(app).get(f"/auth/attiva/{token.token}")
        assert pagina.status_code == 200
        assert giocatore.username in pagina.get_data(as_text=True)

        risposta = _attiva(app, token.token, nome)
        assert risposta.status_code == 302
        assert "/auth/login" in risposta.location

        db.session.expire_all()
        attivato = db.session.get(User, giocatore.id)
        assert not attivato.is_placeholder
        assert attivato.claimed_at is not None
        assert attivato.is_verified
        assert attivato.username == nome

        client, accesso = _login(app, nome, "nuova_pw1")
        assert accesso.status_code == 302
        assert "/auth/login" not in accesso.location
        # Le partite sono rimaste sue: è lo stesso account, nessuna unione.
        partita = db.session.get(Match, partita.id)
        assert partita.player1_id == giocatore.id
        assert Inscription.query.filter_by(user_id=giocatore.id).count() == 1
        g.pop("_login_user", None)
        assert client.get(accesso.location).status_code == 200

    def test_recupero_password_porta_all_attivazione(self, app, posta):
        giocatore = _placeholder_con_email()

        risposta = _post(
            _anonimo(app), "/auth/forgot-password", data={"email": giocatore.email}
        )
        assert risposta.status_code == 302

        assert _token(giocatore.id, "password_reset") is None
        token = _token(giocatore.id)
        assert token is not None
        assert len(posta) == 1
        destinatario, _, corpo = posta[0]
        assert destinatario == giocatore.email
        assert f"/auth/attiva/{token.token}" in corpo

        nome = f"rec_{_uid()}"
        _attiva(app, token.token, nome)
        _, accesso = _login(app, nome, "nuova_pw1")
        assert accesso.status_code == 302
        assert "/dashboard" in accesso.location or accesso.location.endswith("/")

    def test_il_recupero_password_risponde_come_per_tutti(self, app, posta):
        giocatore = _placeholder_con_email()
        normale = _user()
        a = _post(
            _anonimo(app), "/auth/forgot-password", data={"email": giocatore.email}
        )
        b = _post(_anonimo(app), "/auth/forgot-password", data={"email": normale.email})
        assert (a.status_code, a.location) == (b.status_code, b.location)

    def test_token_scaduto(self, app, posta):
        giocatore = _placeholder_con_email()
        _registra(app, f"g_{_uid()}", giocatore.email)
        token = _token(giocatore.id)
        token.expires_at = utc_now() - timedelta(minutes=1)
        db.session.commit()

        assert _anonimo(app).get(f"/auth/attiva/{token.token}").status_code == 302
        _attiva(app, token.token, f"scaduto_{_uid()}")
        db.session.expire_all()
        assert db.session.get(User, giocatore.id).is_placeholder

    def test_token_gia_usato(self, app, posta):
        giocatore = _placeholder_con_email()
        _registra(app, f"h_{_uid()}", giocatore.email)
        token = _token(giocatore.id).token

        primo = f"primo_{_uid()}"
        _attiva(app, token, primo, "prima_pw1")
        _attiva(app, token, f"secondo_{_uid()}", "seconda_pw")

        db.session.expire_all()
        attivato = db.session.get(User, giocatore.id)
        assert attivato.username == primo
        assert attivato.check_password("prima_pw1")
        assert not attivato.check_password("seconda_pw")

    def test_un_link_nuovo_spegne_il_vecchio(self, app, posta):
        giocatore = _placeholder_con_email()
        _registra(app, f"i_{_uid()}", giocatore.email)
        vecchio = _token(giocatore.id).token
        _registra(app, f"j_{_uid()}", giocatore.email)

        assert _anonimo(app).get(f"/auth/attiva/{vecchio}").status_code == 302

    def test_username_occupato_si_ripropone(self, app, posta):
        giocatore = _placeholder_con_email()
        altro = _user()
        _registra(app, f"k_{_uid()}", giocatore.email)
        token = _token(giocatore.id).token

        risposta = _attiva(app, token, altro.username)
        assert risposta.status_code == 200
        db.session.expire_all()
        assert db.session.get(User, giocatore.id).is_placeholder
        assert _token(giocatore.id).is_valid()

    def test_password_che_non_coincidono(self, app, posta):
        giocatore = _placeholder_con_email()
        _registra(app, f"l_{_uid()}", giocatore.email)
        token = _token(giocatore.id).token
        risposta = _post(
            _anonimo(app),
            f"/auth/attiva/{token}",
            data={
                "username": f"m_{_uid()}",
                "password": "abcdef1",
                "confirm_password": "abcdef2",
            },
        )
        assert risposta.status_code == 200
        db.session.expire_all()
        assert db.session.get(User, giocatore.id).is_placeholder

    def test_il_giocatore_riscattato_nel_frattempo_non_si_attiva(self, app, posta):
        giocatore = _placeholder_con_email()
        _registra(app, f"n_{_uid()}", giocatore.email)
        token = _token(giocatore.id).token
        giocatore = db.session.get(User, giocatore.id)
        giocatore.claimed_at = utc_now()
        db.session.commit()

        assert _anonimo(app).get(f"/auth/attiva/{token}").status_code == 302


# ------------------------------------------------- una richiesta di riscatto aperta


class TestRichiestaDiRiscattoInAttesa:
    def test_l_attivazione_chiude_la_richiesta_di_un_altro(self, app, posta):
        creatore = _user(UserRole.DIRECTOR.value)
        giocatore = _placeholder_con_email(creatore)
        altro = _user()
        richiesta = ClaimService.richiedi(giocatore.id, altro)
        db.session.commit()
        richiesta_id = richiesta.id

        _registra(app, f"o_{_uid()}", giocatore.email)
        _attiva(app, _token(giocatore.id).token, f"vero_{_uid()}")

        db.session.expire_all()
        richiesta = db.session.get(ClaimRequest, richiesta_id)
        assert richiesta.status == ClaimRequestStatus.REJECTED.value
        assert richiesta.decided_by_id == giocatore.id
        assert richiesta.decided_at is not None

        # Chi aveva chiesto riceve l'esito; il «Decidi» del creatore si spegne.
        esito = Notification.query.filter_by(
            user_id=altro.id,
            notification_type=NotificationType.CLAIM_REQUEST_PROCESSED,
        ).one()
        assert "attivato" in esito.message
        decidi = Notification.query.filter_by(
            user_id=creatore.id,
            notification_type=NotificationType.CLAIM_REQUEST_RECEIVED,
        ).one()
        assert decidi.read_at is not None

        # Il creatore non può più decidere niente.
        assert ClaimService.da_decidere_per(creatore) == []


# ------------------------------------------------------ cambio email da collegato


class TestCambioEmailNelProfilo:
    """Da collegato, l'indirizzo di un altro account si rifiuta senza dire di chi
    è. Prima non si controllava niente: nascevano due account con la stessa
    email, che si contendevano recupero password e attivazione."""

    @staticmethod
    def _collegato(app, user: User):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = user.get_id()
            sess["_fresh"] = True
        return client

    def test_l_email_di_un_altro_si_rifiuta(self, app, posta):
        altro = _user()
        io = _user()
        client = self._collegato(app, io)

        risposta = _post(
            client, "/player/profile/edit", data={"email": altro.email.upper()}
        )

        assert risposta.status_code == 200
        pagina = risposta.get_data(as_text=True)
        assert "non si può usare" in pagina
        db.session.expire_all()
        assert db.session.get(User, io.id).email == io.email
        assert posta == []

    def test_la_propria_email_si_riscrive(self, app, posta):
        io = _user()
        client = self._collegato(app, io)
        risposta = _post(client, "/player/profile/edit", data={"email": io.email})
        assert risposta.status_code == 302
