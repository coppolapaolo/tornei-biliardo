"""Presidi statici sulla tessera condivisa (canvas «Tessera», 2026-09-10).

Tre scelte che nessun test di comportamento vede, perché sono forma:

* sulle tessere **nessun pulsante piccolo** (`btn-sm`, 40px): sono difficili
  da tappare, e su una tessera si tappa;
* le medaglie del podio hanno i **loro token** — oro, argento, bronzo — e
  non il tono dell'accento: tre chip uguali non dicono chi ha vinto;
* la riga di chi guarda in classifica è **scura** (`is-me`), senza un «sei
  tu» scritto accanto al nome.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TESSERE = [
    ROOT / "templates" / "components" / "_tessera_gara.html",
    ROOT / "templates" / "components" / "_tessera_campionato.html",
    ROOT / "templates" / "components" / "_separated_dashboard_content.html",
]


def _senza_commenti(sorgente: str) -> str:
    return re.sub(r"\{#.*?#\}", "", sorgente, flags=re.S)


@pytest.mark.unit
@pytest.mark.parametrize("template", TESSERE, ids=lambda p: p.name)
def test_sulle_tessere_non_ci_sono_pulsanti_piccoli(template: Path):
    assert "btn-sm" not in _senza_commenti(template.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_le_medaglie_hanno_i_loro_token():
    tokens = (ROOT / "static" / "css" / "tokens-7c.css").read_text(encoding="utf-8")
    for nome in ("--c7-oro", "--c7-argento", "--c7-bronzo"):
        assert f"{nome}:" in tokens, nome
        assert f"{nome}-ink:" in tokens, nome
    tema = (ROOT / "static" / "css" / "theme-7c.css").read_text(encoding="utf-8")
    for pos, token in ((1, "oro"), (2, "argento"), (3, "bronzo")):
        regola = re.search(r"\.c7-medal--%d\s*\{([^}]*)\}" % pos, tema)
        assert regola, pos
        assert f"var(--c7-{token})" in regola.group(1)


@pytest.mark.unit
def test_la_propria_riga_e_scura_e_non_dice_sei_tu():
    tema = (ROOT / "static" / "css" / "theme-7c.css").read_text(encoding="utf-8")
    regola = re.search(r"\.c7-tessera__row\.is-me\s*\{([^}]*)\}", tema)
    assert regola and "var(--c7-accent)" in regola.group(1)
    campionato = _senza_commenti(TESSERE[1].read_text(encoding="utf-8"))
    assert "is-me" in campionato
    assert "sei tu" not in campionato.lower()


@pytest.mark.unit
def test_il_riquadro_della_partita_e_il_bersaglio():
    """Niente «Gioca la tua partita»: il riquadro porta alla partita."""
    gara = _senza_commenti(TESSERE[0].read_text(encoding="utf-8"))
    assert "Gioca la tua partita" not in gara
    riquadro = re.search(r'<a class="c7-inset c7-inset--go" href="([^"]*)"', gara)
    assert riquadro and "admin.match.match_detail" in riquadro.group(1)
