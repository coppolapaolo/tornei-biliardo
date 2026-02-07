"""
Module: models/rating/services.py
Purpose: Re-export shim for rating domain services (split in Round 6)
"""

from .rating_service import RatingService, CategoryService
from .handicap_service import HandicapService

__all__ = [
    "RatingService",
    "CategoryService",
    "HandicapService",
]
