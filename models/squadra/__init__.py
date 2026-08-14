"""Squadre di una competizione.

Modello deliberatamente asimmetrico rispetto al profilo utente: sul profilo la
squadra è **testo libero** (``user.squadra``), qui è un'**entità** che vive
dentro una singola competizione — il campionato, oppure la gara se standalone.

La ragione è che le squadre servono a una cosa sola: separare i compagni nel
sorteggio del tabellone di *quella* competizione. Non esistono classifiche,
statistiche o punteggi per squadra fuori da lì, quindi un'anagrafica globale
sarebbe stata una struttura da mantenere senza nulla che la giustificasse.
"""

from .models import Squadra, normalize_squadra_name
from .service import SquadraService

__all__ = ["Squadra", "SquadraService", "normalize_squadra_name"]
