"""
Module: models/challenge/gara_challenge_models.py
Purpose: DEPRECATED - Backward compatibility re-exports

DEPRECATION NOTICE (Sprint 11 - December 2025):
    This module is DEPRECATED. The models have been moved to the Competition domain
    to properly establish domain boundaries (Competition → Challenge, not vice versa).

    Please update your imports:
        OLD: from models.challenge.gara_challenge_models import GaraChallenge
        NEW: from models.competition.gara_challenge import GaraChallenge

        OLD: from models.challenge.gara_challenge_models import GaraChallengeAttempt
        NEW: from models.competition.gara_challenge import GaraChallengeAttempt

        OLD: from models.challenge.gara_challenge_models import GaraChallengeClassification
        NEW: from models.competition.gara_challenge import GaraChallengeClassification

    This file will be removed in a future release.

    See ADR-004-challenge-gara-decoupling.md for rationale.
"""

import warnings

# Re-export from new location for backward compatibility
from models.competition.gara_challenge import (
    GaraChallenge,
    GaraChallengeAttempt,
    GaraChallengeClassification,
)

# Issue deprecation warning on import
warnings.warn(
    "models.challenge.gara_challenge_models is deprecated. "
    "Import from models.competition.gara_challenge instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "GaraChallenge",
    "GaraChallengeAttempt",
    "GaraChallengeClassification",
]
