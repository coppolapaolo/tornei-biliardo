from __future__ import annotations
from typing import Sequence, Callable, cast, Dict, Any

from .base import BaseStrategy, Pairing, ValidationResult
from models.competition.models import Gara

from amalfi.engine import AmalfiEngine


class AmalfiStrategy(BaseStrategy):
    """Adapter per l'engine Amalfi esistente.

    Il costruttore accetta due callable iniettati per evitare dipendenze forti:
      - `validate_fn(gara) -> tuple[bool, tuple[str, ...]]`
      - `propose_fn(gara, round_number) -> list[tuple[int, ...]]`

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
    description = "Adaptive campionato pairing algorithm with anti-rematch intelligence"
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
    def validate(self, gara: object) -> ValidationResult:
        ok, messages = self._validate_fn(gara)
        return ValidationResult(ok=ok, messages=messages)

    # ── _generate_pairings (abstract method implementation) ──────────────────
    def _generate_pairings(
        self,
        processed_data: Dict[str, Any],
        round_number: int,
        preview_mode: bool = True,
    ) -> Sequence[Pairing]:
        """Generate pairings using the Amalfi engine."""
        gara = processed_data["gara"]

        if preview_mode:
            return self._generate_preview_pairings(gara, round_number)
        else:
            return self._generate_actual_pairings(gara, round_number)

    def _generate_preview_pairings(
        self, gara: object, round_number: int
    ) -> Sequence[Pairing]:
        """Generate preview pairings without side effects."""
        gara_typed = cast(Gara, gara)
        engine = AmalfiEngine(gara_typed)  # rispetta WithdrawPolicy via patch in engine
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

    def _generate_actual_pairings(
        self, gara: object, round_number: int
    ) -> Sequence[Pairing]:
        """Generate actual pairings with side effects."""
        raw = self._propose_fn(gara, round_number)
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
