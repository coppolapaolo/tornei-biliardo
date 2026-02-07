"""
Module: models/challenge/__init__.py
Purpose: Challenge domain initialization and exports
Requirements: SPECIFICHE.md - Challenge system
"""

from .models import Challenge, ChallengeAttempt, ChallengeFavorite
from .services import ChallengeService

__all__ = [
    "Challenge",
    "ChallengeAttempt",
    "ChallengeFavorite",
    "ChallengeService",
]
