from __future__ import annotations
from typing import Sequence
from .registry import EngineRegistry
from .strategies.base import Pairing


class MatchmakingService:
    """Orchestratore che invoca la Strategy registrata.
    Sprint 1: pass-through verso l'engine legacy via Adapter.
    Sprint 2: espone anche `preview()` senza side‑effects.
    """

    def __init__(self, registry: EngineRegistry) -> None:
        self._registry = registry

    def preview(
        self, *, strategy_name: str, prova: object, round_number: int
    ) -> Sequence[Pairing]:
        """Calcola la preview degli abbinamenti senza side‑effects."""
        strategy = self._registry.get(strategy_name)
        validation = strategy.validate(prova)
        if not validation.ok:
            msgs = "; ".join(validation.messages) or "Validazione pairing fallita"
            raise ValueError(msgs)
        return strategy.preview(prova, round_number)

    def run(
        self, *, strategy_name: str, prova: object, round_number: int
    ) -> Sequence[Pairing]:
        """Esegue il pairing *effettivo* (con side‑effects via engine/binding)."""
        strategy = self._registry.get(strategy_name)
        validation = strategy.validate(prova)
        if not validation.ok:
            msgs = "; ".join(validation.messages) or "Validazione pairing fallita"
            raise ValueError(msgs)
        return strategy.propose(prova, round_number)
