"""La scelta «tengo il referto TPA», e come si onora.

La domanda si fa **prima** che la partita cominci, ed è l'unico momento in cui
ha una risposta: appena si è al segnapunti la prima cosa che si fa è segnare, e
al primo triangolo il referto non si apre più (`blocking_reason`). La finestra
era larga esattamente un tocco, e si chiudeva senza dire niente.

Vale per tutt'e due i modi di far partire una sfida — l'avvio rapido, che crea
la partita già in corso (ADR-051), e la proposta accettata, che la fa partire
con «Inizia la sfida». Le due route ponevano la stessa domanda in due punti
diversi del codice: qui c'è una volta sola.
"""

import logging

from flask_login import current_user

from models.exceptions import DomainError
from models.tpa.services import FEATURE_CODE as TPA_FEATURE, TpaRefertoService

logger = logging.getLogger(__name__)

#: Il nome del campo, uguale nei due moduli: chi legge la richiesta di una
#: delle due route sta guardando la stessa cosa.
FIELD = "tpa_referto"


def wants_referto(data) -> bool:
    """La spunta del modulo. Presente e affermativa, o niente.

    Accetta sia il ``1`` che manda un `<input type="checkbox">` premuto sia il
    ``true`` della chiamata JSON: sono due formati della stessa richiesta, e
    uno solo dei due arriva dai telefoni.
    """
    return str(data.get(FIELD)).lower() in ("1", "true", "on", "yes")


def open_tpa_referto(match, wanted: bool) -> bool:
    """Il referto scelto nel modulo, aperto subito dopo la partita.

    **Perché qui e non dentro il servizio che avvia la partita**: sono due
    `@transactional` diversi, e annidarli è il modo noto per far tornare
    indietro anche quello esterno (`models/transaction/CLAUDE.md`). La partita
    è già salvata quando arriviamo qui, quindi le due scritture restano
    separate — e separate devono restare anche nell'esito.

    **Perché il rifiuto non ferma la partita**: chi ha spuntato la casella su
    una disciplina che il referto non copre voleva comunque giocare. Si gioca,
    senza referto, e il perché sta scritto per esteso sulla pagina del referto
    (`blocking_reason`).

    Lo sblocco lo si controlla qui e non nel servizio perché il gate della
    gamification, per il referto, sta sull'*apertura*: è la stessa regola di
    `@feature_required` su `tpa_open`.
    """
    if not wanted or not current_user.can_access(TPA_FEATURE):
        return False
    try:
        TpaRefertoService.open_referto(match.id, current_user.id)
        return True
    except DomainError as exc:
        logger.info("Referto TPA non aperto all'avvio della sfida: %s", exc)
        return False
