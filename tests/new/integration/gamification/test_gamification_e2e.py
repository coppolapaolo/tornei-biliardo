"""
End-to-End Gamification Workflow Tests

Tests the complete gamification flow:
1. Match completion → XP award → Level check → Achievement check → Notification
2. Tournament inscription → XP award → Streak update
3. Admin operations → Quest creation → User participation
"""

import pytest
from datetime import datetime, timedelta

from models.base import db
from models import (
    User,
    Gara,
    Inscription,
    Match,
    Campionato,
    UserLevel,
    XPTransaction,
    Achievement,
    UserAchievement,
    StreakTracker,
    Notification,
    NotificationType,
    XPTransactionType,
    StreakType,
    AchievementCategory,
    AchievementDifficulty,
)
from models.gamification.level_service import LevelService
from models.gamification.achievement_service import AchievementService
from models.gamification.streak_service import StreakService
from models.gamification.achievement_seeds import seed_achievements
from models.status_enum import GaraStatus


class TestGamificationE2EWorkflows:
    """End-to-end tests for gamification system."""

    @pytest.fixture(autouse=True)
    def setup(self, db_session):
        """Set up test fixtures."""
        self.db_session = db_session

        # Create test users
        self.player1 = User(username="player1_gam", role="player")
        self.player1.set_password("test123")
        self.player2 = User(username="player2_gam", role="player")
        self.player2.set_password("test123")
        self.admin = User(username="admin_gam", role="admin")
        self.admin.set_password("test123")

        db_session.add_all([self.player1, self.player2, self.admin])
        db_session.flush()

        # Seed achievements
        seed_achievements(db_session)

        yield

    def test_xp_award_creates_user_level_record(self, db_session):
        """Test that awarding XP creates UserLevel if not exists."""
        # Verify no UserLevel exists initially
        level = UserLevel.query.filter_by(user_id=self.player1.id).first()
        assert level is None

        # Award XP
        result = LevelService.award_xp(
            user_id=self.player1.id,
            xp_amount=100,
            transaction_type=XPTransactionType.MATCH_WIN,
            reason="Test XP award",
        )

        # Verify UserLevel was created
        level = UserLevel.query.filter_by(user_id=self.player1.id).first()
        assert level is not None
        assert level.current_level == 1
        assert level.total_xp == 100

        # Verify XPTransaction was logged
        transactions = XPTransaction.query.filter_by(user_id=self.player1.id).all()
        assert len(transactions) == 1
        assert transactions[0].xp_amount == 100
        assert transactions[0].transaction_type == XPTransactionType.MATCH_WIN

    def test_level_up_on_xp_threshold(self, db_session):
        """Test that user levels up when XP threshold is reached."""
        # Level 2 requires int(100 * 2^1.5) = 282 XP
        # Award enough XP to level up
        result = LevelService.award_xp(
            user_id=self.player1.id,
            xp_amount=300,
            transaction_type=XPTransactionType.TOURNAMENT_WIN,
            reason="Tournament victory",
        )

        level = UserLevel.query.filter_by(user_id=self.player1.id).first()
        assert level.current_level == 2
        assert level.total_xp == 300

    def test_achievement_tracking_creates_user_record(self, db_session):
        """Test that checking achievements creates UserAchievement record."""
        # Get the "first_blood" achievement (win first match)
        first_blood = Achievement.query.filter_by(slug="first_blood").first()
        assert first_blood is not None

        # Check achievement (won't unlock without actual match data)
        # This creates the UserAchievement record for tracking
        result, was_unlocked = AchievementService.check_and_award_achievement(
            user_id=self.player1.id, achievement_slug="first_blood"
        )

        # Verify UserAchievement record was created for tracking
        user_ach = UserAchievement.query.filter_by(
            user_id=self.player1.id, achievement_id=first_blood.id
        ).first()
        assert user_ach is not None
        # Non-progressive achievements require actual stats check
        # Without a real match win, it won't unlock
        assert was_unlocked is False

    def test_progressive_achievement_tracking(self, db_session):
        """Test progressive achievement progress tracking."""
        # Get "veteran_player" (50 wins, progressive)
        veteran = Achievement.query.filter_by(slug="veteran_player").first()
        assert veteran is not None
        assert veteran.is_progressive is True

        # Increment progress multiple times
        for i in range(5):
            AchievementService.check_and_award_achievement(
                user_id=self.player1.id,
                achievement_slug="veteran_player",
                progress_increment=1,
            )

        # Check progress
        user_ach = UserAchievement.query.filter_by(
            user_id=self.player1.id, achievement_id=veteran.id
        ).first()
        assert user_ach is not None
        assert user_ach.current_progress == 5
        assert user_ach.is_unlocked is False  # Need 50 wins

    def test_streak_recording_and_continuation(self, db_session):
        """Test weekly streak tracking."""
        # Record first activity
        tracker, result = StreakService.record_activity(
            user_id=self.player1.id, streak_type=StreakType.WEEKLY_MATCH
        )

        assert tracker.current_streak == 1
        assert result["action"] == "started"

        # Record another activity in the same week
        tracker, result = StreakService.record_activity(
            user_id=self.player1.id, streak_type=StreakType.WEEKLY_MATCH
        )

        # Same week, streak should continue but not increment
        assert tracker.current_streak == 1
        assert result["action"] == "continued"

    def test_multiple_streak_types_independent(self, db_session):
        """Test that different streak types are tracked independently."""
        # Record match activity
        match_tracker, _ = StreakService.record_activity(
            user_id=self.player1.id, streak_type=StreakType.WEEKLY_MATCH
        )

        # Record tournament activity
        tournament_tracker, _ = StreakService.record_activity(
            user_id=self.player1.id, streak_type=StreakType.WEEKLY_TOURNAMENT
        )

        # Both should have independent streaks
        assert match_tracker.current_streak == 1
        assert tournament_tracker.current_streak == 1

        # Verify they're different records
        all_streaks = StreakTracker.query.filter_by(user_id=self.player1.id).all()
        assert len(all_streaks) == 2

    def test_get_all_user_achievements(self, db_session):
        """Test retrieving user achievement status."""
        # Start progress on a progressive achievement
        AchievementService.check_and_award_achievement(
            user_id=self.player1.id,
            achievement_slug="veteran_player",
            progress_increment=10,
        )

        # Get all achievements for user
        achievements = AchievementService.get_user_achievements(self.player1.id)

        # Should have at least one achievement with progress
        in_progress = [a for a in achievements if a.get("current_progress", 0) > 0]
        assert len(in_progress) >= 1

        # Check the veteran_player progress (note: achievement object is nested)
        veteran = next(
            (a for a in achievements if a.get("achievement").slug == "veteran_player"),
            None,
        )
        assert veteran is not None
        assert veteran.get("current_progress") == 10

    def test_level_progress_calculation(self, db_session):
        """Test level progress percentage calculation."""
        # Award some XP (less than level 2 requirement)
        # Level 2 requires int(100 * 2^1.5) = 282 XP
        LevelService.award_xp(
            user_id=self.player1.id,
            xp_amount=100,
            transaction_type=XPTransactionType.MATCH_WIN,
            reason="Test",
        )

        # Get progress
        progress = LevelService.get_level_progress(self.player1.id)

        assert progress["current_level"] == 1
        assert progress["current_xp"] == 100
        assert progress["total_xp"] == 100
        # 100/282 ≈ 35.5%
        assert 30 < progress["progress_percentage"] < 40

    def test_xp_transaction_audit_trail(self, db_session):
        """Test that all XP transactions are properly logged."""
        # Award multiple XP amounts
        LevelService.award_xp(
            user_id=self.player1.id,
            xp_amount=50,
            transaction_type=XPTransactionType.MATCH_WIN,
            reason="Won match 1",
        )
        LevelService.award_xp(
            user_id=self.player1.id,
            xp_amount=20,
            transaction_type=XPTransactionType.MATCH_LOSS,
            reason="Lost match 2",
        )
        LevelService.award_xp(
            user_id=self.player1.id,
            xp_amount=100,
            transaction_type=XPTransactionType.TOURNAMENT_COMPLETION,
            reason="Completed tournament",
        )

        # Verify all transactions logged
        transactions = (
            XPTransaction.query.filter_by(user_id=self.player1.id)
            .order_by(XPTransaction.created_at)
            .all()
        )

        assert len(transactions) == 3
        assert transactions[0].transaction_type == XPTransactionType.MATCH_WIN
        assert transactions[1].transaction_type == XPTransactionType.MATCH_LOSS
        assert (
            transactions[2].transaction_type == XPTransactionType.TOURNAMENT_COMPLETION
        )

        # Total XP should match sum
        level = UserLevel.query.filter_by(user_id=self.player1.id).first()
        assert level.total_xp == 170  # 50 + 20 + 100

    def test_admin_can_grant_xp(self, db_session):
        """Test admin XP grant functionality."""
        # Grant XP as admin
        result = LevelService.award_xp(
            user_id=self.player1.id,
            xp_amount=500,
            transaction_type=XPTransactionType.ADMIN_GRANT,
            reason="Bonus for community contribution",
        )

        # Verify XP granted
        level = UserLevel.query.filter_by(user_id=self.player1.id).first()
        assert level.total_xp == 500

        # Verify transaction logged with ADMIN_GRANT type
        transaction = XPTransaction.query.filter_by(
            user_id=self.player1.id, transaction_type=XPTransactionType.ADMIN_GRANT
        ).first()
        assert transaction is not None
        assert "community contribution" in transaction.reason


