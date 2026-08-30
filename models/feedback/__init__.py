"""Segnalazioni degli utenti (issue #255).

Chi usa l'app non aveva nessun modo di dire che qualcosa non va: il backlog
vive su GitHub, e i giocatori non hanno un account GitHub né sanno cosa sia.
Il ponte lo costruisce l'app — le segnalazioni diventano issue vere, e gli
aggiornamenti tornano indietro come notifiche.
"""

from .models import (
    FeedbackReport,
    FeedbackStatus,
    FeedbackSyncState,
    FeedbackType,
)

__all__ = [
    "FeedbackReport",
    "FeedbackStatus",
    "FeedbackSyncState",
    "FeedbackType",
]
