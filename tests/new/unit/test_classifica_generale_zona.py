"""La classifica generale in righe, con la zona playoff (canvas 7.1 e 7.3).

Il componente si rende con righe finte: etichetta sopra la zona, barra sulle
righe dentro, «Fuori dai playoff» dopo l'ultima, colonne dal sistema di
classifica (ADR-047).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.playoff.zona import ZonaPlayoff
from models.status_enum import ClassificationSystem

pytestmark = pytest.mark.unit

TEMPLATE = "components/_campionato_general_classification.html"


def _righe(n=4):
    return [
        (
            pos,
            {
                "user_id": pos,
                "username": f"gioc{pos}",
                "total_matches_won": 5 - pos,
                "total_rack_difference": 4 - 2 * pos,
                "total_racks_won": 20 - pos,
                "total_spot_shot_wins": 0,
                "total_points": 10 - pos,
                "participations": 3,
                "previous_position": pos + 1 if pos % 2 else pos - 1,
            },
        )
        for pos in range(1, n + 1)
    ]


def _render(app, righe, *, zone=None, sistema=ClassificationSystem.WINS):
    with app.test_request_context():
        return app.jinja_env.get_template(TEMPLATE).render(
            campionato=SimpleNamespace(classification_system=sistema),
            general_classification=righe,
            last_completed_gara_number=2,
            zone_playoff=zone or [],
            ClassificationSystem=ClassificationSystem,
        )


def test_la_zona_ha_etichetta_barra_e_fuori(app):
    zona = ZonaPlayoff("Finale", 2, frozenset({1, 2}), inviti_partiti=False)
    html = _render(app, _righe(), zone=[zona])

    assert "Zona playoff · primi 2" in html
    assert html.count("c7-cg__riga--zona") == 2
    fuori = html.index("Fuori dai playoff")
    assert html.index("gioc2") < fuori < html.index("gioc3")
    assert "inviti partiti" not in html


def test_dopo_gli_inviti_l_etichetta_lo_dice(app):
    zona = ZonaPlayoff("Finale", 2, frozenset({1, 3}), inviti_partiti=True)
    html = _render(app, _righe(), zone=[zona])

    assert "inviti partiti" in html
    # Chi e' entrato al posto di chi ha rifiutato ha la barra, anche se
    # in classifica viene dopo.
    riga3 = html.split("gioc3")[0].rsplit("c7-classifica__riga", 1)[1]
    assert "c7-cg__riga--zona" in riga3


def test_senza_zona_non_ci_sono_etichette(app):
    html = _render(app, _righe())
    assert "Zona playoff" not in html and "Fuori dai playoff" not in html
    assert "c7-cg__riga--zona" not in html


def test_le_colonne_seguono_il_sistema(app):
    a_rack = _render(app, _righe(), sistema=ClassificationSystem.RACK)
    assert ">Triangoli<" in a_rack and ">SSR<" in a_rack
    a_vittorie = _render(app, _righe())
    assert ">Vinte<" in a_vittorie and ">Diff<" in a_vittorie and ">Gare<" in a_vittorie


def test_oltre_le_prime_dieci_le_righe_restano_nascoste(app):
    html = _render(app, _righe(12))
    assert "Tutti (12)" in html
    assert html.count('data-oltre="1" hidden') == 2
