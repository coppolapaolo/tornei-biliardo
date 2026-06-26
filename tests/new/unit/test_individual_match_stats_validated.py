"""Regression: individual-match statistics must count VALIDATED matches.

Bilateral confirmation closes a match as VALIDATED (the normal flow); only
forfeit/legacy-complete produce COMPLETED. Counting only COMPLETED dropped the
majority of finished matches from a user's statistics.
"""

from datetime import timedelta

from models.individual_match.models import IndividualMatch
from models.individual_match.statistics_service import (
    IndividualMatchStatisticsService as Stats,
)
from models.status_enum import MatchStatus
from models.base import utc_now


def _match(db_session, p1, p2, status, winner_id, s1=5, s2=3):
    m = IndividualMatch(
        player1_id=p1,
        player2_id=p2,
        location="Hall",
        scheduled_at=utc_now() + timedelta(hours=1),
        status=status,
        distance=5,
        is_race_to=True,
        player1_score=s1,
        player2_score=s2,
        winner_id=winner_id,
    )
    db_session.add(m)
    db_session.commit()
    return m


def test_statistics_count_validated_matches(app, db_session, isolated_players):
    me, opp = isolated_players[:2]
    # 1 VALIDATED won, 1 VALIDATED lost, 1 COMPLETED won
    _match(db_session, me.id, opp.id, MatchStatus.VALIDATED, me.id, 5, 2)
    _match(db_session, opp.id, me.id, MatchStatus.VALIDATED, opp.id, 5, 1)
    _match(db_session, me.id, opp.id, MatchStatus.COMPLETED, me.id, 5, 0)

    stats = Stats.get_user_statistics(me.id)

    assert stats["total_matches"] == 3  # tutti i finiti, non solo COMPLETED
    assert stats["won_matches"] == 2
    assert stats["lost_matches"] == 1


def test_statistics_exclude_unfinished(app, db_session, isolated_players):
    me, opp = isolated_players[:2]
    _match(db_session, me.id, opp.id, MatchStatus.VALIDATED, me.id)
    _match(db_session, me.id, opp.id, MatchStatus.SCHEDULED, None, 0, 0)
    _match(db_session, me.id, opp.id, MatchStatus.IN_PROGRESS, None, 2, 1)

    stats = Stats.get_user_statistics(me.id)
    assert stats["total_matches"] == 1  # solo il VALIDATED


def test_dashboard_recent_includes_validated(app, db_session, isolated_players):
    me, opp = isolated_players[:2]
    _match(db_session, me.id, opp.id, MatchStatus.VALIDATED, me.id)

    data = Stats.get_user_dashboard_data(me.id)
    assert len(data["recent_matches"]) == 1
    assert data["statistics"]["total_matches"] == 1
