from __future__ import annotations
from typing import Dict, Optional, Any
import random
from .strategies.base import PairingStrategy


class PairingContext:
    """Context for pairing strategies with seed management and state."""
    
    def __init__(self, seed: Optional[int] = None):
        self.seed = seed
        self._rng = random.Random(seed)
        self._state: Dict[str, Any] = {}
    
    def get_rng(self) -> random.Random:
        """Get deterministic RNG instance."""
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
    """Factory for creating strategy instances with context injection."""
    
    def __init__(self, registry: 'EngineRegistry'):
        self._registry = registry
    
    def create(self, strategy_name: str, context: Optional[PairingContext] = None) -> PairingStrategy:
        """Create strategy instance with injected context."""
        base_strategy = self._registry.get(strategy_name)
        
        # Clone strategy to avoid sharing state between instances
        strategy = self._clone_strategy(base_strategy)
        
        # Inject context if strategy supports it
        if context and hasattr(strategy, 'set_context'):
            strategy.set_context(context)
        
        return strategy
    
    def _clone_strategy(self, strategy: PairingStrategy) -> PairingStrategy:
        """Clone strategy to create new instance."""
        # For now, return same instance - strategies should be stateless
        # In future, could implement proper cloning if needed
        return strategy


class EngineRegistry:
    """Enhanced registry delle strategie di pairing con Factory pattern."""

    def __init__(self) -> None:
        self._strategies: Dict[str, PairingStrategy] = {}
        self._factory = StrategyFactory(self)

    def register(self, strategy: PairingStrategy) -> None:
        """Register strategy in registry."""
        key = strategy.name.lower()
        if key in self._strategies:
            raise ValueError(f"Strategy già registrata: {strategy.name}")
        self._strategies[key] = strategy

    def get(self, name: str) -> PairingStrategy:
        """Get strategy by name."""
        try:
            return self._strategies[name.lower()]
        except KeyError as exc:
            raise KeyError(f"Strategy non trovata: {name}") from exc

    def create_strategy(self, name: str, seed: Optional[int] = None) -> PairingStrategy:
        """Create strategy instance with context."""
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


# Alias per compatibilità
StrategyRegistry = EngineRegistry
