"""Il turno nuovo si annuncia a chi sta guardando la gara.

La pagina della gara ricarica quando arriva `round_started`. Il bridge lo
emetteva ascoltando `CompetitionStartedEvent`, che però nessuno pubblicava: né
il primo turno né i successivi producevano nulla, e chi aveva la pagina aperta
scopriva il turno nuovo solo ricaricando a mano. L'evento nasce ora dove nasce
il turno, in `RoundService`, dentro la stessa transazione.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import User
from models.base import utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import Discipline
from models.user.role_enum import UserRole
from routes.sse import EventScope, _get_events_since


def _utente(db_session, ruolo: str) -> User:
    suffisso = uuid.uuid4().hex[:8]
    utente = User(
        username=f"{ruolo}_{suffisso}", email=f"{suffisso}@test.local", role=ruolo
    )
    utente.set_password("x")
    db_session.add(utente)
    db_session.commit()
    return utente


def _gara_con_iscritti(db_session, strategia: str, giocatori: int, turni: int):
    direttore = _utente(db_session, UserRole.DIRECTOR.value)
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Gara live",
        date=date.today() + timedelta(days=7),
        location="Sala",
        description="",
        rounds_count=turni,
        min_participants=2,
        max_participants=16,
        entry_fee=0.0,
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        director_id=direttore.id,
        matchmaking_strategy=strategia,
        first_round_policy="random",
        odd_number_policy="bye",
        anti_rematch_enabled=False,
    )
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for _ in range(giocatori):
        InscriptionService.inscribe_user(
            _utente(db_session, UserRole.PLAYER.value).id, gara.id
        )
    return gara


def _turni_annunciati(gara_id: int) -> list[int]:
    return [
        e["data"]["round_number"]
        for e in _get_events_since(EventScope.GARA, gara_id, 0)
        if e["type"] == "round_started"
    ]


@pytest.fixture(autouse=True)
def _archivio_pulito(db_session):
    from models.live_event import LiveEvent

    LiveEvent.query.delete()
    db_session.commit()


@pytest.mark.integration
def test_il_primo_turno_si_annuncia(db_session):
    gara = _gara_con_iscritti(
        db_session, MatchmakingStrategy.ROUND_ROBIN.value, giocatori=4, turni=3
    )
    RoundService.start_first_round(gara.id)
    assert _turni_annunciati(gara.id) == [1]


@pytest.mark.integration
def test_anche_il_turno_successivo_si_annuncia(db_session):
    gara = _gara_con_iscritti(
        db_session, MatchmakingStrategy.ROUND_ROBIN.value, giocatori=4, turni=3
    )
    RoundService.start_first_round(gara.id)
    # Il turno dopo parte solo a turno chiuso: dal 2026-09-13 lo controlla il
    # servizio, non piu' solo le route (SPECIFICHE.md, «Cosa deve essere chiuso
    # prima del turno successivo»).
    from models.match.models import Match
    from models.status_enum import MatchStatus

    for partita in Match.query.filter_by(gara_id=gara.id, round_number=1).all():
        if not partita.is_bye:
            partita.player1_score, partita.player2_score = 5, 2
            partita.winner_id = partita.player1_id
            partita.status = MatchStatus.CLOSED_UNILATERALLY.value
    db_session.commit()
    RoundService.start_next_round(gara.id, 2)
    assert _turni_annunciati(gara.id) == [1, 2]


@pytest.mark.integration
def test_col_sorteggio_casuale_i_turni_nascono_insieme_e_l_annuncio_e_uno(
    db_session,
):
    """La strategia casuale crea tutti i turni in un colpo: per chi guarda è
    un avvio solo, non tre."""
    gara = _gara_con_iscritti(
        db_session, MatchmakingStrategy.RANDOM.value, giocatori=4, turni=3
    )
    RoundService.start_first_round(gara.id)
    assert _turni_annunciati(gara.id) == [1]
