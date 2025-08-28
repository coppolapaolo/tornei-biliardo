"""
Module: models/exam/__init__.py
Purpose: Exam domain initialization and exports
Requirements: SPECIFICHE.md - Exam system
"""

from .models import Exam, ExamChallenge, ExamAttempt, ExamChallengeResult
from .services import ExamService

__all__ = [
    # Models
    "Exam",
    "ExamChallenge",
    "ExamAttempt",
    "ExamChallengeResult",
    # Services
    "ExamService",
]
