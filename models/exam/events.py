"""Eventi di dominio dell'esame (ADR-042).

L'esame non chiama la gamification: pubblica un fatto e chi vuole ascolta. È la
regola dell'architettura a eventi già in uso (``models/gamification/CLAUDE.md``:
«Do not call gamification services directly from other domains»).

L'evento porta ``mode`` e ``passed`` perché **è lì che sta la differenza**: solo
la sessione certificata e superata vale una certificazione; il tentativo in
autonomia è allenamento e non certifica mai, nemmeno a posteriori. Chi ascolta
non deve ricaricare il tentativo per saperlo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..events.base import DomainEvent


@dataclass
class ExamAttemptCompletedEvent(DomainEvent):
    """Un tentativo d'esame si è chiuso — in autonomia o certificato.

    Non viene pubblicato per i tentativi abbandonati: il candidato che non si
    presenta non ha completato nulla, e ``passed`` resta NULL.
    """

    attempt_id: int
    exam_id: int
    exam_name: str
    user_id: int
    mode: str
    #: Valorizzato solo in modalità certificata; NULL in autonomia.
    passed: Optional[bool] = None
    examiner_id: Optional[int] = None
    total_score: int = 0
    max_possible_score: int = 0

    def __post_init__(self):
        super().__post_init__()
        self.domain = "exam"

    @property
    def is_certified(self) -> bool:
        """True se la sessione era certificata (a prescindere dall'esito)."""
        from ..status_enum import ExamAttemptMode

        return self.mode == ExamAttemptMode.CERTIFIED.value

    @property
    def is_certification(self) -> bool:
        """True solo se l'esame è stato **superato** davanti a un esaminatore."""
        return self.is_certified and bool(self.passed)

    def get_event_type(self) -> str:
        return "exam.attempt_completed"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "exam_id": self.exam_id,
            "exam_name": self.exam_name,
            "user_id": self.user_id,
            "mode": self.mode,
            "passed": self.passed,
            "examiner_id": self.examiner_id,
            "total_score": self.total_score,
            "max_possible_score": self.max_possible_score,
        }


__all__ = ["ExamAttemptCompletedEvent"]
