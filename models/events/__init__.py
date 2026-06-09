"""
Event system for domain decoupling.

This module provides the event-driven architecture to decouple business domains
and replace direct service dependencies with publish-subscribe patterns.

Usage:
    from models.events import EventBus, DomainEvent

    # Publish an event
    EventBus.publish(UserRegisteredEvent(user_id=123))

    # Subscribe to events
    @EventBus.subscribe(UserRegisteredEvent)
    def handle_user_registered(event):
        # Handle the event
        pass
"""

from .base import DomainEvent, EventBus
from .user_events import (
    UserRegisteredEvent,
    DirectorRequestCreatedEvent,
    DirectorRequestProcessedEvent,
    VenueManagerRequestCreatedEvent,
    VenueManagerRequestProcessedEvent,
)
from .match_events import (
    MatchProposalCreatedEvent,
    MatchAcceptedEvent,
    MatchCompletedEvent,
    MatchReopenedEvent,
    IndividualMatchCreatedEvent,
)
from .competition_events import (
    CompetitionCreatedEvent,
    CompetitionRegistrationOpenedEvent,
    CompetitionStartedEvent,
    CompetitionCompletedEvent,
    InscriptionCreatedEvent,
)
from .availability_events import (
    PlayerAvailabilityCreatedEvent,
    AvailabilityNotificationEvent,
)

# Import notification handlers to auto-register them
from . import notification_handlers  # noqa: F401

__all__ = [
    # Core event system
    "DomainEvent",
    "EventBus",
    # User domain events
    "UserRegisteredEvent",
    "DirectorRequestCreatedEvent",
    "DirectorRequestProcessedEvent",
    "VenueManagerRequestCreatedEvent",
    "VenueManagerRequestProcessedEvent",
    # Match domain events
    "MatchProposalCreatedEvent",
    "MatchAcceptedEvent",
    "MatchCompletedEvent",
    "MatchReopenedEvent",
    "IndividualMatchCreatedEvent",
    # Competition domain events
    "CompetitionCreatedEvent",
    "CompetitionRegistrationOpenedEvent",
    "CompetitionStartedEvent",
    "CompetitionCompletedEvent",
    "InscriptionCreatedEvent",
    # Availability domain events
    "PlayerAvailabilityCreatedEvent",
    "AvailabilityNotificationEvent",
]
