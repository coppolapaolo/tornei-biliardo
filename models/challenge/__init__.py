"""
Module: models/challenge/__init__.py
Purpose: Challenge domain initialization and exports
Requirements: SPECIFICHE.md - Challenge system
"""

from .models import (
    Challenge,
    ChallengeAttempt,
    ChallengeCategory,
    ChallengeFavorite,
    ChallengeRating,
    ChallengeVariant,
)
from .profile_service import ChallengeProfileService
from .services import ChallengeService

__all__ = [
    "Challenge",
    "ChallengeAttempt",
    "ChallengeCategory",
    "ChallengeFavorite",
    "ChallengeProfileService",
    "ChallengeRating",
    "ChallengeVariant",
    "ChallengeService",
]
