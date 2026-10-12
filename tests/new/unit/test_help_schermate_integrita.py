"""Integrità del manifest delle schermate della guida e dei suoi file.

`test_help_content.py` controlla che ogni figura **citata da una pagina** abbia
il suo file, nella vista che la pagina chiede. Restano fuori tre guasti che non
danno nessun errore visibile, e che una ricattura parziale (`--only`) produce
facilmente:

* una vista dichiarata e mai catturata: la voce ha `viewports: [mobile,
  desktop]`, la pagina cita la sola vista da telefono, e la `-desktop` manca —
  oggi nessuno se ne accorge, domani una pagina la chiede;
* un PNG **orfano**: la voce è stata rinominata o tolta, il file resta in
  `static/img/help/` e viaggia nel repository per sempre;
* una didascalia mancante in una lingua: l'italiano la tiene nel manifest, le
  altre lingue in `<lingua>/captions.yaml`, e senza la sua chi non vede
  l'immagine in inglese legge la didascalia italiana.

Il procedimento per rigenerare le schermate sta nella skill `help-docs`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "help_content" / "screenshots.yaml"
IMMAGINI = ROOT / "static" / "img" / "help"
LINGUA_DEL_MANIFEST = "it"


def _manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}


def _lingue() -> list[str]:
    return list(_manifest().get("locales") or [LINGUA_DEL_MANIFEST])


def _file_attesi() -> set[str]:
    """I nomi dei PNG che il manifest produce, per una lingua qualunque."""
    attesi: set[str] = set()
    for voce in _manifest().get("shots") or []:
        for vista in voce.get("viewports") or ["mobile"]:
            suffisso = "" if vista == "mobile" else f"-{vista}"
            attesi.add(f"{voce['id']}{suffisso}.png")
    return attesi


@pytest.mark.unit
@pytest.mark.parametrize("lingua", _lingue())
def test_ogni_vista_dichiarata_ha_il_suo_file(lingua):
    presenti = {p.name for p in (IMMAGINI / lingua).glob("*.png")}
    mancanti = sorted(_file_attesi() - presenti)
    assert not mancanti, (
        f"Viste dichiarate in screenshots.yaml e mai catturate in «{lingua}»: "
        f"{mancanti}. Cattura con `capture_screenshots.py --only <id>`."
    )


@pytest.mark.unit
@pytest.mark.parametrize("lingua", _lingue())
def test_nessuna_schermata_orfana(lingua):
    presenti = {p.name for p in (IMMAGINI / lingua).glob("*.png")}
    orfane = sorted(presenti - _file_attesi())
    assert not orfane, (
        f"PNG in static/img/help/{lingua}/ che nessuna voce del manifest "
        f"produce: {orfane}. Toglili, o rimetti la voce."
    )


@pytest.mark.unit
def test_nessuna_cartella_di_una_lingua_non_dichiarata():
    cartelle = {p.name for p in IMMAGINI.iterdir() if p.is_dir()}
    assert cartelle <= set(_lingue()), (
        f"Cartelle di schermate per lingue che il manifest non cattura: "
        f"{sorted(cartelle - set(_lingue()))}"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "lingua", [lingua for lingua in _lingue() if lingua != LINGUA_DEL_MANIFEST]
)
def test_ogni_schermata_ha_la_didascalia_in_ogni_lingua(lingua):
    percorso = ROOT / "help_content" / lingua / "captions.yaml"
    didascalie = yaml.safe_load(percorso.read_text(encoding="utf-8")) or {}
    ids = {voce["id"] for voce in _manifest().get("shots") or []}
    mancanti = sorted(i for i in ids if not str(didascalie.get(i) or "").strip())
    estranee = sorted(set(didascalie) - ids)
    assert not mancanti, f"Didascalie mancanti in {lingua}/captions.yaml: {mancanti}"
    assert not estranee, (
        f"Didascalie in {lingua}/captions.yaml per schermate che non esistono: "
        f"{estranee}"
    )
