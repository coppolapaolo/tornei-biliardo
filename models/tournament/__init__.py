"""
Tournament domain models and services

This module contains all tournament-related models, services, and functionality
following Domain-Driven Design principles.

Domain: Tournament Management
- Tournament entity and lifecycle
- Tournament configuration and strategies
- Tournament status management

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-05
"""

from .models import Tournament

# Export all public classes and functions
__all__ = [
    # Models
    "Tournament",
]

# Domain version and metadata
__version__ = "1.0.0"
__domain__ = "Tournament Management"
__phase__ = "Phase 2 - Sprint 1"
