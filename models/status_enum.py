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
    "WithdrawPolicy",
    "EntityType",
    "choices",
    "parse_enum",
]


class _StrEnum(str, Enum):
    """Enum di stringhe: compatibile con JSON, logging e confronti diretti."""

    def __str__(self) -> str:  # pragma: no cover – banale
        return str(self.value)


# ──────────────────────────────────────────────────────────────────────────────
# GARA
# Persistito: `gara.status` → {setup, inscription, playing, awaiting_ssr, completed}
# Derived/UI (non persistito):
#   {inscription_closed, ready_to_start, round_completed, campionato_completed}
# Fonte: models/competition/models.py
# ──────────────────────────────────────────────────────────────────────────────
class GaraStatus(_StrEnum):
    SETUP = "setup"
    INSCRIPTION = "inscription"
    PLAYING = "playing"
    AWAITING_SSR = "awaiting_ssr"  # Turni finiti, in attesa di spareggi SSR
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProvaDerivedStatus(_StrEnum):
    """Stati *derivati* (non persistiti) usati da UI/flow di Gara.

    Questi stati possono essere restituiti da funzioni di dominio (es. get_real_status)
    ma non vanno salvati nel DB.
    """

    INSCRIPTION_NOT_YET_OPEN = "inscription_not_yet_open"
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
    TERMINATED = "terminated"


# ──────────────────────────────────────────────────────────────────────────────
# MATCH
# Persistito: `match.status` → {pending, playing, completed, validated}
# Fonte: models/match/models.py
# ──────────────────────────────────────────────────────────────────────────────
class MatchStatus(_StrEnum):
    """
    Status for all match types (tournament and individual).

    Tournament matches: PENDING -> PLAYING -> COMPLETED -> VALIDATED
    Individual matches: SCHEDULED -> IN_PROGRESS -> COMPLETED/CANCELLED
    """

    # Tournament match lifecycle
    PENDING = "pending"
    PLAYING = "playing"

    # Individual match lifecycle
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"

    # Common final states
    COMPLETED = "completed"
    VALIDATED = "validated"  # optional/admin only
    CANCELLED = "cancelled"

    @classmethod
    def finished_values(cls) -> Tuple[str, ...]:
        """Status values that count as 'finished' (completed or validated)."""
        return (cls.COMPLETED.value, cls.VALIDATED.value)

    @classmethod
    def is_finished(cls, status: str) -> bool:
        """True if the status string represents a finished match.

        Prefer this over raw ``status in ["completed", "validated"]`` checks:
        a typo'd enum member raises at import, a typo'd string fails silently.
        """
        return status in cls.finished_values()

    @classmethod
    def active_values(cls) -> Tuple[str, ...]:
        """Status values that count as 'in progress' (playing or in_progress)."""
        return (cls.PLAYING.value, cls.IN_PROGRESS.value)

    @classmethod
    def is_active(cls, status: str) -> bool:
        """True if the status string represents a match in progress."""
        return status in cls.active_values()


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


class EntityType(_StrEnum):
    """Entity types for DirectorAssignment and similar relationships."""

    CAMPIONATO = "campionato"
    GARA = "gara"


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
        """Restituisce le scelte form/template come lista di tuple (value, label)."""
        return [(discipline.value, discipline.display_name) for discipline in cls]

    @classmethod
    def get_common_disciplines(cls) -> list["Discipline"]:
        """Restituisce le discipline più comuni."""
        return [
            cls.EIGHT_BALL,
            cls.NINE_BALL,
            cls.TEN_BALL,
            cls.ONE_POCKET,
            cls.STRAIGHT_POOL,
        ]


class WithdrawPolicy(_StrEnum):
    """Policy for handling player withdrawals/forfeits."""
    FORFEIT = "Forfeit"
    EXCLUDE = "Exclude"


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
