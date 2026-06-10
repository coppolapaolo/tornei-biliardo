"""
Module: models/classification/registry.py
Purpose: Registry for classification strategies with lazy initialization
Data Structures: ClassificationStrategyRegistry
Dependencies: typing, .strategies.base
"""

from typing import Dict, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .strategies.base import ClassificationStrategy, ClassificationScope


class ClassificationStrategyRegistry:
    """Registry for classification strategies.

    Provides centralized strategy discovery and instantiation.
    Mirrors the EngineRegistry pattern from matchmaking.
    """

    def __init__(self) -> None:
        self._strategies: Dict[str, "ClassificationStrategy"] = {}

    def register(self, strategy: "ClassificationStrategy") -> None:
        """Register a classification strategy.

        Args:
            strategy: Strategy instance to register

        Raises:
            ValueError: If strategy with same name already registered
        """
        key = strategy.name.lower()
        if key in self._strategies:
            raise ValueError(f"Strategy already registered: {strategy.name}")
        self._strategies[key] = strategy

    def get(self, name: str) -> "ClassificationStrategy":
        """Get a strategy by name.

        Args:
            name: Strategy name (case-insensitive)

        Returns:
            The registered strategy

        Raises:
            KeyError: If strategy not found
        """
        try:
            return self._strategies[name.lower()]
        except KeyError:
            available = ", ".join(self._strategies.keys())
            raise KeyError(
                f"Strategy not found: {name}. Available: {available}"
            ) from None

    def get_for_scope(
        self, scope: "ClassificationScope"
    ) -> List["ClassificationStrategy"]:
        """Get all strategies for a given scope.

        Args:
            scope: The classification scope (ROUND, GARA, CAMPIONATO, CHALLENGE)

        Returns:
            List of strategies that operate at this scope
        """
        return [s for s in self._strategies.values() if s.scope == scope]

    def list_all(self) -> Dict[str, "ClassificationStrategy"]:
        """Get all registered strategies.

        Returns:
            Copy of the strategies dictionary
        """
        return self._strategies.copy()

    def list_names(self) -> List[str]:
        """Get list of all registered strategy names.

        Returns:
            List of strategy names
        """
        return list(self._strategies.keys())


# Global registry instance (lazily initialized)
_registry: Optional[ClassificationStrategyRegistry] = None


def get_classification_registry() -> ClassificationStrategyRegistry:
    """Get or create the global classification registry.

    Uses lazy initialization to avoid import cycles.
    Automatically bootstraps with all built-in strategies.

    Returns:
        The global ClassificationStrategyRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ClassificationStrategyRegistry()
        _bootstrap_registry(_registry)
    return _registry


def _bootstrap_registry(registry: ClassificationStrategyRegistry) -> None:
    """Register all built-in strategies.

    Called once during lazy initialization.
    Import strategies here to avoid circular imports.
    """
    # Round strategies
    from .strategies.round_strategies import (
        AmalfiRoundClassificationStrategy,
        RandomRoundClassificationStrategy,
    )

    registry.register(AmalfiRoundClassificationStrategy())
    registry.register(RandomRoundClassificationStrategy())

    # Gara strategies
    from .strategies.gara_strategies import (
        AmalfiGaraClassificationStrategy,
        RandomGaraClassificationStrategy,
    )

    registry.register(AmalfiGaraClassificationStrategy())
    registry.register(RandomGaraClassificationStrategy())

    # Campionato strategies
    from .strategies.campionato_strategies import (
        AmalfiCampionatoClassificationStrategy,
        RandomCampionatoClassificationStrategy,
        PointBasedCampionatoClassificationStrategy,
    )

    registry.register(AmalfiCampionatoClassificationStrategy())
    registry.register(RandomCampionatoClassificationStrategy())
    registry.register(PointBasedCampionatoClassificationStrategy())

    # Challenge strategies
    from .strategies.challenge_strategies import ChallengeClassificationStrategy

    registry.register(ChallengeClassificationStrategy())


def reset_registry() -> None:
    """Reset the global registry (for testing).

    This clears the global registry so it will be re-bootstrapped
    on next access. Useful for tests that need fresh state.
    """
    global _registry
    _registry = None


__all__ = [
    "ClassificationStrategyRegistry",
    "get_classification_registry",
    "reset_registry",
]
