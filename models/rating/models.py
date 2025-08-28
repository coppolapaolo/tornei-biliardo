"""
Module: models/rating/models.py
Purpose: Rating domain models for player categories and handicap system
Requirements: SPECIFICHE.md - Handicap system based on categories/ratings
Data Structures: PlayerCategory, PlayerRating, HandicapRule
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from enum import Enum


from ..base import db, BaseModel, TimestampMixin

if TYPE_CHECKING:
    pass


class CategoryLevel(Enum):
    """Player category levels."""

    A = "A"  # Advanced
    B = "B"  # Intermediate
    C = "C"  # Beginner
    D = "D"  # Novice


class RatingSystem(Enum):
    """Supported rating systems."""

    FARGO = "fargo"
    ELO = "elo"
    INTERNAL = "internal"  # Club internal rating


class PlayerCategory(BaseModel, TimestampMixin):
    """Player category assignment for handicap purposes."""

    __tablename__ = "player_category"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    category = db.Column(db.Enum(CategoryLevel), nullable=False)

    # Assignment details
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reason = db.Column(db.String(255), nullable=True)

    # Validity
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    expires_at = db.Column(db.DateTime, nullable=True)  # Optional expiration

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])

    # Unique constraint: one active category per user
    __table_args__ = (db.Index("idx_user_active_category", user_id, is_active),)

    @classmethod
    def get_user_current_category(cls, user_id: int) -> Optional["PlayerCategory"]:
        """Get user's current active category."""
        return (
            cls.query.filter_by(user_id=user_id, is_active=True)
            .filter(db.or_(cls.expires_at.is_(None), cls.expires_at > datetime.utcnow()))
            .first()
        )

    def expire_category(self) -> None:
        """Mark category as expired."""
        self.is_active = False
        self.expires_at = datetime.utcnow()

    def __repr__(self) -> str:
        return f"<PlayerCategory {self.user_id}: {self.category.value}>"


class PlayerRating(BaseModel, TimestampMixin):
    """Player rating in various rating systems."""

    __tablename__ = "player_rating"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    rating_system = db.Column(db.Enum(RatingSystem), nullable=False)
    rating_value = db.Column(db.Integer, nullable=False)

    # Rating details
    confidence = db.Column(db.Float, nullable=True)  # Confidence level (0.0-1.0)
    games_played = db.Column(db.Integer, nullable=False, default=0)
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # External rating details
    external_id = db.Column(db.String(50), nullable=True)  # ID in external system
    verified = db.Column(db.Boolean, nullable=False, default=False)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    verified_by = db.relationship("User", foreign_keys=[verified_by_id])

    # Unique constraint: one rating per user per system
    __table_args__ = (
        db.UniqueConstraint("user_id", "rating_system", name="uq_user_rating_system"),
    )

    @classmethod
    def get_user_rating(
        cls, user_id: int, rating_system: RatingSystem
    ) -> Optional["PlayerRating"]:
        """Get user's rating in a specific system."""
        return cls.query.filter_by(user_id=user_id, rating_system=rating_system).first()

    def update_rating(self, new_rating: int, games_increment: int = 1) -> None:
        """Update rating value and statistics."""
        self.rating_value = new_rating
        self.games_played += games_increment
        self.last_updated = datetime.utcnow()

    def get_category_equivalent(self) -> CategoryLevel:
        """Convert rating to category equivalent."""
        if self.rating_system == RatingSystem.FARGO:
            # Fargo rating to category mapping
            if self.rating_value >= 600:
                return CategoryLevel.A
            elif self.rating_value >= 500:
                return CategoryLevel.B
            elif self.rating_value >= 400:
                return CategoryLevel.C
            else:
                return CategoryLevel.D
        elif self.rating_system == RatingSystem.ELO:
            # ELO rating to category mapping
            if self.rating_value >= 1800:
                return CategoryLevel.A
            elif self.rating_value >= 1500:
                return CategoryLevel.B
            elif self.rating_value >= 1200:
                return CategoryLevel.C
            else:
                return CategoryLevel.D
        else:
            # Internal rating to category mapping
            if self.rating_value >= 80:
                return CategoryLevel.A
            elif self.rating_value >= 60:
                return CategoryLevel.B
            elif self.rating_value >= 40:
                return CategoryLevel.C
            else:
                return CategoryLevel.D

    def __repr__(self) -> str:
        return f"<PlayerRating {self.user_id}: {self.rating_system.value}={self.rating_value}>"


