"""Quanto è certificata una partita (ADR-083).

Le prestazioni di un giocatore non valgono tutte allo stesso modo:

* una partita di **torneo** l'ha garantita un direttore di gara;
* una sfida **confermata** l'hanno garantita i due giocatori, firmando
  entrambi (ADR-051). Lo è anche la sfida chiusa con un forfait: chi abbandona
  ammette la sconfitta;
* una sfida **in attesa** l'ha firmata uno solo. Con chi non usa l'app la
  seconda firma può non arrivare mai, e quel risultato è comunque un fatto
  dichiarato.

Le statistiche si leggono in tre **viste cumulative**: *Tornei*, *Confermate*
(tornei e sfide confermate), *Tutte* (anche quelle in attesa).

Il livello si decide **qui e basta**. Storico, statistiche, TPA, runout ed ELO
lo chiedono a questo modulo: una seconda definizione di «confermata» darebbe
due numeri diversi nella stessa pagina, ed è il guasto che i pool ELO hanno
già conosciuto (ADR-073 racconta lo stesso schema per la classifica).

Casi d'uso in ``docs/usecases/sfide-e-certificazione.md``.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, FrozenSet, Optional

from sqlalchemy import and_, false, or_

from models.status_enum import MatchStatus

if TYPE_CHECKING:
    from models.individual_match.match_models import IndividualMatch
    from models.match.models import Match

__all__ = [
    "Livello",
    "Vista",
    "VISTA_PREDEFINITA",
    "livello_di_partita",
    "livello_di_sfida",
    "esito_dichiarato",
    "sfide_della_vista",
    "sfida_conta_per_elo",
]


class Livello(Enum):
    """Chi garantisce il risultato di una partita."""

    TORNEO = "torneo"
    CONFERMATA = "confermata"
    IN_ATTESA = "in_attesa"


class Vista(Enum):
    """Quali livelli entrano nei numeri. Ogni vista contiene la precedente."""

    TORNEI = "tornei"
    CONFERMATE = "confermate"
    TUTTE = "tutte"

    @property
    def livelli(self) -> FrozenSet[Livello]:
        return _LIVELLI_DELLA_VISTA[self]

    def comprende(self, livello: Optional[Livello]) -> bool:
        return livello is not None and livello in self.livelli

    @classmethod
    def da_valore(cls, valore: Optional[str]) -> "Vista":
        """La vista scritta in un parametro; quella predefinita se non c'è."""
        for vista in cls:
            if vista.value == valore:
                return vista
        return VISTA_PREDEFINITA


_LIVELLI_DELLA_VISTA = {
    Vista.TORNEI: frozenset({Livello.TORNEO}),
    Vista.CONFERMATE: frozenset({Livello.TORNEO, Livello.CONFERMATA}),
    Vista.TUTTE: frozenset(Livello),
}

#: Quella che si vede finché chi guarda non ne ha scelta un'altra. È anche
#: quella che si vedeva prima che le viste esistessero: tornei e sfide chiuse.
VISTA_PREDEFINITA = Vista.CONFERMATE


def livello_di_partita(match: "Match") -> Optional[Livello]:
    """Una partita di torneo conclusa è sempre di livello *Torneo*.

    Che conti anche per l'ELO lo decide un'altra regola, `RatingEligibility`
    (ADR-049): un walkover è un risultato certificato che non misura la forza.
    """
    return Livello.TORNEO if MatchStatus.is_finished(_valore(match.status)) else None


def livello_di_sfida(sfida: "IndividualMatch") -> Optional[Livello]:
    """Il livello di una sfida individuale, o ``None`` se non ne ha.

    Senza nessuna firma la sfida non ha livello: i due la stanno ancora
    giocando, oppure non l'hanno giocata.
    """
    stato = _valore(sfida.status)
    if MatchStatus.is_finished(stato):
        return Livello.CONFERMATA
    if stato == MatchStatus.IN_PROGRESS.value and bool(sfida.player1_confirmed) != (
        bool(sfida.player2_confirmed)
    ):
        return Livello.IN_ATTESA
    return None


def esito_dichiarato(sfida: "IndividualMatch") -> Optional[int]:
    """Chi ha vinto la sfida, secondo chi l'ha firmata. ``None`` è un pareggio.

    ``winner_id`` lo scrive la seconda firma, quindi una sfida in attesa non
    ce l'ha: il risultato dichiarato sta nel punteggio, che chi ha firmato ha
    visto e accettato.
    """
    if livello_di_sfida(sfida) is not Livello.IN_ATTESA:
        return sfida.winner_id
    uno, due = sfida.player1_score or 0, sfida.player2_score or 0
    if uno == due:
        return None
    return sfida.player1_id if uno > due else sfida.player2_id


def sfida_conta_per_elo(sfida: "IndividualMatch") -> bool:
    """Se la sfida muove l'ELO delle viste che la comprendono.

    Il forfait no, come nei tornei: un risultato certo che non misura la
    forza. I pareggi nemmeno, come è sempre stato per le sfide.
    """
    if _valore(sfida.status) == MatchStatus.CLOSED_UNILATERALLY.value:
        return False
    return livello_di_sfida(sfida) is not None and esito_dichiarato(sfida) is not None


def sfide_della_vista(vista: Vista) -> Any:
    """La stessa regola di `livello_di_sfida`, come condizione SQL.

    Per le query che contano o sommano sulle sfide individuali. Nella vista
    *Tornei* non entra nessuna sfida.
    """
    from models.individual_match.match_models import IndividualMatch

    concluse = IndividualMatch.status.in_(
        [MatchStatus.CLOSED_UNILATERALLY, MatchStatus.CONFIRMED_BY_BOTH]
    )
    in_attesa = and_(
        IndividualMatch.status == MatchStatus.IN_PROGRESS,
        IndividualMatch.player1_confirmed != IndividualMatch.player2_confirmed,
    )
    condizioni = []
    if Livello.CONFERMATA in vista.livelli:
        condizioni.append(concluse)
    if Livello.IN_ATTESA in vista.livelli:
        condizioni.append(in_attesa)
    if not condizioni:
        return false()
    return or_(*condizioni)


def _valore(status: Any) -> str:
    """Lo stato come stringa: su `Match` è già una stringa, su
    `IndividualMatch` è il membro dell'enum."""
    return getattr(status, "value", status)
