from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Sequence


# Value Objects
@dataclass(frozen=True)
class Pairing:
    """Rappresenta un abbinamento per un round.
    - `players`: tuple di id giocatori; (p1, p2) oppure (p1, p2, p3) per trio
    - `round_number`: round per cui vale il pairing
    - `is_bye`: true se è un bye (X) o equivalente
    """
    players: tuple[int, ...]
    round_number: int
    is_bye: bool = False


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    messages: tuple[str, ...] = ()


class PairingStrategy(Protocol):
    name: str

    def validate(self, prova: object) -> ValidationResult:
        """Valida prerequisiti e vincoli della prova."""
        ...

    def propose(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Ritorna la lista di Pairing per il round.
        Nella fase Adapter può avere side-effect finché il legacy engine li ha.
        """
        ...
