from __future__ import annotations
from typing import Sequence, Callable
from .base import PairingStrategy, Pairing, ValidationResult


class AmalfiStrategy(PairingStrategy):
    """Adapter per l'engine Amalfi esistente.

    Il costruttore accetta due callable iniettati per evitare dipendenze forti:
      - `validate_fn(prova) -> tuple[bool, tuple[str, ...]]`
      - `propose_fn(prova, round_number) -> list[tuple[int, ...]]`

    Dove `propose_fn` restituisce solo la *forma* degli abbinamenti
    (id giocatori per match/trio);
    l'Adapter converte in Value Objects `Pairing`.

    Se l'engine legacy esegue direttamente i side-effect
    (creazione Match, PlayerEncounter),
    questa Strategy si limita a riflettere il risultato in `Pairing`.
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

    def validate(self, prova: object) -> ValidationResult:
        ok, messages = self._validate_fn(prova)
        return ValidationResult(ok=ok, messages=messages)

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
