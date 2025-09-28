"""Matchmaking system bootstrap and dependency injection setup.

Centralizes the initialization of the matchmaking system with all available strategies.
Provides singleton access to configured services while maintaining proper dependency
injection patterns for testability and system modularity.

Bootstrap Process:
1. Initialize strategy registry
2. Register all available pairing algorithms
3. Create matchmaking service with configured registry
4. Provide global access points for application integration

Design Patterns: Singleton + Factory + Dependency Injection
"""

from __future__ import annotations
from .registry import EngineRegistry
from .service import MatchmakingService
from .strategies.amalfi import AmalfiStrategy
from .strategies.round_robin import RoundRobinStrategy
from .strategies.direct_elimination import DirectEliminationStrategy
from .strategies.double_knockout import DoubleKnockoutStrategy
from .strategies.random_anti_rematch import RandomAntiRematchStrategy

# Global strategy registry with all available tournament pairing algorithms
_registry = EngineRegistry()

# Register pure Amalfi strategy
_registry.register(AmalfiStrategy())

# Register modern strategy implementations with full Strategy pattern support
_registry.register(RoundRobinStrategy())  # All-play-all tournament format
_registry.register(DirectEliminationStrategy())  # Single knockout brackets
_registry.register(DoubleKnockoutStrategy())  # Winners + losers brackets
_registry.register(RandomAntiRematchStrategy())  # Casual tournaments with variety

# Global matchmaking service instance with fully configured strategy registry
_service = MatchmakingService(_registry)


def get_matchmaking_service() -> MatchmakingService:
    """Get the configured matchmaking service singleton.

    Returns:
        MatchmakingService instance with all strategies registered and ready for use

    Usage:
        Primary access point for tournament directors and application logic
        to generate pairings using any available strategy.
    """
    return _service


def get_registry() -> EngineRegistry:
    """Get the strategy registry for direct strategy access and management.

    Returns:
        EngineRegistry containing all registered pairing strategies

    Usage:
        Lower-level access for strategy introspection, testing,
        and advanced configuration scenarios.
    """
    return _registry
