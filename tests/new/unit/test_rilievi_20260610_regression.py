"""Regression per i rilievi del test manuale in produzione del 2026-06-10.

1. Card "In diretta ora" (guest): l'icona accanto a "Ai tavoli adesso" era
   una racchetta da ping pong (fa-table-tennis-paddle-ball) invece della
   biglia da biliardo (fa-8-ball, convenzione UI_CONVENTIONS.md).
"""

from types import SimpleNamespace

import pytest
from flask import render_template


@pytest.mark.unit
class TestIndexLiveIconRegression:
    """Rilievo 1: icona biliardo, non ping pong, in 'Ai tavoli adesso'."""

    def _live_card(self):
        gara = SimpleNamespace(
            id=1,
            name="Gara Test",
            discipline="palla_8",
            location="Sala Prova",
        )
        live_match = SimpleNamespace(
            table="Tavolo A",
            is_trio=False,
            player1="Alice",
            player1_score=2,
            player2="Bob",
            player2_score=1,
        )
        return SimpleNamespace(
            gara=gara,
            campionato=None,
            current_round=1,
            rounds_count=3,
            active_count=4,
            live_matches=[live_match],
        )

    def test_ai_tavoli_adesso_uses_billiard_icon(self, app):
        with app.test_request_context("/"):
            html = render_template(
                "components/_index_live.html", live_garas=[self._live_card()]
            )
        assert "table-tennis" not in html
        # fa-8-ball: una per la disciplina, una per "Ai tavoli adesso"
        assert html.count("fa-8-ball") == 2
