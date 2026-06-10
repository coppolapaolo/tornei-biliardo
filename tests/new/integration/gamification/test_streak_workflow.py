"""
Integration tests for Weekly Streak Workflow.

Tests the complete streak lifecycle:
- Recording weekly activities
- Earning freezes at milestones (4/12/52 weeks)
- Using freezes when missing a week
- Streak breaking when missing 2+ weeks
- XP bonus awards for milestones
- Event emission for notifications
"""

import pytest
from datetime import date
from unittest.mock import patch, MagicMock

from models.gamification.streak_service import StreakService
from models.gamification.level_service import LevelService
from models.gamification.models import (
    StreakTracker,
    StreakType,
    UserLevel,
    XPTransaction,
    XPTransactionType,
)
from models.gamification.xp_config import XP_RATES
from models.events.base import EventBus


class TestStreakWorkflowComplete:
    """Test complete streak workflows."""

    def test_complete_4_week_streak_earns_freeze_and_xp(
        self, db_session, isolated_players
    ):
        """
        GIVEN a new user
        WHEN they maintain activity for 4 consecutive weeks
        THEN they earn a freeze and XP bonus
        """
        player = isolated_players[0]
        events_published = []

        # Capture events
        original_publish = EventBus.publish

        def mock_publish(event):
            events_published.append(event)
            return original_publish(event)

        with patch.object(EventBus, "publish", side_effect=mock_publish):
            # Simulate 4 weeks of activity
            for week in range(10, 14):  # Weeks 10, 11, 12, 13
                with patch.object(
                    StreakService, "get_current_iso_week", return_value=(week, 2024)
                ):
                    tracker, result = StreakService.record_activity(
                        user_id=player.id, streak_type=StreakType.WEEKLY_ACTIVITY
                    )

        # Verify final state
        assert tracker.current_streak == 4
        assert tracker.milestone_4_reached is True
        assert tracker.freeze_count == 1  # Earned 1 freeze

        # Verify XP was awarded
        user_level = db_session.get(UserLevel, player.id)
        expected_xp = XP_RATES[XPTransactionType.STREAK_BONUS] * 4  # 30 * 4 = 120
        assert user_level is not None
        assert user_level.total_xp >= expected_xp

        # Verify milestone event was published
        milestone_events = [
            e for e in events_published if hasattr(e, "milestone") and e.milestone == 4
        ]
        assert len(milestone_events) == 1

    def test_freeze_saves_streak_when_missing_one_week(
        self, db_session, isolated_players
    ):
        """
        GIVEN a user with a streak and 1 freeze
        WHEN they miss exactly 1 week
        THEN freeze is consumed and streak continues
        """
        player = isolated_players[0]

        # Build 2-week streak
        with patch.object(
            StreakService, "get_current_iso_week", return_value=(10, 2024)
        ):
            StreakService.record_activity(
                user_id=player.id, streak_type=StreakType.WEEKLY_ACTIVITY
            )

        with patch.object(
            StreakService, "get_current_iso_week", return_value=(11, 2024)
        ):
            StreakService.record_activity(
                user_id=player.id, streak_type=StreakType.WEEKLY_ACTIVITY
            )

        # Grant a freeze
        StreakService.admin_grant_freeze(
            user_id=player.id, streak_type=StreakType.WEEKLY_ACTIVITY, freeze_count=1
        )

        # Miss week 12, return in week 13
        with patch.object(
            StreakService, "get_current_iso_week", return_value=(13, 2024)
        ):
            tracker, result = StreakService.record_activity(
                user_id=player.id, streak_type=StreakType.WEEKLY_ACTIVITY
            )

        # Streak should continue
        assert result["action"] == "freeze_used"
        assert tracker.current_streak == 3  # 2 + 1 (freeze saved)
        assert tracker.freeze_count == 0  # Freeze consumed

    def test_streak_breaks_when_missing_two_weeks(self, db_session, isolated_players):
        """
        GIVEN a user with a 5-week streak
        WHEN they miss 2+ weeks
        THEN streak breaks (even with freezes)
        """
        player = isolated_players[0]

        # Build 5-week streak
        for week in range(10, 15):  # Weeks 10-14
            with patch.object(
                StreakService, "get_current_iso_week", return_value=(week, 2024)
            ):
                StreakService.record_activity(
                    user_id=player.id, streak_type=StreakType.WEEKLY_MATCH
                )

        # Grant multiple freezes
        StreakService.admin_grant_freeze(
            user_id=player.id, streak_type=StreakType.WEEKLY_MATCH, freeze_count=3
        )

        # Verify streak before break
        info_before = StreakService.get_streak_info(
            user_id=player.id, streak_type=StreakType.WEEKLY_MATCH
        )
        assert info_before["current_streak"] == 5
        assert info_before["freeze_count"] == 3

        # Miss weeks 15 and 16, return in week 17 (missed 2 weeks)
        with patch.object(
            StreakService, "get_current_iso_week", return_value=(17, 2024)
        ):
            tracker, result = StreakService.record_activity(
                user_id=player.id, streak_type=StreakType.WEEKLY_MATCH
            )

        # Streak should break
        assert result["action"] == "broken"
        assert tracker.current_streak == 1  # Reset to 1
        assert tracker.longest_streak == 5  # Preserved
        assert tracker.freeze_count == 3  # Freezes not consumed

    def test_year_transition_maintains_streak(self, db_session, isolated_players):
        """
        GIVEN a user with activity in week 52 of 2023
        WHEN they continue in week 1 of 2024
        THEN streak continues correctly
        """
        player = isolated_players[0]

        # Activity in week 52 of 2023
        with patch.object(
            StreakService, "get_current_iso_week", return_value=(52, 2023)
        ):
            StreakService.record_activity(
                user_id=player.id, streak_type=StreakType.WEEKLY_ACTIVITY
            )

        # Activity in week 1 of 2024 (consecutive)
        with patch.object(
            StreakService, "get_current_iso_week", return_value=(1, 2024)
        ):
            tracker, result = StreakService.record_activity(
                user_id=player.id, streak_type=StreakType.WEEKLY_ACTIVITY
            )

        # Streak should continue
        assert result["action"] == "incremented"
        assert tracker.current_streak == 2


