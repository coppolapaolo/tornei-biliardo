"""
Test-Driven Development for max racks validation in BaseMatchMixin.

This test suite defines the expected behavior for preventing rack addition
when the match has reached the maximum possible racks and needs validation.
"""

import pytest
from datetime import datetime
from models.status_enum import MatchStatus
from models.base import utc_now


class TestBaseMatchMaxRacksValidation:
    """Test that racks cannot be added when match is at max and needs validation."""

    def test_can_add_rack_returns_false_when_at_max_racks(
        self, db_session, sample_match
    ):
        """Should not allow adding rack when match is at validation stage."""
        # Given: A match that has reached maximum possible racks
        sample_match.player1_score = 5
        sample_match.player2_score = 3
        sample_match.status = MatchStatus.PLAYING.value

        # When: Checking if can add rack
        result = sample_match.can_add_rack()

        # Then: Should not be able to add rack
        assert result is False

    def test_can_add_rack_returns_true_when_not_at_max_racks(
        self, db_session, sample_match
    ):
        """Should allow adding rack when match is not at validation stage."""
        # Given: A best-of 5 match that has not reached maximum (target is 3)
        sample_match.player1_score = 2
        sample_match.player2_score = 2
        sample_match.status = MatchStatus.PLAYING.value

        # When: Checking if can add rack
        result = sample_match.can_add_rack()

        # Then: Should be able to add rack
        assert result is True

    def test_can_add_rack_returns_true_for_race_to_not_at_target(
        self, db_session, sample_match
    ):
        """Best-of format: should allow rack when no player reached target."""
        # Given: Best-of 5 match with scores below target (3)
        sample_match.player1_score = 2
        sample_match.player2_score = 1
        sample_match.status = MatchStatus.PLAYING.value

        # When: Checking if can add rack
        result = sample_match.can_add_rack()

        # Then: Should be able to add rack
        assert result is True

    def test_can_add_rack_returns_false_for_race_to_at_target(
        self, db_session, sample_match
    ):
        """Best-of format: should not allow rack when target reached."""
        # Given: Race to 5 match where player1 reached target (5)
        sample_match.player1_score = 5
        sample_match.player2_score = 2
        sample_match.status = MatchStatus.PLAYING.value

        # When: Checking if can add rack
        result = sample_match.can_add_rack()

        # Then: Should not be able to add rack
        assert result is False

    def test_can_add_rack_returns_true_for_exact_distance_not_complete(
        self, db_session, sample_match_exact_distance
    ):
        """Exact distance: should allow rack when not all racks played."""
        # Given: Exact 5 racks with 4 played
        sample_match_exact_distance.player1_score = 2
        sample_match_exact_distance.player2_score = 2
        sample_match_exact_distance.status = MatchStatus.PLAYING.value

        # When: Checking if can add rack
        result = sample_match_exact_distance.can_add_rack()

        # Then: Should be able to add rack
        assert result is True

    def test_can_add_rack_returns_false_for_exact_distance_complete(
        self, db_session, sample_match_exact_distance
    ):
        """Exact distance: should not allow rack when all racks played."""
        # Given: Exact 5 racks with all 5 played
        sample_match_exact_distance.player1_score = 3
        sample_match_exact_distance.player2_score = 2
        sample_match_exact_distance.status = MatchStatus.PLAYING.value

        # When: Checking if can add rack
        result = sample_match_exact_distance.can_add_rack()

        # Then: Should not be able to add rack
        assert result is False

    def test_can_add_rack_returns_false_when_match_not_in_progress(
        self, db_session, sample_match
    ):
        """Should not allow adding rack if match is not in progress."""
        # Given: A match that is completed
        sample_match.player1_score = 3
        sample_match.player2_score = 2
        sample_match.status = MatchStatus.COMPLETED.value

        # When: Checking if can add rack
        result = sample_match.can_add_rack()

        # Then: Should not be able to add rack
        assert result is False

    def test_can_add_rack_returns_true_when_match_pending(
        self, db_session, sample_match
    ):
        """Should allow adding first rack if match is pending.

        The first rack addition transitions the match from pending to playing.
        """
        # Given: A match that is pending with no scores
        sample_match.player1_score = 0
        sample_match.player2_score = 0
        sample_match.status = MatchStatus.PENDING.value

        # When: Checking if can add rack
        result = sample_match.can_add_rack()

        # Then: Should be able to add rack (first rack starts the match)
        assert result is True


