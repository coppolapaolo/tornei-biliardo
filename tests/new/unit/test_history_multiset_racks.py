"""Regression: lo storico conta i rack reali per i match multi-set.

Bug (code review 2026-06-09, HIGH correttezza) —
`models/player/history_service.py:291`:

_calculate_match_stats sommava `player1_score`/`player2_score` come rack
vinti/persi anche per i match multi-set, dove però quei campi rappresentano
i SET vinti, non i rack (vedi models/match/CLAUDE.md "Score Interpretation").
Per un best-of-5 vinto 3 set a 1, total_racks_won veniva incrementato di 3
(set) invece dei rack effettivi giocati nei set.

Il fix somma i rack reali dai record Set per i match multi-set.
"""

from __future__ import annotations

import uuid

import pytest

from models.user.models import User
from models.user.role_enum import UserRole
from models.match.models import Match
from models.match.set_models import Set
from models.status_enum import MatchStatus
from models.player.history_service import PlayerHistoryService


def _user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    u = User(
        username=f"h_{uid}", email=f"h_{uid}@test.local", role=UserRole.PLAYER.value
    )
    u.set_password("x")
    db_session.add(u)
    db_session.flush()
    return u


def _add_set(db_session, match, n, p1_racks, p2_racks):
    s = Set(
        match_id=match.id,
        set_number=n,
        distance=5,
        player1_racks=p1_racks,
        player2_racks=p2_racks,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    db_session.add(s)
    db_session.flush()
    return s


@pytest.mark.unit
def test_multiset_counts_real_racks_not_sets(db_session):
    a = _user(db_session)
    b = _user(db_session)

    # Best-of-5: A vince 3 set a 1. player*_score = SET vinti.
    match = Match(
        gara_id=None,
        round_number=1,
        player1_id=a.id,
        player2_id=b.id,
        is_multi_set=True,
        match_distance=3,
        player1_score=3,
        player2_score=1,
        winner_id=a.id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    db_session.add(match)
    db_session.flush()

    # Rack reali nei set: A = 5+5+1+5 = 16; B = 2+3+5+0 = 10.
    _add_set(db_session, match, 1, 5, 2)
    _add_set(db_session, match, 2, 5, 3)
    _add_set(db_session, match, 3, 1, 5)
    _add_set(db_session, match, 4, 5, 0)
    db_session.flush()

    stats = PlayerHistoryService._calculate_match_stats([match], a.id)

    # Prima del fix: 3 / 1 (conteggio set). Dopo: rack reali dai set.
    assert stats.total_racks_won == 16
    assert stats.total_racks_lost == 10


@pytest.mark.unit
def test_single_set_unchanged(db_session):
    """Match single-set: player*_score sono rack, conteggio invariato."""
    a = _user(db_session)
    b = _user(db_session)

    match = Match(
        gara_id=None,
        round_number=1,
        player1_id=a.id,
        player2_id=b.id,
        is_multi_set=False,
        player1_score=5,
        player2_score=3,
        winner_id=a.id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    db_session.add(match)
    db_session.flush()

    stats = PlayerHistoryService._calculate_match_stats([match], a.id)
    assert stats.total_racks_won == 5
    assert stats.total_racks_lost == 3
