"""
Models package initialization - Phase 2 Sprint 1 Complete

This module provides domain-driven model organization while maintaining
backward compatibility with existing code.

Phase Status:
- ✅ Base infrastructure complete
- ✅ User domain extracted and modularized
- ✅ Tournament domain extracted
- ✅ Competition domain extracted
- ✅ Match domain extracted
- ✅ Classification domain extracted
- ⚠️ Playoff still in legacy_models.py (future sprint)

Author: Refactoring Phase 2 - Sprint 1
Updated: 2025-08-06
"""

# Import database instance and utilities from base module
from .base import (
    db,
    get_or_create,
    bulk_create,
    safe_commit,
    init_db,
    reset_db,
)

# PHASE 1 COMPLETE: User domain imported from modular structure
from .user.models import User, TournamentDirector, DirectorRequest

# PHASE 2 SPRINT 1 COMPLETE: All domains separated
from .tournament.models import Tournament
from .competition.models import Prova, Inscription
from .match.models import Match, Rack, MatchResult, TrioMatch
from .classification.models import Classification, RoundClassification, PlayerEncounter

# PHASE 2 TODO: Import remaining model from legacy_models.py
from .legacy_models import Playoff

# Export all available models for backward compatibility
__all__ = [
    # Database and utilities
    "db",
    "get_or_create",
    "bulk_create",
    "safe_commit",
    "init_db",
    "reset_db",
    # User domain models (Phase 1)
    "User",
    "TournamentDirector",
    "DirectorRequest",
    # Tournament domain models (Phase 2 Sprint 1)
    "Tournament",
    # Competition domain models (Phase 2 Sprint 1)
    "Prova",
    "Inscription",
    # Match domain models (Phase 2 Sprint 1)
    "Match",
    "Rack",
    "MatchResult",
    "TrioMatch",
    # Classification domain models (Phase 2 Sprint 1)
    "Classification",
    "RoundClassification",
    "PlayerEncounter",
    # Legacy models (future sprints)
    "Playoff",
]

# Phase tracking
__version__ = "2.0.0-sprint1"
__phase__ = "Phase 2 Sprint 1: Domain Separation COMPLETE"
