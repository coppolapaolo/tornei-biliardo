from __future__ import annotations
from typing import Sequence, Callable, cast, Optional, Dict, Any, List

from .base import BaseStrategy, Pairing, ValidationResult, StrategyMetrics
from models.competition.models import Prova

from amalfi.engine import AmalfiEngine


class AmalfiStrategy(BaseStrategy):
    """Adapter per l'engine Amalfi esistente.

    Il costruttore accetta due callable iniettati per evitare dipendenze forti:
      - `validate_fn(prova) -> tuple[bool, tuple[str, ...]]`
      - `propose_fn(prova, round_number) -> list[tuple[int, ...]]`

    Dove `propose_fn` restituisce solo la *forma* degli abbinamenti
    (id giocatori per match/trio);
    l'Adapter converte in Value Objects `Pairing`.

    Se l'engine legacy esegue direttamente i side‑effect
    (creazione Match, PlayerEncounter, ecc.), questa Strategy si limita a
    riflettere il risultato in `Pairing`.

    Sprint 2: aggiunta `preview()` **senza side‑effects**, con politica di
    anti‑rematch e gestione disparità (trio/bye) via policy.
    """

    # Strategy metadata (required by PairingStrategy protocol)
    display_name = "Amalfi"
    description = "Adaptive tournament pairing algorithm with anti-rematch intelligence"
    min_players = 3
    max_players = None
    supports_byes = True
    requires_classification = True
    
    name = "Amalfi"

    def __init__(
        self,
        *,
        validate_fn: Callable[[object], tuple[bool, tuple[str, ...]]],
        propose_fn: Callable[[object, int], list[tuple[int, ...]]],
    ) -> None:
        super().__init__()
        self._validate_fn = validate_fn
        self._propose_fn = propose_fn

    # ── validate (override to use injected function) ──────────────────────────
    def validate(self, prova: object) -> ValidationResult:
        ok, messages = self._validate_fn(prova)
        return ValidationResult(ok=ok, messages=messages)

    # ── _generate_pairings (abstract method implementation) ──────────────────
    def _generate_pairings(
        self, 
        processed_data: Dict[str, Any], 
        round_number: int, 
        preview_mode: bool = True
    ) -> Sequence[Pairing]:
        """Generate pairings using the Amalfi engine."""
        prova = processed_data["prova"]
        
        if preview_mode:
            return self._generate_preview_pairings(prova, round_number)
        else:
            return self._generate_actual_pairings(prova, round_number)
    
    def _generate_preview_pairings(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Generate preview pairings without side effects."""
        prova_typed = cast(Prova, prova)
        engine = AmalfiEngine(prova_typed)  # rispetta WithdrawPolicy via patch in engine
        raw = (
            engine._preview_first_round()
            if int(round_number) == 1
            else engine.preview_next_round_matches(int(round_number))
        )
        result: list[Pairing] = []
        for m in raw:
            players: list[int] = []
            if m.get("player1"):
                players.append(int(m["player1"].id))
            if m.get("player2"):
                players.append(int(m["player2"].id))
            if m.get("player3"):
                players.append(int(m["player3"].id))
            is_bye = m.get("type") == "bye" or len(players) == 1
            result.append(
                Pairing(
                    players=tuple(players),
                    is_bye=is_bye,
                    round_number=int(round_number),
                )
            )
        return result
    
    def _generate_actual_pairings(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Generate actual pairings with side effects."""
        raw = self._propose_fn(prova, round_number)
        result: list[Pairing] = []
        for players in raw:
            is_bye = len(players) == 1  # convenzione: (X,) se bye
            result.append(
                Pairing(
                    players=tuple(int(p) for p in players),
                    round_number=round_number,
                    is_bye=is_bye,
                )
            )
        return result

