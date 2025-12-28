"""
Classification domain models and services

This module contains all classification-related models, services, and functionality
following Domain-Driven Design principles.

Domain: Classification & Ranking Management
- Campionato classification tracking
- Round-by-round classification for Amalfi system
- Gara final classification with tiebreaker support
- Player encounter tracking for anti-reincontro logic
- Ranking calculations and tie-breaking rules
- Pluggable classification strategies (Amalfi, Random, Point-based)

Author: Refactoring Phase 2 - Sprint 1, Phase 5 - Strategy Pattern Refactor
Created: 2025-08-06
Updated: 2025-12-28
"""

from .models import Classification, RoundClassification, GaraClassification, PlayerEncounter

# Strategy pattern components
from .strategies.base import (
    ClassificationScope,
    PlayerScore,
    ClassificationEntry,
    ClassificationResult,
    ClassificationStrategy,
)
from .registry import get_classification_registry, ClassificationStrategyRegistry
from .score_aggregator import ScoreAggregator
from .tiebreaker_resolver import TiebreakerResolver, TiebreakerContext

# Services
from .services import (
    ClassificationService,
    RoundClassificationService,
    GaraClassificationService,
    StrategyBasedClassificationService,
    PlayerEncounterService,
)

# Export all public classes and functions
__all__ = [
    # Models
    "Classification",
    "RoundClassification",
    "GaraClassification",
    "PlayerEncounter",
    # Strategy base
    "ClassificationScope",
    "PlayerScore",
    "ClassificationEntry",
    "ClassificationResult",
    "ClassificationStrategy",
    # Registry
    "get_classification_registry",
    "ClassificationStrategyRegistry",
    # Support classes
    "ScoreAggregator",
    "TiebreakerResolver",
    "TiebreakerContext",
    # Services
    "ClassificationService",
    "RoundClassificationService",
    "GaraClassificationService",
    "StrategyBasedClassificationService",
    "PlayerEncounterService",
]

# Domain version and metadata
__version__ = "2.0.0"
__domain__ = "Classification & Ranking Management"
__phase__ = "Phase 5 - Strategy Pattern Refactor"
