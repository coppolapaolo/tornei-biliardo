"""Unit tests for RackScore and MatchScore Value Objects.

Tests cover:
1. RackScore: Rack counting within a set
2. MatchScore: Set counting in multi-set matches
3. Validation and edge cases
4. Winner determination
5. Display formatting
"""

import pytest
from models.match.distance import Distance
from models.match.score import RackScore, MatchScore


class TestRackScoreCreation:
    """Test RackScore object creation and validation."""

    def test_create_empty_rack_score_race_to_7(self):
        """Create empty rack score for race-to-7."""
        distance = Distance(racks=7, is_race_to_racks=True)
        score = RackScore(distance=distance)

        assert score.player1_racks == 0
        assert score.player2_racks == 0
        assert score.player3_racks is None
        assert not score.is_complete()

    def test_create_rack_score_with_initial_values(self):
        """Create rack score with initial values."""
        distance = Distance(racks=5, is_race_to_racks=True)
        score = RackScore(distance=distance, player1_racks=2, player2_racks=1)

        assert score.player1_racks == 2
        assert score.player2_racks == 1
        assert not score.is_complete()

    def test_create_trio_rack_score(self):
        """Create rack score for trio match."""
        distance = Distance(racks=3, is_race_to_racks=True)
        score = RackScore(
            distance=distance, player1_racks=1, player2_racks=1, player3_racks=0
        )

        assert score.player3_racks == 0
        assert not score.is_complete()

    def test_reject_negative_rack_count(self):
        """Reject negative rack counts."""
        distance = Distance(racks=5, is_race_to_racks=True)
        with pytest.raises(ValueError, match="cannot be negative"):
            RackScore(distance=distance, player1_racks=-1)

    def test_reject_multi_set_distance_in_rack_score(self):
        """Reject multi-set Distance for RackScore."""
        distance = Distance(racks=5, is_multi_set=True, sets=3, is_race_to_racks=True)
        with pytest.raises(ValueError, match="requires single-set Distance"):
            RackScore(distance=distance)


class TestRackScoreCompletion:
    """Test RackScore completion logic."""

    def test_race_to_7_complete_when_player_reaches_7(self):
        """Race-to-7: Complete when player reaches 7 racks."""
        distance = Distance(racks=7, is_race_to_racks=True)
        score = RackScore(distance=distance, player1_racks=7, player2_racks=2)

        assert score.is_complete()
        assert score.get_winner() == 1

    def test_race_to_5_incomplete_at_3_2(self):
        """Race-to-5: Incomplete at 3-2."""
        distance = Distance(racks=5, is_race_to_racks=True)
        score = RackScore(distance=distance, player1_racks=3, player2_racks=2)

        assert not score.is_complete()
        assert score.get_winner() is None

    def test_exact_4_complete_when_all_played(self):
        """Exact-4: Complete when 4 racks played."""
        distance = Distance(racks=4, is_race_to_racks=False)
        score = RackScore(distance=distance, player1_racks=3, player2_racks=1)

        assert score.is_complete()
        assert score.get_winner() == 1

    def test_exact_4_incomplete_at_3_total(self):
        """Exact-4: Incomplete with only 3 racks played."""
        distance = Distance(racks=4, is_race_to_racks=False)
        score = RackScore(distance=distance, player1_racks=2, player2_racks=1)

        assert not score.is_complete()

    def test_tie_in_exact_mode_returns_none(self):
        """Exact mode tie returns None winner."""
        distance = Distance(racks=4, is_race_to_racks=False)
        score = RackScore(distance=distance, player1_racks=2, player2_racks=2)

        assert score.is_complete()
        assert score.get_winner() is None


class TestRackScoreAddRackWin:
    """Test adding rack wins dynamically."""

    def test_add_rack_win_player_1(self):
        """Add rack win for player 1."""
        distance = Distance(racks=5, is_race_to_racks=True)
        score = RackScore(distance=distance)

        score.add_rack_win(1)
        score.add_rack_win(1)

        assert score.player1_racks == 2
        assert score.player2_racks == 0

    def test_add_rack_win_player_2(self):
        """Add rack win for player 2."""
        distance = Distance(racks=5, is_race_to_racks=True)
        score = RackScore(distance=distance)

        score.add_rack_win(2)

        assert score.player1_racks == 0
        assert score.player2_racks == 1

    def test_add_rack_win_alternating(self):
        """Add alternating rack wins."""
        distance = Distance(racks=5, is_race_to_racks=True)
        score = RackScore(distance=distance)

        score.add_rack_win(1)
        score.add_rack_win(2)
        score.add_rack_win(1)

        assert score.player1_racks == 2
        assert score.player2_racks == 1

    def test_reject_rack_win_when_complete(self):
        """Reject adding rack win when match complete."""
        distance = Distance(racks=5, is_race_to_racks=True)
        score = RackScore(distance=distance, player1_racks=5, player2_racks=1)

        with pytest.raises(ValueError, match="already complete"):
            score.add_rack_win(1)

    def test_trio_add_rack_win_player_3(self):
        """Add rack win for player 3 in trio."""
        distance = Distance(racks=3, is_race_to_racks=True)
        score = RackScore(
            distance=distance, player1_racks=0, player2_racks=0, player3_racks=0
        )

        score.add_rack_win(3)

        assert score.player3_racks == 1


