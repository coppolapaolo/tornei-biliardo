"""
Competition domain models and services

This module contains all competition-related models, services, and functionality
following Domain-Driven Design principles.

Domain: Competition Management
- Gara (competition rounds) entity and lifecycle
- Inscription (player registration) management
- Competition configuration and rules

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-05
"""

from .models import Gara, Inscription

# Export all public classes and functions
__all__ = [
    # Models
    "Gara",
    "Inscription",
]

# Domain version and metadata
__version__ = "1.0.0"
__domain__ = "Competition Management"
__phase__ = "Phase 2 - Sprint 1"
