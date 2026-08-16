"""
Integration tests for LeaderboardService.

Primo test del servizio classifiche (nessuno esisteva). Copre in particolare
STREAK_LONGEST, che prima della Fase 1 non impostava né `score` né
`calculated_at` negli entry calcolati (`_calculate_streak_longest`): poiché
`LeaderboardEntry.score` è NOT NULL, la classifica STREAK_LONGEST falliva del
tutto al refresh. Vedi GAMIFICATION_V3_HANDOFF.md (Task A).
"""

from models.base import db
from models.gamification.leaderboard_service import LeaderboardService
from models.gamification.models import (
    StreakTracker,
    StreakType,
    LeaderboardEntry,
    LeaderboardType,
)


def _make_streak(user_id: int, *, current: int, longest: int) -> StreakTracker:
    tracker = StreakTracker(
        user_id=user_id,
        streak_type=StreakType.WEEKLY_ACTIVITY,
        current_streak=current,
        longest_streak=longest,
    )
    db.session.add(tracker)
    return tracker


class TestStreakLongestLeaderboard:
    """STREAK_LONGEST deve popolarsi con score e calculated_at corretti."""

    def test_streak_longest_populates_score_and_calculated_at(
        self, db_session, isolated_players
    ):
        """
        GIVEN tre giocatori con longest_streak diversi
        WHEN si richiede la classifica STREAK_LONGEST (force_refresh)
        THEN gli entry sono ordinati per longest_streak desc con score valorizzato
             e calculated_at non nullo (prima il refresh falliva: score NOT NULL).
        """
        p0, p1, p2 = isolated_players[0], isolated_players[1], isolated_players[2]
        _make_streak(p0.id, current=1, longest=3)
        _make_streak(p1.id, current=2, longest=9)
        _make_streak(p2.id, current=0, longest=5)
        db_session.commit()

        results = LeaderboardService.get_leaderboard(
            LeaderboardType.STREAK_LONGEST, force_refresh=True
        )

        # Ordine atteso per longest_streak desc: p1 (9), p2 (5), p0 (3)
        assert [r["user"].id for r in results] == [p1.id, p2.id, p0.id]
        # Lo score deve riflettere longest_streak (prima era NULL → crash)
        assert [r["score"] for r in results] == [9.0, 5.0, 3.0]
        assert [r["rank"] for r in results] == [1, 2, 3]

        # calculated_at deve essere valorizzato su ogni entry persistito
        entries = LeaderboardEntry.query.filter_by(
            leaderboard_type=LeaderboardType.STREAK_LONGEST
        ).all()
        assert len(entries) == 3
        assert all(e.calculated_at is not None for e in entries)
        assert all(e.score is not None for e in entries)

    def test_streak_longest_excludes_zero_streaks(self, db_session, isolated_players):
        """Solo le streak > 0 finiscono in classifica."""
        p0, p1 = isolated_players[0], isolated_players[1]
        _make_streak(p0.id, current=0, longest=0)
        _make_streak(p1.id, current=1, longest=4)
        db_session.commit()

        results = LeaderboardService.get_leaderboard(
            LeaderboardType.STREAK_LONGEST, force_refresh=True
        )

        assert [r["user"].id for r in results] == [p1.id]
        assert results[0]["score"] == 4.0
