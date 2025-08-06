"""
Classification domain models and services

This module contains all classification-related models, services, and functionality
following Domain-Driven Design principles.

Domain: Classification & Ranking Management
- Tournament classification tracking
- Round-by-round classification for Amalfi system
- Player encounter tracking for anti-reincontro logic
- Ranking calculations and tie-breaking rules

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-06
"""

from .models import Classification, RoundClassification, PlayerEncounter

# Export all public classes and functions
__all__ = [
    # Models
    "Classification",
    "RoundClassification",
    "PlayerEncounter",
]

# Domain version and metadata
__version__ = "1.0.0"
__domain__ = "Classification & Ranking Management"
__phase__ = "Phase 2 - Sprint 1"
