from __future__ import annotations
from typing import Dict, Optional, Any
import random
from .strategies.base import PairingStrategy


class PairingContext:
    """Execution context for pairing strategies with deterministic behavior support.

    Provides strategies with deterministic random number generation and stateful
    execution context. Essential for testing, debugging, and ensuring reproducible
    tournament rounds when needed (e.g., resolving disputes, validating algorithms).

    Features:
    - Deterministic RNG with optional seeding
    - Strategy-specific state storage
    - Context reset capabilities for multi-round tournaments

    Business Value:
        Tournament integrity requires reproducible results when investigating
        pairing decisions or testing algorithm changes.
    """

    def __init__(self, seed: Optional[int] = None):
        self.seed = seed
        self._rng = random.Random(seed)
        self._state: Dict[str, Any] = {}

    def get_rng(self) -> random.Random:
        """Get deterministic random number generator for reproducible
        pairing algorithms.

        Returns:
            Random instance seeded for deterministic behavior, or
            unseeded for normal operation
        """
        return self._rng

    def reset_seed(self, seed: Optional[int] = None) -> None:
        """Reset RNG with new seed."""
        self.seed = seed
        self._rng = random.Random(seed)
        self._state.clear()

    def get_state(self, key: str, default: Any = None) -> Any:
        """Get context state."""
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        """Set context state."""
        self._state[key] = value

    def clear_state(self) -> None:
        """Clear all context state."""
        self._state.clear()


class StrategyFactory:
    """Factory for creating isolated strategy instances with dependency injection.

    Implements the Factory pattern to create strategy instances with proper context
    injection and state isolation. Prevents strategy instances from sharing state
    across different tournament rounds or concurrent operations.

    Design Pattern: Factory + Dependency Injection
    """

    def __init__(self, registry: "EngineRegistry"):
        self._registry = registry

    def create(
        self, strategy_name: str, context: Optional[PairingContext] = None
    ) -> PairingStrategy:
        """Create strategy instance with optional context injection
        for deterministic behavior.

        Args:
            strategy_name: Identifier for the strategy to instantiate
            context: Optional execution context with seeding and state management

        Returns:
            Strategy instance ready for pairing generation,
            with context injected if supported
        """
        base_strategy = self._registry.get(strategy_name)

        # Clone strategy to avoid sharing state between instances
        strategy = self._clone_strategy(base_strategy)

        # Inject context if strategy supports it
        if context and hasattr(strategy, "set_context"):
            strategy.set_context(context)  # type: ignore[attr-defined]

        return strategy

    def _clone_strategy(self, strategy: PairingStrategy) -> PairingStrategy:
        """Clone strategy instance to prevent state sharing between operations.

        Current Implementation: Returns the same instance since strategies are designed
        to be stateless. Future versions may implement true cloning if stateful
        strategies are introduced.

        Args:
            strategy: Base strategy instance to clone

        Returns:
            Strategy instance (currently the same object, but this may change)
        """
        # For now, return same instance - strategies should be stateless
        # In future, could implement proper cloning if needed
        return strategy


class EngineRegistry:
    """Centralized registry for tournament pairing strategies with factory capabilities.

    Manages the lifecycle and discovery of all available matchmaking algorithms.
    Provides type-safe strategy lookup, dynamic instantiation with context injection,
    and comprehensive strategy metadata for UI and validation purposes.

    Features:
    - Dynamic strategy registration and discovery
    - Context-aware strategy instantiation via factory pattern
    - Conflict detection and prevention during registration
    - Comprehensive strategy listing with metadata

    Business Context:
        Pool tournaments require different pairing algorithms based on format,
        player count, and organizational preferences. This registry enables
        flexible tournament configuration while maintaining system consistency.
    """

    def __init__(self) -> None:
        self._strategies: Dict[str, PairingStrategy] = {}
        self._factory = StrategyFactory(self)

    def register(self, strategy: PairingStrategy) -> None:
        """Register a pairing strategy with conflict detection.

        Args:
            strategy: Strategy instance to register

        Raises:
            ValueError: If a strategy with the same name is already registered

        Business Logic:
            Strategy names must be unique to prevent configuration ambiguity
            and ensure predictable tournament behavior.
        """
        key = strategy.name.lower()
        if key in self._strategies:
            raise ValueError(f"Strategy già registrata: {strategy.name}")
        self._strategies[key] = strategy

    def get(self, name: str) -> PairingStrategy:
        """Retrieve registered strategy by name with case-insensitive lookup.

        Args:
            name: Strategy identifier (case-insensitive)

        Returns:
            Strategy instance ready for tournament pairing generation

        Raises:
            KeyError: If no strategy is registered with the given name
        """
        try:
            return self._strategies[name.lower()]
        except KeyError as exc:
            raise KeyError(f"Strategy non trovata: {name}") from exc

    def create_strategy(self, name: str, seed: Optional[int] = None) -> PairingStrategy:
        """Create strategy instance with optional deterministic seeding.

        Args:
            name: Strategy identifier to instantiate
            seed: Optional seed for deterministic behavior (testing, replay)

        Returns:
            Strategy instance with injected context for reproducible execution

        Business Value:
            Deterministic strategy creation enables tournament round replay
            for dispute resolution and algorithm validation.
        """
        context = PairingContext(seed) if seed is not None else None
        return self._factory.create(name, context)

    def list(self) -> Dict[str, PairingStrategy]:
        """List all registered strategies."""
        return self._strategies.copy()

    def available(self) -> list[str]:
        """Get list of available strategy names."""
        return sorted(self._strategies.keys())

    @property
    def factory(self) -> StrategyFactory:
        """Get strategy factory."""
        return self._factory
