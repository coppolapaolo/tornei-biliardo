"""Un caricamento rifiutato non lascia il file su disco (2026-11-10).

Quando Pillow non riusciva a leggere il file caricato, il contenuto grezzo
veniva scritto comunque nella cartella delle immagini e poi si rilanciava
l'errore. Nessun chiamante usa quel file — tutti e tre mostrano l'errore e non
salvano il percorso — ma restava sotto `static/uploads/`, servito a chiunque
ne conoscesse il nome, col contenuto scelto da chi l'aveva caricato. Ora un
file che non è un'immagine non resta su disco.
"""

import io
import os
import uuid
from datetime import date, timedelta

from PIL import Image

from models import Gara
from models.status_enum import Discipline, GaraStatus
from utils.image_paths import ImagePathManager


def _gara(db_session):
    gara = Gara(
        name=f"G{uuid.uuid4().hex[:6]}",
        number=1,
        date=date.today() + timedelta(days=1),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=True,
        status=GaraStatus.INSCRIPTION.value,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def _cartella_di_prova(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ImagePathManager, "get_banner_upload_dir", staticmethod(lambda: str(tmp_path))
    )


def _carica(client, gara, contenuto, nome):
    return client.post(
        f"/admin/gara/{gara.id}/vetrina/banner",
        data={"banner": (io.BytesIO(contenuto), nome)},
        content_type="multipart/form-data",
    )


def test_un_file_che_non_e_un_immagine_non_resta_su_disco(
    db_session, logged_in_client, monkeypatch, tmp_path
):
    _cartella_di_prova(monkeypatch, tmp_path)
    gara = _gara(db_session)
    client, _admin = logged_in_client(role="admin", username_prefix="adm")

    _carica(client, gara, b"<html><body>non sono una foto</body></html>", "x.png")

    assert os.listdir(tmp_path) == []
    db_session.expire_all()
    assert not db_session.get(Gara, gara.id).banner_path


def test_un_immagine_vera_si_carica_ancora(
    db_session, logged_in_client, monkeypatch, tmp_path
):
    _cartella_di_prova(monkeypatch, tmp_path)
    gara = _gara(db_session)
    client, _admin = logged_in_client(role="admin", username_prefix="adm")
    foto = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 120, 60)).save(foto, format="PNG")

    _carica(client, gara, foto.getvalue(), "locandina.png")

    salvati = os.listdir(tmp_path)
    assert len(salvati) == 1
    with Image.open(os.path.join(tmp_path, salvati[0])) as salvata:
        assert salvata.format == "PNG"
    db_session.expire_all()
    assert db_session.get(Gara, gara.id).banner_path