class TestRackScoreDisplay:
    """Test RackScore display strings."""

    def test_display_two_player_score(self):
        """Display two-player score."""
        distance = Distance(racks=5, is_race_to_racks=True)
        score = RackScore(distance=distance, player1_racks=2, player2_racks=1)

        assert score.to_display_string() == "2-1"

    def test_display_trio_score(self):
        """Display trio score."""
        distance = Distance(racks=3, is_race_to_racks=True)
        score = RackScore(
            distance=distance, player1_racks=1, player2_racks=1, player3_racks=0
        )

        assert score.to_display_string() == "1-1-0"


class TestMatchScoreCreation:
    """Test MatchScore object creation and validation."""

    def test_create_empty_match_score_race_to_3(self):
        """Create empty match score for race-to-3 sets."""
        distance = Distance(racks=5, is_race_to_racks=True, is_multi_set=True, sets=3)
        score = MatchScore(distance=distance)

        assert score.player1_sets == 0
        assert score.player2_sets == 0
        assert not score.is_complete()

    def test_create_match_score_with_initial_values(self):
        """Create match score with initial set values."""
        distance = Distance(racks=5, is_race_to_racks=True, is_multi_set=True, sets=3)
        score = MatchScore(distance=distance, player1_sets=1, player2_sets=0)

        assert score.player1_sets == 1
        assert score.player2_sets == 0
        assert not score.is_complete()

    def test_reject_negative_set_count(self):
        """Reject negative set counts."""
        distance = Distance(racks=5, is_multi_set=True, sets=3)
        with pytest.raises(ValueError, match="cannot be negative"):
            MatchScore(distance=distance, player1_sets=-1)

    def test_reject_single_set_distance_in_match_score(self):
        """Reject single-set Distance for MatchScore."""
        distance = Distance(racks=7, is_race_to_racks=True, is_multi_set=False)
        with pytest.raises(ValueError, match="requires multi-set Distance"):
            MatchScore(distance=distance)


class TestMatchScoreCompletion:
    """Test MatchScore completion logic."""

    def test_race_to_3_complete_when_player_reaches_3(self):
        """Race-to-3 sets: Complete when player reaches 3 sets."""
        distance = Distance(racks=5, is_multi_set=True, sets=3, is_race_to_sets=True)
        score = MatchScore(distance=distance, player1_sets=3, player2_sets=0)

        assert score.is_complete()
        assert score.get_winner() == 1

    def test_race_to_5_incomplete_at_3_2(self):
        """Race-to-5 sets: Incomplete at 3-2."""
        distance = Distance(racks=5, is_multi_set=True, sets=5, is_race_to_sets=True)
        score = MatchScore(distance=distance, player1_sets=3, player2_sets=2)

        assert not score.is_complete()
        assert score.get_winner() is None

    def test_exact_4_sets_complete_when_all_played(self):
        """Exact-4 sets: Complete when 4 sets played."""
        distance = Distance(racks=3, is_multi_set=True, sets=4, is_race_to_sets=False)
        score = MatchScore(distance=distance, player1_sets=3, player2_sets=1)

        assert score.is_complete()
        assert score.get_winner() == 1

    def test_tie_in_exact_mode_returns_none(self):
        """Exact sets tie returns None winner."""
        distance = Distance(racks=3, is_multi_set=True, sets=4, is_race_to_sets=False)
        score = MatchScore(distance=distance, player1_sets=2, player2_sets=2)

        assert score.is_complete()
        assert score.get_winner() is None


class TestMatchScoreAddSetWin:
    """Test adding set wins dynamically."""

    def test_add_set_win_player_1(self):
        """Add set win for player 1."""
        distance = Distance(racks=5, is_multi_set=True, sets=3)
        score = MatchScore(distance=distance)

        score.add_set_win(1)

        assert score.player1_sets == 1
        assert score.player2_sets == 0

    def test_add_set_win_alternating(self):
        """Add alternating set wins."""
        distance = Distance(racks=5, is_multi_set=True, sets=3)
        score = MatchScore(distance=distance)

        score.add_set_win(1)
        score.add_set_win(2)
        score.add_set_win(1)

        assert score.player1_sets == 2
        assert score.player2_sets == 1

    def test_reject_set_win_when_complete(self):
        """Reject adding set win when match complete."""
        distance = Distance(racks=5, is_multi_set=True, sets=3, is_race_to_sets=True)
        score = MatchScore(distance=distance, player1_sets=3, player2_sets=0)

        with pytest.raises(ValueError, match="already complete"):
            score.add_set_win(1)

    def test_reject_invalid_player_number(self):
        """Reject invalid player number in multi-set."""
        distance = Distance(racks=5, is_multi_set=True, sets=3)
        score = MatchScore(distance=distance)

        with pytest.raises(ValueError, match="Invalid player number"):
            score.add_set_win(3)


class TestMatchScoreDisplay:
    """Test MatchScore display strings."""

    def test_display_match_score(self):
        """Display match score (sets)."""
        distance = Distance(racks=5, is_multi_set=True, sets=3)
        score = MatchScore(distance=distance, player1_sets=2, player2_sets=1)

        assert score.to_display_string() == "2-1"

    def test_display_zero_zero(self):
        """Display 0-0 score."""
        distance = Distance(racks=5, is_multi_set=True, sets=3)
        score = MatchScore(distance=distance)

        assert score.to_display_string() == "0-0"
