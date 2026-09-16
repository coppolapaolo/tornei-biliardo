"""Il percorso vero di una segnalazione: richiesta → route → servizio → DB.

Qui si verificano le cose che gli unit test del servizio non possono vedere:
chi arriva alle schermate, che il testo scritto sopravviva anche quando GitHub
non risponde, e che le schermate dell'utente non rimandino mai a GitHub.
"""

from __future__ import annotations

import uuid

import pytest
from flask import g

from models.base import db
from models.feedback.github_client import GitHubClient
from models.feedback.models import FeedbackReport, FeedbackStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _utente(db_session, ruolo=UserRole.PLAYER.value) -> User:
    batch = uuid.uuid4().hex[:8]
    utente = User(
        username=f"fb_{batch}",
        email=f"fb_{batch}@test.com",
        role=ruolo,
        onboarding_completed=True,
    )
    utente.set_password("password123")
    db_session.add(utente)
    db_session.commit()
    return utente


def _login(client, utente):
    """Autentica il client. `g` va ripulito a parte — vedi `_client_di`."""
    with client.session_transaction() as sess:
        # `get_id()` e non l'id nudo: l'id di sessione porta un'impronta della
        # credenziale (ADR-055), e senza il client resta non autenticato.
        sess["_user_id"] = utente.get_id()


def _client_di(app, utente):
    """Un client nuovo per ogni utente, con `g` ripulito.

    In questa suite `g` **non è per-richiesta**: sopravvive fra una richiesta e
    la successiva — e fra un client e l'altro, perché il contesto d'app è uno
    solo. Flask-Login trova l'utente già in cache e non richiama `load_user`,
    quindi cambiare `_user_id` nella sessione non cambia chi è collegato: un
    test sui permessi passerebbe (o fallirebbe) per il motivo sbagliato.

    In produzione ogni richiesta parte con un `g` pulito, che è ciò che qui si
    ricrea a mano.
    """
    client = app.test_client()
    _login(client, utente)
    if hasattr(g, "_login_user"):
        delattr(g, "_login_user")
    return client


@pytest.fixture(autouse=True)
def github_muto(monkeypatch):
    """In prova GitHub non esiste: è anche lo scenario che conta di più."""
    monkeypatch.setattr(
        GitHubClient, "dalla_configurazione", classmethod(lambda cls: cls(None, ""))
    )


class TestChiArrivaAlleSchermate:
    def test_un_anonimo_va_al_login(self, client):
        risposta = client.get("/segnalazioni/")
        assert risposta.status_code == 302
        assert "/auth/login" in risposta.headers["Location"]

    def test_un_giocatore_vede_le_sue_e_il_modulo(self, client, db_session):
        _login(client, _utente(db_session))

        assert client.get("/segnalazioni/").status_code == 200
        assert client.get("/segnalazioni/nuova").status_code == 200

    def test_l_elenco_completo_e_solo_dell_admin(self, app, db_session):
        direttore = _client_di(app, _utente(db_session, UserRole.DIRECTOR.value))
        assert direttore.get("/segnalazioni/tutte").status_code == 403

        admin = _client_di(app, _utente(db_session, UserRole.ADMIN.value))
        assert admin.get("/segnalazioni/tutte").status_code == 200


