"""
Module: models/location/models.py
Purpose: Location domain models for billiard halls and player availability
Requirements: SPECIFICHE.md - Location-based match proposals and availability
Data Structures: BilliardHall, UserLocationAvailability
"""

from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from enum import Enum


from ..base import db, BaseModel, TimestampMixin, utc_now

if TYPE_CHECKING:
    from ..user.models import User


class DayOfWeek(Enum):
    """Days of the week."""

    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7


class BilliardHall(BaseModel):
    """A billiard hall where matches can be played."""

    __tablename__ = "billiard_hall"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    province = db.Column(db.String(2), nullable=True)  # Italian province code (e.g., "RM", "MI")
    postal_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=False, default="Italy")

    # Contact information
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    website = db.Column(db.String(255), nullable=True)

    # Facility details
    number_of_tables = db.Column(db.Integer, nullable=True)
    # JSON list of table names ["1", "2", "Sala Rossa", etc.]
    table_names = db.Column(db.Text, nullable=True)
    table_types = db.Column(db.Text, nullable=True)  # JSON string
    amenities = db.Column(db.Text, nullable=True)  # JSON string

    # Business hours (JSON format for flexibility)
    business_hours = db.Column(db.Text, nullable=True)  # JSON string

    # Pricing
    hourly_rate = db.Column(db.Numeric(10, 2), nullable=True)
    currency = db.Column(db.String(3), nullable=False, default="EUR")

    # Status
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    verified = db.Column(db.Boolean, nullable=False, default=False)
    added_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Location coordinates (for future mapping features)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    # Relationships
    added_by = db.relationship("User", foreign_keys=[added_by_id])

    # User availability at this location
    user_availabilities = db.relationship(
        "UserLocationAvailability",
        back_populates="billiard_hall",
        cascade="all, delete-orphan",
    )

    def get_table_types(self) -> List[str]:
        """Get table types as list."""
        if not self.table_types:
            return []
        try:
            return json.loads(self.table_types)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_table_types(self, types: List[str]) -> None:
        """Set table types as JSON."""
        self.table_types = json.dumps(types) if types else None

    def get_table_names(self) -> List[str]:
        """Get table names as list.

        If table_names is not set, generates default names ["1", "2", ...]
        based on number_of_tables.
        """
        if self.table_names:
            try:
                return json.loads(self.table_names)
            except (json.JSONDecodeError, TypeError):
                pass

        # Generate default table names if not set
        if self.number_of_tables:
            return [str(i) for i in range(1, self.number_of_tables + 1)]
        return []

    def set_table_names(self, names: List[str]) -> None:
        """Set table names as JSON."""
        self.table_names = json.dumps(names) if names else None

    def get_amenities(self) -> List[str]:
        """Get amenities as list."""
        if not self.amenities:
            return []
        try:
            return json.loads(self.amenities)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_amenities(self, amenities: List[str]) -> None:
        """Set amenities as JSON."""
        self.amenities = json.dumps(amenities) if amenities else None

    def get_business_hours(self) -> Dict[str, Dict[str, str]]:
        """Get business hours as structured data."""
        if not self.business_hours:
            return {}
        try:
            return json.loads(self.business_hours)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_business_hours(self, hours: Dict[str, Dict[str, str]]) -> None:
        """Set business hours as JSON.

        Format: {
            "monday": {"open": "09:00", "close": "23:00", "closed": false},
            "tuesday": {"open": "09:00", "close": "23:00", "closed": false},
            ...
        }
        """
        self.business_hours = json.dumps(hours) if hours else None

    def is_open_at(self, day: DayOfWeek, time_check: time) -> bool:
        """Check if hall is open at specific day and time."""
        hours = self.get_business_hours()
        day_name = day.name.lower()

        if day_name not in hours:
            return False

        day_hours = hours[day_name]
        if day_hours.get("closed", False):
            return False

        try:
            open_time = datetime.strptime(day_hours["open"], "%H:%M").time()
            close_time = datetime.strptime(day_hours["close"], "%H:%M").time()

            if open_time <= close_time:
                # Normal day (e.g., 09:00 - 23:00)
                return open_time <= time_check <= close_time
            else:
                # Overnight (e.g., 18:00 - 02:00)
                return time_check >= open_time or time_check <= close_time
        except (ValueError, KeyError):
            return False

    def get_available_users(self, day: Optional[DayOfWeek] = None) -> List["User"]:
        """Get users available at this location."""
        from ..user.models import User

        query = User.query.join(UserLocationAvailability).filter(
            UserLocationAvailability.billiard_hall_id == self.id,
            UserLocationAvailability.is_available.is_(True),
        )

        # Get all available users first, then filter by day in application code if needed
        all_users = query.all()

        if day:
            # Filter by day availability at application level
            filtered_users = []
            for user in all_users:
                # Query the user's availability record for this location directly
                availability = UserLocationAvailability.query.filter_by(
                    user_id=user.id, billiard_hall_id=self.id
                ).first()

                if availability:
                    available_days = availability.get_available_days()
                    if day in available_days:
                        filtered_users.append(user)
            return filtered_users

        return all_users

    def get_full_address(self) -> str:
        """Get formatted full address."""
        parts = []
        if self.address:
            parts.append(self.address)
        if self.city:
            parts.append(self.city)
        if self.postal_code:
            parts.append(self.postal_code)
        if self.country:
            parts.append(self.country)

        return ", ".join(parts)

    def can_be_verified(self) -> bool:
        """Check if hall meets minimum requirements for verification."""
        # Minimum requirements: name (always present) and number of tables
        return self.number_of_tables is not None and self.number_of_tables > 0

    def is_complete_for_verification(self) -> bool:
        """Check if hall has all required data for verification."""
        return self.can_be_verified()

    def __repr__(self) -> str:
        return f"<BilliardHall {self.name}>"


