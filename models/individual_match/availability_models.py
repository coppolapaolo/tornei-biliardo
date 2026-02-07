"""
Module: models/individual_match/availability_models.py
Purpose: Player availability model (deprecated, kept for backward compatibility)
Split from: models/individual_match/models.py (P3a refactoring)
"""

from ..base import db, BaseModel, TimestampMixin


class PlayerAvailability(BaseModel, TimestampMixin):
    """Player availability preferences for match locations.

    DEPRECATED: This model uses string-based location for legacy compatibility.
    For new features, use UserLocationAvailability from models/location/models.py
    which uses proper billiard_hall_id FK reference.

    Migration path:
    1. Use UserLocationAvailability for new availability records
    2. Gradually migrate existing data via admin tools
    3. Eventually deprecate this table
    """

    __tablename__ = "player_availability"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    # Legacy: string-based location. Prefer UserLocationAvailability.billiard_hall_id
    location = db.Column(db.String(255), nullable=False)

    # Availability preferences
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    preferred_days = db.Column(
        db.String(20), nullable=True
    )  # JSON array of weekday numbers
    preferred_times = db.Column(db.String(50), nullable=True)  # e.g., "18:00-22:00"

    # Relationships
    user = db.relationship("User")

    # Unique constraint: one availability record per user per location
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "location", name="uq_user_location_availability"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PlayerAvailability {self.user_id} -> {self.location}: "
            f"{self.is_available}>"
        )
