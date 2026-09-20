"""Quanto è difficile davvero un esercizio, dai risultati di chi l'ha provato (#174).

Il livello dichiarato è un'opinione — e per giunta l'opinione di chi
l'esercizio lo sa già fare. Qui accanto ci va la **difficoltà misurata**, che
non lo sostituisce: sono due informazioni diverse, e la seconda serve a far
correggere la prima.

**L'unità è la stessa dell'andamento** (ADR-068): la quota di ciò che era
ottenibile. Un esercizio in cui la gente prende in media il 41 per cento del
massimo è difficile, qualunque cosa dica la sua scheda.

Tre scelte che decidono se il numero vuol dire qualcosa:

* **una osservazione per giocatore**, non per prova. Chi si allena venti volte
  sullo stesso esercizio peserebbe venti volte, e la difficoltà diventerebbe
  «quanto è bravo il più assiduo»;
* **sotto le soglie non si dice niente.** Con due giocatori una media è un
  aneddoto: si dice che non c'è ancora una stima, invece di mostrarne una
  falsa;
* **l'Elo entra come banda, non come correzione.** «Chi ha il tuo Elo riesce al
  58%» è una frase che si capisce e si può controllare; un punteggio corretto
  da un coefficiente di forza è un numero che nessuno può contestare perché
  nessuno sa come è venuto (#175: una regola spiegabile vale più di un modello
  opaco). Chi l'Elo non ce l'ha — la maggior parte di chi si allena — vede
  comunque la media di tutti, che è meglio di niente.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from flask_babel import gettext as _

from ..base import db
from .models import Challenge, ChallengeAttempt

#: Quanti giocatori distinti servono prima di dire qualcosa. Sotto, il numero
#: è rumore — e mostrarlo sarebbe peggio che tacere, perché una stima falsa la
#: si crede.
MIN_GIOCATORI = 3
#: E quante prove in tutto: tre giocatori con una prova a testa sono tre tiri.
MIN_PROVE = 5

#: Quanto largo è «quelli come te», in punti Elo per lato.
BANDA_ELO = 100
#: Quanti giocatori servono nella banda perché la riga compaia. Più basso della
#: soglia generale: qui la promessa è più modesta — non «questo esercizio è
#: difficile» ma «ecco come è andata a questi».
MIN_NELLA_BANDA = 3

#: Le quattro soglie che portano la quota sul livello 1–5. Non sono del dominio
#: — nessuno ha deciso che sotto il 35 per cento un esercizio sia «5» — sono una
#: convenzione, e stanno in un posto solo perché si cambino lì.
#: In ordine: quota minima per essere livello 1, 2, 3, 4. Sotto l'ultima, è 5.
SOGLIE_LIVELLO = (80, 65, 50, 35)


def livello_da_quota(quota: float) -> int:
    """Il livello 1–5 che corrisponde a una quota di riuscita."""
    for indice, soglia in enumerate(SOGLIE_LIVELLO, start=1):
        if quota >= soglia:
            return indice
    return len(SOGLIE_LIVELLO) + 1


@dataclass(frozen=True)
class PeerBand:
    """Come va a chi ha una forza simile alla tua."""

    low: int
    high: int
    players: int
    quota: int

    @property
    def label(self) -> str:
        return _("Elo fra %(low)s e %(high)s", low=self.low, high=self.high)


@dataclass(frozen=True)
class Difficolta:
    """La difficoltà misurata di un esercizio, e da quanti numeri viene."""

    challenge_id: int
    players: int
    attempts: int
    quota: Optional[int] = None
    declared: Optional[int] = None

    @property
    def has_estimate(self) -> bool:
        """Se c'è abbastanza per dire qualcosa."""
        return (
            self.quota is not None
            and self.players >= MIN_GIOCATORI
            and self.attempts >= MIN_PROVE
        )

    @property
    def level(self) -> Optional[int]:
        return livello_da_quota(self.quota) if self.has_estimate else None

    @property
    def disagrees(self) -> bool:
        """Se il misurato e il dichiarato non coincidono."""
        misurato = self.level
        return (
            misurato is not None
            and self.declared is not None
            and misurato != self.declared
        )

    @property
    def harder(self) -> bool:
        misurato = self.level
        return (
            misurato is not None
            and self.declared is not None
            and misurato > self.declared
        )

    @property
    def sentence(self) -> str:
        """La frase accanto al livello dichiarato. Vuota quando non c'è nulla da dire.

        Tace in tre casi, e sono tre cose diverse: non c'è ancora una stima,
        l'autore non ha dichiarato un livello, i due coincidono. In nessuno dei
        tre una frase aggiungerebbe qualcosa.
        """
        if not self.has_estimate or not self.disagrees:
            return ""
        if self.harder:
            return _(
                "dai risultati sembra più difficile: chi lo prova arriva al "
                "%(q)s%% di quello che si può fare",
                q=self.quota,
            )
        return _(
            "dai risultati sembra più facile: chi lo prova arriva al %(q)s%% di "
            "quello che si può fare",
            q=self.quota,
        )


# ────────────────────────────────────────────────────────────────────────
# Il conto
# ────────────────────────────────────────────────────────────────────────
def _quota(score: Optional[int], massimo: Optional[int]) -> Optional[float]:
    if score is None or not massimo or massimo <= 0:
        return None
    return max(0.0, min(score / massimo * 100, 100.0))


