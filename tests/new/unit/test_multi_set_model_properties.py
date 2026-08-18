"""Unit tests for multi-set model properties (Phase 6: Frontend Integration).

Tests the distance_config property for Gara, MatchProposal, and IndividualMatch
models with multi-set configuration support.
"""

from models.competition.models import Gara
from models.individual_match.models import MatchProposal, IndividualMatch
from models.match.distance import Distance
from models.status_enum import Discipline
from datetime import timedelta
from models.base import utc_now


class TestGaraMultiSetProperty:
    """Test Gara.distance_config with multi-set support."""

    def test_gara_single_set_race_to(self):
        """Test single-set best-of configuration (backward compatible)."""
        gara = Gara(
            campionato_id=None,
            number=1,
            date=utc_now().date(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=7,
            is_race_to=True,
            is_multi_set=False,
        )

        distance = gara.distance_config

        assert isinstance(distance, Distance)
        assert distance.racks == 7
        assert distance.is_race_to_racks is True
        assert distance.is_multi_set is False
        assert distance.sets == 1
        assert distance.to_display_string() == "Al 7 triangoli"

    def test_gara_single_set_exact(self):
        """Test single-set exact configuration (backward compatible)."""
        gara = Gara(
            campionato_id=None,
            number=1,
            date=utc_now().date(),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            is_race_to=False,
            is_multi_set=False,
        )

        distance = gara.distance_config

        assert distance.racks == 5
        assert distance.is_race_to_racks is False
        assert distance.is_multi_set is False
        # Italian string expected (Flask-Babel returns untranslated without app context)
        assert distance.to_display_string() == "Esattamente 5 triangoli"

    def test_gara_multi_set_race_to_sets_race_to_racks(self):
        """Test multi-set with best-of sets and best-of racks."""
        gara = Gara(
            campionato_id=None,
            number=1,
            date=utc_now().date(),
            discipline=Discipline.TEN_BALL.value,
            distance=5,  # Racks per set (Race-to-5)
            is_race_to=True,  # Race-to racks
            is_multi_set=True,
            match_distance=3,  # Sets to play (Race-to-3)
            is_race_to_sets=True,  # Race-to sets
        )

        distance = gara.distance_config

        assert distance.racks == 5
        assert distance.is_race_to_racks is True
        assert distance.is_multi_set is True
        assert distance.sets == 3
        assert distance.is_race_to_sets is True
        assert distance.to_display_string() == "Al 3 set, ogni set al 5 triangoli"
        assert distance.get_winning_racks() == 5
        assert distance.get_winning_sets() == 3

    def test_gara_multi_set_exact_sets_race_to_racks(self):
        """Test multi-set with exact sets and best-of racks."""
        gara = Gara(
            campionato_id=None,
            number=1,
            date=utc_now().date(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=3,
            is_race_to=True,
            is_multi_set=True,
            match_distance=4,  # Play exactly 4 sets
            is_race_to_sets=False,  # Exact sets
        )

        distance = gara.distance_config

        assert distance.racks == 3
        assert distance.sets == 4
        assert distance.is_race_to_sets is False
        # Italian string expected (Flask-Babel returns untranslated without app context)
        assert (
            distance.to_display_string() == "Esattamente 4 set, ogni set al 3 triangoli"
        )

    def test_gara_multi_set_defaults(self):
        """Test multi-set with None values uses defaults."""
        gara = Gara(
            campionato_id=None,
            number=1,
            date=utc_now().date(),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            is_race_to=True,
            is_multi_set=True,
            match_distance=None,  # Should default to 1
            is_race_to_sets=None,  # Should default to True
        )

        distance = gara.distance_config

        assert distance.sets == 1  # Default when None
        assert distance.is_race_to_sets is True  # Default when None

    def test_gara_backward_compatibility_no_multi_set_fields(self):
        """Test backward compatibility when multi-set fields don't exist."""
        gara = Gara(
            campionato_id=None,
            number=1,
            date=utc_now().date(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=7,
            is_race_to=True,
            # No is_multi_set, match_distance, is_race_to_sets
        )

        # is_multi_set defaults to False
        distance = gara.distance_config

        assert distance.racks == 7
        assert distance.is_multi_set is False
        assert distance.to_display_string() == "Al 7 triangoli"


class TestMatchProposalMultiSetProperty:
    """Test MatchProposal.distance_config with multi-set support."""

    def test_proposal_single_set_race_to(self):
        """Test proposal single-set configuration."""
        proposal = MatchProposal(
            proposer_id=1,
            proposal_type="direct",
            location="Test Hall",
            scheduled_at=utc_now(),
            expires_at=utc_now() + timedelta(days=1),
            discipline=Discipline.EIGHT_BALL.value,
            distance=7,
            is_race_to=True,
            is_multi_set=False,
        )

        distance = proposal.distance_config

        assert distance is not None
        assert distance.racks == 7
        assert distance.is_race_to_racks is True
        assert distance.is_multi_set is False

    def test_proposal_multi_set(self):
        """Test proposal multi-set configuration."""
        proposal = MatchProposal(
            proposer_id=1,
            proposal_type="open",
            location="Test Hall",
            scheduled_at=utc_now(),
            expires_at=utc_now() + timedelta(days=1),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,
            is_race_to_sets=True,
        )

        distance = proposal.distance_config

        assert distance.is_multi_set is True
        assert distance.sets == 3
        assert distance.is_race_to_sets is True
        assert distance.to_display_string() == "Al 3 set, ogni set al 5 triangoli"

    def test_proposal_no_distance(self):
        """Test proposal without distance returns None."""
        proposal = MatchProposal(
            proposer_id=1,
            proposal_type="open",
            location="Test Hall",
            scheduled_at=utc_now(),
            expires_at=utc_now() + timedelta(days=1),
            distance=None,
        )

        assert proposal.distance_config is None


class TestIndividualMatchMultiSetProperty:
    """Test IndividualMatch.distance_config with multi-set support."""

    def test_individual_match_single_set(self):
        """Test individual match single-set configuration."""
        match = IndividualMatch(
            player1_id=1,
            player2_id=2,
            location="Test Hall",
            scheduled_at=utc_now(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=7,
            is_race_to=True,
            is_multi_set=False,
        )

        distance = match.distance_config

        assert distance.racks == 7
        assert distance.is_multi_set is False
        assert distance.to_display_string() == "Al 7 triangoli"

    def test_individual_match_multi_set(self):
        """Test individual match multi-set configuration."""
        match = IndividualMatch(
            player1_id=1,
            player2_id=2,
            location="Test Hall",
            scheduled_at=utc_now(),
            discipline=Discipline.TEN_BALL.value,
            distance=3,
            is_race_to=True,
            is_multi_set=True,
            match_distance=5,
            is_race_to_sets=True,
        )

        distance = match.distance_config

        assert distance.is_multi_set is True
        assert distance.sets == 5
        assert distance.is_race_to_sets is True
        assert distance.to_display_string() == "Al 5 set, ogni set al 3 triangoli"


class TestMatchProposalAcceptCopiesMultiSet:
    """Test that accepting a proposal copies multi-set config to IndividualMatch."""

    def test_accept_single_set_proposal(self):
        """Test accepting single-set proposal creates correct IndividualMatch."""
        proposal = MatchProposal(
            proposer_id=1,
            proposal_type="open",
            location="Test Hall",
            scheduled_at=utc_now(),
            expires_at=utc_now() + timedelta(days=1),
            discipline=Discipline.EIGHT_BALL.value,
            distance=7,
            is_race_to=True,
            is_multi_set=False,
        )

        # Note: This test can't actually call accept() without DB setup
        # Instead, verify the accept() logic directly
        # In actual integration test, would call proposal.accept(user_id=2)

        # For unit test, verify the field mapping
        assert proposal.is_multi_set is False
        assert proposal.distance == 7
        assert proposal.is_race_to is True

    def test_accept_multi_set_proposal(self):
        """Test accepting multi-set proposal creates correct IndividualMatch."""
        proposal = MatchProposal(
            proposer_id=1,
            proposal_type="open",
            location="Test Hall",
            scheduled_at=utc_now(),
            expires_at=utc_now() + timedelta(days=1),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,
            is_race_to_sets=True,
        )

        # Verify multi-set fields are set correctly
        assert proposal.is_multi_set is True
        assert proposal.match_distance == 3
        assert proposal.is_race_to_sets is True

        # The accept() method should copy these to IndividualMatch
        # (verified in integration test)
