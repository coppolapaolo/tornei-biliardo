"""
Tiebreaker domain models and services

This module contains all tiebreaker-related models, services, and functionality
following Domain-Driven Design principles.

Domain: Tiebreaker Management
- Tiebreaker entity and lifecycle
- Spot shot tracking for 8-ball/9-ball
- Rally tracking for straight pool
- Playoff match management
- Configuration and rules

Author: Refactoring Phase 4 - Final Sprint
Created: 2025-01-28
"""

from .models import (
    Tiebreaker,
    SpotShot,
    RallyAttempt,
    PlayoffMatch,
    TiebreakerConfiguration,
    TiebreakerType,
    TiebreakerStatus,
    SpotShotResult
)

from .services import (
    TiebreakerService,
    TiebreakerConfigurationService
)

# Export all public classes and functions
__all__ = [
    # Models
    "Tiebreaker",
    "SpotShot",
    "RallyAttempt", 
    "PlayoffMatch",
    "TiebreakerConfiguration",
    # Enums
    "TiebreakerType",
    "TiebreakerStatus",
    "SpotShotResult",
    # Services
    "TiebreakerService",
    "TiebreakerConfigurationService",
]

# Domain version and metadata
__version__ = "1.0.0"
__domain__ = "tiebreaker"