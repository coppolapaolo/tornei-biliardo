"""
Module: models/challenge/__init__.py
Purpose: Challenge domain initialization and exports
Requirements: SPECIFICHE.md - Challenge system
"""

from .models import Challenge, ChallengeAttempt, ChallengeFavorite
from .gara_challenge_models import (
    GaraChallenge,
    GaraChallengeAttempt,
    GaraChallengeClassification,
)
from .services import ChallengeService
from .gara_challenge_service import GaraChallengeService

__all__ = [
    # Models
    "Challenge",
    "ChallengeAttempt",
    "ChallengeFavorite",
    # Gara Challenge Models
    "GaraChallenge",
    "GaraChallengeAttempt",
    "GaraChallengeClassification",
    # Services
    "ChallengeService",
    "GaraChallengeService",
]
