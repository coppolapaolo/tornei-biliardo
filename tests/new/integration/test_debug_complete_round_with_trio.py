"""Regression (bug 7 docs/debug20260528.md): complete_round del debug
footer deve completare anche i trio match (3-player). Prima il codice
saltava i trio (`if match.is_trio: continue`) lasciandoli in stato
PLAYING/PENDING.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Inscription, User
from models.base import utc_now
from models.match.models import Match, TrioMatch
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _make_player(db_session, name: str) -> User:
    uid = uuid.uuid4().hex[:6]
    u = User(
        username=f"{name}_{uid}",
        email=f"{name}_{uid}@test.local",
        role=UserRole.PLAYER.value,
    )
    u.set_password("x")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.mark.integration
def test_complete_round_completes_trio_matches(client, db_session):
    """5 player, 1 trio (3 player) + 1 match normale (2 player), entrambi
    devono essere completati dopo /debug/complete_current_round."""
    players = [_make_player(db_session, f"p{i}") for i in range(1, 6)]
    gara = Gara(
        number=1,
        name="GaraTrioDbg",
        date=date.today() + timedelta(days=1),
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        rounds_count=1,
        min_participants=5,
        max_participants=5,
        status=GaraStatus.PLAYING.value,
        current_round=1,
        inscription_start=utc_now() - timedelta(days=1),
        inscription_end=utc_now() + timedelta(days=2),
        available_tables='["1", "2"]',
        odd_number_policy="trio",
    )
    db_session.add(gara)
    db_session.commit()
    for p in players:
        db_session.add(Inscription(gara_id=gara.id, user_id=p.id))
    db_session.commit()

    normal_match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=players[0].id,
        player2_id=players[1].id,
        status=MatchStatus.PLAYING.value,
        table_assignment="1",
        match_distance=5,
        is_race_to=True,
    )
    trio_match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=players[2].id,
        player2_id=players[3].id,
        status=MatchStatus.PLAYING.value,
        table_assignment="2",
        is_trio=True,
        match_distance=5,
        is_race_to=True,
    )
    db_session.add_all([normal_match, trio_match])
    db_session.flush()

    trio = TrioMatch(
        match_id=trio_match.id,
        player1_id=players[2].id,
        player2_id=players[3].id,
        player3_id=players[4].id,
    )
    db_session.add(trio)
    db_session.commit()

    resp = client.get(
        f"/debug/complete_current_round/{gara.id}", follow_redirects=False
    )
    assert resp.status_code in (302, 303)

    normal_after = Match.query.get(normal_match.id)
    trio_after = Match.query.get(trio_match.id)
    db_session.refresh(trio)

    assert MatchStatus.is_finished(normal_after.status)
    assert trio_after.status == MatchStatus.CLOSED_UNILATERALLY.value
    assert trio.is_completed is True
    assert trio.winner_id is not None, "Il trio deve avere un vincitore"
