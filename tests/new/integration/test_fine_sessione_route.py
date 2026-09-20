"""La fine della sessione, dalle route (fase 5d).

Il riepilogo di **una** prova: la nuvola dei punti d'arrivo, che cosa dice, i
numeri, le note. Racconta come si sbaglia, che è la cosa più personale che
questa app scriva: quindi è solo la propria, e di una prova davvero chiusa.
"""

from __future__ import annotations

import json
import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.recording import RecordingMode
from models.user.models import User
from models.user.role_enum import UserRole

AJAX = {"X-Requested-With": "XMLHttpRequest"}

SCENA = json.dumps(
    {
        "v": 4,
        "items": [
            {"type": "target", "x": 600, "y": 200, "step": 50, "values": [3, 2, 1]}
        ],
    }
)


def _utente(prefisso="f"):
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"{prefisso}_{suffix}",
        email=f"{prefisso}_{suffix}@test.local",
        role=UserRole.PLAYER.value,
        is_verified=True,
    )
    user.set_password("test1234")
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = user.get_id()
        session["_fresh"] = True
    # In questa suite `g` **non** è per-richiesta: senza questa pulizia
    # Flask-Login trova in cache l'utente di prima e non richiama mai
    # `load_user`, quindi «la prova di un altro» passerebbe sempre.
    from flask import g

    g.pop("_login_user", None)


@pytest.fixture
def giocatore(app, client):
    user = _utente()
    _login(client, user)
    return user


@pytest.fixture
def esercizio(app):
    challenge = Challenge(
        title="Ferma nel cerchio",
        description="Ferma la bianca nel cerchio",
        image_path="/static/uploads/challenges/x.png",
        diagram_scene=SCENA,
        pass_fail_only=False,
        recording_mode=RecordingMode.SHOTS.value,
        shots_count=3,
        max_score=9,
        is_active=True,
    )
    db.session.add(challenge)
    db.session.commit()
    return challenge.id


def _prova_chiusa(client, esercizio, punti=((660, 200), (665, 210), None)):
    """Tre colpi lunghi: una nuvola con una direzione da leggere.

    Le azioni passano dalle **route**, non dal servizio: un servizio chiamato
    fuori da una richiesta legge `current_user` dal contesto della fixture e
    rende anonime le richieste successive (memoria del leak di Flask-Login).
    """
    for punto in punti:
        corpo = (
            {"made": False}
            if punto is None
            else {"made": True, "x": punto[0], "y": punto[1]}
        )
        client.post(f"/challenges/{esercizio}/train/shot", json=corpo, headers=AJAX)
    client.post(f"/challenges/{esercizio}/train/shot/close", headers=AJAX)
    return (
        ChallengeAttempt.query.filter_by(completed=True)
        .order_by(ChallengeAttempt.id.desc())
        .first()
    )


class TestIlRiepilogo:
    def test_racconta_la_prova(self, client, giocatore, esercizio):
        prova = _prova_chiusa(client, esercizio)

        html = client.get(f"/challenges/train/summary/{prova.id}").get_data(
            as_text=True
        )

        assert "3 colpi" in html
        assert "Arrivi lungo" in html  # la lettura della nuvola
        assert "Imbucate" in html and "Posizione" in html
        # Il tavolo c'è, ma non si tocca: è un racconto.
        assert "c7-cloth__shot" in html
        assert "data-cloth-full" not in html

    def test_la_prova_di_un_altro_non_si_guarda(self, app, client, esercizio):
        altro = _utente("a")
        _login(client, altro)
        prova = _prova_chiusa(client, esercizio)
        _login(client, _utente("b"))

        risposta = client.get(f"/challenges/train/summary/{prova.id}")

        # Il blueprint degli esercizi rimanda al catalogo invece di mostrare una
        # pagina 404: quello che conta è che il riepilogo non si veda.
        assert risposta.status_code == 302
        assert risposta.headers["Location"].endswith("/challenges/")

    def test_una_prova_aperta_non_ha_una_fine_da_raccontare(
        self, client, giocatore, esercizio
    ):
        client.post(
            f"/challenges/{esercizio}/train/shot", json={"made": False}, headers=AJAX
        )
        aperta = ChallengeAttempt.query.one()

        risposta = client.get(f"/challenges/train/summary/{aperta.id}")

        assert risposta.status_code == 302
        assert f"/challenges/{esercizio}/train" in risposta.headers["Location"]


class TestLeNote:
    def test_si_scrivono_e_restano(self, client, giocatore, esercizio):
        prova = _prova_chiusa(client, esercizio)

        risposta = client.post(
            f"/challenges/train/summary/{prova.id}/notes",
            data={"notes": "  Tavolo 4, panno lento.  "},
        )

        assert risposta.status_code == 302
        assert (
            db.session.get(ChallengeAttempt, prova.id).notes == "Tavolo 4, panno lento."
        )

    def test_svuotare_la_casella_toglie_la_nota(self, client, giocatore, esercizio):
        prova = _prova_chiusa(client, esercizio)
        client.post(
            f"/challenges/train/summary/{prova.id}/notes", data={"notes": "qualcosa"}
        )

        client.post(f"/challenges/train/summary/{prova.id}/notes", data={"notes": ""})

        assert db.session.get(ChallengeAttempt, prova.id).notes is None

    def test_sulla_prova_di_un_altro_non_si_scrive(self, app, client, esercizio):
        altro = _utente("a")
        _login(client, altro)
        prova = _prova_chiusa(client, esercizio)
        _login(client, _utente("b"))

        risposta = client.post(
            f"/challenges/train/summary/{prova.id}/notes", data={"notes": "x"}
        )

        assert risposta.headers["Location"].endswith("/challenges/")
        assert db.session.get(ChallengeAttempt, prova.id).notes is None
