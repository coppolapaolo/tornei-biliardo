"""Regression (bug 8 docs/debug20260528.md): start_playoff non trova
qualificati anche quando la classifica generale del campionato è
visibile in dashboard. Cause concorrenti:

1. `terminate_campionato` soft-eliminava le gare PLAYING anche quando
   erano "TOURNAMENT_COMPLETED" (tutti i match finiti), svuotando la
   classifica.
2. `PlayoffService.start_playoff` leggeva `Classification.query` senza
   prima invocare `update_campionato_classification`: i record non
   esistevano se nessuna pipeline li aveva creati.
3. `PlayoffConfiguration._meets_minimum_requirements` filtrava per
   `Gara.status == "completed"`, fallendo quando le gare erano di
   fatto concluse ma non chiuse formalmente.

Il fix combina i tre interventi: questo test verifica che il flusso
completo (gara con tutti i match finiti → terminate → start_playoff)
produca le qualifiche attese.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Inscription, User
from models.base import utc_now
from models.campionato.models import Campionato
from models.match.models import Match
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
)
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _make_player(db_session, idx: int) -> User:
    uid = uuid.uuid4().hex[:6]
    u = User(
        username=f"playoff_p{idx}_{uid}",
        email=f"playoff_p{idx}_{uid}@test.local",
        role=UserRole.PLAYER.value,
    )
    u.set_password("x")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.mark.integration
def test_start_playoff_finds_qualified_after_terminate(db_session):
    """4 player, 1 gara con tutti i match completati ma gara.status=PLAYING:
    dopo terminate_campionato + start_playoff devono qualificarsi i top 3."""
    from models.campionato.services import TournamentService
    from models.playoff.services import PlayoffService

    players = [_make_player(db_session, i) for i in range(1, 5)]

    campionato = Campionato(
        name=f"PlayoffCamp {uuid.uuid4().hex[:6]}",
        campionato_type="random",
        is_active=True,
    )
    db_session.add(campionato)
    db_session.commit()

    gara = Gara(
        campionato_id=campionato.id,
        number=1,
        name="GaraPlayoff",
        date=date.today() - timedelta(days=1),
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        rounds_count=1,
        min_participants=4,
        max_participants=4,
        status=GaraStatus.PLAYING.value,
        current_round=1,
        inscription_start=utc_now() - timedelta(days=2),
        inscription_end=utc_now() - timedelta(hours=1),
        matchmaking_strategy="random",
        classification_system="WINS",
    )
    db_session.add(gara)
    db_session.commit()

    for p in players:
        db_session.add(Inscription(gara_id=gara.id, user_id=p.id))
    db_session.commit()

    # 2 match completed: player1 batte player2 (5-0), player3 batte player4 (5-0)
    matches = [
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            player1_score=5,
            player2_score=0,
            winner_id=players[0].id,
            match_distance=5,
            is_race_to=True,
        ),
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[2].id,
            player2_id=players[3].id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            player1_score=5,
            player2_score=0,
            winner_id=players[2].id,
            match_distance=5,
            is_race_to=True,
        ),
    ]
    db_session.add_all(matches)
    db_session.commit()

    # Playoff config: top 3, min 1 gara giocata
    config = PlayoffConfiguration(
        campionato_id=campionato.id,
        name="Test Top 3",
        playoff_type=PlayoffType.TOP_N,
        max_participants=3,
        positions_from=1,
        positions_to=3,
        min_garas_played=1,
        is_active=True,
        auto_generate=True,
    )
    db_session.add(config)
    db_session.commit()

    # Terminate: la gara PLAYING-TOURNAMENT_COMPLETED deve passare a COMPLETED,
    # non essere soft-eliminata; la classifica DB viene popolata.
    service = TournamentService()
    assert service.terminate_campionato(campionato.id) is True

    db_session.refresh(gara)
    assert gara.is_deleted is False, "Gara non doveva essere soft-eliminata"
    assert gara.status == GaraStatus.COMPLETED.value

    # start_playoff: troviamo qualificati
    results = PlayoffService.start_playoff(campionato.id)
    assert "Test Top 3" in results
    quals = results["Test Top 3"]
    assert len(quals) == 3, f"Atteso 3 qualificati per top 3, trovati {len(quals)}"

    persisted = PlayoffQualification.query.filter_by(configuration_id=config.id).all()
    assert len(persisted) == 3
    positions = sorted(q.qualifying_position for q in persisted)
    assert positions == [1, 2, 3]
