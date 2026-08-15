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


# ────────────────────────────────────────────────────────────────────────────
# I comandi della testata
# ────────────────────────────────────────────────────────────────────────────
#
# Sotto lg i comandi prendono una riga tutta loro: su 390px due bottoni con
# l'etichetta scritta non stanno accanto a freccia, titolo, badge e avatar, e il
# titolo — che ha `flex-basis: 0` — cedeva loro tutto lo spazio finendo a
# larghezza zero, una parola per riga.
#
# La riga in più la può prendere solo chi i comandi ce li ha davvero: il
# contenitore si disegna solo se il blocco produce qualcosa, altrimenti ogni
# pagina senza comandi si porterebbe dietro un buco sotto il titolo.


def _render(app, page_source: str) -> str:
    """`render_template_string` e non `from_string`: solo il primo applica i
    context processor, e il guscio ne usa parecchi (debug, permessi, enum)."""
    from flask import render_template_string

    with app.test_request_context("/"):
        return render_template_string(page_source)


def _css_rule(css: str, selector: str) -> str:
    """Il corpo di una regola, cercata a inizio riga: i commenti la nominano."""
    marker = f"\n{selector} {{"
    assert marker in css, f"regola {selector} sparita"
    return css.split(marker, 1)[1].split("}", 1)[0]


@pytest.mark.unit
def test_i_comandi_stanno_in_un_contenitore_proprio(app):
    html = _render(
        app,
        """{% extends "base.html" %}
        {% block page_title %}Con comandi{% endblock %}
        {% block page_actions %}<a href="/x" class="btn">Fai</a>{% endblock %}""",
    )

    assert "c7-head__actions" in html
    # E il comando ci finisce dentro davvero, non accanto.
    body = html.split("c7-head__actions", 1)[1]
    assert body.index(">Fai<") < body.index("</div>")


@pytest.mark.unit
def test_senza_comandi_non_si_disegna_la_riga(app):
    html = _render(
        app,
        """{% extends "base.html" %}
        {% block page_title %}Senza comandi{% endblock %}""",
    )

    assert "c7-head__actions" not in html


@pytest.mark.unit
def test_un_blocco_di_soli_spazi_non_conta_come_comando(app):
    """È il caso normale: `{% if %}` che non scatta lascia solo indentazione."""
    html = _render(
        app,
        """{% extends "base.html" %}
        {% block page_title %}Comandi condizionati{% endblock %}
        {% block page_actions %}
            {% if false %}<a href="/x">Mai</a>{% endif %}
        {% endblock %}""",
    )

    assert "c7-head__actions" not in html


@pytest.mark.unit
def test_i_comandi_lasciano_la_riga_del_titolo_sotto_lg():
    """La regola CSS che tiene in piedi tutto il resto."""
    css = (ROOT / "static" / "css" / "theme-7c.css").read_text(encoding="utf-8")

    assert "100%" in _css_rule(
        css, ".c7-head__actions"
    ), "i comandi non prendono più una riga propria"
    assert "flex-wrap: wrap" in _css_rule(
        css, ".c7-head"
    ), "senza `flex-wrap` sulla testata la riga dei comandi non va a capo"
