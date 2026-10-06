"""Come si chiude una partita: alla distanza, o interrotta a tempo (ADR-077).

Una partita si chiude **alla distanza** (`Match.is_at_distance`), oppure la
**interrompe il direttore** quando ha un limite di tempo. Le due domande
dell'interruzione hanno qui la loro sola risposta:

* *si può interrompere?* (`motivo_non_interrompibile`) — sì se la partita ha
  un limite di tempo, è in gioco e non è a set, trio o X. Anche prima dello
  scadere: il direttore è sovrano, e il foglio dice quanto mancava;
* *con quale esito?* (`esito`) — chi è avanti vince; a parità c'è
  **pareggio** dove il pareggio è ammesso (fuori dal tabellone), e nel
  tabellone il direttore indica chi passa.

E una terza, che serve a chi chiude: *questa partita è chiudibile?*
(`chiudibile`) — alla distanza, o interrotta. La validazione del direttore la
chiede qui invece di guardare la sola distanza; «aspetta il direttore»
(`models.match.models.awaiting_validation`) resta invece com'è, perché una
partita interrotta non aspetta nessuno: la chiude chi la interrompe.

Il segno `closed_on_time` lo scrive **solo** l'interruzione: una partita
arrivata alla distanza a tempo scaduto si chiude come sempre, senza segno.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from flask_babel import lazy_gettext as _l

from models.status_enum import MatchStatus


@dataclass(frozen=True)
class Esito:
    """Cosa succede interrompendo adesso."""

    vincitore_id: Optional[int]
    pareggio: bool
    #: Pari nel tabellone: il direttore deve indicare chi passa.
    serve_chi_passa: bool
    #: Secondi che mancavano allo scadere; None se è già scaduto o se il
    #: conto alla rovescia non è partito.
    secondi_mancanti: Optional[int]


def pareggio_ammesso(match: Any) -> bool:
    """Fuori dal tabellone una partita interrotta può finire pari.

    Gironi, girone all'italiana, Amalfi, casuale: il pari è un risultato che
    la classifica sa contare. Nel tabellone no: qualcuno deve passare il
    turno.
    """
    from models.matchmaking.configuration import BRACKET_STRATEGIES

    if getattr(match, "bracket_type", None):
        return False
    gara = getattr(match, "gara", None)
    return gara is None or gara.matchmaking_strategy not in BRACKET_STRATEGIES


def motivo_non_interrompibile(match: Any) -> Optional[Any]:
    """Perché questa partita non si interrompe, o None se si può."""
    from models.match import tempo

    if MatchStatus.is_finished(getattr(match, "status", None)):
        return _l("La partita è già chiusa.")
    if tempo.forma_esclusa(match):
        return _l("Le partite a set, a tre e la X non si interrompono a tempo.")
    if not tempo.ha_limite(match):
        return _l("Questa partita non ha un limite di tempo.")
    if not tempo.in_gioco(match):
        return _l("La partita non è ancora cominciata: aspetta il tavolo.")
    return None


def esito(match: Any, adesso: Optional[datetime] = None) -> Esito:
    """L'esito di un'interruzione sul punteggio di adesso."""
    from models.match import tempo

    p1, p2 = match.player1_score or 0, match.player2_score or 0
    restanti = tempo.secondi_restanti(match, adesso)
    mancanti = restanti if restanti is not None and restanti > 0 else None
    if p1 != p2:
        return Esito(
            vincitore_id=match.player1_id if p1 > p2 else match.player2_id,
            pareggio=False,
            serve_chi_passa=False,
            secondi_mancanti=mancanti,
        )
    ammesso = pareggio_ammesso(match)
    return Esito(
        vincitore_id=None,
        pareggio=ammesso,
        serve_chi_passa=not ammesso,
        secondi_mancanti=mancanti,
    )


def chiudibile(match: Any) -> bool:
    """Alla distanza, o interrotta dal direttore."""
    return bool(match.is_at_distance or getattr(match, "closed_on_time", False))


__all__ = [
    "Esito",
    "pareggio_ammesso",
    "motivo_non_interrompibile",
    "esito",
    "chiudibile",
]
