"""
Module: models/challenge/models.py
Purpose: Challenge domain models for skill challenges system
Requirements: SPECIFICHE.md - Challenge system for individual skill testing
Data Structures: Challenge, ChallengeAttempt, ChallengeFavorite
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING

from sqlalchemy import desc

from ..base import db, BaseModel, TimestampMixin

if TYPE_CHECKING:
    pass


class Challenge(BaseModel, TimestampMixin):
    """A skill challenge that players can attempt individually."""

    __tablename__ = "challenge"

    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=False)

    # Scoring configuration
    pass_fail_only = db.Column(db.Boolean, nullable=False, default=False)

    # Metadata
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Relationships
    attempts = db.relationship(
        "ChallengeAttempt",
        back_populates="challenge",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    favorites = db.relationship(
        "ChallengeFavorite",
        back_populates="challenge",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    created_by = db.relationship("User", foreign_keys=[created_by_id])

    def get_statistics(self) -> Dict[str, Any]:
        """Get challenge statistics for admin view."""
        attempts_query = self.attempts.filter_by(completed=True)

        total_attempts = attempts_query.count()
        unique_players = (
            attempts_query.with_entities(ChallengeAttempt.user_id).distinct().count()
        )

        if total_attempts == 0:
            return {
                "total_attempts": 0,
                "unique_players": 0,
                "average_score": 0,
                "median_score": 0,
                "max_score_achieved": 0,
                "perfect_score_count": 0,
                "pass_rate": 0,
            }

        # Calculate statistics
        scores = [attempt.score for attempt in attempts_query.all()]
        average_score = sum(scores) / len(scores)
        median_score = sorted(scores)[len(scores) // 2]
        max_score_achieved = max(scores)
        perfect_score_count = sum(1 for score in scores if score == max_score_achieved)

        if self.pass_fail_only:
            pass_rate = (
                sum(1 for attempt in attempts_query if attempt.passed)
                / total_attempts
                * 100
            )
        else:
            # Consider passing as achieving 70% of best score achieved
            passing_score = max_score_achieved * 0.7 if max_score_achieved > 0 else 0
            pass_rate = (
                sum(1 for score in scores if score >= passing_score)
                / total_attempts
                * 100
            )

        return {
            "total_attempts": total_attempts,
            "unique_players": unique_players,
            "average_score": round(average_score, 1),
            "median_score": median_score,
            "max_score_achieved": max_score_achieved,
            "perfect_score_count": perfect_score_count,
            "pass_rate": round(pass_rate, 1),
        }

    def get_user_best_attempt(self, user_id: int) -> Optional["ChallengeAttempt"]:
        """Get user's best attempt for this challenge."""
        return (
            self.attempts.filter_by(user_id=user_id, completed=True)
            .order_by(desc("score"))
            .first()
        )

    def can_be_used_for_x_replacement(self) -> bool:
        """Check if challenge can be used as X replacement in campionati."""
        # Only challenges with numeric scoring can be used for X replacement
        return not self.pass_fail_only and self.is_active

    def get_display_name(self) -> str:
        """Get display name from description (first 50 chars)."""
        short_desc = self.description[:50] + "..." if len(self.description) > 50 else self.description
        return short_desc

    @property
    def image_filename(self) -> Optional[str]:
        """Get just the filename from image_path for template usage."""
        if self.image_path:
            return self.image_path.split('/')[-1]
        return None

    def __repr__(self) -> str:
        return f"<Challenge #{self.id}: {self.get_display_name()}>"


class ChallengeAttempt(BaseModel, TimestampMixin):
    """A player's attempt at a challenge."""

    __tablename__ = "challenge_attempt"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # Attempt details
    score = db.Column(db.Integer, nullable=True)  # Null if not completed
    passed = db.Column(db.Boolean, nullable=True)  # For pass/fail challenges
    completed = db.Column(db.Boolean, nullable=False, default=False)
    attempted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Optional: notes or details about the attempt
    notes = db.Column(db.Text, nullable=True)

    # For campionato integration (when used as X replacement)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="SET NULL"), nullable=True
    )
    round_number = db.Column(db.Integer, nullable=True)

    # Relationships
    challenge = db.relationship("Challenge", back_populates="attempts")
    user = db.relationship("User")
    gara = db.relationship("Gara")

    def complete_attempt(
        self, score: Optional[int] = None, passed: Optional[bool] = None
    ) -> None:
        """Mark attempt as completed with score/result."""
        self.completed = True
        self.attempted_at = datetime.utcnow()

        if self.challenge.pass_fail_only:
            self.passed = passed
            self.score = 1 if passed else 0  # Simple numeric representation
        else:
            self.score = score
            # Auto-determine pass/fail if not explicitly set
            # Without a predefined max_score, we consider positive scores as passing
            if passed is None and score is not None:
                self.passed = score > 0
            else:
                self.passed = passed

    def get_rack_difference_equivalent(self) -> int:
        """Convert challenge score to rack difference for campionato classification."""
        if not self.completed or self.score is None:
            return 0

        # Scale score to reasonable rack difference (0 to max expected rack difference)
        max_rack_diff = 5  # Typical maximum rack difference in a match
        # Without a predefined max_score, use a simple scaling based on score value
        if self.score <= 0:
            return 0
        elif self.score >= 100:  # Assume 100 as a "good" score for scaling
            return max_rack_diff
        else:
            return int((self.score / 100) * max_rack_diff)

    def __repr__(self) -> str:
        return (
            f"<ChallengeAttempt {self.user_id} -> Challenge#{self.challenge_id}: {self.score}>"
        )


class ChallengeFavorite(BaseModel):
    """User's favorite challenges for quick access."""

    __tablename__ = "challenge_favorite"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    favorited_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    challenge = db.relationship("Challenge", back_populates="favorites")
    user = db.relationship("User")

    # Unique constraint: user can favorite a challenge only once
    __table_args__ = (
        db.UniqueConstraint("challenge_id", "user_id", name="uq_challenge_favorite"),
    )

    def __repr__(self) -> str:
        return f"<ChallengeFavorite {self.user_id} -> Challenge#{self.challenge_id}>"
