"""Eseguire un esercizio colpo per colpo, dalle route (fase 5b; ADR-066).

Il giunto interfaccia↔server. Due cose che dal browser non si vedono e qui sì:
il **punteggio non passa dal browser** — lo decide il bersaglio, che ha solo il
server — e ogni risposta riporta i due pezzi che cambiano, «come sta andando» e
i comandi, già disegnati.
"""

from __future__ import annotations

import json
import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge, ChallengeAttempt, ChallengeShot
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


@pytest.fixture
def giocatore(app, client):
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"g_{suffix}",
        email=f"g_{suffix}@test.local",
        role=UserRole.PLAYER.value,
        is_verified=True,
    )
    user.set_password("test1234")
    db.session.add(user)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = user.get_id()
        session["_fresh"] = True
    return user.id


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


def _colpo(client, cid, **payload):
    return client.post(f"/challenges/{cid}/train/shot", json=payload, headers=AJAX)


class TestLaPagina:
    def test_si_apre_col_panno_da_toccare(self, client, giocatore, esercizio):
        html = client.get(f"/challenges/{esercizio}/train").get_data(as_text=True)

        assert "data-cloth-full" in html
        assert "data-shot-miss" in html
        assert "exercise-shots.js" in html
        # Il tastierino del punteggio non c'è: qui il totale non si scrive.
        assert "data-score-display" not in html
        assert "Colpo per colpo" in html

    def test_a_meta_prova_riprende_da_dove_si_era(self, client, giocatore, esercizio):
        _colpo(client, esercizio, made=True, x=600, y=200)

        html = client.get(f"/challenges/{esercizio}/train").get_data(as_text=True)

        assert "Colpo 2 di 3" in html


class TestRegistrare:
    def test_il_punteggio_lo_decide_il_bersaglio(self, client, giocatore, esercizio):
        """Dal browser arrivano esito e punto, mai i punti: il server li deriva."""
        payload = _colpo(client, esercizio, made=True, x=600, y=200).get_json()

        assert payload["success"] is True
        colpo = ChallengeShot.query.one()
        assert (colpo.points, colpo.position) == (3, 1)
        assert "Colpo 2 di 3" in payload["progress_html"]
        assert "data-shot-miss" in payload["dock_html"]

    def test_la_mancata_non_ha_un_punto(self, client, giocatore, esercizio):
        _colpo(client, esercizio, made=False)

        colpo = ChallengeShot.query.one()
        assert (colpo.made, colpo.points, colpo.x) == (False, 0, None)

    def test_l_imbucata_senza_punto_si_rifiuta(self, client, giocatore, esercizio):
        risposta = _colpo(client, esercizio, made=True)

        assert risposta.status_code == 422
        assert ChallengeShot.query.count() == 0

    def test_dopo_l_ultimo_colpo_compare_chiudi(self, client, giocatore, esercizio):
        for _ in range(2):
            _colpo(client, esercizio, made=False)
        payload = _colpo(client, esercizio, made=True, x=600, y=200).get_json()

        assert "data-shot-close" in payload["dock_html"]
        assert "data-shot-miss" not in payload["dock_html"]
        # Il panno sparisce: non c'è più niente da toccare.
        assert "data-cloth-full" not in payload["progress_html"]

    def test_oltre_i_colpi_dell_esercizio_non_si_va(self, client, giocatore, esercizio):
        for _ in range(3):
            _colpo(client, esercizio, made=False)

        risposta = _colpo(client, esercizio, made=False)

        assert risposta.status_code == 409
        assert ChallengeShot.query.count() == 3


class TestChiudereEAnnullare:
    def test_chiudere_somma_i_colpi(self, client, giocatore, esercizio):
        for x in (600, 660, 720):  # 3 + 2 + 1
            _colpo(client, esercizio, made=True, x=x, y=200)

        payload = client.post(
            f"/challenges/{esercizio}/train/shot/close", headers=AJAX
        ).get_json()

        assert payload["success"] is True
        prova = ChallengeAttempt.query.one()
        assert (prova.completed, prova.score) == (True, 6)
        # Chiusa la prova si torna alle «prove di oggi», col panno pronto.
        assert "Le prove di oggi" in payload["progress_html"]
        assert "data-cloth-full" in payload["progress_html"]

    def test_a_meta_non_si_chiude(self, client, giocatore, esercizio):
        _colpo(client, esercizio, made=False)

        risposta = client.post(
            f"/challenges/{esercizio}/train/shot/close", headers=AJAX
        )

        assert risposta.status_code == 409
        assert ChallengeAttempt.query.one().completed is False

    def test_l_annulla_toglie_l_ultimo_colpo(self, client, giocatore, esercizio):
        _colpo(client, esercizio, made=True, x=600, y=200)
        _colpo(client, esercizio, made=False)

        payload = client.post(
            f"/challenges/{esercizio}/train/shot/undo", headers=AJAX
        ).get_json()

        assert payload["success"] is True
        assert ChallengeShot.query.count() == 1
        assert "Colpo 2 di 3" in payload["progress_html"]

    def test_ricominciare_butta_la_prova_aperta(self, client, giocatore, esercizio):
        _colpo(client, esercizio, made=True, x=600, y=200)

        payload = client.post(
            f"/challenges/{esercizio}/train/shot/restart", headers=AJAX
        ).get_json()

        assert payload["success"] is True
        assert ChallengeAttempt.query.count() == 0
        assert ChallengeShot.query.count() == 0
        assert "Le prove di oggi" in payload["progress_html"]


class TestIlTotaleNonPassaDiQui:
    def test_la_vecchia_route_lo_rifiuta(self, client, giocatore, esercizio):
        """Due segnapunti che si contraddicono al primo tocco non devono esistere."""
        risposta = client.post(
            f"/challenges/{esercizio}/train", json={"score": 7}, headers=AJAX
        )

        assert risposta.status_code == 422
        assert ChallengeAttempt.query.count() == 0
