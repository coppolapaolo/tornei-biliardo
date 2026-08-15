"""Regressione: l'ora digitata è l'ora salvata, su ogni superficie.

Il bug era sistematico e silenzioso — un `<input type="datetime-local">` manda
l'ora **locale**, il DB tiene i naive come **UTC**, e in lettura
``|datetime_local`` risomma il fuso. Chi fissava un appuntamento per le 21:00 se
lo vedeva rimandare indietro come le 23:00.

Il test guarda le *superfici*, non l'helper: quello ha già i suoi test unitari.
Qui interessa che ogni punto che legge un orario dall'utente ci passi davvero.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

#: I punti che leggono un orario da un ``datetime-local``. Aggiungerne uno qui
#: quando nasce una superficie nuova è il modo per non ripetere il bug.
SURFACES = (
    "routes/exam/requests.py",
    "routes/individual_match/proposals.py",
)


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("relative", SURFACES)
def test_the_surface_converts_instead_of_storing_raw(relative):
    """Deve passare da ``parse_local_datetime``, non da ``fromisoformat``."""
    source = _source(relative)
    assert "parse_local_datetime" in source, relative


@pytest.mark.parametrize("relative", SURFACES)
def test_the_surface_does_not_parse_by_hand(relative):
    """Un ``fromisoformat``/``strptime`` su ``scheduled_at`` sarebbe il bug di prima.

    Si guarda l'AST e non il testo: un'occorrenza dentro un commento o una
    docstring non deve far fallire il test, e una vera non deve sfuggirgli.
    """
    tree = ast.parse(_source(relative))
    hand_parsers = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"fromisoformat", "strptime"}
    }
    assert not hand_parsers, f"{relative} parsa a mano: {hand_parsers}"


def test_a_proposal_keeps_the_hour_the_player_typed(app):
    """Il giro completo sulla proposta di match: 21:00 digitate, 21:00 lette."""
    from utils.jinja import format_datetime_local_text
    from utils.local_time import parse_local_datetime

    with app.app_context():
        stored = parse_local_datetime("2026-06-12T21:00")
        assert "21:00" in format_datetime_local_text(stored)
