"""
Unit tests for StreakService - Weekly streak tracking with freeze mechanics.

Tests:
- Week calculation helpers (ISO week, weeks_between)
- Streak recording (start, continue, increment)
- Freeze mechanics (earn at milestones, use when missing)
- Streak breaks (miss 2+ weeks)
- Milestone rewards (4/12/52 weeks)
"""

import pytest
from datetime import date
from unittest.mock import patch

from models.gamification.streak_service import StreakService
from models.gamification.models import StreakTracker, StreakType
from models.gamification.xp_config import MAX_FREEZE_COUNT


class TestWeekCalculations:
    """Test ISO week calculation helpers."""

    def test_get_current_iso_week_returns_tuple(self):
        """Should return (week_number, year) tuple."""
        week, year = StreakService.get_current_iso_week()

        assert isinstance(week, int)
        assert isinstance(year, int)
        assert 1 <= week <= 53
        assert year >= 2024

    def test_get_current_iso_week_with_date(self):
        """Should calculate ISO week for specific date."""
        # January 1, 2024 is in ISO week 1 of 2024
        week, year = StreakService.get_current_iso_week(date(2024, 1, 1))
        assert week == 1
        assert year == 2024

        # December 31, 2023 is in ISO week 52 of 2023
        week, year = StreakService.get_current_iso_week(date(2023, 12, 31))
        assert week == 52
        assert year == 2023

    def test_weeks_between_same_week(self):
        """Same week should return 0."""
        diff = StreakService.weeks_between(10, 2024, 10, 2024)
        assert diff == 0

    def test_weeks_between_consecutive_weeks(self):
        """Consecutive weeks should return 1."""
        diff = StreakService.weeks_between(10, 2024, 11, 2024)
        assert diff == 1

    def test_weeks_between_year_transition(self):
        """Year transition should be handled correctly."""
        # Week 52 of 2023 to Week 1 of 2024 = 1 week
        diff = StreakService.weeks_between(52, 2023, 1, 2024)
        assert diff == 1

        # Week 51 of 2023 to Week 1 of 2024 = 2 weeks
        diff = StreakService.weeks_between(51, 2023, 1, 2024)
        assert diff == 2

    def test_weeks_between_year_with_53_weeks(self):
        """Year with 53 weeks should be handled correctly."""
        # 2020 had 53 weeks
        # Week 53 of 2020 to Week 1 of 2021 = 1 week
        diff = StreakService.weeks_between(53, 2020, 1, 2021)
        assert diff == 1


class TestStreakRecording:
    """Test streak recording functionality."""

    def test_first_activity_starts_streak(self, db_session, isolated_players):
        """First activity should start streak at 1."""
        player = isolated_players[0]

        tracker, result = StreakService.record_activity(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_ACTIVITY
        )

        assert tracker is not None
        assert tracker.current_streak == 1
        assert tracker.longest_streak == 1
        assert result["action"] == "started"
        assert result["current_streak"] == 1

    def test_same_week_activity_continues_streak(self, db_session, isolated_players):
        """Activity in same week should not increment streak."""
        player = isolated_players[0]
        today = date.today()

        # First activity
        tracker, _ = StreakService.record_activity(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_MATCH,
            activity_date=today
        )
        initial_streak = tracker.current_streak

        # Second activity same week
        tracker, result = StreakService.record_activity(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_MATCH,
            activity_date=today
        )

        assert tracker.current_streak == initial_streak
        assert result["action"] == "continued"

    def test_consecutive_week_increments_streak(self, db_session, isolated_players):
        """Activity in consecutive week should increment streak."""
        player = isolated_players[0]

        # Mock week 10 activity
        with patch.object(
            StreakService,
            'get_current_iso_week',
            return_value=(10, 2024)
        ):
            tracker, _ = StreakService.record_activity(
                user_id=player.id,
                streak_type=StreakType.WEEKLY_ACTIVITY
            )

        # Update tracker to simulate week 10
        tracker.last_activity_week = 10
        tracker.last_activity_year = 2024
        db_session.flush()

        # Mock week 11 activity
        with patch.object(
            StreakService,
            'get_current_iso_week',
            return_value=(11, 2024)
        ):
            tracker, result = StreakService.record_activity(
                user_id=player.id,
                streak_type=StreakType.WEEKLY_ACTIVITY
            )

        assert tracker.current_streak == 2
        assert result["action"] == "incremented"

    def test_streak_updates_longest_streak(self, db_session, isolated_players):
        """Longest streak should be updated when surpassed."""
        player = isolated_players[0]

        # Start streak
        with patch.object(
            StreakService,
            'get_current_iso_week',
            return_value=(10, 2024)
        ):
            tracker, _ = StreakService.record_activity(
                user_id=player.id,
                streak_type=StreakType.WEEKLY_ACTIVITY
            )

        tracker.last_activity_week = 10
        tracker.last_activity_year = 2024
        db_session.flush()

        # Week 11
        with patch.object(
            StreakService,
            'get_current_iso_week',
            return_value=(11, 2024)
        ):
            tracker, _ = StreakService.record_activity(
                user_id=player.id,
                streak_type=StreakType.WEEKLY_ACTIVITY
            )

        assert tracker.longest_streak == 2


