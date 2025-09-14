"""
Module: models/challenge/gara_challenge_models.py
Purpose: Models for integrating challenges into Random tournament competitions (Gara)
Requirements: Support for challenge execution during tournaments with classification tracking
Data Structures: GaraChallenge, GaraChallengeAttempt, GaraChallengeClassification
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from sqlalchemy import desc, asc

from ..base import db, BaseModel, TimestampMixin

if TYPE_CHECKING:
    from .models import Challenge
    from ..user.models import User
    from ..competition.models import Gara


class GaraChallenge(BaseModel, TimestampMixin):
    """Link between a gara (competition) and a challenge."""

    __tablename__ = "gara_challenge"

    id = db.Column(db.Integer, primary_key=True)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=False
    )
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="CASCADE"), nullable=False
    )

    # Configuration
    round_number = db.Column(db.Integer, nullable=False)  # After which round to execute
    max_attempts = db.Column(
        db.Integer, nullable=False, default=1
    )  # Attempts per player
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Metadata
    added_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Relationships
    gara = db.relationship("Gara", backref="gara_challenges")
    challenge = db.relationship("Challenge")
    added_by = db.relationship("User", foreign_keys=[added_by_id])
    attempts = db.relationship(
        "GaraChallengeAttempt",
        back_populates="gara_challenge",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    # Unique constraint: one challenge per gara per round
    __table_args__ = (
        db.UniqueConstraint(
            "gara_id", "challenge_id", "round_number", name="uq_gara_challenge_round"
        ),
    )

    def get_user_attempts(self, user_id: int) -> List["GaraChallengeAttempt"]:
        """Get all attempts for a specific user in this gara challenge."""
        return (
            self.attempts.filter_by(user_id=user_id)
            .order_by(GaraChallengeAttempt.attempt_number)
            .all()
        )

    def get_user_best_attempt(self, user_id: int) -> Optional["GaraChallengeAttempt"]:
        """Get user's best attempt for this gara challenge."""
        return (
            self.attempts.filter_by(user_id=user_id, completed=True)
            .order_by(desc("score"))
            .first()
        )

    def get_user_attempts_count(self, user_id: int) -> int:
        """Get number of attempts made by user."""
        return self.attempts.filter_by(user_id=user_id, completed=True).count()

    def can_user_attempt(self, user_id: int) -> bool:
        """Check if user can make another attempt."""
        current_attempts = self.get_user_attempts_count(user_id)
        return current_attempts < self.max_attempts

    def is_ready_for_round(self, current_round: int) -> bool:
        """Check if this challenge should be available for the current round."""
        return current_round >= self.round_number and self.is_active

    def __repr__(self) -> str:
        return f"<GaraChallenge gara_id={self.gara_id} challenge_id={self.challenge_id} round={self.round_number}>"