class HandicapRule(BaseModel, TimestampMixin):
    """Handicap rules for matches between different categories/ratings."""

    __tablename__ = "handicap_rule"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Rule configuration
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    applies_to_tournaments = db.Column(db.Boolean, nullable=False, default=True)
    applies_to_individual_matches = db.Column(db.Boolean, nullable=False, default=True)

    # Category-based rules
    category_rules = db.relationship(
        "CategoryHandicapRule", back_populates="rule", cascade="all, delete-orphan"
    )

    # Rating-based rules
    rating_rules = db.relationship(
        "RatingHandicapRule", back_populates="rule", cascade="all, delete-orphan"
    )

    def calculate_category_handicap(
        self, higher_category: CategoryLevel, lower_category: CategoryLevel
    ) -> int:
        """Calculate handicap based on category difference."""
        category_rule = CategoryHandicapRule.query.filter_by(
            rule_id=self.id,
            higher_category=higher_category,
            lower_category=lower_category,
        ).first()

        return category_rule.handicap_value if category_rule else 0

    def calculate_rating_handicap(
        self, higher_rating: int, lower_rating: int, rating_system: RatingSystem
    ) -> int:
        """Calculate handicap based on rating difference."""
        rating_rule = RatingHandicapRule.query.filter_by(
            rule_id=self.id, rating_system=rating_system
        ).first()

        if not rating_rule:
            return 0

        rating_diff = higher_rating - lower_rating

        # Apply thresholds and multipliers
        if rating_diff < rating_rule.min_difference:
            return 0

        # Cap the difference
        capped_diff = min(rating_diff, rating_rule.max_difference or rating_diff)

        # Calculate handicap
        handicap = int(capped_diff / rating_rule.points_per_handicap)
        return min(handicap, rating_rule.max_handicap or handicap)

    def __repr__(self) -> str:
        return f"<HandicapRule {self.name}>"


class CategoryHandicapRule(BaseModel):
    """Specific handicap rule for category combinations."""

    __tablename__ = "category_handicap_rule"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(
        db.Integer,
        db.ForeignKey("handicap_rule.id", ondelete="CASCADE"),
        nullable=False,
    )

    higher_category = db.Column(db.Enum(CategoryLevel), nullable=False)
    lower_category = db.Column(db.Enum(CategoryLevel), nullable=False)
    handicap_value = db.Column(
        db.Integer, nullable=False
    )  # Points advantage for lower category

    # Relationships
    rule = db.relationship("HandicapRule", back_populates="category_rules")

    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint(
            "rule_id", "higher_category", "lower_category", name="uq_rule_categories"
        ),
    )

    def __repr__(self) -> str:
        return f"<CategoryHandicapRule {self.higher_category.value} vs {self.lower_category.value}: +{self.handicap_value}>"


class RatingHandicapRule(BaseModel):
    """Handicap rule based on rating differences."""

    __tablename__ = "rating_handicap_rule"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(
        db.Integer,
        db.ForeignKey("handicap_rule.id", ondelete="CASCADE"),
        nullable=False,
    )

    rating_system = db.Column(db.Enum(RatingSystem), nullable=False)
    min_difference = db.Column(
        db.Integer, nullable=False, default=50
    )  # Minimum rating diff for handicap
    max_difference = db.Column(
        db.Integer, nullable=True
    )  # Maximum rating diff to consider
    points_per_handicap = db.Column(
        db.Integer, nullable=False, default=100
    )  # Rating points per handicap point
    max_handicap = db.Column(db.Integer, nullable=True)  # Maximum handicap points

    # Relationships
    rule = db.relationship("HandicapRule", back_populates="rating_rules")

    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint("rule_id", "rating_system", name="uq_rule_rating_system"),
    )

    def __repr__(self) -> str:
        return f"<RatingHandicapRule {self.rating_system.value}: {self.points_per_handicap} pts/handicap>"
