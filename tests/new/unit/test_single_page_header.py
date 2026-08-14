"""La testata di pagina e' una sola: quella del guscio.

Nel design system 7c `base.html` disegna una sola `c7-head` e le pagine la
riempiono con i blocchi `page_back` / `page_title` / `page_sub` /
`page_actions`. Chi ne disegna una seconda dentro `content` ottiene due
testate sovrapposte — e' successo dodici volte durante la conversione, ogni
volta scoperto solo aprendo la pagina nel browser.

Il test guarda i sorgenti, non il rendering: cosi' copre anche le pagine che
nessun test funzionale visita.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "templates"

EXTENDS_BASE = re.compile(r"""{%-?\s*extends\s+["']base\.html["']""")
HEAD_MARKUP = re.compile(r"""class=["'][^"']*\bc7-head\b""")


def _pages():
    """Template che estendono il guscio: sono loro a poter sbagliare."""
    for path in sorted(TEMPLATES.rglob("*.html")):
        source = path.read_text(encoding="utf-8", errors="ignore")
        if EXTENDS_BASE.search(source):
            yield path, source


@pytest.mark.unit
def test_nessuna_seconda_testata_nelle_pagine():
    offenders = []
    for path, source in _pages():
        for match in HEAD_MARKUP.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(ROOT)}:{line}")

    assert not offenders, (
        "seconda `c7-head` dentro una pagina: "
        + ", ".join(offenders)
        + ". La testata la disegna base.html: riempi `page_title` / `page_sub`"
        " / `page_actions` / `page_back` invece di ridisegnarla."
    )


@pytest.mark.unit
def test_il_guscio_disegna_la_testata():
    """Guardia del guardiano: se `base.html` smettesse di avere la `c7-head`,
    il test qui sopra passerebbe per il motivo sbagliato."""
    source = (TEMPLATES / "base.html").read_text(encoding="utf-8")

    assert HEAD_MARKUP.search(source)
    for block in ("page_back", "page_title", "page_sub", "page_actions"):
        assert f"block {block}" in source, f"blocco {block} sparito da base.html"