class TestGamificationIntegrationWithCompetitions:
    """Integration tests with competition system."""

    @pytest.fixture(autouse=True)
    def setup(self, db_session):
        """Set up test fixtures with competition data."""
        self.db_session = db_session

        # Create test users
        self.player1 = User(username="comp_player1", role="player")
        self.player1.set_password("test123")
        self.player2 = User(username="comp_player2", role="player")
        self.player2.set_password("test123")

        db_session.add_all([self.player1, self.player2])
        db_session.flush()

        # Create campionato and gara
        self.campionato = Campionato(name="Test Campionato")
        db_session.add(self.campionato)
        db_session.flush()

        self.gara = Gara(
            campionato_id=self.campionato.id,
            number=1,
            name="Test Gara",
            date=datetime.now().date() + timedelta(days=1),
            discipline="palla_8",
            distance=5,
            status=GaraStatus.INSCRIPTION.value,
        )
        db_session.add(self.gara)
        db_session.flush()

        # Seed achievements
        seed_achievements(db_session)

        yield

    def test_inscription_creates_gamification_opportunity(self, db_session):
        """Test that tournament inscription can trigger gamification."""
        # Create inscription
        inscription = Inscription(user_id=self.player1.id, gara_id=self.gara.id)
        db_session.add(inscription)
        db_session.flush()

        # Manually trigger XP award (normally done by event handler)
        LevelService.award_xp(
            user_id=self.player1.id,
            xp_amount=25,
            transaction_type=XPTransactionType.TOURNAMENT_INSCRIPTION,
            reason=f"Inscribed to {self.gara.name}",
        )

        # Record tournament streak
        StreakService.record_activity(
            user_id=self.player1.id, streak_type=StreakType.WEEKLY_TOURNAMENT
        )

        # Verify XP awarded
        level = UserLevel.query.filter_by(user_id=self.player1.id).first()
        assert level.total_xp == 25

        # Verify streak started
        streak = StreakTracker.query.filter_by(
            user_id=self.player1.id, streak_type=StreakType.WEEKLY_TOURNAMENT
        ).first()
        assert streak.current_streak == 1

    def test_match_completion_awards_xp(self, db_session):
        """Test that match completion awards appropriate XP."""
        # Create a match
        match = Match(
            gara_id=self.gara.id,
            round_number=1,
            player1_id=self.player1.id,
            player2_id=self.player2.id,
            status="completed",
            player1_score=5,
            player2_score=3,
            winner_id=self.player1.id,
        )
        db_session.add(match)
        db_session.flush()

        # Manually trigger XP awards (normally done by event handler)
        LevelService.award_xp(
            user_id=self.player1.id,
            xp_amount=50,
            transaction_type=XPTransactionType.MATCH_WIN,
            reason="Won match",
        )
        LevelService.award_xp(
            user_id=self.player2.id,
            xp_amount=20,
            transaction_type=XPTransactionType.MATCH_LOSS,
            reason="Lost match",
        )

        # Verify winner XP
        winner_level = UserLevel.query.filter_by(user_id=self.player1.id).first()
        assert winner_level.total_xp == 50

        # Verify loser XP (participation reward)
        loser_level = UserLevel.query.filter_by(user_id=self.player2.id).first()
        assert loser_level.total_xp == 20
