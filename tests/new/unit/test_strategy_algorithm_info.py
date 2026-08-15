"""Il riquadro "com'è fatto questo formato" segue il formato della gara.

Prima era un `if/else` binario — Random oppure Amalfi — e ogni altro formato
finiva sul ripiego Amalfi: su una gara a tabellone parlava di "formula salto"
e leggeva `gara.campionato.without_x`, che su una gara **standalone** non
esiste, quindi la pagina si rompeva del tutto.
"""

import pytest
from flask import render_template

pytestmark = pytest.mark.unit


class FakeMatch:
    def __init__(self, bracket_type=None, bracket_round=None, group=None, bye=False):
        self.bracket_type = bracket_type
        self.bracket_round = bracket_round
        self.bracket_group = group
        self.is_bye = bye
        self.status = "completed"


class FakeGara:
    def __init__(self, strategy, **kwargs):
        self.matchmaking_strategy = strategy
        self.separate_teammates = kwargs.get("separate_teammates", False)
        self.third_place_match = kwargs.get("third_place_match", False)
        self.rounds_count = 3
        self.campionato = None


def _render(app, gara, matches=None):
    with app.test_request_context():
        return render_template(
            "components/_strategy_algorithm_info.html",
            gara=gara,
            round_number=1,
            total_players=6,
            matches=matches
            or [
                FakeMatch("W", 1),
                FakeMatch("W", 1, bye=True),
                FakeMatch("W", 1),
                FakeMatch("W", 1),
            ],
        )


class TestDispatch:
    def test_eliminazione_diretta(self, app):
        pagina = _render(app, FakeGara("direct_elimination", third_place_match=True))

        assert "Eliminazione diretta" in pagina
        # La dimensione si legge dal tabellone persistito: 4 nodi = 8 posti.
        assert "8" in pagina
        assert "3°/4°" in pagina
        assert "salto" not in pagina.lower(), "ripiego Amalfi su una gara a tabellone"

    def test_doppio_ko(self, app):
        pagina = _render(app, FakeGara("double_knockout", separate_teammates=True))

        assert "Doppio KO" in pagina
        assert "ripescati" in pagina
        assert "compagni separati" in pagina

    def test_fase_a_gironi_riconosciuta(self, app):
        matches = [
            FakeMatch("W", 1, group=0),
            FakeMatch("W", 1, group=1),
            FakeMatch("W", 1, group=2),
        ]
        pagina = _render(app, FakeGara("double_knockout"), matches=matches)

        assert "3" in pagina
        assert "gironi" in pagina

    def test_random_invariato(self, app):
        pagina = _render(app, FakeGara("random"))
        assert "Strategia Random" in pagina


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
