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
    _match(db_session, me.id, opp.id, MatchStatus.CONFIRMED_BY_BOTH, me.id, 5, 2)
    _match(db_session, opp.id, me.id, MatchStatus.CONFIRMED_BY_BOTH, opp.id, 5, 1)
    _match(db_session, me.id, opp.id, MatchStatus.CLOSED_UNILATERALLY, me.id, 5, 0)

    stats = Stats.get_user_statistics(me.id)

    assert stats["total_matches"] == 3  # tutti i finiti, non solo COMPLETED
    assert stats["won_matches"] == 2
    assert stats["lost_matches"] == 1


def test_statistics_exclude_unfinished(app, db_session, isolated_players):
    me, opp = isolated_players[:2]
    _match(db_session, me.id, opp.id, MatchStatus.CONFIRMED_BY_BOTH, me.id)
    _match(db_session, me.id, opp.id, MatchStatus.SCHEDULED, None, 0, 0)
    _match(db_session, me.id, opp.id, MatchStatus.IN_PROGRESS, None, 2, 1)

    stats = Stats.get_user_statistics(me.id)
    assert stats["total_matches"] == 1  # solo il VALIDATED


def test_dashboard_recent_includes_validated(app, db_session, isolated_players):
    me, opp = isolated_players[:2]
    _match(db_session, me.id, opp.id, MatchStatus.CONFIRMED_BY_BOTH, me.id)

    data = Stats.get_user_dashboard_data(me.id)
    assert len(data["recent_matches"]) == 1
    assert data["statistics"]["total_matches"] == 1


def test_statistics_secondary_panels_populated(app, db_session, isolated_players):
    """I pannelli by_discipline / head_to_head / trend / monthly devono essere
    popolati quando ci sono match (prima erano sempre vuoti: dati mai forniti)."""
    me, opp = isolated_players[:2]
    _match(db_session, me.id, opp.id, MatchStatus.CONFIRMED_BY_BOTH, me.id, 5, 2)
    _match(db_session, opp.id, me.id, MatchStatus.CONFIRMED_BY_BOTH, me.id, 1, 5)
    _match(db_session, me.id, opp.id, MatchStatus.CLOSED_UNILATERALLY, opp.id, 0, 5)

    stats = Stats.get_user_statistics(me.id)

    # by_discipline: tutti 8_ball → 1 riga, 3 match, 2 vinti
    assert len(stats["by_discipline"]) == 1
    d = stats["by_discipline"][0]
    assert d["total_matches"] == 3 and d["wins"] == 2 and d["losses"] == 1

    # head_to_head: un solo avversario, 3 match, 2-1
    assert len(stats["head_to_head"]) == 1
    h = stats["head_to_head"][0]
    assert h["opponent_username"] == opp.username
    assert h["total_matches"] == 3 and h["wins"] == 2 and h["losses"] == 1

    # trend
    assert len(stats["recent_matches"]) == 3
    assert stats["recent_wins"] == 2 and stats["recent_losses"] == 1

    # monthly_activity: almeno un mese con i match
    assert len(stats["monthly_activity"]) >= 1
    assert sum(mo["total_matches"] for mo in stats["monthly_activity"]) == 3