class GaraChallengeAttempt(BaseModel, TimestampMixin):
    """An attempt at a challenge within a specific gara context."""

    __tablename__ = "gara_challenge_attempt"

    id = db.Column(db.Integer, primary_key=True)
    gara_challenge_id = db.Column(
        db.Integer,
        db.ForeignKey("gara_challenge.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # Attempt details
    attempt_number = db.Column(db.Integer, nullable=False)  # 1, 2, 3...
    score = db.Column(db.Integer, nullable=True)  # Null if not completed
    passed = db.Column(db.Boolean, nullable=True)  # For pass/fail challenges
    completed = db.Column(db.Boolean, nullable=False, default=False)
    attempted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Optional: notes or details about the attempt
    notes = db.Column(db.Text, nullable=True)

    # Round context when attempt was made
    round_when_attempted = db.Column(db.Integer, nullable=True)

    # Relationships
    gara_challenge = db.relationship("GaraChallenge", back_populates="attempts")
    user = db.relationship("User")

    # Unique constraint: one attempt per user per attempt number per gara challenge
    __table_args__ = (
        db.UniqueConstraint(
            "gara_challenge_id",
            "user_id",
            "attempt_number",
            name="uq_gara_challenge_user_attempt",
        ),
    )

    def complete_attempt(
        self,
        score: Optional[int] = None,
        passed: Optional[bool] = None,
        gara_challenge: Optional["GaraChallenge"] = None,
    ) -> None:
        """Mark attempt as completed with score/result."""
        self.completed = True
        self.attempted_at = datetime.utcnow()

        # Get gara_challenge from parameter or relationship
        gc = gara_challenge or self.gara_challenge
        if not gc:
            # Load from database if not provided and relationship not available
            gc = db.session.get(GaraChallenge, self.gara_challenge_id)

        if not gc:
            raise ValueError("Cannot find gara_challenge")

        if gc.challenge.pass_fail_only:
            self.passed = passed
            self.score = 1 if passed else 0  # Simple numeric representation
        else:
            # For score-based challenges, just store the score
            self.score = score
            self.passed = passed  # Only set if explicitly provided

    def __repr__(self) -> str:
        return f"<GaraChallengeAttempt gara_challenge_id={self.gara_challenge_id} user_id={self.user_id} attempt={self.attempt_number}>"


class GaraChallengeClassification(BaseModel):
    """Challenge-based classification for a gara."""

    __tablename__ = "gara_challenge_classification"

    id = db.Column(db.Integer, primary_key=True)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # Classification data
    position = db.Column(db.Integer, nullable=False)
    total_best_score = db.Column(
        db.Integer, nullable=False, default=0
    )  # Sum of best attempts across challenges
    total_all_attempts = db.Column(
        db.Integer, nullable=False, default=0
    )  # Sum of all attempts for tiebreaking
    challenges_completed = db.Column(
        db.Integer, nullable=False, default=0
    )  # Number of challenges attempted

    # Metadata
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    gara = db.relationship("Gara")
    user = db.relationship("User")

    # Unique constraint: one classification per user per gara
    __table_args__ = (
        db.UniqueConstraint(
            "gara_id", "user_id", name="uq_gara_challenge_classification"
        ),
    )

    @classmethod
    def calculate_for_gara(cls, gara_id: int) -> List["GaraChallengeClassification"]:
        """Calculate and update challenge classification for a gara."""
        from models.user.models import User
        from models.competition.models import Inscription

        # Get all inscribed users for this gara
        inscribed_users = (
            db.session.query(User)
            .join(Inscription, User.id == Inscription.user_id)
            .filter(
                Inscription.gara_id == gara_id,
                Inscription.is_withdrawn == False,
                Inscription.is_waitlist == False,
            )
            .all()
        )

        # Get all gara challenges for this gara
        gara_challenges = GaraChallenge.query.filter_by(
            gara_id=gara_id, is_active=True
        ).all()

        classifications = []

        # Disable autoflush to avoid premature commit with None positions
        with db.session.no_autoflush:
            for user in inscribed_users:
                total_best_score = 0
                total_all_attempts = 0
                challenges_completed = 0

                # Calculate scores across all challenges for this user
                for gara_challenge in gara_challenges:
                    user_attempts = gara_challenge.get_user_attempts(user.id)
                    completed_attempts = [
                        attempt for attempt in user_attempts if attempt.completed
                    ]

                    if completed_attempts:
                        challenges_completed += 1
                        # Get best score for this challenge
                        best_score = max(
                            attempt.score or 0 for attempt in completed_attempts
                        )
                        total_best_score += best_score
                        # Sum all attempts for this challenge
                        total_all_attempts += sum(
                            attempt.score or 0 for attempt in completed_attempts
                        )

                # Update or create classification record
                classification = cls.query.filter_by(
                    gara_id=gara_id, user_id=user.id
                ).first()
                if not classification:
                    classification = cls(
                        gara_id=gara_id, user_id=user.id, position=0
                    )  # Temporary position
                    db.session.add(classification)

                classification.total_best_score = total_best_score
                classification.total_all_attempts = total_all_attempts
                classification.challenges_completed = challenges_completed
                classification.last_updated = datetime.utcnow()

                classifications.append(classification)

            # Sort by total_best_score DESC, then by total_all_attempts ASC (lower is better for tiebreaker)
            classifications.sort(
                key=lambda x: (-x.total_best_score, x.total_all_attempts)
            )

            # Assign positions
            for idx, classification in enumerate(classifications):
                classification.position = idx + 1

        db.session.commit()
        return classifications

    def get_user_challenge_details(self) -> List[Dict[str, Any]]:
        """Get detailed breakdown of user's performance across all challenges in this gara."""
        gara_challenges = GaraChallenge.query.filter_by(
            gara_id=self.gara_id, is_active=True
        ).all()
        details = []

        for gara_challenge in gara_challenges:
            attempts = gara_challenge.get_user_attempts(self.user_id)
            completed_attempts = [attempt for attempt in attempts if attempt.completed]

            best_score = max(
                (attempt.score or 0 for attempt in completed_attempts), default=0
            )
            total_score = sum(attempt.score or 0 for attempt in completed_attempts)
            attempt_count = len(completed_attempts)

            details.append(
                {
                    "challenge": gara_challenge.challenge,
                    "gara_challenge": gara_challenge,
                    "best_score": best_score,
                    "total_score": total_score,
                    "attempt_count": attempt_count,
                    "max_attempts": gara_challenge.max_attempts,
                    "attempts": completed_attempts,
                }
            )

        return details

    def __repr__(self) -> str:
        return f"<GaraChallengeClassification gara_id={self.gara_id} user_id={self.user_id} pos={self.position}>"
