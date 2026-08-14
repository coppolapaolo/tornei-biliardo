"""Regressione issue #68 — l'etichetta "Pos. Prec." era ambigua.

Nella classifica della singola gara la posizione precedente è quella del
turno prima DENTRO la gara; nella classifica generale del campionato è
quella della prova precedente. La stessa etichetta per le due cose ha fatto
leggere come bug un dato corretto: nella prima prova di un campionato la
colonna risulta valorizzata (dal turno precedente) e sembrava dover essere
vuota. Il dato resta, l'etichetta si specializza.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[3] / "templates" / "components"

GARA_CLASSIFICATION_VIEWS = [
    "_detailed_classification.html",
    "_classification_mobile.html",
]


@pytest.mark.unit
@pytest.mark.parametrize("template_name", GARA_CLASSIFICATION_VIEWS)
def test_gara_views_qualify_the_previous_position_label(template_name):
    """Desktop e mobile dicono "Turno": è la posizione al turno precedente."""
    content = (TEMPLATES / template_name).read_text(encoding="utf-8")

    # Il redesign 7c ha riscritto le etichette ("Turno prec." in tabella,
    # "Turno precedente" nella card): quello che conta e' che la parola
    # "turno" resti attaccata alla posizione precedente, non la stringa
    # esatta di allora.
    assert re.search(r"Turno prec", content, re.IGNORECASE), (
        f"{template_name} deve qualificare la colonna come posizione del "
        "TURNO precedente (issue #68)"
    )


@pytest.mark.unit
@pytest.mark.parametrize("template_name", GARA_CLASSIFICATION_VIEWS)
def test_gara_views_drop_the_ambiguous_label(template_name):
    """L'etichetta nuda non deve sopravvivere accanto a quella qualificata."""
    content = (TEMPLATES / template_name).read_text(encoding="utf-8")

    for ambiguous in ("'Pos. Prec.'", "'Pos. Prec:'", ">Pos. Prec."):
        assert ambiguous not in content, (
            f"{template_name} usa ancora l'etichetta ambigua {ambiguous} " "(issue #68)"
        )


@pytest.mark.unit
def test_campionato_classification_is_untouched():
    """La classifica generale mantiene la sua colonna: lì "precedente" è la
    prova precedente, e la sua intestazione ("Trend") non è in conflitto."""
    content = (TEMPLATES / "_campionato_general_classification.html").read_text(
        encoding="utf-8"
    )

    assert "previous_position" in content
    assert "Pos. Turno Prec" not in content
