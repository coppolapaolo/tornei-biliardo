"""
Unit tests for LevelService - XP award and level progression logic.

Tests:
- XP award functionality
- Level up detection and progression
- Multiple level ups in single award
- Level unlock eligibility checking
"""

from models.gamification.level_service import LevelService
from models.gamification.xp_config import get_xp_for_level
from models.gamification.models import XPTransaction, XPTransactionType


class TestLevelServiceXPAward:
    """Test XP award functionality."""

    def test_award_xp_creates_user_level_if_not_exists(
        self, db_session, isolated_players
    ):
        """First XP award should create UserLevel record."""
        player = isolated_players[0]
        xp_amount = 50

        # Award XP
        user_level, did_level_up = LevelService.award_xp(
            user_id=player.id,
            xp_amount=xp_amount,
            transaction_type=XPTransactionType.MATCH_WIN,
        )

        # Assertions
        assert user_level is not None
        assert user_level.user_id == player.id
        assert user_level.current_level == 1
        assert user_level.current_xp == 50
        assert user_level.total_xp == 50
        assert did_level_up is False

    def test_award_xp_updates_existing_user_level(self, db_session, isolated_players):
        """Subsequent XP awards should update existing UserLevel."""
        player = isolated_players[0]

        # First award
        LevelService.award_xp(
            user_id=player.id,
            xp_amount=50,
            transaction_type=XPTransactionType.MATCH_WIN,
        )

        # Second award
        user_level, did_level_up = LevelService.award_xp(
            user_id=player.id,
            xp_amount=30,
            transaction_type=XPTransactionType.STREAK_BONUS,
        )

        # Assertions
        assert user_level.current_xp == 80
        assert user_level.total_xp == 80
        assert did_level_up is False

    def test_award_xp_creates_transaction_record(self, db_session, isolated_players):
        """XP award should create audit transaction."""
        player = isolated_players[0]
        xp_amount = 50

        user_level, _ = LevelService.award_xp(
            user_id=player.id,
            xp_amount=xp_amount,
            transaction_type=XPTransactionType.MATCH_WIN,
            reason="Test match win",
        )

        # Check transaction exists
        transaction = XPTransaction.query.filter_by(user_id=player.id).first()
        assert transaction is not None
        assert transaction.xp_amount == 50
        assert transaction.transaction_type == XPTransactionType.MATCH_WIN
        assert transaction.reason == "Test match win"


class TestLevelServiceLevelUp:
    """Test level up detection and progression."""

    def test_level_up_triggers_when_xp_reaches_threshold(
        self, db_session, isolated_players
    ):
        """Should level up when XP reaches next level threshold."""
        player = isolated_players[0]

        # XP curve: level 2 requires 100 * (2 ** 1.5) ≈ 283 XP
        xp_for_level_2 = get_xp_for_level(2)  # ~283 XP
        user_level, did_level_up = LevelService.award_xp(
            user_id=player.id,
            xp_amount=xp_for_level_2,
            transaction_type=XPTransactionType.TOURNAMENT_WIN,
        )

        # Should be level 2 now
        assert user_level.current_level == 2
        assert did_level_up is True

    def test_multiple_level_ups_in_single_award(self, db_session, isolated_players):
        """Large XP award should trigger multiple level ups."""
        player = isolated_players[0]

        # Award enough XP for level 5 (around 1118 XP)
        xp_for_level_5 = get_xp_for_level(5)
        user_level, did_level_up = LevelService.award_xp(
            user_id=player.id,
            xp_amount=xp_for_level_5 + 100,  # Extra buffer
            transaction_type=XPTransactionType.TOURNAMENT_WIN,
        )

        # Should be at least level 3 (exact level depends on XP curve)
        assert user_level.current_level >= 3
        assert did_level_up is True
        assert user_level.highest_level_reached == user_level.current_level

    def test_xp_overflow_rolls_to_next_level(self, db_session, isolated_players):
        """Excess XP should roll over to next level."""
        player = isolated_players[0]

        # XP for level 2 is ~283, award 300 XP (17 overflow)
        xp_for_level_2 = get_xp_for_level(2)  # ~283
        user_level, _ = LevelService.award_xp(
            user_id=player.id,
            xp_amount=xp_for_level_2 + 17,
            transaction_type=XPTransactionType.TOURNAMENT_WIN,
        )

        # Level 2 with 17 XP overflow
        assert user_level.current_level == 2
        assert user_level.current_xp == 17
        assert user_level.total_xp == xp_for_level_2 + 17


class TestLevelServiceUnlocks:
    """Test feature unlock eligibility."""

    def test_check_unlock_eligibility_returns_false_below_threshold(
        self, db_session, isolated_players
    ):
        """Should return False when below unlock level."""
        from models.gamification.unlock_engine import UnlockEngine

        player = isolated_players[0]

        # Award some XP (stays at level 1)
        LevelService.award_xp(
            user_id=player.id,
            xp_amount=50,
            transaction_type=XPTransactionType.MATCH_WIN,
        )

        # Check unlock for tournament_creation (level 10 required)
        is_eligible = UnlockEngine.check_eligibility(
            user_id=player.id, feature_code="tournament_creation"
        )

        assert is_eligible is False

    def test_check_unlock_eligibility_returns_true_at_threshold(
        self, db_session, isolated_players
    ):
        """Should return True when at or above unlock level."""
        from models.gamification.unlock_engine import UnlockEngine

        player = isolated_players[0]

        # Award enough XP to reach level 10+
        # Level 10 requires ~3162 total XP (100 * 10^1.5)
        xp_for_level_10 = get_xp_for_level(10)

        LevelService.award_xp(
            user_id=player.id,
            xp_amount=xp_for_level_10 + 100,  # Extra buffer
            transaction_type=XPTransactionType.ADMIN_ADJUSTMENT,
        )

        # Check unlock for tournament_creation (level 10)
        is_eligible = UnlockEngine.check_eligibility(
            user_id=player.id, feature_code="tournament_creation"
        )

        assert is_eligible is True


class TestLevelServiceUIHelpers:
    """Test UI helper methods."""

    def test_get_level_progress_returns_progress_info(
        self, db_session, isolated_players
    ):
        """Should return complete display data for UI."""
        player = isolated_players[0]

        # Award some XP
        LevelService.award_xp(
            user_id=player.id,
            xp_amount=50,
            transaction_type=XPTransactionType.MATCH_WIN,
        )

        # Get progress data (correct method name)
        progress_data = LevelService.get_level_progress(player.id)

        # Check all expected fields exist
        assert "current_level" in progress_data
        assert "current_xp" in progress_data
        assert "total_xp" in progress_data
        assert "xp_for_next_level" in progress_data
        assert "progress_percentage" in progress_data

        # Values should be sensible
        assert progress_data["current_level"] == 1
        assert progress_data["current_xp"] == 50
        assert progress_data["total_xp"] == 50
        assert 0 <= progress_data["progress_percentage"] <= 100
