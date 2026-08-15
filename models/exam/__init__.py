"""
Module: models/exam/__init__.py
Purpose: Dominio esame — esami come sequenza di drill, certificati di persona.
Requirements: ADR-042 (esame certificato di persona)
"""

from .models import (
    Exam,
    ExamAttempt,
    ExamChallenge,
    ExamChallengeResult,
    ExamExaminer,
)
from .services import ExamService

__all__ = [
    # Models
    "Exam",
    "ExamExaminer",
    "ExamChallenge",
    "ExamAttempt",
    "ExamChallengeResult",
    # Services
    "ExamService",
]
