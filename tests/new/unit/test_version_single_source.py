"""Presidio sul numero di versione mostrato nell'app.

Dal 2026-08-26 `Config.VERSION` non si scrive più a mano: la calcola
release-please dai titoli delle PR unite (Conventional Commits) e la riscrive
in `config.py` dentro la PR di rilascio. Il valore compare nel footer di ogni
pagina e nella risposta di `/health`.

Tutto il meccanismo si regge su **tre convenzioni mute**, e mute è la parola
importante: se una salta, niente si rompe in modo visibile — semplicemente il
numero smette di muoversi, e ce ne si accorge mesi dopo guardando il footer.
È lo stesso profilo di guasto del `pip install` fallito con un WARNING descritto
in `scripts/auto_deploy.py`: un no-op non si distingue da un successo.

Le tre convenzioni:

1. l'annotazione ``# x-release-please-version`` in fondo alla riga di
   ``VERSION`` — è l'unico segnale che dice al bot quale riga riscrivere;
2. ``config.py`` elencato fra gli ``extra-files`` di
   ``release-please-config.json`` — senza, il bot aggiorna solo il changelog;
3. il manifest ``.release-please-manifest.json``, che è la memoria del bot: da
   lì riparte per calcolare il numero successivo. Se diverge da ``VERSION``,
   il prossimo rilascio parte dal numero sbagliato.

Il test guarda il **testo** dei file, non il comportamento, perché il
comportamento è di GitHub Actions e in locale non c'è.
"""

import json
import re
from pathlib import Path

from config import Config

_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_PY = _ROOT / "config.py"
_MANIFEST = _ROOT / ".release-please-manifest.json"
_RP_CONFIG = _ROOT / "release-please-config.json"
_BASE_HTML = _ROOT / "templates" / "base.html"

_VERSION_LINE = re.compile(r'^\s*VERSION\s*=\s*"([^"]+)"(.*)$', re.MULTILINE)


def _package_config() -> dict:
    """La configurazione del pacchetto radice ("." = tutto il repo)."""
    return json.loads(_RP_CONFIG.read_text(encoding="utf-8"))["packages"]["."]


def test_version_line_carries_the_release_please_annotation():
    """Senza l'annotazione il bot non trova la riga e la versione si ferma."""
    match = _VERSION_LINE.search(_CONFIG_PY.read_text(encoding="utf-8"))

    assert match is not None, 'La riga `VERSION = "..."` non è più in config.py'
    assert "x-release-please-version" in match.group(2), (
        "L'annotazione `# x-release-please-version` è sparita dalla riga di "
        "VERSION in config.py. Nessun errore si manifesterebbe: release-please "
        "continuerebbe a girare, ad aprire la PR di rilascio e a scrivere il "
        "changelog — solo, il numero nel footer resterebbe fermo per sempre."
    )


def test_release_please_updates_config_py():
    """`config.py` deve restare fra gli extra-files, o nessuno scrive VERSION."""
    paths = {
        entry["path"] if isinstance(entry, dict) else entry
        for entry in _package_config().get("extra-files", [])
    }

    assert "config.py" in paths, (
        "config.py non è più fra gli `extra-files` di release-please-config.json: "
        "il rilascio aggiornerebbe il changelog ma non la versione mostrata."
    )


def test_manifest_matches_the_version_in_config():
    """Il manifest è la memoria del bot: deve dire ciò che dice l'app."""
    manifest_version = json.loads(_MANIFEST.read_text(encoding="utf-8"))["."]

    assert manifest_version == Config.VERSION, (
        f"`.release-please-manifest.json` dice {manifest_version!r} ma "
        f"`Config.VERSION` dice {Config.VERSION!r}. I due si aggiornano insieme "
        "nella PR di rilascio: se divergono, qualcuno ha modificato la versione "
        "a mano e il prossimo rilascio ripartirà dal numero del manifest."
    )


def test_changelog_a_mano_e_changelog_generato_restano_due_file():
    """`CHANGELOG.md` è scritto a mano; il bot ha il suo file separato.

    Il changelog di questo progetto è prosa in italiano, con il *perché* delle
    scelte: release-please genera invece un elenco di titoli di PR. Puntare il
    bot su `CHANGELOG.md` non cancellerebbe lo storico, ma da quel momento le
    voci nuove sarebbero righe secche e la prosa smetterebbe di essere scritta.
    """
    changelog_path = _package_config().get("changelog-path")

    assert changelog_path and changelog_path != "CHANGELOG.md", (
        "release-please sta per scrivere in CHANGELOG.md, che è il changelog "
        "curato a mano. Il file generato è `docs/RELEASES.md`."
    )


def test_la_versione_e_visibile_nel_footer():
    """La versione deve *comparire*: è tutto il senso dell'esercizio."""
    assert "config.VERSION" in _BASE_HTML.read_text(encoding="utf-8"), (
        "Il footer di base.html non mostra più `config.VERSION`: il numero "
        "continuerebbe ad aggiornarsi senza che nessuno lo veda."
    )