def _quote_per_giocatore(
    challenge_ids: Sequence[int],
) -> Dict[int, Dict[int, List[float]]]:
    """Per ogni esercizio, le quote di ogni giocatore — una lista per giocatore.

    Una query sola per tutti gli esercizi chiesti: la scheda ne vuole uno, il
    catalogo e i consigli decine, e una query per card è il difetto che
    `catalog_view` esiste per non rifare.
    """
    if not challenge_ids:
        return {}
    righe = (
        db.session.query(
            ChallengeAttempt.challenge_id,
            ChallengeAttempt.user_id,
            ChallengeAttempt.score,
            ChallengeAttempt.passed,
            Challenge.max_score,
            Challenge.pass_fail_only,
        )
        .join(Challenge, ChallengeAttempt.challenge_id == Challenge.id)
        .filter(
            ChallengeAttempt.challenge_id.in_(list(challenge_ids)),
            ChallengeAttempt.completed.is_(True),
        )
        .all()
    )

    per_esercizio: Dict[int, Dict[int, List[float]]] = {}
    for challenge_id, user_id, score, passed, massimo, netto in righe:
        if netto:
            # Riuscita o no è una quota dell'ottenibile, con l'ottenibile a uno
            # — la stessa lettura dell'andamento (ADR-068).
            quota: Optional[float] = 100.0 if passed else 0.0
        else:
            quota = _quota(score, massimo)
        if quota is None:
            continue
        per_esercizio.setdefault(challenge_id, {}).setdefault(user_id, []).append(quota)
    return per_esercizio


def _media_per_giocatore(quote: Dict[int, List[float]]) -> Dict[int, float]:
    return {
        user_id: sum(valori) / len(valori)
        for user_id, valori in quote.items()
        if valori
    }


def measure_many(challenges: Sequence[Challenge]) -> Dict[int, Difficolta]:
    """La difficoltà misurata di più esercizi, in una query sola."""
    per_esercizio = _quote_per_giocatore([c.id for c in challenges])
    risultato: Dict[int, Difficolta] = {}
    for challenge in challenges:
        quote = per_esercizio.get(challenge.id, {})
        medie = _media_per_giocatore(quote)
        prove = sum(len(valori) for valori in quote.values())
        risultato[challenge.id] = Difficolta(
            challenge_id=challenge.id,
            players=len(medie),
            attempts=prove,
            quota=round(sum(medie.values()) / len(medie)) if medie else None,
            declared=challenge.declared_level,
        )
    return risultato


def measure(challenge: Challenge) -> Difficolta:
    return measure_many([challenge])[challenge.id]


# ────────────────────────────────────────────────────────────────────────
# «Quelli come te»
# ────────────────────────────────────────────────────────────────────────
def _elo_di(user_ids: Iterable[int]) -> Dict[int, int]:
    """L'Elo competitivo di questi giocatori. Chi non ce l'ha non compare."""
    from ..rating.models import PlayerRating, RatingSystem

    ids = list(user_ids)
    if not ids:
        return {}
    righe = (
        db.session.query(PlayerRating.user_id, PlayerRating.rating_value)
        .filter(
            PlayerRating.user_id.in_(ids),
            PlayerRating.rating_system == RatingSystem.ELO,
        )
        .all()
    )
    return {user_id: round(valore) for user_id, valore in righe if valore is not None}


def peers(challenge: Challenge, user_id: Optional[int]) -> Optional[PeerBand]:
    """Come va a chi ha un Elo simile a quello di chi guarda.

    ``None`` quando la riga non si può dire — e i motivi sono tre, tutti
    legittimi: chi guarda non ha un Elo (la maggior parte di chi si allena),
    nessuno di chi ha provato ce l'ha, o nella banda c'è troppa poca gente.
    In tutti e tre resta la media di tutti, che la scheda mostra comunque.
    """
    if not user_id:
        return None
    quote = _quote_per_giocatore([challenge.id]).get(challenge.id, {})
    medie = _media_per_giocatore(quote)
    if not medie:
        return None

    elo = _elo_di(list(medie) + [user_id])
    mio = elo.get(user_id)
    if mio is None:
        return None

    basso, alto = mio - BANDA_ELO, mio + BANDA_ELO
    nella_banda = [
        media
        for altro_id, media in medie.items()
        if elo.get(altro_id) is not None and basso <= elo[altro_id] <= alto
    ]
    if len(nella_banda) < MIN_NELLA_BANDA:
        return None
    return PeerBand(
        low=basso,
        high=alto,
        players=len(nella_banda),
        quota=round(sum(nella_banda) / len(nella_banda)),
    )


# ────────────────────────────────────────────────────────────────────────
# Il rovescio: quanto è probabile che ci riesca *questo* giocatore (#175)
# ────────────────────────────────────────────────────────────────────────
def expected_for(challenge: Challenge, user_id: Optional[int]) -> Optional[int]:
    """Quanto ci si aspetta che faccia questo giocatore, in quota 0–100.

    È l'ingrediente del consiglio (#175), e segue la stessa regola della riga
    «quelli come te»: se c'è una banda di pari forza si usa quella, altrimenti
    la media di tutti. ``None`` quando non c'è nemmeno quella — e lì un
    consiglio non si dà, invece di darne uno a caso.
    """
    banda = peers(challenge, user_id)
    if banda is not None:
        return banda.quota
    stima = measure(challenge)
    return stima.quota if stima.has_estimate else None


__all__ = [
    "Difficolta",
    "PeerBand",
    "BANDA_ELO",
    "MIN_GIOCATORI",
    "MIN_NELLA_BANDA",
    "MIN_PROVE",
    "SOGLIE_LIVELLO",
    "expected_for",
    "livello_da_quota",
    "measure",
    "measure_many",
    "peers",
]
