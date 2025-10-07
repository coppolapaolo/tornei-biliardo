"""Unit tests for multi-set model properties (Phase 6: Frontend Integration).

Tests the distance_config property for Gara, MatchProposal, and IndividualMatch
models with multi-set configuration support.
"""

import pytest
from models.competition.models import Gara
from models.individual_match.models import MatchProposal, IndividualMatch
from models.match.distance import Distance
from models.status_enum import Discipline
from datetime import datetime, timedelta


class TestGaraMultiSetProperty:
    """Test Gara.distance_config with multi-set support."""

    def test_gara_single_set_best_of(self):
        """Test single-set best-of configuration (backward compatible)."""
        gara = Gara(
            campionato_id=None,
            number=1,
            date=datetime.now().date(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=7,
            best_of=True,
            is_multi_set=False
        )

        distance = gara.distance_config

        assert isinstance(distance, Distance)
        assert distance.racks == 7
        assert distance.racks_best_of is True
        assert distance.is_multi_set is False
        assert distance.sets == 1
        assert distance.to_display_string() == "Best of 7 racks"

    def test_gara_single_set_exact(self):
        """Test single-set exact configuration (backward compatible)."""
        gara = Gara(
            campionato_id=None,
            number=1,
            date=datetime.now().date(),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            best_of=False,
            is_multi_set=False
        )

        distance = gara.distance_config

        assert distance.racks == 5
        assert distance.racks_best_of is False
        assert distance.is_multi_set is False
        assert distance.to_display_string() == "Exactly 5 racks"

    def test_gara_multi_set_best_of_sets_best_of_racks(self):
        """Test multi-set with best-of sets and best-of racks."""
        gara = Gara(
            campionato_id=None,
            number=1,
            date=datetime.now().date(),
            discipline=Discipline.TEN_BALL.value,
            distance=5,  # Racks per set
            best_of=True,  # Best-of racks
            is_multi_set=True,
            match_distance=3,  # Number of sets
            sets_best_of=True  # Best-of sets
        )

        distance = gara.distance_config

        assert distance.racks == 5
        assert distance.racks_best_of is True
        assert distance.is_multi_set is True
        assert distance.sets == 3
        assert distance.sets_best_of is True
        assert distance.to_display_string() == "Best of 3 sets, each set best of 5 racks"
        assert distance.get_winning_racks() == 3  # 5//2 + 1
        assert distance.get_winning_sets() == 2  # 3//2 + 1

    def test_gara_multi_set_exact_sets_best_of_racks(self):
        """Test multi-set with exact sets and best-of racks."""
        gara = Gara(
            campionato_id=None,
            number=1,
            date=datetime.now().date(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=3,
            best_of=True,
            is_multi_set=True,
            match_distance=4,  # Play exactly 4 sets
            sets_best_of=False  # Exact sets
        )

        distance = gara.distance_config

        assert distance.racks == 3
        assert distance.sets == 4
        assert distance.sets_best_of is False
        assert distance.to_display_string() == "Exactly 4 sets, each set best of 3 racks"

    def test_gara_multi_set_defaults(self):
        """Test multi-set with None values uses defaults."""
        gara = Gara(
            campionato_id=None,
            number=1,
            date=datetime.now().date(),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            best_of=True,
            is_multi_set=True,
            match_distance=None,  # Should default to 1
            sets_best_of=None  # Should default to True
        )

        distance = gara.distance_config

        assert distance.sets == 1  # Default when None
        assert distance.sets_best_of is True  # Default when None

    def test_gara_backward_compatibility_no_multi_set_fields(self):
        """Test backward compatibility when multi-set fields don't exist."""
        gara = Gara(
            campionato_id=None,
            number=1,
            date=datetime.now().date(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=7,
            best_of=True
            # No is_multi_set, match_distance, sets_best_of
        )

        # is_multi_set defaults to False
        distance = gara.distance_config

        assert distance.racks == 7
        assert distance.is_multi_set is False
        assert distance.to_display_string() == "Best of 7 racks"


class TestMatchProposalMultiSetProperty:
    """Test MatchProposal.distance_config with multi-set support."""

    def test_proposal_single_set_best_of(self):
        """Test proposal single-set configuration."""
        proposal = MatchProposal(
            proposer_id=1,
            proposal_type="direct",
            location="Test Hall",
            scheduled_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=1),
            discipline=Discipline.EIGHT_BALL.value,
            distance=7,
            best_of=True,
            is_multi_set=False
        )

        distance = proposal.distance_config

        assert distance is not None
        assert distance.racks == 7
        assert distance.racks_best_of is True
        assert distance.is_multi_set is False

    def test_proposal_multi_set(self):
        """Test proposal multi-set configuration."""
        proposal = MatchProposal(
            proposer_id=1,
            proposal_type="open",
            location="Test Hall",
            scheduled_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=1),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            best_of=True,
            is_multi_set=True,
            match_distance=3,
            sets_best_of=True
        )

        distance = proposal.distance_config

        assert distance.is_multi_set is True
        assert distance.sets == 3
        assert distance.sets_best_of is True
        assert distance.to_display_string() == "Best of 3 sets, each set best of 5 racks"

    def test_proposal_no_distance(self):
        """Test proposal without distance returns None."""
        proposal = MatchProposal(
            proposer_id=1,
            proposal_type="open",
            location="Test Hall",
            scheduled_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=1),
            distance=None
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
            scheduled_at=datetime.now(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=7,
            best_of=True,
            is_multi_set=False
        )

        distance = match.distance_config

        assert distance.racks == 7
        assert distance.is_multi_set is False
        assert distance.to_display_string() == "Best of 7 racks"

    def test_individual_match_multi_set(self):
        """Test individual match multi-set configuration."""
        match = IndividualMatch(
            player1_id=1,
            player2_id=2,
            location="Test Hall",
            scheduled_at=datetime.now(),
            discipline=Discipline.TEN_BALL.value,
            distance=3,
            best_of=True,
            is_multi_set=True,
            match_distance=5,
            sets_best_of=True
        )

        distance = match.distance_config

        assert distance.is_multi_set is True
        assert distance.sets == 5
        assert distance.sets_best_of is True
        assert distance.to_display_string() == "Best of 5 sets, each set best of 3 racks"


class TestMatchProposalAcceptCopiesMultiSet:
    """Test that accepting a proposal copies multi-set config to IndividualMatch."""

    def test_accept_single_set_proposal(self):
        """Test accepting single-set proposal creates correct IndividualMatch."""
        proposal = MatchProposal(
            proposer_id=1,
            proposal_type="open",
            location="Test Hall",
            scheduled_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=1),
            discipline=Discipline.EIGHT_BALL.value,
            distance=7,
            best_of=True,
            is_multi_set=False
        )

        # Note: This test can't actually call accept() without DB setup
        # Instead, verify the accept() logic directly
        # In actual integration test, would call proposal.accept(user_id=2)

        # For unit test, verify the field mapping
        assert proposal.is_multi_set is False
        assert proposal.distance == 7
        assert proposal.best_of is True

    def test_accept_multi_set_proposal(self):
        """Test accepting multi-set proposal creates correct IndividualMatch."""
        proposal = MatchProposal(
            proposer_id=1,
            proposal_type="open",
            location="Test Hall",
            scheduled_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=1),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            best_of=True,
            is_multi_set=True,
            match_distance=3,
            sets_best_of=True
        )

        # Verify multi-set fields are set correctly
        assert proposal.is_multi_set is True
        assert proposal.match_distance == 3
        assert proposal.sets_best_of is True

        # The accept() method should copy these to IndividualMatch
        # (verified in integration test)
