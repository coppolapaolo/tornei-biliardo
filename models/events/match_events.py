"""
Match domain events for the community platform.

These events represent significant occurrences in match proposals,
individual matches, and match execution workflows.
"""

from __future__ import annotations

from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from .base import DomainEvent


@dataclass
class MatchProposalCreatedEvent(DomainEvent):
    """Event published when a player creates a match proposal."""

    proposal_id: int
    proposer_id: int
    proposer_name: str
    target_user_id: Optional[int] = None
    target_username: Optional[str] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    notes: Optional[str] = None
    is_public: bool = True

    def __post_init__(self):
        super().__post_init__()
        self.domain = "match"

    def get_event_type(self) -> str:
        return "match.proposal_created"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposer_id": self.proposer_id,
            "proposer_name": self.proposer_name,
            "target_user_id": self.target_user_id,
            "target_username": self.target_username,
            "location_id": self.location_id,
            "location_name": self.location_name,
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None,
            "notes": self.notes,
            "is_public": self.is_public
        }


@dataclass
class MatchAcceptedEvent(DomainEvent):
    """Event published when a match proposal is accepted."""

    proposal_id: int
    match_id: int
    proposer_id: int
    proposer_name: str
    accepter_id: int
    accepter_name: str
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    scheduled_time: Optional[datetime] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "match"

    def get_event_type(self) -> str:
        return "match.accepted"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "match_id": self.match_id,
            "proposer_id": self.proposer_id,
            "proposer_name": self.proposer_name,
            "accepter_id": self.accepter_id,
            "accepter_name": self.accepter_name,
            "location_id": self.location_id,
            "location_name": self.location_name,
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None
        }


@dataclass
class MatchCompletedEvent(DomainEvent):
    """Event published when a match is completed."""

    match_id: int
    player1_id: int
    player1_name: str
    player2_id: int
    player2_name: str
    winner_id: Optional[int] = None
    winner_name: Optional[str] = None
    score: Optional[str] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "match"

    def get_event_type(self) -> str:
        return "match.completed"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "match_id": self.match_id,
            "player1_id": self.player1_id,
            "player1_name": self.player1_name,
            "player2_id": self.player2_id,
            "player2_name": self.player2_name,
            "winner_id": self.winner_id,
            "winner_name": self.winner_name,
            "score": self.score,
            "location_id": self.location_id,
            "location_name": self.location_name
        }


@dataclass
class IndividualMatchCreatedEvent(DomainEvent):
    """Event published when an individual match is created from a proposal."""

    match_id: int
    proposal_id: int
    player1_id: int
    player1_name: str
    player2_id: int
    player2_name: str
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    scheduled_time: Optional[datetime] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "match"

    def get_event_type(self) -> str:
        return "match.individual_created"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "match_id": self.match_id,
            "proposal_id": self.proposal_id,
            "player1_id": self.player1_id,
            "player1_name": self.player1_name,
            "player2_id": self.player2_id,
            "player2_name": self.player2_name,
            "location_id": self.location_id,
            "location_name": self.location_name,
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None
        }