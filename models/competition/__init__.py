"""
Competition domain models and services

This module contains all competition-related models, services, and functionality
following Domain-Driven Design principles.

Domain: Competition Management
- Gara (competition rounds) entity and lifecycle
- Inscription (player registration) management
- Competition configuration and rules
- GaraChallenge integration (challenges within competitions)
- GaraByeChallenge (bye replacement with challenges)

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-05
Updated: 2025-12-30 (Sprint 11 - Challenge/Gara decoupling)
"""

from .models import Gara, Inscription

# Challenge integration models (moved from challenge domain in Sprint 11)
from .gara_challenge import (
    GaraChallenge,
    GaraChallengeAttempt,
    GaraChallengeClassification,
)
from .gara_bye_challenge import GaraByeChallenge
from .gara_challenge_service import GaraChallengeService

# Export all public classes and functions
__all__ = [
    # Core Models
    "Gara",
    "Inscription",
    # Challenge Integration (Sprint 11)
    "GaraChallenge",
    "GaraChallengeAttempt",
    "GaraChallengeClassification",
    "GaraByeChallenge",
    "GaraChallengeService",
]

# Domain version and metadata
__version__ = "2.0.0"
__domain__ = "Competition Management"
__phase__ = "Phase 2 - Sprint 11 (Challenge Decoupling)"
