"""La classifica finale della gara non conserva i numeri di uno spareggio annullato.

Difetto trovato il 2026-11-10 in `SpareggioService.apply_final_positions`.
Registrare i punteggi dello spareggio crea le righe `GaraClassification` dei
giocatori a pari merito, con vittorie e triangoli di quel momento. Se poi il
direttore annulla lo spareggio e corregge un risultato, le righe restano
(`clear_ssr_scores` azzera solo lo spareggio, e dice che «il prossimo ricalcolo
le riscrive»). Ma alla chiusura della gara `apply_final_positions`, su una
riga già esistente, riscriveva posizione e punti e **non** vittorie, triangoli
vinti e differenza: la classifica finale mostrava il giocatore al posto giusto
con i numeri della partita com'era prima della correzione.

Le righe `GaraClassification` sono quelle che il campionato somma
(`classifica_generale`, ADR-073): un numero vecchio lì entra nella classifica
generale.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models.classification.models import GaraClassification, RoundClassification
from models.competition.models import Gara, Inscription
from models.competition.spareggio_service import SpareggioService
from models.match.models import Match
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import ClassificationSystem, Discipline, GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _utente(db_session) -> User:
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"fin_{sigla}",
        email=f"fin_{sigla}@test.local",
        role=UserRole.PLAYER.value,
    )
    utente.set_password("prova1234")
    db_session.add(utente)
    db_session.flush()
    return utente


def _partita(db_session, gara, vince, perde, persi) -> Match:
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=vince.id,
        player2_id=perde.id,
        player1_score=3,
        player2_score=persi,
        winner_id=vince.id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    db_session.add(match)
    db_session.flush()
    return match


def _riga(gara_id, utente) -> GaraClassification:
    return GaraClassification.query.filter_by(gara_id=gara_id, user_id=utente.id).one()


def test_la_correzione_dopo_lo_spareggio_annullato_arriva_in_classifica(db_session):
    gara = Gara(
        name="Finale corretta",
        number=1,
        date=date.today(),
        discipline=Discipline.NINE_BALL.value,
        distance=3,
        is_race_to=True,
        status=GaraStatus.PLAYING.value,
        rounds_count=1,
        current_round=1,
        classification_system=ClassificationSystem.WINS.value,
        matchmaking_strategy=MatchmakingStrategy.AMALFI.value,
    )
    db_session.add(gara)
    db_session.flush()
    anna, bruno, carla, dario = (_utente(db_session) for _ in range(4))
    for giocatore in (anna, bruno, carla, dario):
        db_session.add(Inscription(user_id=giocatore.id, gara_id=gara.id))
    _partita(db_session, gara, anna, bruno, 1)
    da_correggere = _partita(db_session, gara, carla, dario, 1)
    db_session.commit()
    gara_id = gara.id
    RoundClassification.calculate_classification_after_round(gara_id, 1)
    db_session.commit()

    # Anna e Carla sono prime a pari merito: si registra lo spareggio…
    riuscito, messaggio = SpareggioService.save_ssr_scores(
        gara_id, {anna.id: 2, carla.id: 1}
    )
    assert riuscito, messaggio
    db_session.commit()
    assert _riga(gara_id, carla).matches_won == 1

    # …poi il direttore lo annulla e corregge: aveva vinto Dario, 3-0.
    SpareggioService.clear_ssr_scores(gara_id)
    da_correggere.player1_score, da_correggere.player2_score = 0, 3
    da_correggere.winner_id = dario.id
    db_session.commit()
    RoundClassification.calculate_classification_after_round(gara_id, 1)
    db_session.commit()

    riuscito, messaggio = SpareggioService.apply_final_positions(gara_id)
    assert riuscito, messaggio
    db_session.commit()

    di_turno = RoundClassification.query.filter_by(
        gara_id=gara_id, round_number=1, user_id=carla.id
    ).one()
    assert di_turno.matches_won == 0, "premessa: la classifica di turno è corretta"
    finale = _riga(gara_id, carla)
    assert finale.matches_won == 0
    assert finale.racks_won == 0
    assert finale.rack_difference == -3
    # Chi non aveva una riga la riceve giusta, come prima.
    assert _riga(gara_id, dario).matches_won == 1
    assert _riga(gara_id, dario).rack_difference == 3
