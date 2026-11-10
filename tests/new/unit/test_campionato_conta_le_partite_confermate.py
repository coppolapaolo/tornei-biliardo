"""Le partite chiuse dai due giocatori contano come giocate, nel campionato.

Difetto trovato il 2026-11-10, in due punti con la stessa svista: «partita
giocata» scritto come `status == CLOSED_UNILATERALLY`, che è la sola chiusura
del direttore. `CONFIRMED_BY_BOTH` è la chiusura dei due giocatori, ed è
giocata quanto l'altra.

* `calculate_campionato_statistics`: «partite completate» e «rack giocati»
  della pagina del campionato non contavano le partite confermate dai
  giocatori — in un campionato dove i giocatori si segnano i punti da soli,
  quasi tutte.
* `Campionato.can_be_hard_deleted`: un campionato le cui partite erano tutte
  confermate dai giocatori risultava «senza partite giocate», quindi
  eliminabile per sempre.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models import Gara, Match, User
from models.campionato.models import Campionato
from models.campionato.statistics_service import TournamentStatisticsService
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import ClassificationSystem, Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _utente(db_session) -> User:
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"u_{sigla}", email=f"u_{sigla}@test.com", role=UserRole.PLAYER.value
    )
    utente.set_password("x")
    db_session.add(utente)
    db_session.flush()
    return utente


def _campionato_con_partite(db_session, stati):
    """Un campionato con una gara e una partita 3-1 per ogni stato dato."""
    campionato = Campionato(
        name=f"Campionato {uuid.uuid4().hex[:8]}",
        campionato_type=MatchmakingStrategy.RANDOM.value,
        default_classification_system=ClassificationSystem.WINS.value,
        planned_gare_count=1,
    )
    db_session.add(campionato)
    db_session.flush()
    gara = Gara(
        number=1,
        name="Gara 1",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline=Discipline.NINE_BALL.value,
        distance=3,
        is_race_to=True,
        campionato_id=campionato.id,
        rounds_count=1,
        min_participants=2,
        matchmaking_strategy=MatchmakingStrategy.RANDOM.value,
        classification_system=ClassificationSystem.WINS.value,
        status=GaraStatus.PLAYING.value,
    )
    db_session.add(gara)
    db_session.flush()
    for stato in stati:
        primo, secondo = _utente(db_session), _utente(db_session)
        finita = MatchStatus.is_finished(stato)
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=primo.id,
                player2_id=secondo.id,
                player1_score=3 if finita else 0,
                player2_score=1 if finita else 0,
                winner_id=primo.id if finita else None,
                status=stato,
            )
        )
    db_session.commit()
    return campionato


def test_le_statistiche_contano_le_partite_confermate_dai_giocatori(db_session):
    campionato = _campionato_con_partite(
        db_session,
        [
            MatchStatus.CONFIRMED_BY_BOTH.value,
            MatchStatus.CONFIRMED_BY_BOTH.value,
            MatchStatus.CLOSED_UNILATERALLY.value,
            MatchStatus.PENDING.value,
        ],
    )

    statistiche = TournamentStatisticsService().calculate_campionato_statistics(
        campionato.id
    )

    assert statistiche["total_completed_matches"] == 3
    assert statistiche["total_racks_played"] == 12


def test_non_si_elimina_per_sempre_un_campionato_giocato(db_session):
    campionato = _campionato_con_partite(
        db_session, [MatchStatus.CONFIRMED_BY_BOTH.value]
    )

    assert campionato.can_be_hard_deleted() is False


def test_senza_partite_giocate_si_elimina_ancora(db_session):
    campionato = _campionato_con_partite(db_session, [MatchStatus.PENDING.value])

    assert campionato.can_be_hard_deleted() is True
