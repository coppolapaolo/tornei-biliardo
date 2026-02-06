"""
Unit tests for IndividualMatch free format (no distance limit) functionality.

Tests the free format match workflow where distance=None:
- Players can add unlimited racks
- Match is ready for validation when at least one rack is played
- Players manually end the match
- Winner is determined by higher score
"""

import pytest
from datetime import datetime, timedelta

from models.individual_match.models import IndividualMatch
from models.status_enum import MatchStatus
from models.base import utc_now


class TestFreeFormatMatchCreation:
    """Tests for creating free format matches."""

    def test_create_match_with_no_distance(self, app, db_session, isolated_players):
        """Should be able to create a match with distance=None."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            discipline="palla_8",
            distance=None,  # Free format
            is_race_to=True,
            is_multi_set=False,
        )
        db_session.add(match)
        db_session.commit()

        assert match.distance is None
        assert match.distance_config is None

    def test_free_format_match_start(self, app, db_session, isolated_players):
        """Starting a free format match should work normally."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now() + timedelta(hours=1),
            status=MatchStatus.SCHEDULED,
            distance=None,
            is_race_to=True,
            is_multi_set=False,
        )
        db_session.add(match)
        db_session.commit()

        match.start_match()

        assert match.status == MatchStatus.IN_PROGRESS
        assert match.started_at is not None


class TestFreeFormatCanAddRack:
    """Tests for can_add_rack() with free format matches."""

    def test_can_add_rack_always_true_for_free_format(
        self, app, db_session, isolated_players
    ):
        """Free format matches should always allow adding racks."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            started_at=utc_now(),
            distance=None,
            is_race_to=True,
            is_multi_set=False,
            player1_score=0,
            player2_score=0,
        )
        db_session.add(match)
        db_session.commit()

        # Can add racks even with 0 score
        assert match.can_add_rack() is True

        # Add many racks
        for _ in range(10):
            match.add_rack_result(player1.id)

        # Still can add more
        assert match.can_add_rack() is True

    def test_cannot_add_rack_when_not_in_progress(
        self, app, db_session, isolated_players
    ):
        """Free format matches still respect status constraints."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.SCHEDULED,  # Not in progress
            distance=None,
            is_race_to=True,
        )
        db_session.add(match)
        db_session.commit()

        # Cannot add rack when not in progress
        assert match.can_add_rack() is False


class TestFreeFormatValidation:
    """Tests for is_ready_for_validation() with free format matches."""

    def test_not_ready_when_no_racks_played(self, app, db_session, isolated_players):
        """Free format match is NOT ready for validation with 0 racks."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            started_at=utc_now(),
            distance=None,
            is_race_to=True,
            player1_score=0,
            player2_score=0,
        )
        db_session.add(match)
        db_session.commit()

        assert match.is_ready_for_validation() is False

    def test_ready_when_any_rack_played(self, app, db_session, isolated_players):
        """Free format match IS ready for validation after any rack is played."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            started_at=utc_now(),
            distance=None,
            is_race_to=True,
            player1_score=0,
            player2_score=0,
        )
        db_session.add(match)
        db_session.commit()

        # Add one rack
        match.add_rack_result(player1.id)

        assert match.is_ready_for_validation() is True

    def test_still_can_add_after_ready_for_validation(
        self, app, db_session, isolated_players
    ):
        """Unlike normal matches, free format can add racks even when ready."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            started_at=utc_now(),
            distance=None,
            is_race_to=True,
            player1_score=0,
            player2_score=0,
        )
        db_session.add(match)
        db_session.commit()

        # Add one rack
        match.add_rack_result(player1.id)

        # Ready for validation BUT can still add racks
        assert match.is_ready_for_validation() is True
        assert match.can_add_rack() is True

        # Add more racks
        match.add_rack_result(player2.id)
        match.add_rack_result(player1.id)

        # Still can add and still ready
        assert match.can_add_rack() is True
        assert match.is_ready_for_validation() is True


class TestFreeFormatCompletion:
    """Tests for completing free format matches."""

    def test_winner_determined_by_higher_score(
        self, app, db_session, isolated_players
    ):
        """Winner should be the player with more racks."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            started_at=utc_now(),
            distance=None,
            is_race_to=True,
            player1_score=0,
            player2_score=0,
        )
        db_session.add(match)
        db_session.commit()

        # Player 1 wins more racks
        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)
        match.add_rack_result(player2.id)
        match.add_rack_result(player1.id)

        # Both confirm
        match.confirm_result(player1.id)
        match.confirm_result(player2.id)

        assert match.status == MatchStatus.VALIDATED
        assert match.winner_id == player1.id

    def test_player2_wins_when_higher_score(
        self, app, db_session, isolated_players
    ):
        """Player 2 should win when they have higher score."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            started_at=utc_now(),
            distance=None,
            is_race_to=True,
            player1_score=0,
            player2_score=0,
        )
        db_session.add(match)
        db_session.commit()

        # Player 2 wins more racks
        match.add_rack_result(player1.id)
        match.add_rack_result(player2.id)
        match.add_rack_result(player2.id)
        match.add_rack_result(player2.id)
        match.add_rack_result(player2.id)

        # Both confirm
        match.confirm_result(player1.id)
        match.confirm_result(player2.id)

        assert match.status == MatchStatus.VALIDATED
        assert match.winner_id == player2.id

    def test_tie_results_in_no_winner(self, app, db_session, isolated_players):
        """A tie should result in no winner (winner_id = None)."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            started_at=utc_now(),
            distance=None,
            is_race_to=True,
            player1_score=0,
            player2_score=0,
        )
        db_session.add(match)
        db_session.commit()

        # Equal racks
        match.add_rack_result(player1.id)
        match.add_rack_result(player2.id)
        match.add_rack_result(player1.id)
        match.add_rack_result(player2.id)

        # Both confirm
        match.confirm_result(player1.id)
        match.confirm_result(player2.id)

        assert match.status == MatchStatus.VALIDATED
        assert match.winner_id is None  # Tie


