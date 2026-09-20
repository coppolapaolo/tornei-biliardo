"""Eseguire un esercizio con estrazione, dalle route (fase 5c, #452).

Il giunto interfaccia↔server. Le due cose che dal browser non si vedono: la
consegna **non si riestrae** a ogni lettura — o ricaricare la pagina sarebbe un
modo di cambiarla finché non piace — e dal browser arriva **quale** esito, non
quanto vale.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.draw_spec import build_spec, dump_spec
from models.challenge.models import Challenge, ChallengeAttempt, ChallengeShot
from models.challenge.recording import RecordingMode
from models.user.models import User
from models.user.role_enum import UserRole

AJAX = {"X-Requested-With": "XMLHttpRequest"}

SORGENTI = [
    {"label": "sponde", "options": ["1 sponda", "2 sponde"]},
    {"label": "bilia", "options": ["bilia 7"]},
]
ESITI = [
    {"label": "Mancata", "points": 0},
    {"label": "Colpita regolare", "points": 2},
    {"label": "Imbucata", "points": 4},
]


@pytest.fixture
def giocatore(app, client):
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"e_{suffix}",
        email=f"e_{suffix}@test.local",
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
        title="Kicking Madness",
        description="Estrai, tira, di' com'è andata",
        image_path="/static/uploads/challenges/x.png",
        pass_fail_only=False,
        recording_mode=RecordingMode.DRAW.value,
        shots_count=2,
        max_score=8,
        draw_spec=dump_spec(
            build_spec(
                [{"label": "sponde", "options": ["1 sponda", "2 sponde"]}], ESITI
            )
        ),
        is_active=True,
    )
    db.session.add(challenge)
    db.session.commit()
    return challenge.id


def _estrai(client, cid):
    return client.post(f"/challenges/{cid}/train/draw", headers=AJAX)


def _esito(client, cid, indice):
    return client.post(
        f"/challenges/{cid}/train/outcome",
        json={"outcome_index": indice},
        headers=AJAX,
    )


class TestLaPagina:
    def test_si_apre_col_tasto_per_estrarre(self, client, giocatore, esercizio):
        html = client.get(f"/challenges/{esercizio}/train").get_data(as_text=True)

        assert "data-draw-next" in html
        assert "Estrai il primo colpo" in html
        # Niente panno: qui non si tocca nessun punto.
        assert "data-cloth-full" not in html

    def test_estratta_la_consegna_compare_la_scala(self, client, giocatore, esercizio):
        payload = _estrai(client, esercizio).get_json()

        assert "L'app ha estratto" in payload["progress_html"]
        assert 'data-draw-outcome="2"' in payload["progress_html"]
        assert "Imbucata" in payload["progress_html"]

    def test_la_consegna_resta_quella_ricaricando(self, client, giocatore, esercizio):
        """Riestrarre a ogni lettura sarebbe un modo di rifare il sorteggio."""
        _estrai(client, esercizio)
        consegna = ChallengeAttempt.query.one().pending_prompt

        client.get(f"/challenges/{esercizio}/train")
        _estrai(client, esercizio)

        assert ChallengeAttempt.query.one().pending_prompt == consegna


class TestRegistrare:
    def test_l_esito_lo_pesa_il_server(self, client, giocatore, esercizio):
        """Dal browser arriva quale voce, mai quanto vale."""
        _estrai(client, esercizio)

        payload = _esito(client, esercizio, 2).get_json()

        colpo = ChallengeShot.query.one()
        assert (colpo.points, colpo.outcome_label) == (4, "Imbucata")
        assert colpo.prompt
        # La consegna dopo esce subito: chi tira non deve chiederla.
        assert "L'app ha estratto" in payload["progress_html"]

    def test_senza_consegna_non_si_registra(self, client, giocatore, esercizio):
        risposta = _esito(client, esercizio, 1)

        assert risposta.status_code == 409
        assert ChallengeShot.query.count() == 0

    def test_un_esito_che_non_c_e_si_rifiuta(self, client, giocatore, esercizio):
        _estrai(client, esercizio)

        risposta = _esito(client, esercizio, 9)

        assert risposta.status_code == 422
        assert ChallengeShot.query.count() == 0

    def test_all_ultimo_colpo_si_chiude(self, client, giocatore, esercizio):
        for _ in range(2):
            _estrai(client, esercizio)
            _esito(client, esercizio, 2)

        payload = client.post(
            f"/challenges/{esercizio}/train/shot/close", headers=AJAX
        ).get_json()

        assert payload["success"] is True
        prova = ChallengeAttempt.query.one()
        assert (prova.completed, prova.score, prova.pending_prompt) == (True, 8, None)

    def test_il_panno_non_c_entra(self, client, giocatore, esercizio):
        """Toccare un punto su un esercizio con estrazione non vuol dire niente."""
        _estrai(client, esercizio)

        risposta = client.post(
            f"/challenges/{esercizio}/train/shot",
            json={"made": True, "x": 600, "y": 200},
            headers=AJAX,
        )

        assert risposta.status_code == 422
        assert ChallengeShot.query.count() == 0