class UserLocationAvailability(BaseModel):
    """User availability preferences for specific billiard halls."""

    __tablename__ = "user_location_availability"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    billiard_hall_id = db.Column(
        db.Integer,
        db.ForeignKey("billiard_hall.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Availability settings
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    available_days = db.Column(
        db.String(20), nullable=True
    )  # JSON array of day numbers

    # Time preferences
    preferred_time_start = db.Column(db.Time, nullable=True)
    preferred_time_end = db.Column(db.Time, nullable=True)

    # Notification preferences for this location
    notify_on_proposals = db.Column(db.Boolean, nullable=False, default=True)
    notify_on_cancellations = db.Column(db.Boolean, nullable=False, default=True)

    # Scheduling preferences
    advance_notice_hours = db.Column(
        db.Integer, nullable=False, default=24
    )  # Minimum advance notice
    max_distance_km = db.Column(db.Float, nullable=True)  # Future: distance filtering

    # Experience tracking
    matches_played_here = db.Column(db.Integer, nullable=False, default=0)
    last_played_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    billiard_hall = db.relationship(
        "BilliardHall", back_populates="user_availabilities"
    )

    # Unique constraint: one availability record per user per location
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "billiard_hall_id", name="uq_user_location_availability"
        ),
    )

    def get_available_days(self) -> List[DayOfWeek]:
        """Get available days as enum list."""
        if not self.available_days:
            return []

        try:
            day_numbers = json.loads(self.available_days)
            return [DayOfWeek(num) for num in day_numbers if 1 <= num <= 7]
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    def set_available_days(self, days: List[DayOfWeek]) -> None:
        """Set available days from enum list."""
        day_numbers = [day.value for day in days]
        self.available_days = json.dumps(day_numbers) if day_numbers else None

    def is_available_at(self, check_datetime: datetime) -> bool:
        """Check if user is available at specific datetime."""
        if not self.is_available:
            return False

        # Check advance notice requirement
        notice_hours = (check_datetime - utc_now()).total_seconds() / 3600
        if notice_hours < self.advance_notice_hours:
            return False

        # Check day availability
        weekday = DayOfWeek(check_datetime.weekday() + 1)  # Convert 0-6 to 1-7
        available_days = self.get_available_days()
        if available_days and weekday not in available_days:
            return False

        # Check time preferences
        if self.preferred_time_start and self.preferred_time_end:
            check_time = check_datetime.time()

            if self.preferred_time_start <= self.preferred_time_end:
                # Normal time range
                if not (
                    self.preferred_time_start <= check_time <= self.preferred_time_end
                ):
                    return False
            else:
                # Overnight time range
                if not (
                    check_time >= self.preferred_time_start
                    or check_time <= self.preferred_time_end
                ):
                    return False

        return True

    def record_match_played(self) -> None:
        """Record that a match was played at this location."""
        self.matches_played_here += 1
        self.last_played_at = utc_now()

    def get_availability_summary(self) -> Dict[str, Any]:
        """Get availability summary for this location."""
        available_days = self.get_available_days()

        return {
            "is_available": self.is_available,
            "available_days": [day.name for day in available_days],
            "preferred_time_start": (
                self.preferred_time_start.strftime("%H:%M")
                if self.preferred_time_start
                else None
            ),
            "preferred_time_end": (
                self.preferred_time_end.strftime("%H:%M")
                if self.preferred_time_end
                else None
            ),
            "advance_notice_hours": self.advance_notice_hours,
            "matches_played_here": self.matches_played_here,
            "last_played_at": (
                self.last_played_at.isoformat() if self.last_played_at else None
            ),
            "notify_on_proposals": self.notify_on_proposals,
        }

    def __repr__(self) -> str:
        return f"<UserLocationAvailability {self.user_id} @ {self.billiard_hall.name}>"
