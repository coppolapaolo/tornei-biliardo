"""Istruttori e allievi (ADR-069).

Il legame è **allievo–scheda–istruttore** (D11): non esiste «Luca mi segue»,
esiste «questa scheda la legge Luca». Non c'è quindi una tabella dei legami —
c'è `training_sheet_reader`, nata con le schede (ADR-067), e le due pagine «I
miei istruttori» e «I miei allievi» sono la **stessa riga letta dai due lati**.

Qui stanno le viste derivate. I gruppi di allievi arrivano con la fase 8c.
"""

from .ricerca import MAX_RISULTATI, cerca_istruttori
from .viste import Legame, allievi_di, istruttori_di

__all__ = [
    "Legame",
    "MAX_RISULTATI",
    "allievi_di",
    "cerca_istruttori",
    "istruttori_di",
]
