"""La classifica per chi dirige: frecce di tendenza e colonne del sistema.

Canvas 3.5 e 3.6. Il componente `direttore/_classifica.html` legge solo le
righe e la gara, quindi si rende senza database: la route ricalcola le righe
del turno a ogni visita, e righe seminate in un test d'integrazione verrebbero
sostituite prima di arrivare al template.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.matchmaking.configuration import MatchmakingStrategy

pytestmark = pytest.mark.unit

TEMPLATE = "direttore/_classifica.html"


def _riga(username, pos, prev, vinte, diff, racks, *, rack=False):
    return SimpleNamespace(
        user=SimpleNamespace(username=username),
        user_id=hash(username) % 1000,
        position=pos,
        previous_position=prev,
        matches_won=vinte,
        rack_difference=diff,
        racks_won=racks,
        is_rack_ranking=rack,
        ranking_rack_value=racks if rack else diff,
        total_racks_value=racks,
    )


def _render(app, righe, *, round_number=1, strategy="amalfi"):
    gara = SimpleNamespace(matchmaking_strategy=strategy)
    with app.test_request_context():
        return app.jinja_env.get_template(TEMPLATE).render(
            classification=righe,
            round_number=round_number,
            gara=gara,
            MatchmakingStrategy=MatchmakingStrategy,
            ssr_scores_map={},
        )


def _riga_di(html, username):
    return html.split(username)[0].rsplit("c7-classifica__riga", 1)[1]


def test_la_freccia_confronta_con_il_turno_prima(app):
    html = _render(
        app,
        [
            _riga("cl_su", 1, 3, 2, 4, 9),
            _riga("cl_giu", 2, 1, 1, -1, 6),
            _riga("cl_pari", 3, 3, 0, -3, 3),
            _riga("cl_nuovo", 4, None, 0, -3, 3),
        ],
    )
    assert 'aria-label="sale di 2"' in _riga_di(html, "cl_su")
    assert 'aria-label="scende di 1"' in _riga_di(html, "cl_giu")
    assert 'aria-label="stabile"' in _riga_di(html, "cl_pari")
    assert 'aria-label="primo turno"' in _riga_di(html, "cl_nuovo")


def test_a_vittorie_le_colonne_sono_vinte_e_diff(app):
    html = _render(app, [_riga("cl_a", 1, 1, 2, 4, 9)])
    assert ">Vinte<" in html and ">Diff<" in html
    assert "+4" in html
    assert "vale una vittoria e zero differenza" in html
    assert "dopo il turno 1" in html


def test_a_rack_le_colonne_sono_vinti_e_persi(app):
    """cl_su: 9 triangoli vinti con differenza +4, quindi 5 persi."""
    html = _render(app, [_riga("cl_su", 1, 1, 2, 4, 9, rack=True)])
    assert ">Vinti<" in html and ">Persi<" in html
    riga = html.split("cl_su")[1]
    assert ">9<" in riga and ">5<" in riga
    assert "vale zero triangoli" in html


def test_oltre_le_prime_sei_le_righe_restano_nascoste(app):
    righe = [_riga(f"cl_{n}", n, n, 0, 0, 0) for n in range(1, 9)]
    html = _render(app, righe)
    assert "Tutti (8)" in html
    assert html.count("c7-classifica__riga--oltre") == 2


def test_con_la_formula_casuale_e_complessiva(app):
    html = _render(
        app, [_riga("cl_a", 1, None, 1, 1, 1)], round_number=0, strategy="random"
    )
    assert "complessiva" in html
