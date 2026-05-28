"""Regression (bug 6 docs/debug20260528.md): nuove debug action
`complete_next_match` (un match alla volta) e `complete_gara` (loop
fino a fine gara con avanzamento automatico dei turni)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Inscription, User
from models.base import utc_now
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _make_player(db_session, idx: int) -> User:
    uid = uuid.uuid4().hex[:6]
    u = User(
        username=f"player{idx}_{uid}",
        email=f"p{idx}_{uid}@test.local",
        role=UserRole.PLAYER.value,
    )
    u.set_password("x")
    db_session.add(u)
    db_session.commit()
    return u


def _setup_random_pregenerated_gara(db_session, num_players: int = 4):
    """Crea gara PLAYING al turno 1, 2 turni, match pre-generati su
    entrambi (random/round-robin style)."""
    players = [_make_player(db_session, i) for i in range(1, num_players + 1)]
    gara = Gara(
        number=1,
        name="GaraDbg",
        date=date.today() + timedelta(days=1),
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        rounds_count=2,
        min_participants=num_players,
        max_participants=num_players,
        status=GaraStatus.PLAYING.value,
        current_round=1,
        inscription_start=utc_now() - timedelta(days=1),
        inscription_end=utc_now() + timedelta(days=2),
        available_tables='["1", "2"]',
        matchmaking_strategy="random",
    )
    db_session.add(gara)
    db_session.commit()
    for p in players:
        db_session.add(Inscription(gara_id=gara.id, user_id=p.id))
    db_session.commit()

    # Round 1 - 2 match PLAYING con tavolo
    matches = [
        Match(
            gara_id=gara.id, round_number=1,
            player1_id=players[0].id, player2_id=players[1].id,
            status=MatchStatus.PLAYING.value, table_assignment="1",
            match_distance=5, is_race_to=True,
        ),
        Match(
            gara_id=gara.id, round_number=1,
            player1_id=players[2].id, player2_id=players[3].id,
            status=MatchStatus.PLAYING.value, table_assignment="2",
            match_distance=5, is_race_to=True,
        ),
        # Round 2 - 2 match PENDING senza tavolo (rotazione)
        Match(
            gara_id=gara.id, round_number=2,
            player1_id=players[0].id, player2_id=players[2].id,
            status=MatchStatus.PENDING.value,
            match_distance=5, is_race_to=True,
        ),
        Match(
            gara_id=gara.id, round_number=2,
            player1_id=players[1].id, player2_id=players[3].id,
            status=MatchStatus.PENDING.value,
            match_distance=5, is_race_to=True,
        ),
    ]
    db_session.add_all(matches)
    db_session.commit()
    return gara


@pytest.mark.integration
def test_complete_next_match_completes_one(client, db_session):
    gara = _setup_random_pregenerated_gara(db_session)

    resp = client.get(
        f"/debug/complete_next_match/{gara.id}", follow_redirects=False
    )
    assert resp.status_code in (302, 303)

    completed = Match.query.filter_by(
        gara_id=gara.id, round_number=1, status=MatchStatus.COMPLETED.value
    ).count()
    pending = Match.query.filter_by(
        gara_id=gara.id, round_number=1
    ).filter(
        Match.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value])
    ).count()

    assert completed == 1, f"Atteso 1 completato, trovati {completed}"
    assert pending == 1, f"Atteso 1 ancora in corso, trovati {pending}"


@pytest.mark.integration
def test_complete_gara_finishes_all_matches(client, db_session):
    gara = _setup_random_pregenerated_gara(db_session)

    resp = client.get(f"/debug/complete_gara/{gara.id}", follow_redirects=False)
    assert resp.status_code in (302, 303)

    # Tutti i 4 match devono essere completati
    all_matches = Match.query.filter_by(gara_id=gara.id).all()
    assert len(all_matches) == 4
    assert all(
        m.status in (MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value)
        for m in all_matches
    ), f"Match status: {[m.status for m in all_matches]}"
