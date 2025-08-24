"""
Module: models/playoff/__init__.py
Purpose: Playoff domain initialization and exports
Requirements: SPECIFICHE.md - Playoff system
"""

from .models import (
    PlayoffConfiguration, PlayoffQualification, PlayoffTournament,
    PlayoffType, QualificationStatus
)
from .services import PlayoffService

__all__ = [
    # Models
    "PlayoffConfiguration",
    "PlayoffQualification", 
    "PlayoffTournament",
    
    # Enums
    "PlayoffType",
    "QualificationStatus",
    
    # Services
    "PlayoffService",
]