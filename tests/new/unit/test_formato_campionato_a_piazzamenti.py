"""Il campionato a piazzamenti non nomina un formato che le serate non hanno.

La testata di «Serate del lunedì» diceva «Amalfi · In corso» perché leggeva
il `campionato_type`, cioè il formato che il campionato **propone** alle gare
nuove; ma a piazzamenti ogni serata ha il suo (ADR-080), e quelle a gironi
non sono Amalfi. Testata, lista dei campionati, tessera, cronologia e
pagina pubblica fanno ora la stessa domanda:
`piazzamenti.nome_del_formato`.

E nella classifica generale a piazzamenti la colonna «Diff» mostrava la
differenza triangoli sommata, che lì non decide niente (ADR-080, #647): sembrava
lo spareggio, e lo spareggio sono i piazzamenti.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from models.campionato.piazzamenti import nome_del_formato
from models.classification.campionato_classification import ClassificationService
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import ClassificationSystem

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "templates"


def _campionato(tipo: str, sistema: str | None) -> SimpleNamespace:
    return SimpleNamespace(campionato_type=tipo, default_classification_system=sistema)


def test_a_piazzamenti_il_formato_e_a_piazzamenti(app):
    campionato = _campionato(
        MatchmakingStrategy.AMALFI.value, ClassificationSystem.POSITION.value
    )
    with app.test_request_context():
        assert nome_del_formato(campionato) == "A piazzamenti"


def test_un_campionato_a_tabellone_di_prima_e_a_piazzamenti(app):
    campionato = _campionato(MatchmakingStrategy.DIRECT_ELIMINATION.value, None)
    with app.test_request_context():
        assert nome_del_formato(campionato) == "A piazzamenti"


def test_sommando_i_totali_resta_la_formula_proposta(app):
    campionato = _campionato(
        MatchmakingStrategy.AMALFI.value, ClassificationSystem.WINS.value
    )
    with app.test_request_context():
        assert nome_del_formato(campionato) == "Amalfi"


def test_il_filtro_delle_pagine_e_la_stessa_domanda(app):
    assert app.jinja_env.filters["formato_campionato"] is nome_del_formato


def test_nessuna_pagina_nomina_il_tipo_del_campionato_come_formato():
    """Il wizard e i moduli scelgono il tipo proposto: lì il tipo è il tipo."""
    esclusi = {"admin/campionato_wizard_step2.html"}
    colpevoli = [
        str(p.relative_to(TEMPLATES))
        for p in TEMPLATES.rglob("*.html")
        if str(p.relative_to(TEMPLATES)) not in esclusi
        and "campionato_type|nome_formula" in p.read_text(encoding="utf-8")
    ]
    assert not colpevoli, "usa il filtro `formato_campionato`: " + ", ".join(colpevoli)


def test_la_classifica_dei_punti_posizione_e_la_stessa_domanda():
    a_piazzamenti = _campionato(
        MatchmakingStrategy.ROUND_ROBIN.value, ClassificationSystem.POSITION.value
    )
    sommando = _campionato(
        MatchmakingStrategy.ROUND_ROBIN.value, ClassificationSystem.WINS.value
    )
    assert ClassificationService.uses_position_points(a_piazzamenti) is True
    assert ClassificationService.uses_position_points(sommando) is False


def test_a_piazzamenti_la_classifica_generale_non_mostra_la_differenza():
    testo = (
        TEMPLATES / "components" / "_campionato_general_classification.html"
    ).read_text(encoding="utf-8")
    rami = re.findall(
        r"\{% elif (?:classification_sys|sys) == ClassificationSystem\.POSITION %\}"
        r"(.*?)\{% elif",
        testo,
        flags=re.S,
    )
    # Quattro rami: la testata e la riga (macro comuni alla fascia della
    # finale playoff), i numeri del campionato sotto il nome, e la nota.
    assert len(rami) == 4
    for ramo in rami:
        assert "Diff" not in ramo
        assert "total_rack_difference" not in ramo
