"""
Match domain models and services

This module contains all match-related models, services, and functionality
following Domain-Driven Design principles.

Domain: Match Management
- Match entity and lifecycle
- Rack tracking for detailed scoring
- Match result submission and validation
- Trio match special handling

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-05
"""

from .models import Match, Rack, MatchResult, TrioMatch

# Export all public classes and functions
__all__ = [
    # Models
    "Match",
    "Rack",
    "MatchResult",
    "TrioMatch",
]

# Domain version and metadata
__version__ = "1.0.0"
__domain__ = "Match Management"
__phase__ = "Phase 2 - Sprint 1"
