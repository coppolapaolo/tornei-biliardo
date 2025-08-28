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
    "RatingService",
]
