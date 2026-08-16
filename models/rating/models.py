"""
Module: models/rating/models.py
Purpose: Rating domain models for player categories and handicap system
Requirements: SPECIFICHE.md - Handicap system based on categories/ratings
Data Structures: PlayerCategory, PlayerRating, HandicapRule
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from enum import Enum


from ..base import db, BaseModel, utc_now

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

    ELO = "elo"  # Competitivo: SOLO match di torneo. Pilota categoria/handicap.
    ELO_GLOBAL = "elo_global"  # Tornei + casual VALIDATED. SOLO display (dual ELO).
    INTERNAL = "internal"  # Club internal rating


class PlayerCategory(BaseModel):
    """Player category assignment for handicap purposes."""

    __tablename__ = "player_category"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    category = db.Column(db.Enum(CategoryLevel), nullable=False)

    # Assignment details
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=utc_now)
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
            .filter(
                db.or_(cls.expires_at.is_(None), cls.expires_at > utc_now())  # type: ignore[attr-defined] # noqa: E501
            )
            .first()
        )

    def expire_category(self) -> None:
        """Mark category as expired."""
        self.is_active = False
        self.expires_at = utc_now()

    def __repr__(self) -> str:
        return f"<PlayerCategory {self.user_id}: {self.category.value}>"


class PlayerRating(BaseModel):
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
    last_updated = db.Column(db.DateTime, nullable=False, default=utc_now)

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
        self.last_updated = utc_now()

    def get_category_equivalent(self) -> CategoryLevel:
        """Convert rating to category equivalent."""
        if self.rating_system == RatingSystem.ELO:
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
        return (
            f"<PlayerRating {self.user_id}: "
            f"{self.rating_system.value}={self.rating_value}>"
        )


class MatchRatingHistory(BaseModel):
    """Registro dei delta di rating applicati per ogni match.

    Due scopi:
    1. **Idempotenza**: un match contribuisce al rating ESATTAMENTE una volta.
       Se esiste già un record per (match_id, rating_system) il ricalcolo è un
       no-op — protegge da MatchCompletedEvent ri-emessi (reset→ricompletamento)
       e da recalc_elo lanciato su match già processati.
    2. **Revert**: quando un match viene riaperto/resettato si ripristina
       `old_rating` e si decrementa `games_played`, poi si eliminano i record.

    Nota (Elo è path-dependent): il revert per-match è esatto se il match è
    l'ultimo processato per quei giocatori; altrimenti i rating successivi
    restano approssimati finché non si rilancia `recalc_elo` (ricostruzione
    autorevole). Vedi docstring di RatingCalculationService.
    """

    __tablename__ = "match_rating_history"

    id = db.Column(db.Integer, primary_key=True)
    # Sorgente polimorfa: ESATTAMENTE uno tra match_id / individual_match_id.
    # I match di torneo usano match_id; i casual (dual ELO, pool ELO_GLOBAL)
    # usano individual_match_id. Vedi ADR/dual-ELO.
    match_id = db.Column(
        db.Integer, db.ForeignKey("match.id", ondelete="CASCADE"), nullable=True
    )
    individual_match_id = db.Column(
        db.Integer,
        db.ForeignKey("individual_match.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    rating_system = db.Column(db.Enum(RatingSystem), nullable=False)

    old_rating = db.Column(db.Integer, nullable=False)
    new_rating = db.Column(db.Integer, nullable=False)
    delta = db.Column(db.Integer, nullable=False)
    games_increment = db.Column(db.Integer, nullable=False, default=1)

    user = db.relationship("User", foreign_keys=[user_id])

    # Indici unici parziali: idempotenza per-sorgente senza che le righe con
    # l'altra sorgente NULL collidano tra loro.
    __table_args__ = (
        db.Index(
            "uq_match_user_rating_system",
            "match_id",
            "user_id",
            "rating_system",
            unique=True,
            sqlite_where=db.text("match_id IS NOT NULL"),
        ),
        db.Index(
            "uq_individual_match_user_rating_system",
            "individual_match_id",
            "user_id",
            "rating_system",
            unique=True,
            sqlite_where=db.text("individual_match_id IS NOT NULL"),
        ),
    )

    @classmethod
    def exists_for_match(cls, match_id: int, rating_system: RatingSystem) -> bool:
        """True se esiste già almeno un record per quel match torneo/sistema."""
        return (
            cls.query.filter_by(match_id=match_id, rating_system=rating_system).first()
            is not None
        )

    @classmethod
    def exists_for_individual_match(
        cls, individual_match_id: int, rating_system: RatingSystem
    ) -> bool:
        """True se esiste già almeno un record per quel match individuale/sistema."""
        return (
            cls.query.filter_by(
                individual_match_id=individual_match_id, rating_system=rating_system
            ).first()
            is not None
        )

    def __repr__(self) -> str:
        source = (
            f"match={self.match_id}"
            if self.match_id is not None
            else f"individual_match={self.individual_match_id}"
        )
        return (
            f"<MatchRatingHistory {source} user={self.user_id} "
            f"{self.rating_system.value} {self.old_rating}->{self.new_rating}>"
        )


class HandicapRule(BaseModel):
    """Handicap rules for matches between different categories/ratings."""

    __tablename__ = "handicap_rule"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Rule configuration
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    applies_to_campionatos = db.Column(db.Boolean, nullable=False, default=True)
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
        return (
            f"<CategoryHandicapRule {self.higher_category.value} vs "
            f"{self.lower_category.value}: +{self.handicap_value}>"
        )


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
        return (
            f"<RatingHandicapRule {self.rating_system.value}: "
            f"{self.points_per_handicap} pts/handicap>"
        )
