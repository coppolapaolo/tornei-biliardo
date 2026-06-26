"""Workstream A — un match casual VALIDATO alimenta la gamification (gated).

Verifica end-to-end che la conferma bilaterale di un IndividualMatch:
- assegni XP RIDOTTO (CASUAL_MATCH_WIN/LOSS, 20/5) e non quello torneo;
- registri streak/quest;
- NON crei rating ELO competitivo (resta riservato ai tornei).
"""

from datetime import timedelta

import pytest

from models.individual_match.models import IndividualMatch
from models.gamification.models import XPTransaction, XPTransactionType
from models.gamification.models import StreakTracker, StreakType
from models.rating.models import PlayerRating, RatingSystem
from models.status_enum import MatchStatus
from models.base import utc_now


@pytest.fixture(autouse=True)
def _seed(db_session):
    """Achievement seed: l'handler casual ne controlla alcuni (first_blood, ...)."""
    from models.gamification.achievement_seeds import seed_achievements

    seed_achievements(db_session)
    yield


def _validate_casual(db_session, p1, p2, s1, s2):
    m = IndividualMatch(
        player1_id=p1,
        player2_id=p2,
        location="Hall",
        scheduled_at=utc_now() + timedelta(hours=1),
        status=MatchStatus.IN_PROGRESS,
        distance=5,
        is_race_to=True,
        player1_score=s1,
        player2_score=s2,
    )
    db_session.add(m)
    db_session.commit()
    m.confirm_result(p1)
    m.confirm_result(p2)
    db_session.commit()
    return m


def test_casual_validated_awards_reduced_xp(app, db_session, isolated_players):
    winner, loser = isolated_players[:2]
    _validate_casual(db_session, winner.id, loser.id, 5, 2)

    win_tx = XPTransaction.query.filter_by(
        user_id=winner.id, transaction_type=XPTransactionType.CASUAL_MATCH_WIN
    ).all()
    loss_tx = XPTransaction.query.filter_by(
        user_id=loser.id, transaction_type=XPTransactionType.CASUAL_MATCH_LOSS
    ).all()

    assert len(win_tx) == 1 and win_tx[0].xp_amount == 20
    assert len(loss_tx) == 1 and loss_tx[0].xp_amount == 5

    # Nessun XP "torneo" assegnato per un casual
    assert (
        XPTransaction.query.filter_by(
            user_id=winner.id, transaction_type=XPTransactionType.MATCH_WIN
        ).count()
        == 0
    )


def test_casual_validated_records_match_streak(app, db_session, isolated_players):
    winner, loser = isolated_players[:2]
    _validate_casual(db_session, winner.id, loser.id, 5, 1)

    for uid in (winner.id, loser.id):
        streak = StreakTracker.query.filter_by(
            user_id=uid, streak_type=StreakType.WEEKLY_MATCH
        ).first()
        assert streak is not None and streak.current_streak >= 1


def test_casual_validated_does_not_touch_competitive_elo(
    app, db_session, isolated_players
):
    """Vincolo integrità: il casual non crea rating ELO competitivo."""
    winner, loser = isolated_players[:2]
    _validate_casual(db_session, winner.id, loser.id, 5, 0)

    elo_ratings = PlayerRating.query.filter_by(rating_system=RatingSystem.ELO).count()
    assert elo_ratings == 0
