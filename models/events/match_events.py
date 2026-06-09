"""
Match domain events for the community platform.

These events represent significant occurrences in match proposals,
individual matches, and match execution workflows.
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional
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
            "scheduled_time": (
                self.scheduled_time.isoformat() if self.scheduled_time else None
            ),
            "notes": self.notes,
            "is_public": self.is_public,
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
            "scheduled_time": (
                self.scheduled_time.isoformat() if self.scheduled_time else None
            ),
        }


@dataclass
class MatchCompletedEvent(DomainEvent):
    """Event published when a match is completed.

    `player_ids` carries the full participant roster (trio = 3, 2-player = 2).
    Handlers iterating per-player side effects (streak/quest) must prefer this
    field over (`player1_id`, `player2_id`) so that trio `player3` is not
    silently skipped — `player1_id`/`player2_id` map to `Match.player1_id` and
    `Match.player2_id`, which in trios are only the first two of three.
    Optional for backward compatibility; fallback is `[player1_id, player2_id]`.
    """

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
    gara_id: Optional[int] = None  # For SSE routing to gara detail page
    player_ids: Optional[List[int]] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "match"

    def get_event_type(self) -> str:
        return "match.completed"

    def get_all_player_ids(self) -> List[int]:
        """All participant ids — trio p3 included when `player_ids` is populated."""
        if self.player_ids:
            return list(self.player_ids)
        return [pid for pid in (self.player1_id, self.player2_id) if pid is not None]

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
            "location_name": self.location_name,
            "gara_id": self.gara_id,
            "player_ids": list(self.player_ids) if self.player_ids else None,
        }


@dataclass
class MatchReopenedEvent(DomainEvent):
    """Pubblicato quando un match completato viene riaperto/resettato.

    Permette al rating handler di annullare (revert) i delta Elo applicati per
    quel match, mantenendo `match_rating_history` coerente. Idempotente lato
    handler: se non c'è history da annullare è un no-op.
    """

    match_id: int

    def __post_init__(self):
        super().__post_init__()
        self.domain = "match"

    def get_event_type(self) -> str:
        return "match.reopened"

    def _get_event_data(self) -> Dict[str, Any]:
        return {"match_id": self.match_id}


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
            "scheduled_time": (
                self.scheduled_time.isoformat() if self.scheduled_time else None
            ),
        }
