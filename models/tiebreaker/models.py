"""
Module: models/tiebreaker/models.py
Purpose: Tiebreaker domain models for handling ties in matches
Requirements: SPECIFICHE.md - Tiebreaker system with spot shot rallies and playoff
matches
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship, Mapped

from ..base import db, utc_now
from ..status_enum import Discipline

if TYPE_CHECKING:
    from ..match.models import Match
    from ..user.models import User


class TiebreakerType(Enum):
    """Types of tiebreaker methods."""

    SPOT_SHOT = "spot_shot"
    RALLY = "rally"
    PLAYOFF_MATCH = "playoff_match"
    SUDDEN_DEATH = "sudden_death"
    BEST_OF_SERIES = "best_of_series"


class TiebreakerStatus(Enum):
    """Status of a tiebreaker."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SpotShotResult(Enum):
    """Result of a spot shot attempt."""

    MADE = "made"
    MISSED = "missed"
    FOUL = "foul"
    SCRATCH = "scratch"


class Tiebreaker(db.Model):
    """
    Main tiebreaker entity for handling tied matches.

    Supports multiple tiebreaker types:
    - Spot shots for 8-ball/9-ball
    - Rally for straight pool
    - Playoff matches for campionato ties
    - Sudden death racks
    """

    __tablename__ = "tiebreaker"

    id = Column(Integer, primary_key=True)

    # Relationship to the tied match/situation
    match_id = Column(Integer, ForeignKey("match.id"), nullable=False)
    campionato_id = Column(Integer, ForeignKey("campionato.id"), nullable=True)
    gara_id = Column(Integer, ForeignKey("gara.id"), nullable=True)

    # Tiebreaker configuration
    tiebreaker_type = Column(String(20), nullable=False)  # TiebreakerType enum
    status = Column(String(20), default=TiebreakerStatus.PENDING.value)

    # Players involved
    player1_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    player2_id = Column(Integer, ForeignKey("user.id"), nullable=False)

    # Result
    winner_id = Column(Integer, ForeignKey("user.id"), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=utc_now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Configuration data (JSON)
    configuration = Column(JSON, nullable=True)  # Specific settings for each type

    # Notes and comments
    notes = Column(Text, nullable=True)

    # Relationships
    match: Mapped["Match"] = relationship("Match", back_populates="tiebreakers")
    player1: Mapped["User"] = relationship("User", foreign_keys=[player1_id])
    player2: Mapped["User"] = relationship("User", foreign_keys=[player2_id])
    winner: Mapped[Optional["User"]] = relationship("User", foreign_keys=[winner_id])

    spot_shots: Mapped[List["SpotShot"]] = relationship(
        "SpotShot", back_populates="tiebreaker", cascade="all, delete-orphan"
    )
    rally_attempts: Mapped[List["RallyAttempt"]] = relationship(
        "RallyAttempt", back_populates="tiebreaker", cascade="all, delete-orphan"
    )
    playoff_matches: Mapped[List["PlayoffMatch"]] = relationship(
        "PlayoffMatch", back_populates="tiebreaker", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<Tiebreaker {self.id} {self.tiebreaker_type} {self.player1.username} vs "
            f"{self.player2.username}>"
        )

    def start(self) -> None:
        """Start the tiebreaker."""
        if str(self.status) != TiebreakerStatus.PENDING.value:
            raise ValueError("Tiebreaker must be pending to start")

        self.status = TiebreakerStatus.IN_PROGRESS.value
        self.started_at = utc_now()

    def complete(self, winner_id: int) -> None:
        """Complete the tiebreaker with a winner."""
        if str(self.status) != TiebreakerStatus.IN_PROGRESS.value:
            raise ValueError("Tiebreaker must be in progress to complete")

        if winner_id not in [self.player1_id, self.player2_id]:
            raise ValueError("Winner must be one of the players")

        self.status = TiebreakerStatus.COMPLETED.value
        self.winner_id = winner_id
        self.completed_at = utc_now()

    def cancel(self, reason: Optional[str] = None) -> None:
        """Cancel the tiebreaker."""
        self.status = TiebreakerStatus.CANCELLED.value
        if reason:
            self.notes = f"{self.notes or ''}\nCancelled: {reason}".strip()

    def get_score_summary(self) -> dict:
        """Get current score summary based on tiebreaker type."""
        if str(self.tiebreaker_type) == TiebreakerType.SPOT_SHOT.value:
            return self._get_spot_shot_score()
        elif str(self.tiebreaker_type) == TiebreakerType.RALLY.value:
            return self._get_rally_score()
        elif str(self.tiebreaker_type) == TiebreakerType.PLAYOFF_MATCH.value:
            return self._get_playoff_score()
        else:
            return {"player1_score": 0, "player2_score": 0}

    def _get_spot_shot_score(self) -> dict:
        """Calculate spot shot scores."""
        player1_id = self.player1_id
        player2_id = self.player2_id
        p1_made = sum(
            1
            for shot in self.spot_shots
            if shot.player_id == player1_id
            and str(shot.result) == SpotShotResult.MADE.value
        )  # type: ignore
        p2_made = sum(
            1
            for shot in self.spot_shots
            if shot.player_id == player2_id
            and str(shot.result) == SpotShotResult.MADE.value
        )  # type: ignore

        return {
            "player1_score": p1_made,
            "player2_score": p2_made,
            "total_rounds": len(set(shot.round_number for shot in self.spot_shots)),
        }

    def _get_rally_score(self) -> dict:
        """Calculate rally scores."""
        player1_id = self.player1_id
        player2_id = self.player2_id
        p1_score = sum(
            attempt.points_scored
            for attempt in self.rally_attempts
            if attempt.player_id == player1_id
        )  # type: ignore
        p2_score = sum(
            attempt.points_scored
            for attempt in self.rally_attempts
            if attempt.player_id == player2_id
        )  # type: ignore

        return {"player1_score": p1_score, "player2_score": p2_score}

    def _get_playoff_score(self) -> dict:
        """Calculate playoff match scores."""
        player1_id = self.player1_id
        player2_id = self.player2_id
        p1_wins = sum(
            1
            for match in self.playoff_matches
            if match.winner_id is not None and match.winner_id == player1_id
        )  # type: ignore
        p2_wins = sum(
            1
            for match in self.playoff_matches
            if match.winner_id is not None and match.winner_id == player2_id
        )  # type: ignore

        return {
            "player1_score": p1_wins,
            "player2_score": p2_wins,
            "total_matches": len(
                [m for m in self.playoff_matches if m.winner_id is not None]
            ),
        }


class SpotShot(db.Model):
    """
    Individual spot shot attempt in a spot shot tiebreaker.
    Used primarily for 8-ball and 9-ball tied games.
    """

    __tablename__ = "spot_shot"

    id = Column(Integer, primary_key=True)
    tiebreaker_id = Column(Integer, ForeignKey("tiebreaker.id"), nullable=False)

    # Shot details
    round_number = Column(Integer, nullable=False)  # Which round of spot shots
    player_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    order_in_round = Column(Integer, nullable=False)  # 1 or 2 (shooting order)

    # Result
    result = Column(String(10), nullable=False)  # SpotShotResult enum

    # Timing
    attempted_at = Column(DateTime, default=utc_now)

    # Notes
    notes = Column(Text, nullable=True)

    # Relationships
    tiebreaker: Mapped["Tiebreaker"] = relationship(
        "Tiebreaker", back_populates="spot_shots"
    )
    player: Mapped["User"] = relationship("User")

    def __repr__(self):
        return (
            f"<SpotShot {self.id} R{self.round_number} {self.player.username} "
            f"{self.result}>"
        )


class RallyAttempt(db.Model):
    """
    Rally attempt for straight pool tiebreakers.
    Players alternate shooting until they miss.
    """

    __tablename__ = "rally_attempt"

    id = Column(Integer, primary_key=True)
    tiebreaker_id = Column(Integer, ForeignKey("tiebreaker.id"), nullable=False)

    # Attempt details
    player_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    sequence_number = Column(Integer, nullable=False)  # Order of attempts

    # Results
    points_scored = Column(Integer, default=0)
    balls_pocketed = Column(Integer, default=0)
    was_successful = Column(Boolean, default=False)  # Did they continue the rally?
    ended_rally = Column(Boolean, default=False)  # Did this attempt end the rally?

    # Timing
    started_at = Column(DateTime, default=utc_now)
    completed_at = Column(DateTime, nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Relationships
    tiebreaker: Mapped["Tiebreaker"] = relationship(
        "Tiebreaker", back_populates="rally_attempts"
    )
    player: Mapped["User"] = relationship("User")

    def __repr__(self):
        return (
            f"<RallyAttempt {self.id} {self.player.username} {self.points_scored}pts>"
        )


class PlayoffMatch(db.Model):
    """
    Mini playoff match for campionato tiebreakers.
    Short matches to resolve campionato position ties.
    """

    __tablename__ = "playoff_match"

    id = Column(Integer, primary_key=True)
    tiebreaker_id = Column(Integer, ForeignKey("tiebreaker.id"), nullable=False)

    # Match details
    match_number = Column(Integer, nullable=False)  # Sequence in playoff series
    player1_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    player2_id = Column(Integer, ForeignKey("user.id"), nullable=False)

    # Configuration
    distance = Column(Integer, default=3)  # Usually short matches like race to 3
    discipline = Column(String(20), default=Discipline.EIGHT_BALL.value)

    # Results
    player1_score = Column(Integer, default=0)
    player2_score = Column(Integer, default=0)
    winner_id = Column(Integer, ForeignKey("user.id"), nullable=True)

    # Status
    status = Column(String(20), default="pending")

    # Timing
    created_at = Column(DateTime, default=utc_now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    tiebreaker: Mapped["Tiebreaker"] = relationship(
        "Tiebreaker", back_populates="playoff_matches"
    )
    player1: Mapped["User"] = relationship("User", foreign_keys=[player1_id])
    player2: Mapped["User"] = relationship("User", foreign_keys=[player2_id])
    winner: Mapped[Optional["User"]] = relationship("User", foreign_keys=[winner_id])

    def __repr__(self):
        return (
            f"<PlayoffMatch {self.id} {self.player1.username} vs "
            f"{self.player2.username}>"
        )

    def start_match(self) -> None:
        """Start the playoff match."""
        if str(self.status) != "pending":
            raise ValueError("Match must be pending to start")

        self.status = "in_progress"
        self.started_at = utc_now()

    def complete_match(self, winner_id: int, p1_score: int, p2_score: int) -> None:
        """Complete the playoff match."""
        if str(self.status) != "in_progress":
            raise ValueError("Match must be in progress to complete")

        if winner_id not in [self.player1_id, self.player2_id]:
            raise ValueError("Winner must be one of the players")

        self.winner_id = winner_id
        self.player1_score = p1_score
        self.player2_score = p2_score
        self.status = "completed"
        self.completed_at = utc_now()


class TiebreakerConfiguration(db.Model):
    """
    Campionato-level configuration for tiebreaker rules.
    Defines how ties should be resolved in different situations.
    """

    __tablename__ = "tiebreaker_configuration"

    id = Column(Integer, primary_key=True)

    # Scope
    campionato_id = Column(Integer, ForeignKey("campionato.id"), nullable=True)
    gara_id = Column(Integer, ForeignKey("gara.id"), nullable=True)

    # Configuration name
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Rules (JSON configuration)
    rules = Column(JSON, nullable=False)

    # Status
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    def __repr__(self):
        return f"<TiebreakerConfiguration {self.name}>"

    def get_rule_for_discipline(self, discipline: str) -> dict:
        """Get tiebreaker rule for specific discipline."""
        return self.rules.get(discipline, self.rules.get("default", {}))

    def supports_discipline(self, discipline: str) -> bool:
        """Check if configuration supports a discipline."""
        return discipline in self.rules or "default" in self.rules
