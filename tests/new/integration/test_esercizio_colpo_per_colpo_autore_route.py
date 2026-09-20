"""Dichiarare il colpo per colpo dal modulo e dal disegnatore (fase 5b; ADR-066).

Il giunto interfaccia↔server: la terza voce di «Come si registra» compare solo
se il disegno ha un bersaglio, il salvataggio deriva il massimo, e il
disegnatore — che è dove il bersaglio si tocca — non può lasciare senza anelli
un esercizio che ne ha bisogno.
"""

from __future__ import annotations

import io
import json
import uuid

import pytest
from PIL import Image

from models.base import db
from models.challenge.models import Challenge
from models.challenge.recording import RecordingMode
from models.challenge.services import ChallengeService
from models.user.models import User
from models.user.role_enum import UserRole
from utils.image_paths import ImagePathManager

AJAX = {"X-Requested-With": "XMLHttpRequest"}


def _scena(values=(3, 2, 1), bersaglio=True) -> str:
    voci = (
        [{"type": "target", "x": 600, "y": 200, "step": 50, "values": list(values)}]
        if bersaglio
        else [{"type": "ball", "id": "b1", "ball": "cue", "x": 100, "y": 100}]
    )
    return json.dumps({"v": 4, "orient": "h", "items": voci})


@pytest.fixture
def upload_dir(app, tmp_path):
    precedente = app.config.get("CHALLENGE_UPLOAD_FOLDER")
    app.config["CHALLENGE_UPLOAD_FOLDER"] = str(tmp_path)
    yield tmp_path
    if precedente is None:
        app.config.pop("CHALLENGE_UPLOAD_FOLDER", None)
    else:
        app.config["CHALLENGE_UPLOAD_FOLDER"] = precedente


@pytest.fixture
def direttore(app, client):
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"d_{suffix}",
        email=f"d_{suffix}@test.local",
        role=UserRole.DIRECTOR.value,
        is_verified=True,
    )
    user.set_password("test1234")
    db.session.add(user)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = user.get_id()
        session["_fresh"] = True
    return user.id


def _esercizio(upload_dir, autore_id, scena) -> int:
    nome = f"{uuid.uuid4().hex}.png"
    Image.new("RGB", (40, 30), "green").save(upload_dir / nome, "PNG")
    challenge = ChallengeService.create_challenge(
        title="Ferma nel cerchio",
        description="Ferma la bianca nel cerchio",
        image_path=ImagePathManager.get_challenge_db_path(nome),
        created_by_id=autore_id,
        max_score=10,
        diagram_scene=scena,
    )
    db.session.commit()
    return challenge.id


def _campi(**extra):
    campi = {
        "title": "Ferma nel cerchio",
        "description": "Ferma la bianca nel cerchio",
        "scoring_type": "score",
        "max_score": "10",
        "is_active_sent": "1",
        "is_active": "1",
    }
    campi.update(extra)
    return campi


def _png():
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "blue").save(buffer, "PNG")
    buffer.seek(0)
    return (buffer, "disegno.png")


class TestIlModulo:
    def test_col_bersaglio_la_terza_voce_c_e(self, app, client, upload_dir, direttore):
        cid = _esercizio(upload_dir, direttore, _scena())
        pagina = client.get(f"/challenges/{cid}/edit").get_data(as_text=True)
        assert 'name="scoring_type" value="shots"' in pagina
        assert 'name="shots_count"' in pagina

    def test_senza_bersaglio_c_e_la_riga_che_dice_come_averla(
        self, app, client, upload_dir, direttore
    ):
        cid = _esercizio(upload_dir, direttore, _scena(bersaglio=False))
        pagina = client.get(f"/challenges/{cid}/edit").get_data(as_text=True)
        assert 'value="shots"' not in pagina
        assert "nel disegno va messo un bersaglio" in pagina

    def test_salvare_deriva_il_massimo(self, app, client, upload_dir, direttore):
        cid = _esercizio(upload_dir, direttore, _scena())
        risposta = client.post(
            f"/challenges/{cid}/edit",
            data=_campi(scoring_type="shots", shots_count="20", max_score=""),
            headers=AJAX,
        )
        assert risposta.get_json()["success"] is True
        c = db.session.get(Challenge, cid)
        assert (c.recording_mode, c.shots_count, c.max_score) == (
            RecordingMode.SHOTS.value,
            20,
            60,
        )

    def test_senza_i_colpi_il_modulo_lo_dice(self, app, client, upload_dir, direttore):
        cid = _esercizio(upload_dir, direttore, _scena())
        risposta = client.post(
            f"/challenges/{cid}/edit",
            data=_campi(scoring_type="shots", shots_count=""),
            headers=AJAX,
        )
        assert risposta.status_code == 422
        assert "quanti colpi" in risposta.get_json()["error"]


class TestIlDisegnatore:
    def _colpo_per_colpo(self, client, upload_dir, direttore) -> int:
        cid = _esercizio(upload_dir, direttore, _scena())
        client.post(
            f"/challenges/{cid}/edit",
            data=_campi(scoring_type="shots", shots_count="10", max_score=""),
            headers=AJAX,
        )
        return cid

    def _salva_disegno(self, client, cid, scena):
        return client.post(
            f"/challenges/{cid}/builder",
            data={
                "diagram_scene": scena,
                "description": "Ferma la bianca nel cerchio",
                "title": "Ferma nel cerchio",
                "pass_fail_only": "false",
                "max_score": "30",
                "image": _png(),
            },
            headers=AJAX,
            content_type="multipart/form-data",
        )

    def test_cambiare_un_anello_cambia_il_massimo(
        self, app, client, upload_dir, direttore
    ):
        cid = self._colpo_per_colpo(client, upload_dir, direttore)
        risposta = self._salva_disegno(client, cid, _scena(values=(5, 2, 1)))
        assert risposta.get_json()["success"] is True
        assert db.session.get(Challenge, cid).max_score == 50

    def test_il_bersaglio_non_si_toglie(self, app, client, upload_dir, direttore):
        cid = self._colpo_per_colpo(client, upload_dir, direttore)
        risposta = self._salva_disegno(client, cid, _scena(bersaglio=False))
        assert risposta.status_code == 422
        assert "il bersaglio" in risposta.get_json()["error"]
        assert db.session.get(Challenge, cid).max_score == 30
