"""
Module: models/status_enum
Purpose: Definizione centralizzata degli *status* applicativi come Enum string-based.
Data Structures: GaraStatus, ProvaDerivedStatus, TournamentStatus, MatchStatus,
                 DirectorRequestStatus, PlayoffConfirmationStatus
Dependencies: Solo stdlib (enum, typing)

Note di migrazione (soft):
- Gli Enum ereditano da `str` per mantenere piena retrocompatibilità con il DB
  (colonne VARCHAR). Nessun DDL richiesto in questo sprint.
- Gli status "derived" di Gara NON sono persistiti: servono a UI/flow.
"""

from __future__ import annotations

from enum import Enum
from typing import Tuple, Type, TypeVar

__all__ = [
    "GaraStatus",
    "ProvaDerivedStatus",
    "TournamentStatus",
    "MatchStatus",
    "DirectorRequestStatus",
    "VenueManagerRequestStatus",
    "PlayoffConfirmationStatus",
    "Discipline",
    "choices",
    "parse_enum",
]


class _StrEnum(str, Enum):
    """Enum di stringhe: compatibile con JSON, logging e confronti diretti."""

    def __str__(self) -> str:  # pragma: no cover – banale
        return str(self.value)


# ──────────────────────────────────────────────────────────────────────────────
# GARA
# Persistito: `gara.status` → {setup, inscription, playing, completed}
# Derived/UI (non persistito):
#   {inscription_closed, ready_to_start, round_completed, campionato_completed}
# Fonte: models/competition/models.py
# ──────────────────────────────────────────────────────────────────────────────
class GaraStatus(_StrEnum):
    SETUP = "setup"
    INSCRIPTION = "inscription"
    PLAYING = "playing"
    COMPLETED = "completed"


class ProvaDerivedStatus(_StrEnum):
    """Stati *derivati* (non persistiti) usati da UI/flow di Gara.

    Questi stati possono essere restituiti da funzioni di dominio (es. get_real_status)
    ma non vanno salvati nel DB.
    """

    INSCRIPTION_CLOSED = "inscription_closed"
    READY_TO_START = "ready_to_start"
    ROUND_COMPLETED = "round_completed"
    TOURNAMENT_COMPLETED = "campionato_completed"


# ──────────────────────────────────────────────────────────────────────────────
# CAMPIONATO (derivato dalle Gare)
# Restituito da `Campionato.get_status()`:
#           {setup, registration_open, in_progress, completed}
# Fonte: models/campionato/models.py
# ──────────────────────────────────────────────────────────────────────────────
class TournamentStatus(_StrEnum):
    SETUP = "setup"
    REGISTRATION_OPEN = "registration_open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


# ──────────────────────────────────────────────────────────────────────────────
# MATCH
# Persistito: `match.status` → {pending, playing, completed, validated}
# Fonte: models/match/models.py
# ──────────────────────────────────────────────────────────────────────────────
class MatchStatus(_StrEnum):
    PENDING = "pending"
    PLAYING = "playing"
    COMPLETED = "completed"
    VALIDATED = "validated"  # opzionale/solo flussi admin


# ──────────────────────────────────────────────────────────────────────────────
# DIRECTOR REQUEST
# Persistito: `director_request.status` → {pending, approved, rejected}
# Fonte: models/user/models.py (DirectorRequest)
# ──────────────────────────────────────────────────────────────────────────────
class DirectorRequestStatus(_StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ──────────────────────────────────────────────────────────────────────────────
# VENUE MANAGER REQUEST
# Persistito: `venue_manager_request.status` → {pending, approved, rejected, cancelled}
# Fonte: models/user/models.py (VenueManagerRequest)
# ──────────────────────────────────────────────────────────────────────────────
class VenueManagerRequestStatus(_StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# ──────────────────────────────────────────────────────────────────────────────
# PLAYOFF (legacy)
# Persistito: `legacy_models.Playoff.confirmation_status`
# → {pending, confirmed, declined}
# Fonte: models/legacy_models.py (Playoff)
# ──────────────────────────────────────────────────────────────────────────────
class PlayoffConfirmationStatus(_StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"


# ──────────────────────────────────────────────────────────────────────────────
# Utility generiche
# ──────────────────────────────────────────────────────────────────────────────
E = TypeVar("E", bound=_StrEnum)


class Discipline(_StrEnum):
    """Discipline di biliardo americano supportate."""

    EIGHT_BALL = "8_ball"
    NINE_BALL = "9_ball"
    TEN_BALL = "10_ball"
    ONE_POCKET = "one_pocket"
    STRAIGHT_POOL = "straight_pool"
    BANK_POOL = "bank_pool"
    ROTATION = "rotation"

    @property
    def display_name(self) -> str:
        """Nome display della disciplina."""
        display_map = {
            self.EIGHT_BALL: "8-Ball",
            self.NINE_BALL: "9-Ball",
            self.TEN_BALL: "10-Ball",
            self.ONE_POCKET: "One Pocket",
            self.STRAIGHT_POOL: "Straight Pool",
            self.BANK_POOL: "Bank Pool",
            self.ROTATION: "Rotation",
        }
        return display_map.get(self, self.value.replace("_", " ").title())

    @classmethod
    def get_choices(cls) -> list[tuple[str, str]]:
        """Restituisce le scelte per form/template come lista di tuple (value, label)."""
        return [(discipline.value, discipline.display_name) for discipline in cls]

    @classmethod
    def get_common_disciplines(cls) -> list["Discipline"]:
        """Restituisce le discipline più comuni."""
        return [cls.EIGHT_BALL, cls.NINE_BALL, cls.TEN_BALL, cls.ONE_POCKET, cls.STRAIGHT_POOL]


def choices(enum_cls: Type[E]) -> Tuple[str, ...]:
    """Restituisce la tupla delle stringhe ammesse dall'enum.

    Utile per validazioni e (in futuro) CHECK constraint DB.
    """

    return tuple(member.value for member in enum_cls)  # type: ignore[return-value]


def parse_enum(enum_cls: Type[E], value: str) -> E:
    """Parsa una stringa verso l'enum indicato, sollevando
    ValueError su valore invalido."""

    try:
        # Accesso diretto per value esatto
        return enum_cls(value)  # type: ignore[call-arg]
    except ValueError as exc:
        valid = ", ".join(choices(enum_cls))
        raise ValueError(
            f"Valore '{value}' non valido per {enum_cls.__name__}. Ammessi: {valid}."
        ) from exc
