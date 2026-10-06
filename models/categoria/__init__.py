"""Categorie di gioco di una competizione.

L'elenco vive nel campionato — condiviso da tutte le sue gare — oppure nella
gara, se standalone. Non esiste un'anagrafica globale: «C, B, A, N» è la scala
della federazione italiana per il pool, ma il vocabolario cambia da
organizzatore a organizzatore e da paese a paese.

Le categorie servono a due cose. In una gara con handicap l'ELO si aggiorna
solo fra giocatori della stessa categoria, perché lì l'handicap non è in gioco
e il risultato dice davvero qualcosa sulla forza dei due (ADR-049). E con il
listino delle quote, anche senza handicap, dicono chi paga quanto (ADR-079):
lì sono solo informazione e non toccano l'ELO.
"""

from .models import Categoria, MAX_NAME_LENGTH
from .service import CategoriaService

__all__ = ["Categoria", "CategoriaService", "MAX_NAME_LENGTH"]
