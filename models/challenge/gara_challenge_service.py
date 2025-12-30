"""
Module: models/challenge/gara_challenge_service.py
Purpose: DEPRECATED - Backward compatibility re-export

DEPRECATION NOTICE (Sprint 11 - December 2025):
    This module is DEPRECATED. The service has been moved to the Competition domain
    to properly establish domain boundaries (Competition → Challenge, not vice versa).

    Please update your imports:
        OLD: from models.challenge.gara_challenge_service import GaraChallengeService
        NEW: from models.competition.gara_challenge_service import GaraChallengeService

        Or use the package import:
        from models.competition import GaraChallengeService

    This file will be removed in a future release.

    See ADR-004-challenge-gara-decoupling.md for rationale.
"""

import warnings

# Re-export from new location for backward compatibility
from models.competition.gara_challenge_service import GaraChallengeService

# Issue deprecation warning on import
warnings.warn(
    "models.challenge.gara_challenge_service is deprecated. "
    "Import from models.competition.gara_challenge_service instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["GaraChallengeService"]
