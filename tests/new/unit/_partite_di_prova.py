"""Gara e partita minime per i test sulle partite chiuse (2026-11-10).

Non è un file di test: lo importano i presìdi nati dalla revisione del
2026-11-10 (partite chiuse, walkover, correzioni), che hanno bisogno tutti
della stessa gara «al 5» in corso e della stessa partita fra due giocatori.
"""

from __future__ import annotations

from models.base import utc_now
from models.competition.models import Gara, Inscription
from models.match.models import Match, Rack
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import Discipline, GaraStatus, MatchStatus


def crea_gara(db_session, **campi) -> Gara:
    base = dict(
        number=1,
        name="Gara di prova",
        date=utc_now().date(),
        time=utc_now().time(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
        status=GaraStatus.PLAYING.value,
        current_round=1,
        matchmaking_strategy=MatchmakingStrategy.AMALFI.value,
    )
    base.update(campi)
    gara = Gara(**base)
    db_session.add(gara)
    db_session.commit()
    return gara


def crea_partita(db_session, gara, giocatori, **campi) -> Match:
    base = dict(
        gara_id=gara.id,
        round_number=1,
        player1_id=giocatori[0].id,
        player2_id=giocatori[1].id,
        status=MatchStatus.PLAYING.value,
        match_distance=5,
    )
    base.update(campi)
    partita = Match(**base)
    db_session.add(partita)
    db_session.commit()
    return partita


def segna_triangoli(db_session, partita, vincitori) -> list:
    """Scrive i triangoli sul DB senza toccare il punteggio della partita."""
    racks = []
    for numero, vincitore in enumerate(vincitori, start=1):
        rack = Rack(match_id=partita.id, rack_number=numero, winner_id=vincitore.id)
        db_session.add(rack)
        racks.append(rack)
    db_session.commit()
    return racks


def iscrivi(db_session, gara, giocatori) -> None:
    for giocatore in giocatori:
        db_session.add(Inscription(gara_id=gara.id, user_id=giocatore.id))
    db_session.commit()
