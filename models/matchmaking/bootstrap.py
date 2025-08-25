from __future__ import annotations
from .registry import EngineRegistry
from .service import MatchmakingService
from .strategies.amalfi_adapter import AmalfiStrategy
from .strategies.round_robin import RoundRobinStrategy
from .strategies.direct_elimination import DirectEliminationStrategy
from .strategies.double_knockout import DoubleKnockoutStrategy
from .strategies.random_anti_rematch import RandomAntiRematchStrategy
from .bindings.amalfi_binding import validate_prova, propose_pairings

_registry = EngineRegistry()

# Register Amalfi strategy (existing)
_registry.register(
    AmalfiStrategy(validate_fn=validate_prova, propose_fn=propose_pairings)  # type: ignore
)

# Register new strategies
_registry.register(RoundRobinStrategy())
_registry.register(DirectEliminationStrategy())
_registry.register(DoubleKnockoutStrategy())
_registry.register(RandomAntiRematchStrategy())

_service = MatchmakingService(_registry)


def get_matchmaking_service() -> MatchmakingService:
    return _service


def get_registry() -> EngineRegistry:
    return _registry