class TestLInvio:
    def test_la_segnalazione_si_salva_anche_con_github_irraggiungibile(
        self, client, db_session
    ):
        """Il punto di tutta la funzione: il testo non si perde. Se questo
        percorso mostrasse un errore, chi ha appena scritto dieci righe non
        le riscriverebbe."""
        utente = _utente(db_session)
        _login(client, utente)

        risposta = client.post(
            "/segnalazioni/nuova",
            data={
                "tipo": "bug",
                "titolo": "Il tasto non risponde",
                "corpo": "Premo e non succede niente.",
            },
            follow_redirects=True,
        )

        assert risposta.status_code == 200
        salvata = FeedbackReport.query.filter_by(user_id=utente.id).one()
        assert salvata.titolo == "Il tasto non risponde"
        assert salvata.stato == FeedbackStatus.RICEVUTA.value
        assert salvata.issue_number is None

    def test_il_contesto_tecnico_lo_raccoglie_l_app(self, client, db_session):
        """È ciò che l'utente non saprebbe dare e che serve sempre."""
        utente = _utente(db_session)
        _login(client, utente)

        client.post(
            "/segnalazioni/nuova",
            data={"tipo": "enhancement", "titolo": "Idea", "corpo": "Testo."},
            headers={"Referer": "http://localhost/gare/7"},
        )

        salvata = FeedbackReport.query.filter_by(user_id=utente.id).one()
        contesto = salvata.contesto or ""
        assert "/gare/7" in contesto
        assert utente.role in contesto
        assert utente.email not in contesto

    def test_un_modulo_incompleto_torna_al_modulo(self, client, db_session):
        utente = _utente(db_session)
        _login(client, utente)

        risposta = client.post(
            "/segnalazioni/nuova", data={"tipo": "bug", "titolo": "", "corpo": ""}
        )

        assert risposta.status_code == 302
        assert "/segnalazioni/nuova" in risposta.headers["Location"]
        assert FeedbackReport.query.filter_by(user_id=utente.id).count() == 0

    def test_si_vedono_solo_le_proprie(self, app, db_session):
        uno, due = _utente(db_session), _utente(db_session)
        _client_di(app, uno).post(
            "/segnalazioni/nuova",
            data={"tipo": "bug", "titolo": "Segreto di uno", "corpo": "Testo."},
        )

        pagina = _client_di(app, due).get("/segnalazioni/").get_data(as_text=True)

        assert "Segreto di uno" not in pagina


class TestNessunLinkAGithubPerGliUtenti:
    def test_nessun_link_a_github_nelle_schermate_dell_utente(self, client, db_session):
        """Chi segnala resta nell'app: GitHub è il nostro backlog, non un posto
        dove mandare l'utente.

        Fino al 2026-09-16 il motivo era anche che il repository era privato e
        il link avrebbe dato un 404 senza spiegazione. Aprendolo quella metà è
        caduta, e la scelta è stata riesaminata: **confermata** lo stesso
        giorno, perché la prima ragione basta da sola."""
        utente = _utente(db_session)
        _login(client, utente)
        client.post(
            "/segnalazioni/nuova",
            data={"tipo": "bug", "titolo": "T", "corpo": "C"},
        )
        segnalazione = FeedbackReport.query.filter_by(user_id=utente.id).one()
        segnalazione.issue_number = 123
        db.session.commit()

        for percorso in ("/segnalazioni/", "/segnalazioni/nuova"):
            pagina = client.get(percorso).get_data(as_text=True)
            assert "github.com" not in pagina.lower()

    def test_l_admin_invece_vede_il_numero_della_issue(self, app, db_session):
        """A lui serve: è il ponte fra la segnalazione e il backlog."""
        autore = _utente(db_session)
        segnalazione = FeedbackReport(
            user_id=autore.id,
            tipo="bug",
            titolo="Con issue",
            corpo="C",
            stato=FeedbackStatus.RICEVUTA.value,
            issue_number=321,
        )
        db.session.add(segnalazione)
        db.session.commit()

        admin = _client_di(app, _utente(db_session, UserRole.ADMIN.value))
        pagina = admin.get("/segnalazioni/tutte").get_data(as_text=True)

        assert "321" in pagina


class TestLaVoceNelMenu:
    def test_compare_a_chi_e_autenticato(self, client, db_session):
        _login(client, _utente(db_session))
        pagina = client.get("/segnalazioni/").get_data(as_text=True)
        assert "/segnalazioni/" in pagina

    def test_non_compare_a_un_anonimo(self, client):
        """La segnalazione nasce da un account: mandare al login chi clicca
        una voce di menu è peggio che non mostrarla."""
        pagina = client.get("/").get_data(as_text=True)
        assert "/segnalazioni/" not in pagina
