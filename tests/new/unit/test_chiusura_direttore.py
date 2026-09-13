"""Spareggio e gara conclusa per chi dirige, senza database (canvas 4.x e 5.x).

I componenti si rendono con righe finte: il podio nei colori delle medaglie,
le pastiglie SSR e «pari» in classifica, gli stepper dei punti SSR con il
campo che `saveSsrGroup` legge.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.matchmaking.configuration import MatchmakingStrategy

pytestmark = pytest.mark.unit


def _riga(nome, pos, uid, prev=None, vinte=1, diff=0):
    return SimpleNamespace(
        user=SimpleNamespace(username=nome),
        user_id=uid,
        position=pos,
        previous_position=prev,
        matches_won=vinte,
        rack_difference=diff,
        racks_won=None,
        is_rack_ranking=False,
        is_position_ranking=False,
        ranking_rack_value=diff,
        total_racks_value=0,
    )


def _render(app, template, **ctx):
    with app.test_request_context():
        return app.jinja_env.get_template(template).render(**ctx)


def test_il_podio_mette_il_primo_al_centro_con_le_medaglie(app):
    righe = [_riga("rossi", 1, 1), _riga("galli", 2, 2), _riga("bianchi", 3, 3)]
    html = _render(
        app, "direttore/_podio.html", classification=righe, ssr_scores_map={3: 4}
    )
    assert html.index("galli") < html.index("rossi") < html.index("bianchi")
    assert "c7-podio-finale__avatar--oro" in html
    assert (
        "c7-podio-finale__avatar--argento" in html
        and "c7-podio-finale__avatar--bronzo" in html
    )
    # Il terzo posto l'ha deciso lo spareggio, e il numero dice come: senza,
    # «SSR» non spiega chi l'ha vinto (rilievo del 2026-09-13).
    assert "3° · SSR 4" in html


def test_la_classifica_finale_ha_medaglie_e_pastiglia_ssr(app):
    righe = [
        _riga("rossi", 1, 1, prev=1),
        _riga("bianchi", 3, 3, prev=4),
        _riga("ferrari", 4, 4, prev=3),
    ]
    html = _render(
        app,
        "direttore/_classifica.html",
        classification=righe,
        round_number=4,
        gara=SimpleNamespace(matchmaking_strategy="amalfi"),
        MatchmakingStrategy=MatchmakingStrategy,
        ssr_scores_map={3: 4, 4: 2},
        medaglie=True,
        titolo_classifica="Classifica finale",
    )
    assert "Classifica finale" in html
    assert "c7-pos c7-pos--lg c7-classifica__medaglia c7-pos--1" in html
    # La pastiglia porta i punti: è quel che spiega l'ordine fra i parimerito.
    assert ">SSR 4<" in html and ">SSR 2<" in html
    assert "dopo il turno 3" in html


def test_i_parimerito_aperti_hanno_la_pastiglia_pari(app):
    righe = [_riga("rossi", 1, 1), _riga("bianchi", 3, 3), _riga("ferrari", 3, 4)]
    html = _render(
        app,
        "direttore/_classifica.html",
        classification=righe,
        round_number=4,
        gara=SimpleNamespace(matchmaking_strategy="amalfi"),
        MatchmakingStrategy=MatchmakingStrategy,
        ssr_scores_map={},
        pari_ids=[3, 4],
        nota_testa="fino al 3° posto",
    )
    assert html.count(">pari<") == 2
    assert "fino al 3° posto" in html


def _gruppi(punti_a=None, punti_b=None):
    return [
        {
            "position": 3,
            "needs_distinct_top": 1,
            "players": [
                {"user_id": 3, "username": "bianchi", "current_ssr_score": punti_a},
                {"user_id": 4, "username": "ferrari", "current_ssr_score": punti_b},
            ],
        }
    ]


def test_i_punti_ssr_si_segnano_con_gli_stepper(app):
    html = _render(
        app,
        "components/_ssr_section.html",
        ssr_groups=_gruppi(),
        has_unresolved_tiebreakers=True,
        can_edit_ssr=True,
        gara=SimpleNamespace(id=7),
    )
    assert "Parimerito per il 3° posto" in html
    assert html.count("passoSsr(this, 1)") == 2
    # Il campo che `saveSsrGroup` legge, con i suoi attributi.
    assert html.count('class="ssr-group-input c7-ssr__valore c7-num"') == 2
    assert 'data-group-position="3"' in html and 'data-needs-distinct-top="1"' in html
    assert "saveSsrGroup(7, 3, this)" in html


def test_a_gara_conclusa_i_punti_ssr_sono_in_sola_lettura(app):
    html = _render(
        app,
        "components/_ssr_section.html",
        ssr_groups=_gruppi(4, 2),
        has_unresolved_tiebreakers=False,
        can_edit_ssr=False,
        gara=SimpleNamespace(id=7),
    )
    assert "passoSsr" not in html and "ssr-group-input" not in html
    assert ">4<" in html and ">2<" in html
