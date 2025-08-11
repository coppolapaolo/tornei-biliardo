from __future__ import annotations
from models.matchmaking.registry import EngineRegistry
from models.matchmaking.service import MatchmakingService
from models.matchmaking.strategies.base import Pairing, ValidationResult


class _FakeStrategy:
    name = "Fake"

    def __init__(self, roster: list[int]) -> None:
        self.roster = roster

    def validate(self, prova: object) -> ValidationResult:
        return ValidationResult(
            ok=len(self.roster) >= 2,
            messages=("min 2 players",) if len(self.roster) < 2 else (),
        )

    def propose(self, prova: object, round_number: int):
        it = iter(self.roster)
        res: list[Pairing] = []
        for a in it:
            try:
                b = next(it)
            except StopIteration:
                res.append(
                    Pairing(players=(a,), round_number=round_number, is_bye=True)
                )
                break
            res.append(Pairing(players=(a, b), round_number=round_number))
        return res


def test_registry_and_service_contract():
    registry = EngineRegistry()
    strategy = _FakeStrategy([1, 2, 3])
    registry.register(strategy)
    svc = MatchmakingService(registry)
    pairings = svc.run(strategy_name="Fake", prova=object(), round_number=1)
    assert len(pairings) == 2
    assert pairings[0].players == (1, 2)
    assert pairings[1].players == (3,)
    assert pairings[1].is_bye is True
