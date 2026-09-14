"""Il conteggio delle gare di un campionato tiene la finale a parte.

Regola unica in `models/campionato/conteggio_gare.py` (SPECIFICHE.md,
«Campionati», nota del 2026-09-14): le gare regolari si contano, la gara di
playoff si aggiunge — «5 gare + finale». Qui la regola e il presidio sui
template che contavano `campionato.gare|length`, finale compresa.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from models.campionato.conteggio_gare import ConteggioGare, gare_regolari
from models.campionato.models import Campionato
from models.competition.models import Gara

RADICE = Path(__file__).resolve().parents[3]


def _gara(numero: int, *, playoff: bool = False) -> Gara:
    return Gara(
        name=f"Gara {numero}",
        number=numero,
        playoff_config_id=7 if playoff else None,
    )


def test_la_finale_non_e_una_gara_regolare():
    gare = [_gara(1), _gara(2), _gara(3, playoff=True)]

    assert [g.number for g in gare_regolari(gare)] == [1, 2]
    conteggio = ConteggioGare.da_gare(gare)
    assert (conteggio.regolari, conteggio.finali) == (2, 1)


def test_il_campionato_usa_la_stessa_regola():
    campionato = Campionato(name="Sociale")
    campionato.gare = [_gara(1), _gara(2, playoff=True)]

    assert campionato.conteggio_gare == ConteggioGare(regolari=1, finali=1)


@pytest.mark.parametrize(
    "regolari, finali, numero, gare",
    [
        (5, 0, "5", "5 gare"),
        (1, 0, "1", "1 gara"),
        (5, 1, "5 + finale", "5 gare + finale"),
        (6, 2, "6 + 2 finali", "6 gare + 2 finali"),
    ],
)
def test_i_testi(app, regolari, finali, numero, gare):
    conteggio = ConteggioGare(regolari=regolari, finali=finali)
    with app.test_request_context():
        assert conteggio.numero_testo == numero
        assert conteggio.gare_testo == gare


TEMPLATE_CON_CONTEGGIO = [
    "templates/components/_tessera_campionato.html",
    "templates/components/_unified_cards.html",
    "templates/components/_history_campionati_tab.html",
    "templates/components/_campionato_statistics.html",
    "templates/public/campionato_detail.html",
    "templates/public/campionatos_list.html",
]


@pytest.mark.parametrize("percorso", TEMPLATE_CON_CONTEGGIO)
def test_i_template_non_contano_la_finale_fra_le_gare(percorso):
    testo = (RADICE / percorso).read_text(encoding="utf-8")

    assert not re.search(r"gare\s*\|\s*length", testo), (
        f"{percorso}: `gare|length` conta anche la finale dei playoff; "
        "usa `campionato.conteggio_gare`"
    )
