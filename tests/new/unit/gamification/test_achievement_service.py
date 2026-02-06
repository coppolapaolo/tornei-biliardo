"""
Unit tests for AchievementService - Achievement unlock and progress tracking.

Tests:
- Achievement unlock when requirements met
- Progress tracking for progressive achievements
- XP award on achievement unlock
- Requirement checking logic
"""

import pytest
import json
from datetime import datetime
from unittest.mock import patch, MagicMock

from models.gamification.achievement_service import AchievementService
from models.gamification.models import (
    Achievement,
    UserAchievement,
    AchievementCategory,
    AchievementDifficulty,
    UserLevel,
)
from models.base import utc_now


class TestAchievementUnlock:
    """Test achievement unlock functionality."""

    def test_unlock_non_progressive_achievement_when_requirements_met(
        self, db_session, isolated_players
    ):
        """
        GIVEN a non-progressive achievement with simple requirements
        WHEN user meets requirements
        THEN achievement is unlocked
        """
        player = isolated_players[0]

        # Arrange: Create "first_blood" achievement (1 win)
        achievement = Achievement(
            slug="first_blood",
            name="First Blood",
            description="Win your first match",
            category=AchievementCategory.MATCH,
            difficulty=AchievementDifficulty.COMMON,
            requirements='{"type": "match_wins", "count": 1}',
            is_progressive=False,
            xp_reward=50
        )
        db_session.add(achievement)
        db_session.flush()

        # Mock UserStatsService to return 1 win
        with patch('models.user.services.UserStatsService.get_user_stats') as mock_stats:
            mock_stats.return_value = {"won_matches": 1}

            # Act
            user_achievement, was_unlocked = AchievementService.check_and_award_achievement(
                user_id=player.id,
                achievement_slug="first_blood"
            )

        # Assert
        assert was_unlocked is True
        assert user_achievement.is_unlocked is True
        assert user_achievement.unlocked_at is not None

    def test_progressive_achievement_tracks_progress(self, db_session, isolated_players):
        """
        GIVEN a progressive achievement (e.g., 50 wins)
        WHEN user incrementally progresses
        THEN progress is tracked and achievement unlocks at target
        """
        player = isolated_players[0]

        # Arrange: Create "veteran_player" achievement (50 wins)
        achievement = Achievement(
            slug="veteran_player",
            name="Veteran Player",
            description="Win 50 matches",
            category=AchievementCategory.MATCH,
            difficulty=AchievementDifficulty.UNCOMMON,
            requirements='{"type": "match_wins", "count": 50}',
            is_progressive=True,
            xp_reward=250
        )
        db_session.add(achievement)
        db_session.flush()

        # Act: Simulate 50 wins
        for i in range(50):
            user_achievement, was_unlocked = AchievementService.check_and_award_achievement(
                user_id=player.id,
                achievement_slug="veteran_player",
                progress_increment=1
            )

            if i < 49:
                assert was_unlocked is False  # Not yet unlocked
                assert user_achievement.current_progress == i + 1
            else:
                assert was_unlocked is True  # Unlocked on 50th win
                assert user_achievement.current_progress == 50
                assert user_achievement.is_unlocked is True

    def test_achievement_unlock_awards_xp_bonus(self, db_session, isolated_players):
        """
        GIVEN an achievement with XP reward
        WHEN achievement is unlocked
        THEN user receives XP bonus
        """
        player = isolated_players[0]

        # Arrange
        achievement = Achievement(
            slug="test_achievement",
            name="Test Achievement",
            description="Test",
            category=AchievementCategory.MATCH,
            difficulty=AchievementDifficulty.COMMON,
            requirements='{"type": "match_wins", "count": 1}',
            is_progressive=False,
            xp_reward=100
        )
        db_session.add(achievement)
        db_session.flush()

        # Mock requirements check
        with patch('models.user.services.UserStatsService.get_user_stats') as mock_stats:
            mock_stats.return_value = {"won_matches": 1}

            # Act
            user_achievement, was_unlocked = AchievementService.check_and_award_achievement(
                user_id=player.id,
                achievement_slug="test_achievement"
            )

        # Assert: XP was awarded
        user_level = db_session.get(UserLevel, player.id)
        assert user_level is not None
        assert user_level.total_xp >= 100  # At least the achievement XP

    def test_already_unlocked_achievement_returns_false(self, db_session, isolated_players):
        """
        GIVEN an already unlocked achievement
        WHEN check_and_award is called again
        THEN returns False for was_unlocked
        """
        player = isolated_players[0]

        # Arrange: Create and unlock achievement
        achievement = Achievement(
            slug="test_achievement",
            name="Test",
            description="Test",
            category=AchievementCategory.MATCH,
            difficulty=AchievementDifficulty.COMMON,
            requirements='{"type": "match_wins", "count": 1}',
            is_progressive=False,
            xp_reward=50
        )
        db_session.add(achievement)
        db_session.flush()

        user_achievement = UserAchievement(
            user_id=player.id,
            achievement_id=achievement.id,
            current_progress=0,
            is_unlocked=True,
            unlocked_at=utc_now()
        )
        db_session.add(user_achievement)
        db_session.flush()

        # Act
        result, was_unlocked = AchievementService.check_and_award_achievement(
            user_id=player.id,
            achievement_slug="test_achievement"
        )

        # Assert
        assert was_unlocked is False


