from __future__ import annotations
from .registry import EngineRegistry
from .service import MatchmakingService
from .strategies.amalfi_adapter import AmalfiStrategy
from .bindings.amalfi_binding import validate_prova, propose_pairings

_registry = EngineRegistry()
_registry.register(
    AmalfiStrategy(validate_fn=validate_prova, propose_fn=propose_pairings)
)
_service = MatchmakingService(_registry)


def get_matchmaking_service() -> MatchmakingService:
    return _service


def get_registry() -> EngineRegistry:
    return _registry
