"""
Module: models/challenge/__init__.py
Purpose: Challenge domain initialization and exports
Requirements: SPECIFICHE.md - Challenge system

Note (Sprint 11 - December 2025):
    GaraChallenge models and service have been moved to the Competition domain.
    They are re-exported here for backward compatibility but imports from
    models.competition are preferred.

    See ADR-004-challenge-gara-decoupling.md for rationale.
"""

from .models import Challenge, ChallengeAttempt, ChallengeFavorite
from .services import ChallengeService

# Re-export from Competition domain for backward compatibility
# DEPRECATED: Import directly from models.competition instead
from models.competition.gara_challenge import (
    GaraChallenge,
    GaraChallengeAttempt,
    GaraChallengeClassification,
)
from models.competition.gara_challenge_service import GaraChallengeService

__all__ = [
    # Core Challenge Models (pure domain)
    "Challenge",
    "ChallengeAttempt",
    "ChallengeFavorite",
    "ChallengeService",
    # DEPRECATED: Re-exports from Competition domain
    # Import from models.competition instead
    "GaraChallenge",
    "GaraChallengeAttempt",
    "GaraChallengeClassification",
    "GaraChallengeService",
]
