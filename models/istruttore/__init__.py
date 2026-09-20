"""Istruttori e allievi (ADR-069).

Il legame è **allievo–scheda–istruttore** (D11): non esiste «Luca mi segue»,
esiste «questa scheda la legge Luca». Non c'è quindi una tabella dei legami —
c'è `training_sheet_reader`, nata con le schede (ADR-067), e le due pagine «I
miei istruttori» e «I miei allievi» sono la **stessa riga letta dai due lati**.

I **gruppi** (fase 8c) non cambiano questa frase di una virgola: ordinano chi
ti ha già aperto una scheda, e non aprono niente a nessuno.
"""

from .allievi_view import Allievi, RigaAllievo, Segnale, build_allievi
from .gruppi import GruppoService
from .models import TrainingGroup, TrainingGroupMember
from .ricerca import MAX_RISULTATI, cerca_istruttori
from .viste import Legame, allievi_di, istruttori_di

__all__ = [
    "Allievi",
    "GruppoService",
    "Legame",
    "MAX_RISULTATI",
    "RigaAllievo",
    "Segnale",
    "TrainingGroup",
    "TrainingGroupMember",
    "allievi_di",
    "build_allievi",
    "cerca_istruttori",
    "istruttori_di",
]
