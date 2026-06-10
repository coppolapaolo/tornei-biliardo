"""Regression (bug 5 docs/debug20260528.md): dopo `debug_complete_current_round`
i tavoli del turno corrente devono essere rilasciati e riassegnati ai
match in attesa del turno successivo. Prima del fix il debug action
settava match.status=COMPLETED ma non chiamava assign_available_tables,
lasciando i match del turno 2+ pending senza tavolo.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Inscription, User
from models.base import utc_now
from models.match.models import Match
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
def test_complete_round_reassigns_tables_to_next_round(client, db_session):
    """Setup: 4 player, 2 tavoli, 2 match al turno 1 (PLAYING con tavoli)
    + 2 match al turno 2 (PENDING senza tavoli). Dopo complete_round del
    debug footer i tavoli devono spostarsi sui match del turno 2."""
    players = [_make_player(db_session, f"p{i}") for i in range(1, 5)]

    gara = Gara(
        number=1,
        name="GaraTblReassign",
        date=date.today() + timedelta(days=1),
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        rounds_count=2,
        min_participants=4,
        max_participants=4,
        status=GaraStatus.PLAYING.value,
        current_round=1,
        inscription_start=utc_now() - timedelta(days=1),
        inscription_end=utc_now() + timedelta(days=2),
        available_tables='["1", "2"]',
    )
    db_session.add(gara)
    db_session.commit()

    for p in players:
        db_session.add(Inscription(gara_id=gara.id, user_id=p.id))
    db_session.commit()

    # Turno 1: 2 match PLAYING con tavolo
    m1_r1 = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=players[0].id,
        player2_id=players[1].id,
        status=MatchStatus.PLAYING.value,
        table_assignment="1",
        match_distance=5,
        is_race_to=True,
    )
    m2_r1 = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=players[2].id,
        player2_id=players[3].id,
        status=MatchStatus.PLAYING.value,
        table_assignment="2",
        match_distance=5,
        is_race_to=True,
    )
    # Turno 2: 2 match PENDING senza tavolo (rotazione opponents)
    m1_r2 = Match(
        gara_id=gara.id,
        round_number=2,
        player1_id=players[0].id,
        player2_id=players[2].id,
        status=MatchStatus.PENDING.value,
        match_distance=5,
        is_race_to=True,
    )
    m2_r2 = Match(
        gara_id=gara.id,
        round_number=2,
        player1_id=players[1].id,
        player2_id=players[3].id,
        status=MatchStatus.PENDING.value,
        match_distance=5,
        is_race_to=True,
    )
    db_session.add_all([m1_r1, m2_r1, m1_r2, m2_r2])
    db_session.commit()

    resp = client.get(
        f"/debug/complete_current_round/{gara.id}", follow_redirects=False
    )
    assert resp.status_code in (302, 303)

    # Refresh dal DB
    r1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
    r2_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()

    # Turno 1: completato, tavoli rilasciati
    assert all(m.status == MatchStatus.COMPLETED.value for m in r1_matches)
    assert all(
        m.table_assignment is None for m in r1_matches
    ), "Tavoli del turno 1 devono essere rilasciati"

    # Turno 2: i 2 match hanno ricevuto i 2 tavoli, status PLAYING
    r2_with_table = [m for m in r2_matches if m.table_assignment is not None]
    assert (
        len(r2_with_table) == 2
    ), f"Atteso 2 match turno 2 con tavolo, trovati {len(r2_with_table)}"
    assert all(m.status == MatchStatus.PLAYING.value for m in r2_with_table)
    assert {m.table_assignment for m in r2_with_table} == {"1", "2"}