class TestFreezeUsage:
    """Test freeze mechanics when missing weeks."""

    def test_miss_one_week_uses_freeze_if_available(self, db_session, isolated_players):
        """Missing 1 week should use freeze if available."""
        player = isolated_players[0]

        # Create a 2-week streak (avoiding the 4-week milestone which grants freeze)
        with patch.object(
            StreakService,
            'get_current_iso_week',
            return_value=(10, 2024)
        ):
            tracker, _ = StreakService.record_activity(
                user_id=player.id,
                streak_type=StreakType.WEEKLY_MATCH
            )

        with patch.object(
            StreakService,
            'get_current_iso_week',
            return_value=(11, 2024)
        ):
            tracker, _ = StreakService.record_activity(
                user_id=player.id,
                streak_type=StreakType.WEEKLY_MATCH
            )

        assert tracker.current_streak == 2
        assert tracker.freeze_count == 0  # No freezes yet

        # Grant 1 freeze using admin method
        StreakService.admin_grant_freeze(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_MATCH,
            freeze_count=1
        )

        # Verify freeze was granted
        info = StreakService.get_streak_info(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_MATCH
        )
        assert info["freeze_count"] == 1

        # Activity in week 13 (missed week 12) - should use freeze
        with patch.object(
            StreakService,
            'get_current_iso_week',
            return_value=(13, 2024)
        ):
            tracker, result = StreakService.record_activity(
                user_id=player.id,
                streak_type=StreakType.WEEKLY_MATCH
            )

        assert result["action"] == "freeze_used"
        assert tracker.current_streak == 3  # Streak continued (2 + 1)
        assert tracker.freeze_count == 0  # Freeze consumed

    def test_miss_one_week_breaks_streak_without_freeze(self, db_session, isolated_players):
        """Missing 1 week without freeze should break streak."""
        player = isolated_players[0]

        # Create tracker with 0 freezes
        tracker = StreakTracker(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_MATCH,
            current_streak=5,
            longest_streak=5,
            freeze_count=0,
            total_freeze_earned=0,
            last_activity_week=10,
            last_activity_year=2024
        )
        db_session.add(tracker)
        db_session.flush()

        # Activity in week 12 (missed week 11)
        with patch.object(
            StreakService,
            'get_current_iso_week',
            return_value=(12, 2024)
        ):
            tracker, result = StreakService.record_activity(
                user_id=player.id,
                streak_type=StreakType.WEEKLY_MATCH
            )

        assert result["action"] == "broken"
        assert tracker.current_streak == 1  # Reset to 1
        assert tracker.longest_streak == 5  # Preserved

    def test_miss_two_weeks_breaks_streak_even_with_freeze(self, db_session, isolated_players):
        """Missing 2+ weeks should break streak even with freeze."""
        player = isolated_players[0]

        # Create tracker with 3 freezes
        tracker = StreakTracker(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_ACTIVITY,
            current_streak=10,
            longest_streak=10,
            freeze_count=3,
            total_freeze_earned=3,
            last_activity_week=10,
            last_activity_year=2024
        )
        db_session.add(tracker)
        db_session.flush()

        # Activity in week 14 (missed weeks 11, 12, 13)
        with patch.object(
            StreakService,
            'get_current_iso_week',
            return_value=(14, 2024)
        ):
            tracker, result = StreakService.record_activity(
                user_id=player.id,
                streak_type=StreakType.WEEKLY_ACTIVITY
            )

        assert result["action"] == "broken"
        assert tracker.current_streak == 1  # Reset
        assert tracker.freeze_count == 3  # Freezes not consumed


