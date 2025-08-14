from __future__ import annotations
from typing import Sequence, Callable

from .base import PairingStrategy, Pairing, ValidationResult

from amalfi.engine import AmalfiEngine


class AmalfiStrategy(PairingStrategy):
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

    name = "Amalfi"

    def __init__(
        self,
        *,
        validate_fn: Callable[[object], tuple[bool, tuple[str, ...]]],
        propose_fn: Callable[[object, int], list[tuple[int, ...]]],
    ) -> None:
        self._validate_fn = validate_fn
        self._propose_fn = propose_fn

    # ── validate ──────────────────────────────────────────────────────────────
    def validate(self, prova: object) -> ValidationResult:
        ok, messages = self._validate_fn(prova)
        return ValidationResult(ok=ok, messages=messages)

    # ── preview (no IO) ──────────────────────────────────────────────────────
    def preview(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Calcola anteprima abbinamenti usando l'engine di preview (no side-effect)."""
        engine = AmalfiEngine(prova)  # rispetta WithdrawPolicy via patch in engine
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

    # ── propose (side‑effects via engine) ─────────────────────────────────────
    def propose(self, prova: object, round_number: int) -> Sequence[Pairing]:
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