class TestAchievementProgress:
    """Test achievement progress tracking."""

    def test_get_user_achievements_returns_all_with_progress(
        self, db_session, isolated_players
    ):
        """
        GIVEN multiple achievements (some unlocked, some not)
        WHEN get_user_achievements is called
        THEN returns all achievements with progress info
        """
        player = isolated_players[0]

        # Arrange: Create 2 achievements
        achievement1 = Achievement(
            slug="first",
            name="First",
            description="Test",
            category=AchievementCategory.MATCH,
            difficulty=AchievementDifficulty.COMMON,
            requirements='{"type": "match_wins", "count": 1}',
            is_progressive=False,
            xp_reward=50
        )
        achievement2 = Achievement(
            slug="second",
            name="Second",
            description="Test",
            category=AchievementCategory.MATCH,
            difficulty=AchievementDifficulty.UNCOMMON,
            requirements='{"type": "match_wins", "count": 50}',
            is_progressive=True,
            xp_reward=250
        )
        db_session.add_all([achievement1, achievement2])
        db_session.flush()

        # Unlock first achievement
        user_achievement1 = UserAchievement(
            user_id=player.id,
            achievement_id=achievement1.id,
            current_progress=0,
            is_unlocked=True,
            unlocked_at=utc_now()
        )
        db_session.add(user_achievement1)

        # Partial progress on second
        user_achievement2 = UserAchievement(
            user_id=player.id,
            achievement_id=achievement2.id,
            current_progress=25,
            is_unlocked=False
        )
        db_session.add(user_achievement2)
        db_session.flush()

        # Act
        achievements = AchievementService.get_user_achievements(user_id=player.id)

        # Assert
        assert len(achievements) == 2

        # First achievement (unlocked)
        first = [a for a in achievements if a["achievement"].slug == "first"][0]
        assert first["is_unlocked"] is True
        assert first["progress_percentage"] == 100.0

        # Second achievement (50% progress: 25/50)
        second = [a for a in achievements if a["achievement"].slug == "second"][0]
        assert second["is_unlocked"] is False
        assert second["current_progress"] == 25
        assert second["progress_percentage"] == 50.0

    def test_get_user_achievements_unlocked_only_filters(
        self, db_session, isolated_players
    ):
        """
        GIVEN achievements (some unlocked, some not)
        WHEN get_user_achievements(unlocked_only=True)
        THEN only returns unlocked achievements
        """
        player = isolated_players[0]

        # Arrange: Create 2 achievements, unlock 1
        achievement1 = Achievement(
            slug="unlocked",
            name="Unlocked",
            description="Test",
            category=AchievementCategory.MATCH,
            difficulty=AchievementDifficulty.COMMON,
            requirements='{"type": "match_wins", "count": 1}',
            is_progressive=False,
            xp_reward=50
        )
        achievement2 = Achievement(
            slug="locked",
            name="Locked",
            description="Test",
            category=AchievementCategory.MATCH,
            difficulty=AchievementDifficulty.UNCOMMON,
            requirements='{"type": "match_wins", "count": 50}',
            is_progressive=True,
            xp_reward=250
        )
        db_session.add_all([achievement1, achievement2])
        db_session.flush()

        user_achievement1 = UserAchievement(
            user_id=player.id,
            achievement_id=achievement1.id,
            current_progress=0,
            is_unlocked=True,
            unlocked_at=utc_now()
        )
        db_session.add(user_achievement1)
        db_session.flush()

        # Act
        unlocked = AchievementService.get_user_achievements(
            user_id=player.id, unlocked_only=True
        )

        # Assert
        assert len(unlocked) == 1
        assert unlocked[0]["achievement"].slug == "unlocked"


class TestAchievementStats:
    """Test achievement statistics."""

    def test_get_achievement_stats_returns_summary(self, db_session, isolated_players):
        """
        GIVEN multiple achievements with some unlocked
        WHEN get_achievement_stats is called
        THEN returns comprehensive statistics
        """
        player = isolated_players[0]

        # Arrange: Create achievements across categories
        achievements = [
            Achievement(
                slug=f"achievement_{i}",
                name=f"Achievement {i}",
                description="Test",
                category=AchievementCategory.MATCH if i < 2 else AchievementCategory.TOURNAMENT,
                difficulty=AchievementDifficulty.COMMON,
                requirements='{"type": "match_wins", "count": 1}',
                is_progressive=False,
                xp_reward=50
            )
            for i in range(4)
        ]
        db_session.add_all(achievements)
        db_session.flush()

        # Unlock 2 achievements (1 from each category)
        user_achievement1 = UserAchievement(
            user_id=player.id,
            achievement_id=achievements[0].id,
            current_progress=0,
            is_unlocked=True,
            unlocked_at=utc_now()
        )
        user_achievement2 = UserAchievement(
            user_id=player.id,
            achievement_id=achievements[2].id,
            current_progress=0,
            is_unlocked=True,
            unlocked_at=utc_now()
        )
        db_session.add_all([user_achievement1, user_achievement2])
        db_session.flush()

        # Act
        stats = AchievementService.get_achievement_stats(user_id=player.id)

        # Assert
        assert stats["total_unlocked"] == 2
        assert stats["total_achievements"] == 4
        assert stats["completion_percentage"] == 50.0
        assert stats["by_category"]["match"]["unlocked"] == 1
        assert stats["by_category"]["match"]["total"] == 2
        assert stats["by_category"]["tournament"]["unlocked"] == 1
        assert stats["by_category"]["tournament"]["total"] == 2
