import pytest
from models.matchmaking.registry import EngineRegistry
from models.matchmaking.service import MatchmakingService
from models.matchmaking.strategies.amalfi_adapter import AmalfiStrategy


@pytest.mark.xfail(reason="Binding al legacy engine non ancora cablato nel repo")
def test_amalfi_adapter_smoke():
    def _validate(_prova):
        return True, ()

    def _propose(_prova, _round):
        return [(10, 20), (30,)]  # match e bye

    registry = EngineRegistry()
    registry.register(AmalfiStrategy(validate_fn=_validate, propose_fn=_propose))
    svc = MatchmakingService(registry)

    pairings = svc.run(strategy_name="Amalfi", prova=object(), round_number=1)
    assert [p.players for p in pairings] == [(10, 20), (30,)]
