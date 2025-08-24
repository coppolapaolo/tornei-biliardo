from __future__ import annotations
from .registry import EngineRegistry
from .service import MatchmakingService
from .strategies.amalfi_adapter import AmalfiStrategy
from .strategies.round_robin import RoundRobinPairingStrategy
from .strategies.direct_elimination import DirectEliminationPairingStrategy
from .strategies.double_knockout import DoubleKnockoutPairingStrategy
from .strategies.random_anti_rematch import RandomAntiRematchPairingStrategy
from .bindings.amalfi_binding import validate_prova, propose_pairings

_registry = EngineRegistry()

# Register Amalfi strategy (existing)
_registry.register(
    AmalfiStrategy(validate_fn=validate_prova, propose_fn=propose_pairings)
)

# Register new strategies
_registry.register(RoundRobinPairingStrategy())
_registry.register(DirectEliminationPairingStrategy())
_registry.register(DoubleKnockoutPairingStrategy())
_registry.register(RandomAntiRematchPairingStrategy())

_service = MatchmakingService(_registry)


def get_matchmaking_service() -> MatchmakingService:
    return _service


def get_registry() -> EngineRegistry:
    return _registry
