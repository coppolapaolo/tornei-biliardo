"""
Competition domain events for the community platform.

These events represent significant occurrences in competition management,
registrations, and tournament workflows.
"""

from __future__ import annotations

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

from .base import DomainEvent


@dataclass
class CompetitionCreatedEvent(DomainEvent):
    """Event published when a new competition (gara) is created."""

    gara_id: int
    name: str
    creator_id: int
    creator_name: str
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    min_participants: int = 4
    max_participants: Optional[int] = None
    registration_deadline: Optional[datetime] = None
    is_campionato: bool = False
    campionato_id: Optional[int] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "competition"

    def get_event_type(self) -> str:
        return "competition.created"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "gara_id": self.gara_id,
            "name": self.name,
            "creator_id": self.creator_id,
            "creator_name": self.creator_name,
            "location_id": self.location_id,
            "location_name": self.location_name,
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None,
            "min_participants": self.min_participants,
            "max_participants": self.max_participants,
            "registration_deadline": self.registration_deadline.isoformat() if self.registration_deadline else None,
            "is_campionato": self.is_campionato,
            "campionato_id": self.campionato_id
        }


@dataclass
class CompetitionRegistrationOpenedEvent(DomainEvent):
    """Event published when registration opens for a competition."""

    gara_id: int
    name: str
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    registration_deadline: Optional[datetime] = None
    eligible_user_ids: Optional[List[int]] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "competition"

    def get_event_type(self) -> str:
        return "competition.registration_opened"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "gara_id": self.gara_id,
            "name": self.name,
            "location_id": self.location_id,
            "location_name": self.location_name,
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None,
            "registration_deadline": self.registration_deadline.isoformat() if self.registration_deadline else None,
            "eligible_user_ids": self.eligible_user_ids
        }


@dataclass
class CompetitionStartedEvent(DomainEvent):
    """Event published when a competition starts (first round created)."""

    gara_id: int
    name: str
    participant_count: int
    participant_ids: List[int]
    round_number: int = 1
    strategy: Optional[str] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "competition"

    def get_event_type(self) -> str:
        return "competition.started"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "gara_id": self.gara_id,
            "name": self.name,
            "participant_count": self.participant_count,
            "participant_ids": self.participant_ids,
            "round_number": self.round_number,
            "strategy": self.strategy,
            "location_id": self.location_id,
            "location_name": self.location_name
        }


@dataclass
class CompetitionCompletedEvent(DomainEvent):
    """Event published when a competition is completed."""

    gara_id: int
    name: str
    winner_id: Optional[int] = None
    winner_name: Optional[str] = None
    final_standings: Optional[List[Dict[str, Any]]] = None
    total_participants: int = 0
    total_rounds: int = 0
    location_id: Optional[int] = None
    location_name: Optional[str] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "competition"

    def get_event_type(self) -> str:
        return "competition.completed"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "gara_id": self.gara_id,
            "name": self.name,
            "winner_id": self.winner_id,
            "winner_name": self.winner_name,
            "final_standings": self.final_standings,
            "total_participants": self.total_participants,
            "total_rounds": self.total_rounds,
            "location_id": self.location_id,
            "location_name": self.location_name
        }


@dataclass
class InscriptionCreatedEvent(DomainEvent):
    """Event published when a player registers for a competition."""

    inscription_id: int
    gara_id: int
    gara_name: str
    user_id: int
    username: str
    inscription_status: str = "confirmed"
    waitlist_position: Optional[int] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "competition"

    def get_event_type(self) -> str:
        return "competition.inscription_created"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "inscription_id": self.inscription_id,
            "gara_id": self.gara_id,
            "gara_name": self.gara_name,
            "user_id": self.user_id,
            "username": self.username,
            "inscription_status": self.inscription_status,
            "waitlist_position": self.waitlist_position,
            "location_id": self.location_id,
            "location_name": self.location_name
        }