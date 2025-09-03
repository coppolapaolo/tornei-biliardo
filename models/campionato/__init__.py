"""
Campionato domain models and services

This module contains all campionato-related models, services, and functionality
following Domain-Driven Design principles.

Domain: Campionato Management
- Campionato entity and lifecycle
- Campionato configuration and strategies
- Campionato status management

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-05
"""

from .models import Campionato

# Export all public classes and functions
__all__ = [
    # Models
    "Campionato",
]

# Domain version and metadata
__version__ = "1.0.0"
__domain__ = "Campionato Management"
__phase__ = "Phase 2 - Sprint 1"
