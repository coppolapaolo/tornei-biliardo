"""Il modulo unico dell'esercizio dalle route: crea, modifica, duplica (#252, #253).

I criteri di accettazione delle due issue, uno per uno. Le immagini sono **file
veri** in una cartella temporanea: «la copia ha un file suo» non si può
verificare confrontando due stringhe.
"""

from __future__ import annotations

import io
import os
import uuid

import pytest
from PIL import Image

from models.base import db
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.profile_service import ChallengeProfileService
from models.challenge.services import ChallengeService
from models.user.models import User
from models.user.role_enum import UserRole
from utils.image_paths import ImagePathManager

AJAX = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def upload_dir(app, tmp_path):
    precedente = app.config.get("CHALLENGE_UPLOAD_FOLDER")
    app.config["CHALLENGE_UPLOAD_FOLDER"] = str(tmp_path)
    yield tmp_path
    if precedente is None:
        app.config.pop("CHALLENGE_UPLOAD_FOLDER", None)
    else:
        app.config["CHALLENGE_UPLOAD_FOLDER"] = precedente


def _utente(ruolo=UserRole.DIRECTOR.value) -> int:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"u_{suffix}",
        email=f"u_{suffix}@test.local",
        role=ruolo,
        is_verified=True,
    )
    user.set_password("test1234")
    db.session.add(user)
    db.session.commit()
    return user.id


def _login(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = db.session.get(User, user_id).get_id()
        session["_fresh"] = True


def _foto(colore="red"):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), colore).save(buffer, "PNG")
    buffer.seek(0)
    return (buffer, "tavolo.png")


def _file_su_disco(upload_dir) -> str:
    nome = f"{uuid.uuid4().hex}.jpg"
    Image.new("RGB", (40, 30), "green").save(upload_dir / nome, "JPEG")
    return nome


def _esercizio(app, upload_dir, autore_id, *, scena=None, prove=0) -> int:
    with app.app_context():
        nome = _file_su_disco(upload_dir)
        challenge = ChallengeService.create_challenge(
            title="Spot Shot Rally",
            description="Dieci tiri dalla stessa posizione",
            image_path=ImagePathManager.get_challenge_db_path(nome),
            created_by_id=autore_id,
            max_score=10,
            diagram_scene=scena,
        )
        db.session.commit()
        ChallengeProfileService.set_profile(
            challenge.id, abilita=["tiro"], gesti=["stop"], declared_level=2
        )
        for _ in range(prove):
            ChallengeService.record_attempt(
                _utente(UserRole.PLAYER.value), challenge.id, score=7
            )
        db.session.commit()
        return challenge.id


def _campi(**extra):
    campi = {
        "title": "Spot Shot Rally",
        "description": "Dieci tiri dalla stessa posizione",
        "scoring_type": "score",
        "max_score": "10",
        "abilita": ["tiro"],
        "gesti": ["stop"],
        "declared_level": "2",
        "is_active_sent": "1",
        "is_active": "1",
    }
    campi.update(extra)
    return campi


# ────────────────────────────────────────────────────────────────────────
# Creare
# ────────────────────────────────────────────────────────────────────────
def test_il_modulo_nuovo_mostra_i_due_vocabolari(app, client, upload_dir):
    _login(client, _utente())
    pagina = client.get("/challenges/create").get_data(as_text=True)
    assert "Cosa allena" in pagina and "Con che gesto" in pagina
    assert 'name="abilita" value="spaccata"' in pagina
    assert 'name="gesti" value="masse"' in pagina
    assert 'name="csrf_token"' in pagina


