"""L'evento della seduta chiusa (ADR-067, punto 6; #184).

La fase 6 aveva lasciato la seduta **muta** di proposito: far emettere un
evento a una tabella nuova avrebbe deciso in silenzio che XP, serie e traguardi
si guadagnano anche a scheda. Quella decisione si prende qui, e la risposta è
sì: una seduta di scheda è un allenamento come una prova del catalogo — di più,
perché è una sequenza decisa prima e portata a termine.

Come per il drill, la scheda **non chiama** la gamification: pubblica un fatto
e chi vuole ascolta.

L'evento porta quante caselle sono state compilate perché una seduta aperta e
chiusa senza segnare niente non è un allenamento, ed è chi ascolta a doverlo
sapere senza ricaricare la seduta.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..events.base import DomainEvent


@dataclass
class TrainingSessionClosedEvent(DomainEvent):
    """Una seduta di scheda è stata chiusa."""

    session_id: int
    sheet_id: int
    sheet_name: str
    user_id: int
    #: Quante caselle sono state compilate. Zero vuol dire che si è aperta la
    #: seduta e non si è segnato niente.
    filled: int = 0
    total: int = 0
    max_total: int = 0
    #: Se la seduta ha superato la soglia della scheda. ``None`` per le schede
    #: che una soglia non ce l'hanno, che è diverso da «non l'ha superata».
    above_threshold: Optional[bool] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "training_sheet"

    @property
    def is_empty(self) -> bool:
        return self.filled == 0

    def get_event_type(self) -> str:
        return "training_sheet.session_closed"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "sheet_id": self.sheet_id,
            "sheet_name": self.sheet_name,
            "user_id": self.user_id,
            "filled": self.filled,
            "total": self.total,
            "max_total": self.max_total,
            "above_threshold": self.above_threshold,
        }


__all__ = ["TrainingSessionClosedEvent"]
