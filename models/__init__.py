"""
Models package initialization - Phase 2 Sprint 1 Update

This module provides domain-driven model organization while maintaining
backward compatibility with existing code.

Phase Status:
- ✅ Base infrastructure complete
- ✅ User domain extracted and modularized
- ✅ Tournament domain extracted
- 🏃 Competition domain extraction in progress
- ⚠️ Other domains in legacy_models.py (Sprint 1 target)

Author: Refactoring Phase 2 - Sprint 1
Updated: 2025-08-05
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

# PHASE 2 SPRINT 1: Separated domains
from .tournament.models import Tournament
from .competition.models import Prova, Inscription

# PHASE 2 TODO: Import remaining models from legacy_models.py
from .legacy_models import (
    # Tournament,  # Now imported from tournament domain
    # Prova,       # Now imported from competition domain
    # Inscription, # Now imported from competition domain
    Match,
    Rack,
    MatchResult,
    Classification,
    Playoff,
    PlayerEncounter,
    RoundClassification,
    TrioMatch,
)

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
    # Legacy models (Phase 2 Sprint 1 target)
    "Match",
    "Rack",
    "MatchResult",
    "Classification",
    "Playoff",
    "PlayerEncounter",
    "RoundClassification",
    "TrioMatch",
]

# Phase tracking
__version__ = "2.0.0-sprint1-wip"
__phase__ = "Phase 2 Sprint 1: Domain Separation"