class TestMilestoneRewards:
    """Test freeze earning at milestones."""

    def test_4_week_milestone_earns_freeze(self, db_session, isolated_players):
        """Reaching 4-week streak should earn 1 freeze."""
        player = isolated_players[0]

        # Create tracker at 3 weeks
        tracker = StreakTracker(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_ACTIVITY,
            current_streak=3,
            longest_streak=3,
            freeze_count=0,
            total_freeze_earned=0,
            last_activity_week=10,
            last_activity_year=2024,
            milestone_4_reached=False
        )
        db_session.add(tracker)
        db_session.flush()

        # Activity in week 11 (reaches 4-week milestone)
        with patch.object(
            StreakService,
            'get_current_iso_week',
            return_value=(11, 2024)
        ):
            tracker, result = StreakService.record_activity(
                user_id=player.id,
                streak_type=StreakType.WEEKLY_ACTIVITY
            )

        assert tracker.current_streak == 4
        assert tracker.milestone_4_reached is True
        assert tracker.freeze_count == 1
        assert result["milestone_reached"] == 4
        assert result["freeze_earned"] == 1
        assert result["xp_bonus"] > 0

    def test_52_week_milestone_earns_two_freezes(self, db_session, isolated_players):
        """Reaching 52-week streak should earn 2 freezes."""
        player = isolated_players[0]

        # Create tracker at 51 weeks
        tracker = StreakTracker(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_ACTIVITY,
            current_streak=51,
            longest_streak=51,
            freeze_count=0,
            total_freeze_earned=2,  # Already earned 4-week + 12-week
            last_activity_week=52,
            last_activity_year=2023,
            milestone_4_reached=True,
            milestone_12_reached=True,
            milestone_52_reached=False
        )
        db_session.add(tracker)
        db_session.flush()

        # Activity in week 1 of 2024 (reaches 52-week milestone)
        with patch.object(
            StreakService,
            'get_current_iso_week',
            return_value=(1, 2024)
        ):
            tracker, result = StreakService.record_activity(
                user_id=player.id,
                streak_type=StreakType.WEEKLY_ACTIVITY
            )

        assert tracker.current_streak == 52
        assert tracker.milestone_52_reached is True
        assert tracker.freeze_count == 2  # 52-week milestone gives 2 freezes
        assert result["milestone_reached"] == 52

    def test_freeze_count_capped_at_max(self, db_session, isolated_players):
        """Freeze count should not exceed MAX_FREEZE_COUNT."""
        player = isolated_players[0]

        # Create tracker at max freezes, approaching milestone
        tracker = StreakTracker(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_ACTIVITY,
            current_streak=3,
            longest_streak=3,
            freeze_count=MAX_FREEZE_COUNT,  # Already at max
            total_freeze_earned=MAX_FREEZE_COUNT,
            last_activity_week=10,
            last_activity_year=2024,
            milestone_4_reached=False
        )
        db_session.add(tracker)
        db_session.flush()

        # Activity in week 11 (would earn freeze at 4-week milestone)
        with patch.object(
            StreakService,
            'get_current_iso_week',
            return_value=(11, 2024)
        ):
            tracker, result = StreakService.record_activity(
                user_id=player.id,
                streak_type=StreakType.WEEKLY_ACTIVITY
            )

        assert tracker.freeze_count == MAX_FREEZE_COUNT  # Still at max
        assert result["freeze_earned"] == 0  # No additional freeze


