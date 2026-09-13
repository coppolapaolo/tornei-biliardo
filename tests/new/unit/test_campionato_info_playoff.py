"""La scheda informazioni del campionato dice quali playoff ci sono.

Il blocco leggeva `campionato.playoff_elite_enabled` e
`playoff_elite_participants`, che sono i campi del wizard e non colonne del
modello: su un oggetto `Campionato` erano sempre vuoti, e il blocco non
compariva mai. Trovato il 13/09/2026 mentre si segnava la zona playoff nella
classifica generale (canvas 7.1).
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from models.matchmaking.configuration import MatchmakingStrategy

pytestmark = pytest.mark.unit

TEMPLATE = "components/_campionato_details_info.html"


def _campionato(configurazioni):
    return SimpleNamespace(
        campionato_type="amalfi",
        created_at=datetime(2026, 9, 1, 20, 0),
        planned_gare_count=6,
        without_x=False,
        challenge_mode=False,
        is_active=True,
        playoff_configurations=configurazioni,
        default_venue=None,
        default_entry_fee=None,
        default_rounds_count=None,
        default_odd_policy=None,
        default_anti_rematch=None,
    )


def _cfg(nome, da, a, attiva=True):
    return SimpleNamespace(
        name=nome,
        positions_from=da,
        positions_to=a,
        max_participants=a - da + 1,
        is_active=attiva,
    )


def _render(app, campionato):
    with app.test_request_context():
        return app.jinja_env.get_template(TEMPLATE).render(
            campionato=campionato, MatchmakingStrategy=MatchmakingStrategy
        )


def test_le_configurazioni_attive_compaiono_con_le_posizioni(app):
    html = _render(
        app,
        _campionato(
            [
                _cfg("Playoff Elite", 1, 8),
                _cfg("Playoff Academy", 9, 14),
                _cfg("Vecchia", 1, 4, attiva=False),
            ]
        ),
    )
    assert "Playoff Elite" in html and "posizioni 1–8" in html
    assert "Playoff Academy" in html and "posizioni 9–14" in html
    assert "Vecchia" not in html


def test_senza_playoff_il_blocco_non_c_e(app):
    assert "fa-medal" not in _render(app, _campionato([]))
