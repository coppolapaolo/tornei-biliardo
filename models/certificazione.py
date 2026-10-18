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

Nella **partita di altri due** (ADR-084) — il referto lo tiene un istruttore
o un direttore — il livello è **per giocatore** finché nessuno la rifiuta: chi
la conferma la vede *Confermata*, chi non ha ancora deciso *In attesa*. Le
funzioni che ricevono una persona (`livello_di_sfida_per`,
`sfide_della_vista(vista, user_id=…)`) applicano quella regola; senza persona la
regola è **di coppia**, ed è quella dell'ELO, che misura una partita fra due e
non si divide.

Il rifiuto invece non è per giocatore (emendamento del 2026-10-18): ne basta
uno e la partita va a ``MatchStatus.REJECTED``, che non è né conclusa né in
corso, quindi non ha livello per nessuno dei due e nessuna vista la comprende.
I controlli sulle colonne ``player*_rejected_at`` qui sotto restano come
difesa: una riga che le avesse scritte senza cambiare stato resterebbe fuori lo
stesso.

Casi d'uso in ``docs/usecases/sfide-e-certificazione.md``.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, FrozenSet, Optional

from sqlalchemy import and_, exists, false, not_, or_
from sqlalchemy.orm import aliased

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
    "livello_di_sfida_per",
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
    """Il livello di una sfida individuale **per la coppia**, o ``None``.

    Senza nessuna firma la sfida non ha livello: i due la stanno ancora
    giocando, oppure non l'hanno giocata.

    È il livello che decide l'ELO. Per i numeri di **un** giocatore si chiede
    `livello_di_sfida_per`: nella partita di un terzo i due possono vederla in
    modo diverso.
    """
    stato = _valore(sfida.status)
    if MatchStatus.is_finished(stato):
        return Livello.CONFERMATA
    if getattr(sfida, "scorer_id", None) is not None:
        # Partita di un terzo (ADR-084): dichiarata e nessuno l'ha rifiutata.
        if (
            stato == MatchStatus.IN_PROGRESS.value
            and sfida.is_declared_by_scorer
            and sfida.player1_rejected_at is None
            and sfida.player2_rejected_at is None
        ):
            return Livello.IN_ATTESA
        return None
    if stato == MatchStatus.IN_PROGRESS.value and bool(sfida.player1_confirmed) != (
        bool(sfida.player2_confirmed)
    ):
        return Livello.IN_ATTESA
    return None


def livello_di_sfida_per(sfida: "IndividualMatch", user_id: int) -> Optional[Livello]:
    """Il livello della sfida **per questo giocatore** (ADR-084).

    Sulla sfida normale coincide con `livello_di_sfida`: le firme sono dei due
    insieme. Nella partita di un terzo ciascuno conferma per sé: chi l'ha
    confermata la vede *Confermata*, chi non ha ancora deciso *In attesa*
    (purché chi la segna l'abbia dichiarata chiudendo il referto). Rifiutata
    da uno dei due, non ha livello per nessuno (``REJECTED``, 2026-10-18).
    """
    if getattr(sfida, "scorer_id", None) is None:
        return livello_di_sfida(sfida)
    if not sfida.is_player(user_id):
        return None
    stato = _valore(sfida.status)
    if MatchStatus.is_finished(stato):
        return Livello.CONFERMATA
    if stato != MatchStatus.IN_PROGRESS.value or not sfida.is_declared_by_scorer:
        return None
    decisione = sfida.decision_of(user_id)
    if decisione == "rejected":
        return None
    if decisione == "confirmed":
        return Livello.CONFERMATA
    return Livello.IN_ATTESA


def esito_dichiarato(sfida: "IndividualMatch") -> Optional[int]:
    """Chi ha vinto la sfida, secondo chi l'ha firmata. ``None`` è un pareggio.

    ``winner_id`` lo scrive la seconda firma, quindi una sfida non ancora
    chiusa non ce l'ha: il risultato dichiarato sta nel punteggio, che chi ha
    firmato ha visto e accettato. Vale anche per la partita di un terzo
    confermata da uno solo: per chi l'ha confermata è una vittoria o una
    sconfitta, non un pareggio.
    """
    if MatchStatus.is_finished(_valore(sfida.status)):
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


def sfide_della_vista(vista: Vista, user_id: Optional[int] = None) -> Any:
    """La stessa regola di `livello_di_sfida`, come condizione SQL.

    Per le query che contano o sommano sulle sfide individuali. Nella vista
    *Tornei* non entra nessuna sfida.

    Con ``user_id`` è la regola di `livello_di_sfida_per`: **le query sulle
    sfide di un giocatore lo passano sempre**. Senza, la regola è di coppia
    (quella dell'ELO), e una partita di un terzo confermata da lui e non
    ancora dall'altro conterebbe per lui solo come *In attesa*.
    """
    from models.individual_match.match_models import IndividualMatch
    from models.tpa.models import TpaReferto

    concluse = IndividualMatch.status.in_(
        [MatchStatus.CLOSED_UNILATERALLY, MatchStatus.CONFIRMED_BY_BOTH]
    )
    normale = IndividualMatch.scorer_id.is_(None)
    in_attesa_normale = and_(
        normale,
        IndividualMatch.status == MatchStatus.IN_PROGRESS,
        IndividualMatch.player1_confirmed != IndividualMatch.player2_confirmed,
    )
    # La partita di un terzo, dichiarata: chi la segna ha chiuso il referto.
    # Un alias con correlazione esplicita: chi interroga i referti
    # (`TpaStatsService.referti_for_user`) ha già `tpa_referto` nella query, e
    # senza alias l'EXISTS si correlerebbe anche a quello, restando vuoto.
    referto = aliased(TpaReferto)
    dichiarata = and_(
        IndividualMatch.scorer_id.isnot(None),
        IndividualMatch.status == MatchStatus.IN_PROGRESS,
        exists()
        .where(
            referto.individual_match_id == IndividualMatch.id,
            referto.closed_at.isnot(None),
        )
        .correlate(IndividualMatch),
    )

    if user_id is None:
        confermate_di_un_terzo = false()
        in_attesa_di_un_terzo = and_(
            dichiarata,
            IndividualMatch.player1_rejected_at.is_(None),
            IndividualMatch.player2_rejected_at.is_(None),
        )
    else:
        come_primo = IndividualMatch.player1_id == user_id
        come_secondo = IndividualMatch.player2_id == user_id
        ha_confermato = or_(
            and_(come_primo, IndividualMatch.player1_confirmed.is_(True)),
            and_(come_secondo, IndividualMatch.player2_confirmed.is_(True)),
        )
        ha_rifiutato = or_(
            and_(come_primo, IndividualMatch.player1_rejected_at.isnot(None)),
            and_(come_secondo, IndividualMatch.player2_rejected_at.isnot(None)),
        )
        confermate_di_un_terzo = and_(dichiarata, ha_confermato)
        in_attesa_di_un_terzo = and_(
            dichiarata,
            or_(come_primo, come_secondo),
            not_(ha_confermato),
            not_(ha_rifiutato),
        )

    condizioni = []
    if Livello.CONFERMATA in vista.livelli:
        condizioni.extend([concluse, confermate_di_un_terzo])
    if Livello.IN_ATTESA in vista.livelli:
        condizioni.extend([in_attesa_normale, in_attesa_di_un_terzo])
    if not condizioni:
        return false()
    return or_(*condizioni)


def _valore(status: Any) -> str:
    """Lo stato come stringa: su `Match` è già una stringa, su
    `IndividualMatch` è il membro dell'enum."""
    return getattr(status, "value", status)
