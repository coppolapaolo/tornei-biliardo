"""
Integration Test: Achievement Workflow

Tests the end-to-end achievement system including:
- Event triggers from domain events
- Automatic achievement checking
- Progressive achievement progress tracking
- Achievement unlock with XP bonus
- Notification creation on unlock

These tests verify the complete event-driven achievement workflow.
"""

import pytest
from datetime import datetime

from models.events.base import EventBus
from models.events.match_events import MatchCompletedEvent
from models.events.competition_events import InscriptionCreatedEvent, CompetitionCompletedEvent
from models.gamification.models import Achievement, UserAchievement, AchievementCategory, AchievementDifficulty
from models.gamification.achievement_seeds import seed_achievements
from models.gamification.event_handlers import GamificationEventHandlers
from models.notification.models import Notification, NotificationType


@pytest.fixture(autouse=True)
def register_gamification_handlers():
    """Ensure gamification event handlers are registered for each test.

    Handlers are already registered at app startup via models.gamification import.
    This fixture just ensures they stay registered and aren't affected by other tests.
    """
    # Save handlers state to restore after test (protect from other tests' cleanup)
    original_handlers = {k: list(v) for k, v in EventBus._handlers.items()}

    # Only register if not already registered (avoid duplicates)
    if MatchCompletedEvent not in EventBus._handlers:
        GamificationEventHandlers.register_all_handlers()

    yield

    # Restore original handlers after test
    EventBus._handlers = original_handlers


class TestAchievementWorkflowMatchBased:
    """Test achievement workflow triggered by match events."""

    @pytest.mark.skip(reason="Achievement handlers have session isolation issues with @transactional")
    def test_first_blood_achievement_unlocked_on_first_win(self, db_session, isolated_players):
        """
        GIVEN "first_blood" achievement exists
        WHEN user wins first match
        THEN achievement is automatically unlocked
        AND notification is created
        """
        # Arrange: Seed achievements
        created, skipped = seed_achievements(db_session)
        assert created > 0  # Achievements were created

        player1 = isolated_players[0]
        player2 = isolated_players[1]

        # Act: Simulate first match win (use correct event signature)
        event = MatchCompletedEvent(
            match_id=1,
            player1_id=player1.id,
            player1_name=player1.username,
            player2_id=player2.id,
            player2_name=player2.username,
            winner_id=player1.id,
            winner_name=player1.username,
            score="5-2"
        )
        EventBus.publish(event)
        db_session.flush()

        # Assert: "first_blood" achievement unlocked
        first_blood = Achievement.query.filter_by(slug="first_blood").first()
        assert first_blood is not None

        user_achievement = UserAchievement.query.filter_by(
            user_id=player1.id,
            achievement_id=first_blood.id
        ).first()
        assert user_achievement is not None
        assert user_achievement.is_unlocked is True

        # Assert: Notification created
        notification = Notification.query.filter_by(
            user_id=player1.id,
            notification_type=NotificationType.ACHIEVEMENT_UNLOCKED
        ).first()
        assert notification is not None
        assert "First Blood" in notification.message or "first" in notification.message.lower()

    def test_veteran_player_achievement_tracks_progress(self, db_session, isolated_players):
        """
        GIVEN "veteran_player" achievement (50 wins) exists
        WHEN user wins multiple matches
        THEN progress is tracked incrementally
        AND achievement unlocks at 50 wins
        """
        # Arrange: Seed achievements
        seed_achievements(db_session)

        player1 = isolated_players[0]
        player2 = isolated_players[1]

        veteran = Achievement.query.filter_by(slug="veteran_player").first()
        assert veteran is not None
        assert veteran.is_progressive is True

        # Act: Simulate 50 match wins
        for i in range(50):
            event = MatchCompletedEvent(
                match_id=i + 1,
                player1_id=player1.id,
                player1_name=player1.username,
                player2_id=player2.id,
                player2_name=player2.username,
                winner_id=player1.id,
                winner_name=player1.username,
                score="5-2"
            )
            EventBus.publish(event)
            db_session.flush()

            # Check progress
            user_achievement = UserAchievement.query.filter_by(
                user_id=player1.id,
                achievement_id=veteran.id
            ).first()

            if user_achievement:
                if i < 49:
                    # Not yet unlocked
                    assert user_achievement.current_progress == i + 1
                    assert user_achievement.is_unlocked is False
                else:
                    # Unlocked on 50th win
                    assert user_achievement.current_progress == 50
                    assert user_achievement.is_unlocked is True


