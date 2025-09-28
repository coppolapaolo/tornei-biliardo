"""
Player availability domain events for the community platform.

These events represent significant occurrences in player availability
and location-based match notifications.
"""

from __future__ import annotations

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

from .base import DomainEvent


@dataclass
class PlayerAvailabilityCreatedEvent(DomainEvent):
    """Event published when a player sets their availability at a location."""

    availability_id: int
    user_id: int
    username: str
    location_id: int
    location_name: str
    available_from: datetime
    available_until: Optional[datetime] = None
    notes: Optional[str] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "availability"

    def get_event_type(self) -> str:
        return "availability.player_available"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "availability_id": self.availability_id,
            "user_id": self.user_id,
            "username": self.username,
            "location_id": self.location_id,
            "location_name": self.location_name,
            "available_from": self.available_from.isoformat(),
            "available_until": self.available_until.isoformat() if self.available_until else None,
            "notes": self.notes
        }


@dataclass
class AvailabilityNotificationEvent(DomainEvent):
    """Event published when players should be notified about availability at a location."""

    location_id: int
    location_name: str
    available_user_id: int
    available_username: str
    notification_user_ids: List[int]
    notification_message: str
    notification_context: Dict[str, Any]

    def __post_init__(self):
        super().__post_init__()
        self.domain = "availability"

    def get_event_type(self) -> str:
        return "availability.notification_required"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "location_id": self.location_id,
            "location_name": self.location_name,
            "available_user_id": self.available_user_id,
            "available_username": self.available_username,
            "notification_user_ids": self.notification_user_ids,
            "notification_message": self.notification_message,
            "notification_context": self.notification_context
        }