def test_creare_scrive_esercizio_e_profilo_insieme(app, client, upload_dir):
    autore = _utente()
    _login(client, autore)
    risposta = client.post(
        "/challenges/create",
        data={
            **_campi(
                title="Ferma nel cerchio", abilita=["posizione", "tiro"], gesti=["draw"]
            ),
            "family": "stop shot",
            "family_step": "2",
            "cue_ball_reset": "0",
            "variant_label": ["destra", "", "sinistra"],
            "variant_id": ["", "", ""],
            "image": _foto(),
        },
        headers=AJAX,
        content_type="multipart/form-data",
    )
    assert risposta.status_code == 200, risposta.get_data(as_text=True)
    corpo = risposta.get_json()
    with app.app_context():
        c = db.session.get(Challenge, corpo["challenge_id"])
        assert c.created_by_id == autore
        assert [a.value for a in c.abilita] == ["tiro", "posizione"]
        assert [g.value for g in c.gesti] == ["draw"]
        assert (c.family, c.family_step, c.cue_ball_reset) == ("stop shot", 2, False)
        assert [v.label for v in c.variants] == ["destra", "sinistra"]
        assert os.path.isfile(upload_dir / c.image_filename)


def test_un_profilo_rifiutato_non_lascia_ne_esercizio_ne_file(app, client, upload_dir):
    _login(client, _utente())
    with app.app_context():
        prima = db.session.query(Challenge).count()
    risposta = client.post(
        "/challenges/create",
        data={
            **_campi(abilita=["tiro", "posizione", "sponde", "difesa"]),
            "image": _foto(),
        },
        headers=AJAX,
        content_type="multipart/form-data",
    )
    assert risposta.status_code == 422
    with app.app_context():
        assert db.session.query(Challenge).count() == prima
    assert list(upload_dir.iterdir()) == []


# ────────────────────────────────────────────────────────────────────────
# Modificare (#252)
# ────────────────────────────────────────────────────────────────────────
def test_il_modulo_di_modifica_arriva_compilato(app, client, upload_dir):
    autore = _utente()
    challenge_id = _esercizio(app, upload_dir, autore, prove=2)
    _login(client, autore)
    pagina = client.get(f"/challenges/{challenge_id}/edit").get_data(as_text=True)
    assert "Modifica l&#39;esercizio" in pagina or "Modifica l'esercizio" in pagina
    assert 'value="Spot Shot Rally"' in pagina
    assert "2 prove registrate" in pagina
    assert 'name="abilita" value="tiro"\n                 checked' in pagina
    assert (
        "Usa una foto" in pagina
        and " required" not in pagina.split('id="image"')[1][:80]
    )


def test_un_esercizio_fotografato_si_corregge_senza_ricaricare_la_foto(
    app, client, upload_dir
):
    autore = _utente()
    challenge_id = _esercizio(app, upload_dir, autore)
    with app.app_context():
        foto = db.session.get(Challenge, challenge_id).image_path
    _login(client, autore)
    risposta = client.post(
        f"/challenges/{challenge_id}/edit",
        data=_campi(title="Spot Shot Rally — dieci", max_score="12"),
        headers=AJAX,
    )
    assert risposta.status_code == 200, risposta.get_data(as_text=True)
    with app.app_context():
        c = db.session.get(Challenge, challenge_id)
        assert c.title == "Spot Shot Rally — dieci"
        assert c.max_score == 12
        assert c.image_path == foto
        assert c.is_active is True


def test_con_prove_cambiare_le_regole_chiede_e_non_salva(app, client, upload_dir):
    autore = _utente()
    challenge_id = _esercizio(app, upload_dir, autore, prove=3)
    _login(client, autore)
    risposta = client.post(
        f"/challenges/{challenge_id}/edit", data=_campi(max_score="15"), headers=AJAX
    )
    assert risposta.status_code == 409
    corpo = risposta.get_json()
    assert corpo["needs_decision"] is True
    assert corpo["attempts"] == 3 and corpo["players"] == 3
    assert "3 prove" in corpo["title"]
    assert "da 10 a 15" in corpo["text"]
    with app.app_context():
        assert db.session.get(Challenge, challenge_id).max_score == 10