class TestFreeFormatRackScore:
    """Tests for rack_score property with free format matches."""

    def test_rack_score_is_none_for_free_format(
        self, app, db_session, isolated_players
    ):
        """rack_score should return None for free format matches."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            distance=None,
            is_race_to=True,
            player1_score=5,
            player2_score=3,
        )
        db_session.add(match)
        db_session.commit()

        assert match.rack_score is None


class TestFreeFormatWithBilateralConfirmation:
    """Tests for bilateral confirmation in free format matches."""

    def test_first_confirm_returns_false(self, app, db_session, isolated_players):
        """First confirmation should return False."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            started_at=utc_now(),
            distance=None,
            is_race_to=True,
            player1_score=0,
            player2_score=0,
        )
        db_session.add(match)
        db_session.commit()

        match.add_rack_result(player1.id)

        result = match.confirm_result(player1.id)

        assert result is False
        assert match.player1_confirmed is True
        assert match.player2_confirmed is False
        assert match.status == MatchStatus.IN_PROGRESS

    def test_second_confirm_returns_true_and_completes(
        self, app, db_session, isolated_players
    ):
        """Second confirmation should return True and complete match."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            started_at=utc_now(),
            distance=None,
            is_race_to=True,
            player1_score=0,
            player2_score=0,
        )
        db_session.add(match)
        db_session.commit()

        match.add_rack_result(player1.id)
        match.confirm_result(player1.id)
        result = match.confirm_result(player2.id)

        assert result is True
        assert match.player1_confirmed is True
        assert match.player2_confirmed is True
        assert match.status == MatchStatus.VALIDATED

    def test_reject_resets_confirmations_and_removes_rack(
        self, app, db_session, isolated_players
    ):
        """Rejecting result should reset confirmations and remove last rack."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            started_at=utc_now(),
            distance=None,
            is_race_to=True,
            player1_score=0,
            player2_score=0,
        )
        db_session.add(match)
        db_session.commit()

        match.add_rack_result(player1.id)
        match.add_rack_result(player1.id)  # Score: 2-0
        match.confirm_result(player1.id)

        # Player 2 rejects
        match.reject_result(player2.id)

        assert match.player1_confirmed is False
        assert match.player2_confirmed is False
        assert match.player1_score == 1  # Last rack removed


class TestFreeFormatDistanceConfig:
    """Tests for distance_config property with free format matches."""

    def test_distance_config_returns_none(self, app, db_session, isolated_players):
        """distance_config should return None for free format matches."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            distance=None,
            is_race_to=True,
        )
        db_session.add(match)
        db_session.commit()

        assert match.distance_config is None

    def test_normal_match_distance_config_not_none(
        self, app, db_session, isolated_players
    ):
        """Normal matches should have a distance_config."""
        player1, player2 = isolated_players[:2]

        match = IndividualMatch(
            player1_id=player1.id,
            player2_id=player2.id,
            location="Test Hall",
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            distance=5,
            is_race_to=True,
        )
        db_session.add(match)
        db_session.commit()

        assert match.distance_config is not None
        assert match.distance_config.racks == 5
