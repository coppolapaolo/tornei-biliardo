"""
Module: models/competition/round_configuration.py
Purpose: Configuration models for round-specific settings in competitions
Requirements: Support discipline configuration per round for Random strategy
Data Structures: RoundConfiguration
"""

from __future__ import annotations

from typing import Optional, List, TYPE_CHECKING

from models.base import db, BaseModel, TimestampMixin

if TYPE_CHECKING:
    pass


class RoundConfiguration(BaseModel):
    """Configuration for a specific round in a gara."""

    __tablename__ = "round_configuration"

    id = db.Column(db.Integer, primary_key=True)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=False
    )
    round_number = db.Column(db.Integer, nullable=False)

    # Discipline configuration for this round
    discipline = db.Column(
        db.String(50), nullable=True
    )  # Override discipline for this round

    # Additional round-specific settings (extensible for future features)
    distance = db.Column(db.Integer, nullable=True)  # Override distance for this round
    best_of = db.Column(
        db.Boolean, nullable=True
    )  # Override best_of mode for this round

    # Metadata
    notes = db.Column(db.Text, nullable=True)  # Optional notes for this round

    # Relationships
    gara = db.relationship("Gara", backref="round_configurations")

    # Unique constraint: one configuration per gara per round
    __table_args__ = (
        db.UniqueConstraint(
            "gara_id", "round_number", name="uq_gara_round_configuration"
        ),
    )

    @classmethod
    def get_for_gara_round(
        cls, gara_id: int, round_number: int
    ) -> Optional["RoundConfiguration"]:
        """Get configuration for a specific gara and round."""
        return cls.query.filter_by(gara_id=gara_id, round_number=round_number).first()

    @classmethod
    def get_all_for_gara(cls, gara_id: int) -> List["RoundConfiguration"]:
        """Get all round configurations for a gara, ordered by round number."""
        return cls.query.filter_by(gara_id=gara_id).order_by(cls.round_number).all()

    @classmethod
    def create_or_update(
        cls,
        gara_id: int,
        round_number: int,
        discipline: Optional[str] = None,
        distance: Optional[int] = None,
        best_of: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> "RoundConfiguration":
        """Create or update round configuration."""
        config = cls.get_for_gara_round(gara_id, round_number)

        if not config:
            config = cls(gara_id=gara_id, round_number=round_number)
            db.session.add(config)

        # Update fields only if provided
        if discipline is not None:
            config.discipline = discipline
        if distance is not None:
            config.distance = distance
        if best_of is not None:
            config.best_of = best_of
        if notes is not None:
            config.notes = notes

        return config

    @classmethod
    def delete_for_gara(cls, gara_id: int) -> None:
        """Delete all round configurations for a gara."""
        cls.query.filter_by(gara_id=gara_id).delete()

    def get_effective_discipline(self, fallback_discipline: str) -> str:
        """Get the effective discipline for this round, with fallback."""
        return self.discipline if self.discipline else fallback_discipline

    def get_effective_distance(self, fallback_distance: int) -> int:
        """Get the effective distance for this round, with fallback."""
        return self.distance if self.distance is not None else fallback_distance

    def get_effective_best_of(self, fallback_best_of: bool) -> bool:
        """Get the effective best_of mode for this round, with fallback."""
        return self.best_of if self.best_of is not None else fallback_best_of

    def has_overrides(self) -> bool:
        """Check if this configuration has any overrides from gara defaults."""
        return any(
            [
                self.discipline is not None,
                self.distance is not None,
                self.best_of is not None,
            ]
        )

    def __repr__(self) -> str:
        return f"<RoundConfiguration gara_id={self.gara_id} round={self.round_number} discipline={self.discipline}>"
