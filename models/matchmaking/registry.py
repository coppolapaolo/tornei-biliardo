from __future__ import annotations
from typing import Dict
from .strategies.base import PairingStrategy


class EngineRegistry:
    """Registry delle strategie di pairing (nome → Strategy)."""

    def __init__(self) -> None:
        self._strategies: Dict[str, PairingStrategy] = {}

    def register(self, strategy: PairingStrategy) -> None:
        key = strategy.name.lower()
        if key in self._strategies:
            raise ValueError(f"Strategy già registrata: {strategy.name}")
        self._strategies[key] = strategy

    def get(self, name: str) -> PairingStrategy:
        try:
            return self._strategies[name.lower()]
        except KeyError as exc:
            raise KeyError(f"Strategy non trovata: {name}") from exc

    def available(self) -> list[str]:
        return sorted(self._strategies.keys())
