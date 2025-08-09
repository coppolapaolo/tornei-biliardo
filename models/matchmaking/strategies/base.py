from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Sequence, Tuple


@dataclass(frozen=True)
class Pairing:
    """Value Object di output del matchmaking (preview/propose)."""
    players: Tuple[int, ...]
    is_bye: bool = False
    round_number: int | None = None


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    messages: Tuple[str, ...] = ()


class PairingStrategy(Protocol):
    def validate(self, prova: object) -> ValidationResult: ...
    def preview(self, prova: object, round_number: int) -> Sequence[Pairing]: ...
    def propose(self, prova: object, round_number: int) -> Sequence[Pairing]: ...