def test_con_prove_il_solo_titolo_passa_liscio(app, client, upload_dir):
    autore = _utente()
    challenge_id = _esercizio(app, upload_dir, autore, prove=1)
    _login(client, autore)
    risposta = client.post(
        f"/challenges/{challenge_id}/edit",
        data=_campi(title="Spot Shot Rally!", abilita=["tiro", "posizione"]),
        headers=AJAX,
    )
    assert risposta.status_code == 200


def test_scegliendo_copia_l_originale_resta_immutato_coi_suoi_tentativi(
    app, client, upload_dir
):
    autore = _utente()
    challenge_id = _esercizio(app, upload_dir, autore, prove=2)
    _login(client, autore)
    risposta = client.post(
        f"/challenges/{challenge_id}/edit",
        data=_campi(max_score="15", on_evidence="copy"),
        headers=AJAX,
    )
    assert risposta.status_code == 200, risposta.get_data(as_text=True)
    copia_id = risposta.get_json()["challenge_id"]
    assert copia_id != challenge_id
    with app.app_context():
        originale = db.session.get(Challenge, challenge_id)
        copia = db.session.get(Challenge, copia_id)
        assert originale.max_score == 10 and copia.max_score == 15
        assert copia.created_by_id == autore
        assert ChallengeAttempt.query.filter_by(challenge_id=challenge_id).count() == 2
        assert ChallengeAttempt.query.filter_by(challenge_id=copia_id).count() == 0
        # due file diversi, entrambi sul disco
        assert originale.image_filename != copia.image_filename
        assert os.path.isfile(upload_dir / originale.image_filename)
        assert os.path.isfile(upload_dir / copia.image_filename)


def test_scegliendo_modifica_comunque_si_scrive_qui(app, client, upload_dir):
    autore = _utente()
    challenge_id = _esercizio(app, upload_dir, autore, prove=2)
    _login(client, autore)
    risposta = client.post(
        f"/challenges/{challenge_id}/edit",
        data=_campi(max_score="15", on_evidence="overwrite"),
        headers=AJAX,
    )
    assert risposta.get_json()["challenge_id"] == challenge_id
    with app.app_context():
        assert db.session.get(Challenge, challenge_id).max_score == 15


def test_senza_javascript_il_foglio_arriva_gia_aperto(app, client, upload_dir):
    autore = _utente()
    challenge_id = _esercizio(app, upload_dir, autore, prove=1)
    _login(client, autore)
    risposta = client.post(
        f"/challenges/{challenge_id}/edit", data=_campi(max_score="15")
    )
    assert risposta.status_code == 409
    pagina = risposta.get_data(as_text=True)
    assert 'data-decision-open="1"' in pagina
    assert "Crea una copia e modifica quella" in pagina
    # quello che era stato scritto non si perde
    assert 'name="max_score"' in pagina and 'value="15"' in pagina


def test_il_modulo_non_disattiva_l_esercizio_se_il_campo_non_arriva(
    app, client, upload_dir
):
    autore = _utente()
    challenge_id = _esercizio(app, upload_dir, autore)
    _login(client, autore)
    campi = _campi()
    del campi["is_active_sent"], campi["is_active"]
    client.post(f"/challenges/{challenge_id}/edit", data=campi, headers=AJAX)
    with app.app_context():
        assert db.session.get(Challenge, challenge_id).is_active is True


def test_spegnere_nel_catalogo(app, client, upload_dir):
    autore = _utente()
    challenge_id = _esercizio(app, upload_dir, autore)
    _login(client, autore)
    campi = _campi()
    del campi["is_active"]
    client.post(f"/challenges/{challenge_id}/edit", data=campi, headers=AJAX)
    with app.app_context():
        assert db.session.get(Challenge, challenge_id).is_active is False