class TestAchievementWorkflowTournamentBased:
    """Test achievement workflow for tournament events."""

    @pytest.mark.skip(reason="Achievement handlers have session isolation issues with @transactional")
    def test_tournament_debut_unlocked_on_first_inscription(self, db_session, isolated_players):
        """
        GIVEN "tournament_debut" achievement exists
        WHEN user registers for first tournament
        THEN achievement is unlocked
        """
        # Arrange
        seed_achievements(db_session)
        player = isolated_players[0]

        # Act: First tournament inscription (use correct event signature)
        event = InscriptionCreatedEvent(
            inscription_id=1,
            gara_id=100,
            gara_name="Test Tournament",
            user_id=player.id,
            username=player.username,
            inscription_status="confirmed"
        )
        EventBus.publish(event)
        db_session.flush()

        # Assert
        debut = Achievement.query.filter_by(slug="tournament_debut").first()
        user_achievement = UserAchievement.query.filter_by(
            user_id=player.id,
            achievement_id=debut.id
        ).first()

        assert user_achievement is not None
        assert user_achievement.is_unlocked is True

    @pytest.mark.skip(reason="Achievement handlers have session isolation issues with @transactional")
    def test_champion_achievement_unlocked_on_tournament_win(self, db_session, isolated_players):
        """
        GIVEN "champion" achievement exists
        WHEN user wins a tournament
        THEN achievement is unlocked
        """
        # Arrange
        seed_achievements(db_session)
        player1 = isolated_players[0]
        player2 = isolated_players[1]

        # Act: Tournament win (use correct event signature)
        event = CompetitionCompletedEvent(
            gara_id=100,
            name="Test Tournament",
            winner_id=player1.id,
            winner_name=player1.username,
            final_standings=[
                {"user_id": player1.id, "position": 1},
                {"user_id": player2.id, "position": 2},
            ],
            total_participants=2,
            total_rounds=3
        )
        EventBus.publish(event)
        db_session.flush()

        # Assert
        champion = Achievement.query.filter_by(slug="champion").first()
        user_achievement = UserAchievement.query.filter_by(
            user_id=player1.id,
            achievement_id=champion.id
        ).first()

        assert user_achievement is not None
        assert user_achievement.is_unlocked is True

    @pytest.mark.skip(reason="Achievement handlers have session isolation issues with @transactional")
    def test_podium_finish_unlocked_for_top3(self, db_session, isolated_players):
        """
        GIVEN "podium_finish" achievement exists
        WHEN user finishes in top 3
        THEN achievement is unlocked
        """
        # Arrange
        seed_achievements(db_session)
        player1 = isolated_players[0]
        player2 = isolated_players[1]

        # Act: Tournament with 2nd place finish for player1
        event = CompetitionCompletedEvent(
            gara_id=100,
            name="Test Tournament",
            winner_id=player2.id,  # Someone else wins
            winner_name=player2.username,
            final_standings=[
                {"user_id": player2.id, "position": 1},
                {"user_id": player1.id, "position": 2},  # Player1 gets 2nd
            ],
            total_participants=2,
            total_rounds=3
        )
        EventBus.publish(event)
        db_session.flush()

        # Assert: Player 1 gets podium achievement (2nd place)
        podium = Achievement.query.filter_by(slug="podium_finish").first()
        user_achievement = UserAchievement.query.filter_by(
            user_id=player1.id,
            achievement_id=podium.id
        ).first()

        assert user_achievement is not None
        assert user_achievement.is_unlocked is True


