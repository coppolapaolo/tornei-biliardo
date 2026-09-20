"""
Module: models/obiettivo/__init__.py
Purpose: Gli obiettivi di allenamento — porli, misurarli, timbrarli.
Requirements: issue #316, e la parte «obiettivi» della #175
"""

from .kinds import (
    FINESTRA_MEDIA,
    MAX_ATTIVI,
    MAX_SETTIMANE,
    MAX_VOLTE,
    MIN_SETTIMANE,
    MIN_VOLTE,
    GoalDeadline,
    GoalKind,
    GoalRule,
)
from .models import TrainingGoal
from .progress import GoalProgress, build_all, build_progress
from .service import TrainingGoalService

__all__ = [
    # Modello
    "TrainingGoal",
    # Vocabolario
    "GoalDeadline",
    "GoalKind",
    "GoalRule",
    "FINESTRA_MEDIA",
    "MAX_ATTIVI",
    "MAX_SETTIMANE",
    "MAX_VOLTE",
    "MIN_SETTIMANE",
    "MIN_VOLTE",
    # Lettura e servizio
    "GoalProgress",
    "TrainingGoalService",
    "build_all",
    "build_progress",
]