class TestIndividualMatchCannotAddRackAtMax:
    """Test IndividualMatch add_rack_result method validation."""

    def test_add_rack_result_raises_when_at_max_racks(
        self, db_session, sample_individual_match
    ):
        """Should raise error when trying to add rack at max."""
        from models.individual_match.models import MatchStatus as IndividualMatchStatus

        # Given: An individual match at max racks
        sample_individual_match.player1_score = 5
        sample_individual_match.player2_score = 3
        sample_individual_match.distance = 5
        sample_individual_match.is_race_to = True
        sample_individual_match.status = IndividualMatchStatus.IN_PROGRESS

        # When/Then: Adding rack should raise ValueError
        with pytest.raises(ValueError, match="Cannot add rack"):
            sample_individual_match.add_rack_result(sample_individual_match.player1_id)

    def test_add_rack_result_succeeds_when_not_at_max(
        self, db_session, sample_individual_match
    ):
        """Should successfully add rack when not at max."""
        from models.individual_match.models import MatchStatus as IndividualMatchStatus

        # Given: An individual match not at max racks
        sample_individual_match.player1_score = 2
        sample_individual_match.player2_score = 1
        sample_individual_match.distance = 5
        sample_individual_match.is_race_to = True
        sample_individual_match.status = IndividualMatchStatus.IN_PROGRESS

        # When: Adding rack
        rack = sample_individual_match.add_rack_result(
            sample_individual_match.player1_id
        )

        # Then: Rack should be added successfully
        assert rack is not None
        assert sample_individual_match.player1_score == 3


class TestTournamentMatchCannotAddRackAtMax:
    """Test Match (tournament) add_rack method validation."""

    def test_add_rack_raises_when_at_max_racks(
        self, db_session, sample_tournament_match
    ):
        """Should raise error when trying to add rack at max."""
        # Given: A tournament match at max racks
        sample_tournament_match.player1_score = 5
        sample_tournament_match.player2_score = 3
        db_session.commit()

        # When/Then: Adding rack should raise ValueError
        with pytest.raises(ValueError, match="Cannot add rack"):
            from models.match.services import add_rack

            add_rack(
                sample_tournament_match.id,
                sample_tournament_match.player1_id,
                sample_tournament_match.player1_id,
            )

    def test_add_rack_succeeds_when_not_at_max(
        self, db_session, sample_tournament_match
    ):
        """Should successfully add rack when not at max."""
        # Given: A tournament match not at max racks
        sample_tournament_match.player1_score = 2
        sample_tournament_match.player2_score = 1
        db_session.commit()

        # When: Adding rack
        from models.match.services import add_rack

        rack = add_rack(
            sample_tournament_match.id,
            sample_tournament_match.player1_id,
            sample_tournament_match.player1_id,
        )

        # Then: Rack should be added successfully
        assert rack is not None
        refreshed = db_session.get(
            type(sample_tournament_match), sample_tournament_match.id
        )
        assert refreshed.player1_score == 3


# Fixtures
@pytest.fixture
def sample_match(db_session, sample_users):
    """Create a sample tournament match for testing."""
    from models.match.models import Match
    from models.competition.models import Gara
    from models.status_enum import GaraStatus

    # Create a gara first
    gara = Gara(
        number=1,
        name="Test Gara",
        date=utc_now().date(),
        discipline="8_ball",
        distance=5,
        is_race_to=True,
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
def sample_match_exact_distance(db_session, sample_users):
    """Create a sample tournament match with exact distance for testing."""
    from models.match.models import Match
    from models.competition.models import Gara
    from models.status_enum import GaraStatus

    # Create a gara with exact distance (is_race_to=False)
    gara = Gara(
        number=2,
        name="Test Gara Exact",
        date=utc_now().date(),
        discipline="8_ball",
        distance=5,
        is_race_to=False,  # Exact distance
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
def sample_individual_match(db_session, sample_users):
    """Create a sample individual match for testing."""
    from models.individual_match.models import (
        IndividualMatch,
        MatchStatus as IndividualMatchStatus,
    )

    match = IndividualMatch(
        player1_id=sample_users[0].id,
        player2_id=sample_users[1].id,
        location="Test Location",
        scheduled_at=utc_now(),
        discipline="8_ball",
        distance=5,
        is_race_to=True,
        status=IndividualMatchStatus.IN_PROGRESS,
    )
    db_session.add(match)
    db_session.commit()

    return match


@pytest.fixture
def sample_tournament_match(db_session, sample_users):
    """Create a sample tournament match for testing add_rack service."""
    from models.match.models import Match
    from models.competition.models import Gara
    from models.status_enum import GaraStatus

    # Create a gara first
    gara = Gara(
        number=3,
        name="Test Gara Tournament",
        date=utc_now().date(),
        discipline="8_ball",
        distance=5,
        is_race_to=True,
        status=GaraStatus.PLAYING.value,
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
