"""L'app installabile: manifest, icone e i tag che le collegano.

Le regole dei tre sistemi si contraddicono — Android ritaglia l'icona a
cerchio, iOS la arrotonda da sé e trasforma in **nero** ogni pixel
trasparente, la favicon deve reggere a 16 px — e nessuna di queste rotture si
vede provando l'app in sviluppo: si vede sul telefono di qualcun altro,
settimane dopo. Qui si misurano.

Le icone si rigenerano con::

    python scripts/disegna_icona_app.py --variante pieno --cartella /tmp/i
    python scripts/disegna_icona_app.py --variante pieno --quota 0.62 \
        --suffisso=-maskable --cartella /tmp/i
    python scripts/genera_icone_app.py --master /tmp/i/master-pieno.png \
        --maskable /tmp/i/master-pieno-maskable.png --sfondo "#2C4A52"
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from PIL import Image

RADICE = Path(__file__).resolve().parents[3]
MANIFEST = RADICE / "static" / "manifest.webmanifest"
BASE_HTML = RADICE / "templates" / "base.html"

# Android può ritagliare fino al cerchio inscritto: quel che sta fuori
# dall'80% centrale non è garantito che si veda.
QUOTA_SICURA = 0.80


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _percorso(src: str) -> Path:
    return RADICE / src.lstrip("/")


def _angoli(immagine: Image.Image) -> list[tuple[int, ...]]:
    lato = immagine.size[0]
    rgba = immagine.convert("RGBA")
    return [
        rgba.getpixel(punto)
        for punto in ((0, 0), (lato - 1, 0), (0, lato - 1), (lato - 1, lato - 1))
    ]


def test_il_manifest_dice_quel_che_dice_la_configurazione(manifest):
    from config import Config

    assert manifest["name"] == Config.APP_NAME
    # Sotto l'icona ci stanno una dozzina di caratteri: il nome per esteso
    # verrebbe troncato dal telefono, non da noi.
    assert manifest["short_name"] == "Biliardo"
    assert len(manifest["short_name"]) <= 12
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"


def test_le_icone_dichiarate_esistono_e_hanno_la_misura_dichiarata(manifest):
    for icona in manifest["icons"]:
        percorso = _percorso(icona["src"])
        assert percorso.exists(), f"{percorso} dichiarata nel manifest ma assente"
        atteso = int(icona["sizes"].split("x")[0])
        assert Image.open(percorso).size == (atteso, atteso)


def test_nessuna_icona_ha_angoli_trasparenti(manifest):
    """iOS annerisce la trasparenza, e gli angoli sono dove si nasconde."""
    percorsi = [_percorso(i["src"]) for i in manifest["icons"]]
    percorsi.append(RADICE / "static/img/app/apple-touch-icon.png")
    for percorso in percorsi:
        for angolo in _angoli(Image.open(percorso)):
            assert angolo[3] == 255, f"{percorso.name}: angolo trasparente"


def test_le_maskable_stanno_nel_cerchio_che_android_ritaglia(manifest):
    maskable = [i for i in manifest["icons"] if i["purpose"] == "maskable"]
    assert maskable, "senza una icona maskable Android ritaglia quella normale"

    for icona in maskable:
        immagine = Image.open(_percorso(icona["src"])).convert("RGB")
        lato = immagine.size[0]
        centro = (lato - 1) / 2.0
        sfondo = immagine.getpixel((0, 0))
        pixel = immagine.load()
        massimo = 0.0
        for y in range(lato):
            for x in range(lato):
                if pixel[x, y] != sfondo:
                    massimo = max(massimo, math.hypot(x - centro, y - centro))
        quota = 2.0 * massimo / lato
        assert quota <= QUOTA_SICURA, (
            f"{icona['src']}: il segno occupa un cerchio pari al {quota:.0%} "
            f"del lato, oltre il {QUOTA_SICURA:.0%} che Android garantisce"
        )


def test_apple_touch_icon_esiste_ed_e_opaca():
    percorso = RADICE / "static/img/app/apple-touch-icon.png"
    immagine = Image.open(percorso)
    assert immagine.size == (180, 180)
    assert immagine.mode == "RGB", "iOS non vuole un canale alfa: lo rende nero"


def test_le_favicon_esistono():
    for nome, lato in (("favicon-32.png", 32), ("favicon-16.png", 16)):
        assert Image.open(RADICE / "static/img/app" / nome).size == (lato, lato)
    assert (RADICE / "static/img/app/favicon.ico").exists()


def test_base_html_collega_manifest_e_icone():
    """Un manifest che nessuna pagina cita è un file che nessuno scarica."""
    html = BASE_HTML.read_text(encoding="utf-8")
    assert 'rel="manifest"' in html
    assert "manifest.webmanifest" in html
    assert 'rel="apple-touch-icon"' in html
    assert "favicon-32.png" in html and "favicon-16.png" in html
    assert 'name="apple-mobile-web-app-title" content="Biliardo"' in html
