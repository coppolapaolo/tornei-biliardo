"""Eventi di dominio del drill.

Il drill non chiama la gamification: pubblica un fatto e chi vuole ascolta —
la stessa regola che l'esame segue già (``models/gamification/CLAUDE.md``: «Do
not call gamification services directly from other domains»).

L'evento porta l'**origine** perché è lì che sta la differenza fra i due modi
di allenarsi. Dal catalogo il giocatore sceglie un drill e lo completa: un
tentativo, una sessione. In gara lo stesso drill si prova più volte nello
stesso turno — è la stessa prova ripetuta, non tre allenamenti — e il
direttore le registra spesso in blocco. Chi ascolta deve poterle distinguere
senza ricaricare nulla.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from ..events.base import DomainEvent


class DrillOrigin(Enum):
    """Da dove arriva il tentativo."""

    #: Catalogo drill: il giocatore si allena per conto suo.
    CATALOG = "catalog"
    #: Drill di gara: prova del turno, ripetibile fino a ``max_attempts``.
    GARA = "gara"
    #: Dentro una scheda di allenamento (ADR-072): la prova conta per le
    #: statistiche e le serie, ma l'XP lo paga la seduta chiusa, non lei.
    SHEET = "sheet"


@dataclass
class ChallengeAttemptCompletedEvent(DomainEvent):
    """Un drill è stato completato — dal catalogo o dentro una gara.

    Un tentativo *iniziato* e mai chiuso non arriva qui: allenarsi vuol dire
    arrivare in fondo alla prova, non aprirla.
    """

    attempt_id: int
    challenge_id: int
    challenge_name: str
    user_id: int
    origin: str
    score: Optional[int] = None
    passed: Optional[bool] = None
    gara_id: Optional[int] = None
    #: Progressivo del tentativo sulla stessa prova. In gara conta: dal
    #: catalogo vale sempre 1, perché ogni tentativo è una sessione a sé.
    attempt_number: int = 1
    #: Il `GaraChallenge` del tentativo, solo per gli esercizi fra i turni.
    #: Dice **da quale tabella** viene `attempt_id`: gli id di
    #: `challenge_attempt` e di `gara_challenge_attempt` si sovrappongono, e
    #: chi restituisce l'XP deve riconoscere il movimento giusto.
    gara_challenge_id: Optional[int] = None

    def __post_init__(self):
        super().__post_init__()
        self.domain = "challenge"

    @property
    def is_from_gara(self) -> bool:
        return self.origin == DrillOrigin.GARA.value

    @property
    def is_from_sheet(self) -> bool:
        return self.origin == DrillOrigin.SHEET.value

    @property
    def is_a_retry(self) -> bool:
        """True dal secondo tentativo in poi della **stessa** prova di gara."""
        return self.attempt_number > 1

    def get_event_type(self) -> str:
        return "challenge.attempt_completed"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "challenge_id": self.challenge_id,
            "challenge_name": self.challenge_name,
            "user_id": self.user_id,
            "origin": self.origin,
            "score": self.score,
            "passed": self.passed,
            "gara_id": self.gara_id,
            "attempt_number": self.attempt_number,
            "gara_challenge_id": self.gara_challenge_id,
        }


__all__ = ["ChallengeAttemptCompletedEvent", "DrillOrigin"]
