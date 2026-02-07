"""
Module: models/classification/services.py
Purpose: Re-export shim for classification domain services (split in Round 6)
"""

from .campionato_classification import ClassificationService
from .gara_classification import (
    RoundClassificationService,
    GaraClassificationService,
    StrategyBasedClassificationService,
    visible_user_ids_for_gara,
)
from .encounter_service import PlayerEncounterService

__all__ = [
    "ClassificationService",
    "RoundClassificationService",
    "GaraClassificationService",
    "StrategyBasedClassificationService",
    "PlayerEncounterService",
    "visible_user_ids_for_gara",
]
