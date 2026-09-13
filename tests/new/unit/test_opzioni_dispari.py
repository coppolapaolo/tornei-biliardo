"""Le formule dei dispari hanno un nome solo, in ogni menu e in ogni pagina.

Ogni modulo aveva il suo: «Bye (riposo)» nel wizard del campionato, «Riposo
(punto gratis)» nella gara singola, «X (vinto a tavolino)» e «Match a 3
Giocatori» nel modal della nuova gara, «X con Challenge» — e nemmeno tradotto —
nella modifica del campionato. La pagina della gara, intanto, diceva «X a
tavolino». Adesso i menu passano da `opzioni_dispari`, che usa gli stessi nomi
di `etichetta_dispari`.
"""

import inspect
import re
from pathlib import Path

import pytest

from models.matchmaking.configuration import OddNumberPolicy
from utils.jinja import etichetta_dispari, opzioni_dispari

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "templates"


def test_le_voci_sono_i_nomi_della_pagina_gara(app):
    with app.test_request_context():
        voci = opzioni_dispari()
        assert [valore for valore, _ in voci] == [p.value for p in OddNumberPolicy]
        for valore, nome in voci:
            assert nome == etichetta_dispari(valore)
            assert not re.search(r"\bbye\b|\bmatch\b|challenge", nome, re.I)


def test_col_sistema_rack_la_x_semplice_non_c_e(app):
    """La X a tavolino semplice darebbe zero triangoli a chi riposa."""
    with app.test_request_context():
        rack = [valore for valore, _ in opzioni_dispari("RACK")]
        assert OddNumberPolicy.BYE.value not in rack
        assert OddNumberPolicy.BYE_WITH_CHALLENGE.value in rack
        assert len(opzioni_dispari("WINS")) == len(OddNumberPolicy)


def test_wizard_e_modifica_del_campionato_usano_la_fonte_unica():
    from routes.admin import campionato

    for vista in (campionato.wizard_step2, campionato.edit_campionato):
        sorgente = inspect.getsource(vista)
        assert "opzioni_dispari(" in sorgente, vista.__name__
        for vecchia in ("Bye", "Match a 3", "X con Challenge", "vinto a tavolino"):
            assert vecchia not in sorgente, (vista.__name__, vecchia)


def test_nessun_template_scrive_bye_in_una_stringa_italiana():
    colpevoli = [
        str(p.relative_to(TEMPLATES))
        for p in TEMPLATES.rglob("*.html")
        if re.search(r"""_\(\s*['"][^'"]*\b[Bb]ye\b""", p.read_text(encoding="utf-8"))
    ]
    assert colpevoli == []


def test_nessun_menu_dei_dispari_elenca_le_voci_a_mano():
    """Un `<option value="trio">` scritto a mano è un nome in più da allineare."""
    colpevoli = [
        str(p.relative_to(TEMPLATES))
        for p in TEMPLATES.rglob("*.html")
        if re.search(
            r"""<option\s+value=["'](bye|bye_with_challenge|trio)["']""",
            p.read_text(encoding="utf-8"),
        )
        or "Match a 3" in p.read_text(encoding="utf-8")
    ]
    assert colpevoli == []