def test_un_altro_direttore_non_modifica_ne_duplica(app, client, upload_dir):
    challenge_id = _esercizio(app, upload_dir, _utente())
    _login(client, _utente())
    # Il blueprint trasforma il 403 in un redirect con messaggio: conta che il
    # modulo non si apra (200) e che la POST non scriva.
    assert client.get(f"/challenges/{challenge_id}/edit").status_code in (302, 403)
    assert client.get(f"/challenges/{challenge_id}/duplicate").status_code in (302, 403)
    client.post(
        f"/challenges/{challenge_id}/edit", data=_campi(title="Mio"), headers=AJAX
    )
    with app.app_context():
        assert db.session.get(Challenge, challenge_id).title == "Spot Shot Rally"


# ────────────────────────────────────────────────────────────────────────
# Duplicare (#253)
# ────────────────────────────────────────────────────────────────────────
def test_duplica_apre_il_modulo_con_i_dati_dell_originale(app, client, upload_dir):
    autore = _utente()
    challenge_id = _esercizio(app, upload_dir, autore, prove=4)
    _login(client, autore)
    pagina = client.get(f"/challenges/{challenge_id}/duplicate").get_data(as_text=True)
    assert 'value="Spot Shot Rally (copia)"' in pagina
    assert "Crea la copia" in pagina
    assert "parte senza prove" in pagina


def test_la_copia_di_un_esercizio_fotografato_tiene_l_immagine_in_un_file_suo(
    app, client, upload_dir
):
    autore = _utente()
    challenge_id = _esercizio(app, upload_dir, autore, prove=2)
    _login(client, autore)
    risposta = client.post(
        f"/challenges/{challenge_id}/duplicate",
        data=_campi(title="Spot Shot Rally — difficile", max_score="15"),
        headers=AJAX,
    )
    assert risposta.status_code == 200, risposta.get_data(as_text=True)
    copia_id = risposta.get_json()["challenge_id"]
    with app.app_context():
        originale = db.session.get(Challenge, challenge_id)
        copia = db.session.get(Challenge, copia_id)
        assert copia.id != originale.id
        assert copia.title == "Spot Shot Rally — difficile"
        assert copia.image_filename != originale.image_filename
        assert os.path.isfile(upload_dir / copia.image_filename)
        assert ChallengeAttempt.query.filter_by(challenge_id=copia_id).count() == 0
        assert [a.value for a in copia.abilita] == ["tiro"]
        file_originale = originale.image_filename

    # cancellare la copia non tocca l'originale, immagine compresa
    client.post(f"/challenges/{copia_id}/delete", headers=AJAX)
    assert os.path.isfile(upload_dir / file_originale)


def test_la_copia_di_un_esercizio_disegnato_porta_la_scena_e_apre_il_disegno(
    app, client, upload_dir
):
    autore = _utente()
    scena = '{"v": 1, "items": [{"type": "ball", "n": 1}]}'
    challenge_id = _esercizio(app, upload_dir, autore, scena=scena)
    _login(client, autore)
    risposta = client.post(
        f"/challenges/{challenge_id}/duplicate",
        data=_campi(title="Variante", then="diagram"),
        headers=AJAX,
    )
    corpo = risposta.get_json()
    with app.app_context():
        copia = db.session.get(Challenge, corpo["challenge_id"])
        assert copia.diagram_scene == scena
        assert (
            db.session.query(Challenge).filter_by(title="Spot Shot Rally").count() == 1
        )
    assert corpo["redirect_url"].endswith(
        f"/challenges/{corpo['challenge_id']}/builder"
    )


# ────────────────────────────────────────────────────────────────────────
# La porta sul retro: il disegnatore
# ────────────────────────────────────────────────────────────────────────
def test_la_scheda_offre_modifica_e_duplica_a_chi_l_ha_creato(app, client, upload_dir):
    autore = _utente()
    challenge_id = _esercizio(app, upload_dir, autore)
    _login(client, autore)
    pagina = client.get(f"/challenges/{challenge_id}").get_data(as_text=True)
    assert f"/challenges/{challenge_id}/edit" in pagina
    assert f"/challenges/{challenge_id}/duplicate" in pagina
