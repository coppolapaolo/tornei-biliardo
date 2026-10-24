"""Il testo segue la dimensione scelta nelle impostazioni del telefono, fino a un tetto.

Fino al 24 ottobre 2026 ogni dimensione del testo era scritta in pixel —
`body { font-size: 14px }` e più di novecento `font-size: Npx` fra fogli di
stile e template — e su iPhone «Dimensioni testo» non spostava niente: le app
native la seguono da sole, una pagina web solo se la chiede con
`font: -apple-system-body`. Chi alzava il cursore per leggere senza occhiali
trovava la nostra app identica a prima, e doveva zoomare a due dita.

Lo schema, in `tokens-7c.css` e nella regola `body` di `theme-7c.css`:

* su iOS `body` prende `font: -apple-system-body` (17px con il cursore a metà);
  altrove `17/16 rem`, cioè 17px con il default del browser;
* `--c7-tpx` è **un pixel di testo**: `min(1em, tetto) / 17`, registrata con
  `@property` come `<length>` così che l'`em` si risolva **su body** e i figli
  ereditino un numero, non una formula da ricalcolare a ogni livello;
* ogni dimensione si scrive `calc(N * var(--c7-tpx))`: con il cursore a metà
  vale N pixel esatti, quindi l'app di prima resta identica al pixel;
* `--c7-tpx-lento` è lo stesso con un tetto più basso (20/17), per ciò che
  deve crescere meno: titoli e cifre da 24px in su, la testata di pagina, le
  iniziali dentro un cerchio di misura fissa, il tastierino del referto.

Il tetto esiste perché oltre una certa misura il layout fitto — tabellone,
referto, classifiche — si rompe; per chi ha bisogno di più resta lo zoom a due
dita, che il `viewport` non deve bloccare. `rem` resta 16px: Bootstrap misura
in `rem` margini e spaziature, e metterci la preferenza del telefono li
avrebbe fatti crescere senza limite.

Il presidio legge il **testo** di fogli e template: un test di comportamento
non vede un `13px` al posto di `calc(13 * var(--c7-tpx))`.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CSS_DIR = ROOT / "static" / "css"
TEMPLATES = ROOT / "templates"
TOKENS = CSS_DIR / "tokens-7c.css"
THEME = CSS_DIR / "theme-7c.css"

# Una dimensione del testo scritta in pixel fissi: `font-size: 13px`, o il
# corpo dello shorthand `font: 800 12px/1 …`. Le `clamp(Npx, Nvh, Npx)` del
# tabellone non rientrano: seguono lo schermo del tavolo, non chi legge.
PX_FISSO = re.compile(
    r"(?<![\w-])(?:font-size\s*:\s*\d*\.?\d+px" r"|font\s*:[^;}\"']*?\s\d*\.?\d+px)"
)


def _senza_commenti(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _sorgenti():
    yield from sorted(CSS_DIR.glob("*.css"))
    yield from sorted(TEMPLATES.rglob("*.html"))


@pytest.mark.parametrize(
    "percorso", list(_sorgenti()), ids=lambda p: str(p.relative_to(ROOT))
)
def test_nessuna_dimensione_del_testo_in_pixel_fissi(percorso):
    testo = _senza_commenti(percorso.read_text(encoding="utf-8"))
    trovate = [
        f"riga {testo.count(chr(10), 0, m.start()) + 1}: {m.group(0)}"
        for m in PX_FISSO.finditer(testo)
    ]
    assert not trovate, (
        "Dimensione del testo in pixel fissi: non segue le impostazioni del "
        "telefono. Scrivila `calc(N * var(--c7-tpx))`.\n" + "\n".join(trovate)
    )


@pytest.mark.parametrize("nome", ["--c7-tpx", "--c7-tpx-lento"])
def test_il_pixel_di_testo_e_registrato_come_lunghezza(nome):
    css = _senza_commenti(TOKENS.read_text(encoding="utf-8"))
    m = re.search(rf"@property\s+{re.escape(nome)}\s*\{{([^}}]*)\}}", css)
    assert m, f"@property {nome} manca in tokens-7c.css"
    assert re.search(r"syntax\s*:\s*['\"]<length>['\"]", m.group(1))
    assert re.search(r"inherits\s*:\s*true", m.group(1))
    assert re.search(r"initial-value\s*:\s*1px", m.group(1))


def _regole_body(css: str) -> list[str]:
    return re.findall(r"(?<![\w.#-])body\s*\{([^}]*)\}", _senza_commenti(css))


def test_body_legge_la_preferenza_di_ios_e_mette_il_tetto():
    css = THEME.read_text(encoding="utf-8")
    corpo = " ".join(_regole_body(css))
    assert "-apple-system-body" in corpo
    # Il tetto: un pixel di testo non supera 23/17 (la tacca più grande fra
    # le sette normali di iOS).
    assert re.search(
        r"--c7-tpx\s*:\s*calc\(\s*min\(\s*1em\s*,\s*23px\s*\)\s*/\s*17\s*\)", corpo
    )
    # Titoli, cifre grandi e comandi fitti crescono meno: fino a 20/17, come
    # il titolo grande di iOS (da 34 a 40).
    assert re.search(
        r"--c7-tpx-lento\s*:\s*calc\(\s*min\(\s*1em\s*,\s*20px\s*\)\s*/\s*17\s*\)",
        corpo,
    )
    # Solo su iOS: su macOS Safari `-apple-system-body` vale 13px, e
    # rimpicciolirebbe tutto.
    assert re.search(
        r"@supports\s*\(\s*font\s*:\s*-apple-system-body\s*\)\s*and\s*"
        r"\(\s*-webkit-touch-callout\s*:\s*none\s*\)",
        css,
    )


def test_il_viewport_non_blocca_lo_zoom():
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    viewport = re.search(r'<meta name="viewport" content="([^"]*)"', base)
    assert viewport
    assert "maximum-scale" not in viewport.group(1)
    assert "user-scalable" not in viewport.group(1)
