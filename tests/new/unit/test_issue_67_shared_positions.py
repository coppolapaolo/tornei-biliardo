"""Regressione issue #67 — pari punti devono condividere la posizione.

`finalize_classification` assegnava le posizioni con `enumerate(..., 1)`,
quindi sempre progressive: due giocatori con gli stessi rack, che nessuno
spareggio doveva separare, comparivano come 7° e 8°. A pari merito l'ordine
di elencazione deve inoltre seguire l'estrazione, non il rowid.
"""

from __future__ import annotations

import pytest

from models.competition.spareggio_service import SpareggioService


def _rack_merit(x):
    """Chiave di merito di una gara RACK: rack totali, poi SSR."""
    return (-x["rack_totali"], -x["ssr_score"])


@pytest.mark.unit
class TestAssignSharedPositions:

    def test_issue_scenario_ties_share_seventh_place(self):
        """Scenario dell'issue: ROBERTO e PAOLO M a 3 rack sono entrambi 7°."""
        ordered = [
            {"user_id": 1, "rack_totali": 8, "ssr_score": -1},  # MATTEO Q
            {"user_id": 2, "rack_totali": 6, "ssr_score": -1},  # NICOLA
            {"user_id": 3, "rack_totali": 4, "ssr_score": 3},  # MARCO
            {"user_id": 4, "rack_totali": 4, "ssr_score": 2},  # LEONARDO
            {"user_id": 5, "rack_totali": 4, "ssr_score": 1},  # FLAVIO
            {"user_id": 6, "rack_totali": 4, "ssr_score": 0},  # LAURA B
            {"user_id": 7, "rack_totali": 3, "ssr_score": -1},  # PAOLO M
            {"user_id": 8, "rack_totali": 3, "ssr_score": -1},  # ROBERTO
        ]

        result = SpareggioService.assign_shared_positions(ordered, _rack_merit)
        positions = [pos for pos, _ in result]

        assert positions == [1, 2, 3, 4, 5, 6, 7, 7]

    def test_position_skips_after_a_tie(self):
        """Competition ranking: dopo due secondi si passa al quarto."""
        ordered = [
            {"user_id": 1, "rack_totali": 9, "ssr_score": -1},
            {"user_id": 2, "rack_totali": 5, "ssr_score": -1},
            {"user_id": 3, "rack_totali": 5, "ssr_score": -1},
            {"user_id": 4, "rack_totali": 2, "ssr_score": -1},
        ]

        positions = [
            pos
            for pos, _ in SpareggioService.assign_shared_positions(ordered, _rack_merit)
        ]

        assert positions == [1, 2, 2, 4]

    def test_ssr_separates_players_on_equal_racks(self):
        """Lo SSR resta parte del merito: chi lo vince sale davvero."""
        ordered = [
            {"user_id": 1, "rack_totali": 4, "ssr_score": 2},
            {"user_id": 2, "rack_totali": 4, "ssr_score": 1},
            {"user_id": 3, "rack_totali": 4, "ssr_score": 0},
        ]

        positions = [
            pos
            for pos, _ in SpareggioService.assign_shared_positions(ordered, _rack_merit)
        ]

        assert positions == [1, 2, 3]

    def test_all_tied_share_first_place(self):
        ordered = [
            {"user_id": 1, "rack_totali": 4, "ssr_score": -1},
            {"user_id": 2, "rack_totali": 4, "ssr_score": -1},
            {"user_id": 3, "rack_totali": 4, "ssr_score": -1},
        ]

        positions = [
            pos
            for pos, _ in SpareggioService.assign_shared_positions(ordered, _rack_merit)
        ]

        assert positions == [1, 1, 1]

    def test_empty_input(self):
        assert SpareggioService.assign_shared_positions([], _rack_merit) == []
