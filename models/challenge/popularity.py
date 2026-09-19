"""Quanti hanno provato un esercizio, e che voto gli danno (ADR-065).

I due numeri si leggono **insieme** — un 4,8 dato da tre giocatori pesa meno di
un 4,5 dato da duecento — quindi escono insieme, da una funzione sola, per tutti
gli esercizi di una pagina in un colpo: tre query qualunque sia la lunghezza del
catalogo, non tre per card.

**Chi ha provato.** Chi ha almeno una prova *completata* dell'esercizio, dal
catalogo (``ChallengeAttempt``) o in gara (``GaraChallengeAttempt``): le stesse
due fonti dello storico d'allenamento (``TrainingHistoryService``). È anche la
regola di chi può votare (D6), e sta qui una volta sola perché le due cose non
possano divergere: un contatore che dice «14 giocatori» e un voto rifiutato a uno
di quei quattordici sarebbe un difetto che nessun test di un solo lato vede.

Gli esami restano fuori, ed è una scelta: una prova d'esame è una valutazione
davanti a un esaminatore, non un allenamento, e lo storico d'allenamento già la
tiene in una sezione sua.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Set

from sqlalchemy import func

from ..base import db
from .models import ChallengeAttempt, ChallengeRating


@dataclass(frozen=True)
class ChallengePopularity:
    """I numeri sociali di un esercizio. Tutto a zero è uno stato legittimo."""

    players: int = 0
    rating_count: int = 0
    rating_average: Optional[float] = None

    @property
    def has_rating(self) -> bool:
        return self.rating_count > 0


def _players_by_challenge(challenge_ids: Set[int]) -> Dict[int, Set[int]]:
    """Per esercizio, l'insieme di chi l'ha provato: catalogo ∪ gara.

    Si uniscono **insiemi di giocatori**, non conteggi: chi l'ha provato sia dal
    catalogo sia in gara è una persona, non due.
    """
    from ..competition.gara_challenge import GaraChallenge, GaraChallengeAttempt

    giocatori: Dict[int, Set[int]] = {cid: set() for cid in challenge_ids}
    if not challenge_ids:
        return giocatori

    dal_catalogo = (
        db.session.query(ChallengeAttempt.challenge_id, ChallengeAttempt.user_id)
        .filter(
            ChallengeAttempt.challenge_id.in_(challenge_ids),
            ChallengeAttempt.completed.is_(True),
        )
        .distinct()
        .all()
    )
    in_gara = (
        db.session.query(GaraChallenge.challenge_id, GaraChallengeAttempt.user_id)
        .join(
            GaraChallengeAttempt,
            GaraChallengeAttempt.gara_challenge_id == GaraChallenge.id,
        )
        .filter(
            GaraChallenge.challenge_id.in_(challenge_ids),
            GaraChallengeAttempt.completed.is_(True),
        )
        .distinct()
        .all()
    )
    for challenge_id, user_id in [*dal_catalogo, *in_gara]:
        giocatori[challenge_id].add(user_id)
    return giocatori


def popularity_for(challenge_ids: Iterable[int]) -> Dict[int, ChallengePopularity]:
    """I numeri di ogni esercizio richiesto. Chi non ha niente ha comunque una voce."""
    ids = set(challenge_ids)
    giocatori = _players_by_challenge(ids)

    voti: Dict[int, tuple[int, Optional[float]]] = {}
    if ids:
        for challenge_id, quanti, media in (
            db.session.query(
                ChallengeRating.challenge_id,
                func.count(ChallengeRating.id),
                func.avg(ChallengeRating.rating),
            )
            .filter(ChallengeRating.challenge_id.in_(ids))
            .group_by(ChallengeRating.challenge_id)
            .all()
        ):
            voti[challenge_id] = (int(quanti), float(media) if media else None)

    return {
        cid: ChallengePopularity(
            players=len(giocatori[cid]),
            rating_count=voti.get(cid, (0, None))[0],
            rating_average=voti.get(cid, (0, None))[1],
        )
        for cid in ids
    }


def has_tried(user_id: int, challenge_id: int) -> bool:
    """Questo giocatore ha almeno una prova completata di questo esercizio?"""
    return user_id in _players_by_challenge({challenge_id})[challenge_id]
