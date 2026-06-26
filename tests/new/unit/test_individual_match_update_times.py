"""Regression: IndividualMatchService.update_times must reject an end time
that precedes the start time (HIGH finding)."""

import pytest
from datetime import timedelta

from models.individual_match.models import IndividualMatch
from models.individual_match.services import IndividualMatchService
from models.status_enum import MatchStatus
from models.base import utc_now


def _make_match(db_session, players):
    player1, player2 = players[:2]
    match = IndividualMatch(
        player1_id=player1.id,
        player2_id=player2.id,
        location="Test Hall",
        scheduled_at=utc_now() + timedelta(hours=1),
        status=MatchStatus.IN_PROGRESS,
        distance=5,
        is_race_to=True,
    )
    db_session.add(match)
    db_session.commit()
    return match


def test_update_times_rejects_end_before_start(app, db_session, isolated_players):
    match = _make_match(db_session, isolated_players)
    start = utc_now()
    end = start - timedelta(hours=1)  # fine prima dell'inizio

    with pytest.raises(ValueError, match="fine non può precedere"):
        # user_id=None salta il permission check, isola la validazione temporale
        IndividualMatchService.update_times(
            match_id=match.id, started_at=start, ended_at=end, user_id=None
        )


def test_update_times_accepts_consistent_range(app, db_session, isolated_players):
    match = _make_match(db_session, isolated_players)
    start = utc_now()
    end = start + timedelta(hours=2)

    result = IndividualMatchService.update_times(
        match_id=match.id, started_at=start, ended_at=end, user_id=None
    )
    assert result.started_at == start
    assert result.ended_at == end