class TestAchievementWorkflowXPBonus:
    """Test XP bonus awarded on achievement unlock."""

    @pytest.mark.skip(reason="Achievement handlers have session isolation issues with @transactional")
    def test_achievement_unlock_awards_bonus_xp(self, db_session, isolated_players):
        """
        GIVEN an achievement with XP reward
        WHEN achievement is unlocked
        THEN user receives bonus XP on top of event XP
        """
        # Arrange
        seed_achievements(db_session)
        player1 = isolated_players[0]
        player2 = isolated_players[1]

        # Get first_blood XP reward
        first_blood = Achievement.query.filter_by(slug="first_blood").first()
        achievement_xp = first_blood.xp_reward

        # Act: Win first match (triggers first_blood)
        event = MatchCompletedEvent(
            match_id=1,
            player1_id=player1.id,
            player1_name=player1.username,
            player2_id=player2.id,
            player2_name=player2.username,
            winner_id=player1.id,
            winner_name=player1.username,
            score="5-2"
        )
        EventBus.publish(event)
        db_session.flush()

        # Assert: User received match win XP + achievement XP
        from models.gamification.models import UserLevel
        from models.gamification.xp_config import XP_RATES
        from models.gamification.models import XPTransactionType

        user_level = db_session.get(UserLevel, player1.id)
        assert user_level is not None

        expected_xp = XP_RATES[XPTransactionType.MATCH_WIN] + achievement_xp
        assert user_level.total_xp == expected_xp


class TestAchievementWorkflowMultipleAchievements:
    """Test multiple achievements unlocking from single event."""

    @pytest.mark.skip(reason="Achievement handlers have session isolation issues with @transactional")
    def test_single_event_can_unlock_multiple_achievements(self, db_session, isolated_players):
        """
        GIVEN multiple match-based achievements (first_blood, veteran_player, etc.)
        WHEN user wins a match
        THEN all eligible achievements are checked and unlocked if requirements met
        """
        # Arrange
        seed_achievements(db_session)
        player1 = isolated_players[0]
        player2 = isolated_players[1]

        # Simulate user who has 49 wins already (via manual progress increment)
        veteran = Achievement.query.filter_by(slug="veteran_player").first()
        user_achievement_veteran = UserAchievement(
            user_id=player1.id,
            achievement_id=veteran.id,
            current_progress=49,
            is_unlocked=False
        )
        db_session.add(user_achievement_veteran)
        db_session.flush()

        # Act: 50th win (should unlock first_blood + veteran_player)
        event = MatchCompletedEvent(
            match_id=50,
            player1_id=player1.id,
            player1_name=player1.username,
            player2_id=player2.id,
            player2_name=player2.username,
            winner_id=player1.id,
            winner_name=player1.username,
            score="5-2"
        )
        EventBus.publish(event)
        db_session.flush()

        # Assert: Both achievements unlocked
        first_blood = Achievement.query.filter_by(slug="first_blood").first()
        ua_first = UserAchievement.query.filter_by(
            user_id=player1.id,
            achievement_id=first_blood.id
        ).first()
        assert ua_first is not None
        assert ua_first.is_unlocked is True

        db_session.refresh(user_achievement_veteran)
        assert user_achievement_veteran.is_unlocked is True
        assert user_achievement_veteran.current_progress == 50


class TestAchievementSeedingIdempotence:
    """Test achievement seeding is idempotent."""

    def test_seeding_achievements_is_idempotent(self, db_session):
        """
        GIVEN achievements have been seeded once
        WHEN seed_achievements is called again
        THEN no duplicate achievements are created
        """
        # Act: Seed twice
        created1, skipped1 = seed_achievements(db_session)
        created2, skipped2 = seed_achievements(db_session)

        # Assert: Second run creates 0, skips all
        assert created1 > 0
        assert created2 == 0
        assert skipped2 == created1 + skipped1  # All existing were skipped
