"""
Unit tests for QuestService - Quest management and participation tracking.

Tests:
- Quest creation and lifecycle management
- Participation join and progress tracking
- Quest completion and XP awards
- Activity-based quest progress
- Query methods and statistics
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from models.gamification.quest_service import QuestService
from models.gamification.models import (
    Quest,
    QuestParticipation,
    QuestType,
    QuestStatus,
    UserLevel,
)
from models.gamification.xp_config import QUEST_XP_REWARDS
from models.base import utc_now


class TestQuestCreation:
    """Test quest creation functionality."""

    def test_create_quest_with_upcoming_status(self, db_session, isolated_players):
        """Quest created with future start date should be UPCOMING."""
        future_start = utc_now() + timedelta(days=1)
        future_end = utc_now() + timedelta(days=8)

        quest = QuestService.create_quest(
            name="Future Quest",
            description="A quest that starts tomorrow",
            quest_type=QuestType.WEEKLY,
            start_date=future_start,
            end_date=future_end,
            requirements={"type": "matches_played", "target": 5}
        )

        assert quest is not None
        assert quest.status == QuestStatus.UPCOMING
        assert quest.name == "Future Quest"

    def test_create_quest_with_active_status(self, db_session, isolated_players):
        """Quest created with current dates should be ACTIVE."""
        past_start = utc_now() - timedelta(days=1)
        future_end = utc_now() + timedelta(days=6)

        quest = QuestService.create_quest(
            name="Active Quest",
            description="A quest that is currently active",
            quest_type=QuestType.WEEKLY,
            start_date=past_start,
            end_date=future_end,
            requirements={"type": "matches_won", "target": 3}
        )

        assert quest.status == QuestStatus.ACTIVE

    def test_create_quest_with_expired_status(self, db_session, isolated_players):
        """Quest created with past dates should be EXPIRED."""
        past_start = utc_now() - timedelta(days=10)
        past_end = utc_now() - timedelta(days=3)

        quest = QuestService.create_quest(
            name="Expired Quest",
            description="A quest that has already ended",
            quest_type=QuestType.MONTHLY,
            start_date=past_start,
            end_date=past_end,
            requirements={"type": "tournaments_played", "target": 2}
        )

        assert quest.status == QuestStatus.EXPIRED

    def test_create_quest_uses_default_xp_reward(self, db_session, isolated_players):
        """Quest without explicit XP should use type-based default."""
        quest = QuestService.create_quest(
            name="Weekly Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 5}
        )

        assert quest.xp_reward == QUEST_XP_REWARDS["WEEKLY"]  # 150

    def test_create_quest_with_custom_xp_reward(self, db_session, isolated_players):
        """Quest with explicit XP should use that value."""
        quest = QuestService.create_quest(
            name="Special Quest",
            description="Test",
            quest_type=QuestType.SPECIAL_EVENT,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 10},
            xp_reward=500
        )

        assert quest.xp_reward == 500


class TestQuestLifecycle:
    """Test quest lifecycle management."""

    def test_update_quest_statuses_activates_upcoming(self, db_session, isolated_players):
        """Should activate quests that have started."""
        # Create a quest that should be active now
        quest = Quest(
            name="Should Be Active",
            description="Test",
            quest_type=QuestType.WEEKLY,
            status=QuestStatus.UPCOMING,  # Manually set as upcoming
            start_date=utc_now() - timedelta(hours=1),  # Started 1 hour ago
            end_date=utc_now() + timedelta(days=6),
            requirements='{"type": "matches_played", "target": 5}',
            xp_reward=150,
            participant_count=0,
            completion_count=0
        )
        db_session.add(quest)
        db_session.flush()

        result = QuestService.update_quest_statuses()

        assert result["activated"] == 1
        assert quest.status == QuestStatus.ACTIVE

    def test_update_quest_statuses_expires_active(self, db_session, isolated_players):
        """Should expire quests that have ended."""
        quest = Quest(
            name="Should Be Expired",
            description="Test",
            quest_type=QuestType.WEEKLY,
            status=QuestStatus.ACTIVE,  # Currently active
            start_date=utc_now() - timedelta(days=8),
            end_date=utc_now() - timedelta(hours=1),  # Ended 1 hour ago
            requirements='{"type": "matches_played", "target": 5}',
            xp_reward=150,
            participant_count=0,
            completion_count=0
        )
        db_session.add(quest)
        db_session.flush()

        result = QuestService.update_quest_statuses()

        assert result["expired"] == 1
        assert quest.status == QuestStatus.EXPIRED


class TestQuestParticipation:
    """Test quest participation functionality."""

    def test_join_quest_creates_participation(self, db_session, isolated_players):
        """Joining a quest should create participation record."""
        player = isolated_players[0]

        quest = QuestService.create_quest(
            name="Active Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 10}
        )

        participation, is_new = QuestService.join_quest(
            user_id=player.id,
            quest_id=quest.id
        )

        assert is_new is True
        assert participation.user_id == player.id
        assert participation.quest_id == quest.id
        assert participation.current_progress == 0
        assert participation.target_progress == 10
        assert quest.participant_count == 1

    def test_join_quest_returns_existing_participation(self, db_session, isolated_players):
        """Joining same quest twice should return existing participation."""
        player = isolated_players[0]

        quest = QuestService.create_quest(
            name="Active Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 5}
        )

        # First join
        first_participation, first_is_new = QuestService.join_quest(
            user_id=player.id,
            quest_id=quest.id
        )

        # Second join
        second_participation, second_is_new = QuestService.join_quest(
            user_id=player.id,
            quest_id=quest.id
        )

        assert first_is_new is True
        assert second_is_new is False
        assert first_participation.id == second_participation.id

    def test_join_quest_fails_for_inactive_quest(self, db_session, isolated_players):
        """Joining an inactive quest should raise error."""
        player = isolated_players[0]

        quest = QuestService.create_quest(
            name="Expired Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=10),
            end_date=utc_now() - timedelta(days=3),
            requirements={"type": "matches_played", "target": 5}
        )

        with pytest.raises(ValueError, match="not active"):
            QuestService.join_quest(user_id=player.id, quest_id=quest.id)


class TestQuestProgress:
    """Test quest progress tracking."""

    def test_update_progress_increments_correctly(self, db_session, isolated_players):
        """Progress should increment by specified amount."""
        player = isolated_players[0]

        quest = QuestService.create_quest(
            name="Active Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 10}
        )

        QuestService.join_quest(user_id=player.id, quest_id=quest.id)

        participation, completed = QuestService.update_progress(
            user_id=player.id,
            quest_id=quest.id,
            progress_increment=3
        )

        assert participation.current_progress == 3
        assert completed is False

    def test_update_progress_completes_quest_at_target(self, db_session, isolated_players):
        """Quest should complete when progress reaches target."""
        player = isolated_players[0]

        quest = QuestService.create_quest(
            name="Active Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 5}
        )

        QuestService.join_quest(user_id=player.id, quest_id=quest.id)

        # Progress to completion
        participation, completed = QuestService.update_progress(
            user_id=player.id,
            quest_id=quest.id,
            progress_increment=5
        )

        assert participation.is_completed is True
        assert participation.completed_at is not None
        assert completed is True
        assert quest.completion_count == 1

    def test_completed_quest_awards_xp(self, db_session, isolated_players):
        """Completing quest should award XP."""
        player = isolated_players[0]

        quest = QuestService.create_quest(
            name="Active Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 1},
            xp_reward=200
        )

        QuestService.join_quest(user_id=player.id, quest_id=quest.id)

        participation, _ = QuestService.update_progress(
            user_id=player.id,
            quest_id=quest.id,
            progress_increment=1
        )

        assert participation.xp_awarded == 200

        # Check user level
        user_level = db_session.get(UserLevel, player.id)
        assert user_level is not None
        assert user_level.total_xp >= 200


class TestActivityBasedProgress:
    """Test activity-based quest progress."""

    def test_record_activity_updates_matching_quests(self, db_session, isolated_players):
        """Recording activity should update quests with matching type."""
        player = isolated_players[0]

        # Create quests with different activity types
        matches_quest = QuestService.create_quest(
            name="Matches Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 5}
        )

        wins_quest = QuestService.create_quest(
            name="Wins Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_won", "target": 3}
        )

        # Record "matches_played" activity
        results = QuestService.record_activity_for_quests(
            user_id=player.id,
            activity_type="matches_played",
            activity_count=2
        )

        # Should only affect matches_quest
        assert len(results) == 1
        affected_quest, _ = results[0]
        assert affected_quest.id == matches_quest.id

        # Check progress
        participation = QuestParticipation.query.filter_by(
            user_id=player.id,
            quest_id=matches_quest.id
        ).first()
        assert participation.current_progress == 2

    def test_record_activity_auto_joins_quest(self, db_session, isolated_players):
        """Recording activity should auto-join matching quests."""
        player = isolated_players[0]

        quest = QuestService.create_quest(
            name="Matches Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 5}
        )

        # Record activity without explicitly joining
        results = QuestService.record_activity_for_quests(
            user_id=player.id,
            activity_type="matches_played",
            activity_count=1
        )

        assert len(results) == 1

        # Verify auto-joined
        participation = QuestParticipation.query.filter_by(
            user_id=player.id,
            quest_id=quest.id
        ).first()
        assert participation is not None
        assert participation.current_progress == 1

    def test_record_activity_completes_quest(self, db_session, isolated_players):
        """Recording activity should complete quest when target reached."""
        player = isolated_players[0]

        quest = QuestService.create_quest(
            name="Easy Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 2}
        )

        results = QuestService.record_activity_for_quests(
            user_id=player.id,
            activity_type="matches_played",
            activity_count=3  # More than target
        )

        assert len(results) == 1
        _, completed = results[0]
        assert completed is True


class TestQuestQueries:
    """Test quest query methods."""

    def test_get_user_quests_returns_all_with_progress(self, db_session, isolated_players):
        """Should return all quests with user's participation status."""
        player = isolated_players[0]

        quest1 = QuestService.create_quest(
            name="Quest 1",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 10}
        )

        quest2 = QuestService.create_quest(
            name="Quest 2",
            description="Test",
            quest_type=QuestType.MONTHLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=29),
            requirements={"type": "matches_won", "target": 20}
        )

        # Join only quest1
        QuestService.join_quest(user_id=player.id, quest_id=quest1.id)

        quests = QuestService.get_user_quests(user_id=player.id, active_only=True)

        assert len(quests) == 2

        # Find quest1 in results
        quest1_result = [q for q in quests if q["quest"].id == quest1.id][0]
        assert quest1_result["is_participating"] is True
        assert quest1_result["progress_percentage"] == 0.0

        # Find quest2 in results
        quest2_result = [q for q in quests if q["quest"].id == quest2.id][0]
        assert quest2_result["is_participating"] is False

    def test_get_user_quest_stats_returns_summary(self, db_session, isolated_players):
        """Should return comprehensive quest statistics."""
        player = isolated_players[0]

        # Create and complete a quest
        quest = QuestService.create_quest(
            name="Easy Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 1},
            xp_reward=100
        )

        QuestService.join_quest(user_id=player.id, quest_id=quest.id)
        QuestService.update_progress(
            user_id=player.id,
            quest_id=quest.id,
            progress_increment=1
        )

        stats = QuestService.get_user_quest_stats(user_id=player.id)

        assert stats["total_participated"] == 1
        assert stats["total_completed"] == 1
        assert stats["completion_rate"] == 100.0
        assert stats["total_xp_earned"] == 100
        assert stats["quests_by_type"]["weekly"]["completed"] == 1

    def test_get_quest_leaderboard_ordered_correctly(self, db_session, isolated_players):
        """Leaderboard should order by completion, then progress."""
        player1 = isolated_players[0]
        player2 = isolated_players[1]

        quest = QuestService.create_quest(
            name="Quest",
            description="Test",
            quest_type=QuestType.WEEKLY,
            start_date=utc_now() - timedelta(days=1),
            end_date=utc_now() + timedelta(days=6),
            requirements={"type": "matches_played", "target": 10}
        )

        # Player 1: 3 progress
        QuestService.join_quest(user_id=player1.id, quest_id=quest.id)
        QuestService.update_progress(
            user_id=player1.id,
            quest_id=quest.id,
            progress_increment=3
        )

        # Player 2: 7 progress
        QuestService.join_quest(user_id=player2.id, quest_id=quest.id)
        QuestService.update_progress(
            user_id=player2.id,
            quest_id=quest.id,
            progress_increment=7
        )

        leaderboard = QuestService.get_quest_leaderboard(quest_id=quest.id)

        assert len(leaderboard) == 2
        assert leaderboard[0]["user_id"] == player2.id  # Higher progress
        assert leaderboard[0]["rank"] == 1
        assert leaderboard[1]["user_id"] == player1.id
        assert leaderboard[1]["rank"] == 2
