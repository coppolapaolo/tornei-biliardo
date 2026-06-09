"""
Module: models/rating/__init__.py
Purpose: Rating domain initialization and exports
Requirements: SPECIFICHE.md - Handicap system
"""

from .models import (
    PlayerCategory,
    PlayerRating,
    HandicapRule,
    CategoryHandicapRule,
    RatingHandicapRule,
    CategoryLevel,
    RatingSystem,
)
from .services import RatingService

__all__ = [
    # Models
    "PlayerCategory",
    "PlayerRating",
    "HandicapRule",
    "CategoryHandicapRule",
    "RatingHandicapRule",
    # Enums
    "CategoryLevel",
    "RatingSystem",
    # Services
    # Services
    "RatingService",
]


def register_rating_handlers():
    """Register domain event handlers."""
    from models.events import EventBus, MatchCompletedEvent, MatchReopenedEvent
    from .event_handlers import RatingEventHandlers

    # EventBus.subscribe is a decorator, use register_handler for direct registration
    EventBus.register_handler(
        MatchCompletedEvent, RatingEventHandlers.handle_match_completed
    )
    EventBus.register_handler(
        MatchReopenedEvent, RatingEventHandlers.handle_match_reopened
    )


# Auto-register when module is imported
register_rating_handlers()