class TestStreakInfo:
    """Test streak info retrieval."""

    def test_get_streak_info_no_tracker(self, db_session, isolated_players):
        """Should return defaults when no tracker exists."""
        player = isolated_players[0]

        info = StreakService.get_streak_info(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_MATCH
        )

        assert info["current_streak"] == 0
        assert info["longest_streak"] == 0
        assert info["freeze_count"] == 0
        assert info["next_milestone"] == 4

    def test_get_streak_info_with_tracker(self, db_session, isolated_players):
        """Should return accurate streak information."""
        player = isolated_players[0]

        # Create tracker
        tracker = StreakTracker(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_ACTIVITY,
            current_streak=8,
            longest_streak=15,
            freeze_count=2,
            total_freeze_earned=2,
            last_activity_week=20,
            last_activity_year=2024,
            milestone_4_reached=True,
            milestone_12_reached=False
        )
        db_session.add(tracker)
        db_session.flush()

        info = StreakService.get_streak_info(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_ACTIVITY
        )

        assert info["current_streak"] == 8
        assert info["longest_streak"] == 15
        assert info["freeze_count"] == 2
        assert info["next_milestone"] == 12
        assert 4 in info["milestones_reached"]

    def test_get_all_streaks(self, db_session, isolated_players):
        """Should return info for all streak types."""
        player = isolated_players[0]

        # Create one tracker
        tracker = StreakTracker(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_MATCH,
            current_streak=5,
            longest_streak=5,
            freeze_count=1,
            total_freeze_earned=1
        )
        db_session.add(tracker)
        db_session.flush()

        all_streaks = StreakService.get_all_streaks(player.id)

        assert "weekly_activity" in all_streaks
        assert "weekly_match" in all_streaks
        assert "weekly_tournament" in all_streaks
        assert "weekly_drill" in all_streaks
        assert all_streaks["weekly_match"]["current_streak"] == 5


class TestAdminFreezeGrant:
    """Test admin freeze granting."""

    def test_admin_grant_freeze_creates_tracker(self, db_session, isolated_players):
        """Admin grant should create tracker if not exists."""
        player = isolated_players[0]

        tracker, success = StreakService.admin_grant_freeze(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_ACTIVITY,
            freeze_count=2,
            reason="Test grant"
        )

        assert success is True
        assert tracker.freeze_count == 2
        assert tracker.total_freeze_earned == 2

    def test_admin_grant_freeze_respects_max(self, db_session, isolated_players):
        """Admin grant should not exceed max freeze count."""
        player = isolated_players[0]

        # Create tracker at max - 1
        tracker = StreakTracker(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_ACTIVITY,
            current_streak=0,
            longest_streak=0,
            freeze_count=MAX_FREEZE_COUNT - 1,
            total_freeze_earned=MAX_FREEZE_COUNT - 1
        )
        db_session.add(tracker)
        db_session.flush()

        # Try to grant 2 freezes
        tracker, success = StreakService.admin_grant_freeze(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_ACTIVITY,
            freeze_count=2,
            reason="Test grant"
        )

        assert success is True
        assert tracker.freeze_count == MAX_FREEZE_COUNT  # Capped at max

    def test_admin_grant_freeze_fails_at_max(self, db_session, isolated_players):
        """Admin grant should fail when already at max."""
        player = isolated_players[0]

        # Create tracker at max
        tracker = StreakTracker(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_ACTIVITY,
            current_streak=0,
            longest_streak=0,
            freeze_count=MAX_FREEZE_COUNT,
            total_freeze_earned=MAX_FREEZE_COUNT
        )
        db_session.add(tracker)
        db_session.flush()

        tracker, success = StreakService.admin_grant_freeze(
            user_id=player.id,
            streak_type=StreakType.WEEKLY_ACTIVITY,
            freeze_count=1,
            reason="Test grant"
        )

        assert success is False
        assert tracker.freeze_count == MAX_FREEZE_COUNT
