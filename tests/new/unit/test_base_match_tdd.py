"""
Test-Driven Development for BaseMatchMixin mixin class.

This test suite defines the expected behavior for the shared match functionality
between Match (tournament matches) and IndividualMatch (casual matches).
"""

import pytest
from datetime import datetime
from models.base import db
from models.match.base_match import BaseMatchMixin
from models.status_enum import MatchStatus


class TestBaseMatchValidation:
    """Test validation and confirmation workflow."""

    def test_is_ready_for_validation_returns_false_when_not_complete(
        self, db_session, sample_match
    ):
        """Match not at distance should not be ready for validation."""
        # Given: A match with scores below distance
        sample_match.player1_score = 2
        sample_match.player2_score = 1
        sample_match.distance = 5

        # When: Checking if ready for validation
        result = sample_match.is_ready_for_validation()

        # Then: Should not be ready
        assert result is False

    def test_is_ready_for_validation_returns_true_when_complete(
        self, db_session, sample_match
    ):
        """Match at distance should be ready for validation."""
        # Given: A match that has reached the distance
        sample_match.player1_score = 5
        sample_match.player2_score = 3
        sample_match.distance = 5
        sample_match.best_of = True
        sample_match.status = MatchStatus.PLAYING.value

        # When: Checking if ready for validation
        result = sample_match.is_ready_for_validation()

        # Then: Should be ready
        assert result is True

    def test_confirm_result_sets_player1_confirmed(self, db_session, sample_match):
        """Confirming result should set player1_confirmed flag."""
        # Given: A match ready for validation
        sample_match.player1_score = 5
        sample_match.player2_score = 3
        sample_match.status = MatchStatus.PLAYING.value

        # When: Player 1 confirms
        sample_match.confirm_result(sample_match.player1_id)

        # Then: Player 1 should be marked as confirmed
        assert sample_match.player1_confirmed is True
        assert sample_match.player1_confirmed_at is not None
        assert sample_match.player2_confirmed is False

    def test_confirm_result_sets_player2_confirmed(self, db_session, sample_match):
        """Confirming result should set player2_confirmed flag."""
        # Given: A match ready for validation
        sample_match.player1_score = 5
        sample_match.player2_score = 3
        sample_match.status = MatchStatus.PLAYING.value

        # When: Player 2 confirms
        sample_match.confirm_result(sample_match.player2_id)

        # Then: Player 2 should be marked as confirmed
        assert sample_match.player2_confirmed is True
        assert sample_match.player2_confirmed_at is not None
        assert sample_match.player1_confirmed is False

    def test_confirm_result_completes_match_when_both_confirm(
        self, db_session, sample_match
    ):
        """Match should complete when both players confirm."""
        # Given: A match ready for validation
        sample_match.player1_score = 5
        sample_match.player2_score = 3
        sample_match.status = MatchStatus.PLAYING.value

        # When: Both players confirm
        sample_match.confirm_result(sample_match.player1_id)
        completed = sample_match.confirm_result(sample_match.player2_id)

        # Then: Match should be completed
        assert completed is True
        assert sample_match.status == MatchStatus.COMPLETED.value
        assert sample_match.winner_id == sample_match.player1_id

    def test_confirm_result_raises_for_invalid_user(self, db_session, sample_match):
        """Should raise error if user is not part of match."""
        # Given: A match
        invalid_user_id = 999

        # When/Then: Confirming with invalid user should raise
        with pytest.raises(ValueError, match="User is not part of this match"):
            sample_match.confirm_result(invalid_user_id)

    def test_reject_result_removes_last_rack_and_resets_confirmations(
        self, db_session, sample_match, sample_racks
    ):
        """Rejecting should remove last rack and reset confirmations."""
        # Given: A match with confirmations
        sample_match.player1_confirmed = True
        sample_match.player1_score = 5
        sample_match.player2_score = 3

        # When: Player 2 rejects
        sample_match.reject_result(sample_match.player2_id)

        # Then: Last rack should be removed, confirmations reset
        assert sample_match.player1_confirmed is False
        assert sample_match.player2_confirmed is False
        assert sample_match.player1_score == 4  # Reduced by 1


class TestBaseMatchRackScore:
    """Test rack_score property integration."""

    def test_rack_score_returns_correct_abstraction(self, db_session, sample_match):
        """Should return RackScore value object."""
        # Given: A match with scores
        sample_match.player1_score = 3
        sample_match.player2_score = 2

        # When: Getting rack_score
        rack_score = sample_match.rack_score

        # Then: Should have correct values
        assert rack_score.player1_racks == 3
        assert rack_score.player2_racks == 2

    def test_rack_score_is_complete_detects_winner(self, db_session, sample_match):
        """Should detect when match is complete."""
        # Given: A match at winning distance
        sample_match.player1_score = 5
        sample_match.player2_score = 3
        sample_match.distance = 5
        sample_match.best_of = True

        # When: Checking if complete
        is_complete = sample_match.rack_score.is_complete()

        # Then: Should be complete
        assert is_complete is True


class TestBaseMatchDistanceConfig:
    """Test distance_config property."""

    def test_distance_config_single_set(self, db_session, sample_match):
        """Should return correct Distance for single-set match."""
        # Given: A single-set match
        sample_match.distance = 5
        sample_match.best_of = True
        sample_match.is_multi_set = False

        # When: Getting distance config
        distance = sample_match.distance_config

        # Then: Should be single-set configuration
        assert distance.racks == 5
        assert distance.racks_best_of is True
        assert distance.is_multi_set is False


# Fixtures
@pytest.fixture
def sample_match(db_session, sample_users):
    """Create a sample match for testing."""
    from models.match.models import Match
    from models.competition.models import Gara
    from models.status_enum import GaraStatus

    # Create a gara first
    gara = Gara(
        number=1,
        name="Test Gara",
        date=datetime.utcnow().date(),
        discipline="palla_8",
        distance=5,
        best_of=True,
        status=GaraStatus.INSCRIPTION.value,
    )
    db_session.add(gara)
    db_session.flush()

    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=sample_users[0].id,
        player2_id=sample_users[1].id,
        player1_score=0,
        player2_score=0,
        status=MatchStatus.PLAYING.value,
    )
    db_session.add(match)
    db_session.commit()

    return match


@pytest.fixture
def sample_racks(db_session, sample_match):
    """Create sample racks for testing."""
    from models.match.models import Rack

    racks = []
    for i in range(5):
        rack = Rack(
            match_id=sample_match.id,
            rack_number=i + 1,
            winner_id=sample_match.player1_id,
            added_by_id=sample_match.player1_id,
            added_at=datetime.utcnow(),
        )
        db_session.add(rack)
        racks.append(rack)

    db_session.commit()
    return racks


@pytest.fixture
def sample_users(db_session):
    """Create sample users for testing."""
    from models.user.models import User

    users = []
    for i in range(2):
        user = User(
            username=f"player{i+1}",
            email=f"player{i+1}@test.com",
            role="player",
        )
        user.set_password("password")
        db_session.add(user)
        users.append(user)

    db_session.commit()
    return users
