"""
User domain events for the community platform.

These events represent significant occurrences in user management,
director promotions, and venue management requests.
"""

from __future__ import annotations

from typing import Dict, Any, Optional
from dataclasses import dataclass

from .base import DomainEvent


@dataclass
class UserRegisteredEvent(DomainEvent):
    """Event published when a new user registers on the platform."""

    user_id: int
    username: str
    email: str
    role: str = "player"

    def __post_init__(self):
        super().__post_init__()
        self.domain = "user"

    def get_event_type(self) -> str:
        return "user.registered"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role
        }


@dataclass
class DirectorRequestCreatedEvent(DomainEvent):
    """Event published when a player requests director promotion."""

    request_id: int
    user_id: int
    username: str
    motivation: str
    admin_user_ids: list[int]

    def __post_init__(self):
        super().__post_init__()
        self.domain = "user"

    def get_event_type(self) -> str:
        return "user.director_request_created"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "username": self.username,
            "motivation": self.motivation,
            "admin_user_ids": self.admin_user_ids
        }


@dataclass
class DirectorRequestProcessedEvent(DomainEvent):
    """Event published when a director request is approved or rejected."""

    request_id: int
    user_id: int
    username: str
    status: str  # 'approved' or 'rejected'
    processed_by_id: int
    notes: Optional[str] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "user"

    def get_event_type(self) -> str:
        return f"user.director_request_{self.status}"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "username": self.username,
            "status": self.status,
            "processed_by_id": self.processed_by_id,
            "notes": self.notes
        }


@dataclass
class VenueManagerRequestCreatedEvent(DomainEvent):
    """Event published when a user requests to manage a venue."""

    request_id: int
    user_id: int
    username: str
    venue_id: int
    venue_name: str
    motivation: str
    admin_user_ids: list[int]
    is_contested: bool = False

    def __post_init__(self):
        super().__post_init__()
        self.domain = "user"

    def get_event_type(self) -> str:
        return "user.venue_manager_request_created"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "username": self.username,
            "venue_id": self.venue_id,
            "venue_name": self.venue_name,
            "motivation": self.motivation,
            "admin_user_ids": self.admin_user_ids,
            "is_contested": self.is_contested
        }


@dataclass
class VenueManagerRequestProcessedEvent(DomainEvent):
    """Event published when a venue manager request is approved or rejected."""

    request_id: int
    user_id: int
    username: str
    venue_id: int
    venue_name: str
    status: str  # 'approved' or 'rejected'
    processed_by_id: int
    notes: Optional[str] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "user"

    def get_event_type(self) -> str:
        return f"user.venue_manager_request_{self.status}"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "username": self.username,
            "venue_id": self.venue_id,
            "venue_name": self.venue_name,
            "status": self.status,
            "processed_by_id": self.processed_by_id,
            "notes": self.notes
        }