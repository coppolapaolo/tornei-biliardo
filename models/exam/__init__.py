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
from .request_models import (
    ExamRequest,
    ExamRequestRecipient,
    ExamTimeProposal,
)
from .request_service import ExamRequestService
from .services import CompositionItem, ExamService

__all__ = [
    # Models
    "Exam",
    "ExamExaminer",
    "ExamChallenge",
    "ExamAttempt",
    "ExamChallengeResult",
    # Appuntamento d'esame (Fase 3)
    "ExamRequest",
    "ExamRequestRecipient",
    "ExamTimeProposal",
    # Services
    "ExamService",
    "CompositionItem",
    "ExamRequestService",
]
