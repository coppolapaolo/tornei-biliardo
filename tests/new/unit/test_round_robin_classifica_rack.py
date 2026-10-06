"""Il girone all'italiana con sistema RACK si ordina sui triangoli vinti.

Bug (esplorazione per i gironi multipli, 2026-10-06) —
`StrategyBasedClassificationService.get_strategy_for_gara`:

per ogni gara round robin restituiva `round_robin_round`, che ordina per
vittorie e differenza rack, **prima** di guardare il sistema di classifica.
Una gara round robin RACK — combinazione ammessa da `STRATEGY_CONSTRAINTS` —
si ordinava quindi come una WINS: chi aveva vinto più triangoli ma meno
partite finiva sotto. Il sistema di classifica decide come si ordina, la
strategia di abbinamento come si formano le partite (ADR-047).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.classification.gara_classification import (
    StrategyBasedClassificationService,
)
from models.classification.strategies.base import PlayerScore
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import ClassificationSystem

pytestmark = pytest.mark.unit


def _gara(sistema: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        matchmaking_strategy=MatchmakingStrategy.ROUND_ROBIN.value,
        classification_system=sistema,
    )


def _ordine(sistema: str) -> list[int]:
    strategy = StrategyBasedClassificationService().get_strategy_for_gara(
        _gara(sistema)
    )
    # 1 ha vinto due partite di misura, 2 una sola ma con molti più triangoli.
    scores = [
        PlayerScore(
            player_id=1, matches_won=2, racks_won=6, racks_lost=4, rack_difference=2
        ),
        PlayerScore(
            player_id=2, matches_won=1, racks_won=9, racks_lost=3, rack_difference=6
        ),
    ]
    result = strategy.calculate(scores=scores, context={"round_number": 3})
    return [entry.player_id for entry in result.entries]


def test_round_robin_rack_ordina_sui_triangoli_vinti():
    assert _ordine(ClassificationSystem.RACK.value) == [2, 1]


def test_round_robin_wins_ordina_sulle_vittorie():
    assert _ordine(ClassificationSystem.WINS.value) == [1, 2]