class TestMultipleStreakTypes:
    """Test independent streak type tracking."""

    def test_different_streak_types_tracked_independently(
        self, db_session, isolated_players
    ):
        """
        GIVEN a user with activity in multiple streak types
        WHEN they miss a week in one type
        THEN only that streak type is affected
        """
        player = isolated_players[0]

        # Record activity for both types in week 10
        with patch.object(
            StreakService, "get_current_iso_week", return_value=(10, 2024)
        ):
            StreakService.record_activity(
                user_id=player.id, streak_type=StreakType.WEEKLY_MATCH
            )
            StreakService.record_activity(
                user_id=player.id, streak_type=StreakType.WEEKLY_DRILL
            )

        # Week 11: only record MATCH activity
        with patch.object(
            StreakService, "get_current_iso_week", return_value=(11, 2024)
        ):
            match_tracker, _ = StreakService.record_activity(
                user_id=player.id, streak_type=StreakType.WEEKLY_MATCH
            )

        # Week 12: record DRILL (missed week 11)
        with patch.object(
            StreakService, "get_current_iso_week", return_value=(12, 2024)
        ):
            drill_tracker, drill_result = StreakService.record_activity(
                user_id=player.id, streak_type=StreakType.WEEKLY_DRILL
            )

        # MATCH streak continued (2 weeks)
        assert match_tracker.current_streak == 2

        # DRILL streak broke (missed week 11, no freeze)
        assert drill_result["action"] == "broken"
        assert drill_tracker.current_streak == 1


class TestStreakWithXPIntegration:
    """Test streak XP integration with level service."""

    def test_streak_milestone_awards_cumulative_xp(self, db_session, isolated_players):
        """
        GIVEN a user reaching the 4-week milestone
        WHEN milestone is reached
        THEN XP is awarded and tracked in transactions
        """
        player = isolated_players[0]

        # Simulate 4 weeks
        for week in range(10, 14):
            with patch.object(
                StreakService, "get_current_iso_week", return_value=(week, 2024)
            ):
                StreakService.record_activity(
                    user_id=player.id, streak_type=StreakType.WEEKLY_ACTIVITY
                )

        # Check XP transaction was created
        streak_transactions = XPTransaction.query.filter_by(
            user_id=player.id, transaction_type=XPTransactionType.STREAK_BONUS
        ).all()

        assert len(streak_transactions) >= 1

        # Check total XP matches expected
        total_streak_xp = sum(t.xp_amount for t in streak_transactions)
        expected_xp = XP_RATES[XPTransactionType.STREAK_BONUS] * 4  # 120 XP
        assert total_streak_xp == expected_xp


class TestStreakInfoRetrieval:
    """Test streak info for UI display."""

    def test_get_all_streaks_returns_complete_picture(
        self, db_session, isolated_players
    ):
        """
        GIVEN a user with various streak states
        WHEN get_all_streaks is called
        THEN complete streak picture is returned
        """
        player = isolated_players[0]

        # Create different streak states
        with patch.object(
            StreakService, "get_current_iso_week", return_value=(10, 2024)
        ):
            # Activity for match and drill
            StreakService.record_activity(
                user_id=player.id, streak_type=StreakType.WEEKLY_MATCH
            )
            StreakService.record_activity(
                user_id=player.id, streak_type=StreakType.WEEKLY_DRILL
            )

        # Get all streaks
        all_streaks = StreakService.get_all_streaks(player.id)

        # Verify structure
        assert "weekly_activity" in all_streaks
        assert "weekly_match" in all_streaks
        assert "weekly_drill" in all_streaks
        assert "weekly_tournament" in all_streaks

        # Verify streak info fields
        match_info = all_streaks["weekly_match"]
        assert "current_streak" in match_info
        assert "longest_streak" in match_info
        assert "freeze_count" in match_info
        assert "next_milestone" in match_info
        assert "is_at_risk" in match_info

        # Verify values
        assert match_info["current_streak"] == 1
        assert match_info["next_milestone"] == 4
