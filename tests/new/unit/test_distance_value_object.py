"""Unit tests for Distance Value Object.

Tests cover:
1. Single-set distance (best-of and exact)
2. Multi-set distance (all combinations)
3. Validation rules
4. Factory methods
5. Display strings
"""

import pytest
from models.match.distance import Distance


class TestDistanceCreation:
    """Test Distance object creation and validation."""

    def test_create_single_set_distance_best_of_7(self):
        """Create single-set best-of-7 distance."""
        distance = Distance(racks=7, racks_best_of=True, is_multi_set=False)

        assert distance.racks == 7
        assert distance.racks_best_of is True
        assert distance.is_multi_set is False
        assert distance.sets == 1
        assert distance.get_winning_racks() == 4
        assert distance.get_winning_sets() == 1

    def test_create_single_set_distance_best_of_5(self):
        """Create single-set best-of-5 distance."""
        distance = Distance(racks=5, racks_best_of=True)

        assert distance.racks == 5
        assert distance.get_winning_racks() == 3
        assert distance.is_multi_set is False

    def test_create_single_set_exact_4_racks(self):
        """Create single-set exactly-4 distance."""
        distance = Distance(racks=4, racks_best_of=False, is_multi_set=False)

        assert distance.racks == 4
        assert distance.racks_best_of is False
        assert distance.get_winning_racks() == 4  # Play all 4
        assert distance.is_multi_set is False

    def test_create_single_set_exact_3_racks(self):
        """Create single-set exactly-3 distance."""
        distance = Distance(racks=3, racks_best_of=False)

        assert distance.racks == 3
        assert distance.racks_best_of is False
        assert distance.get_winning_racks() == 3

    def test_create_multi_set_best_of_3_sets_best_of_5_racks(self):
        """Create multi-set: best-of-3 sets, each best-of-5 racks."""
        distance = Distance(
            racks=5,
            racks_best_of=True,
            is_multi_set=True,
            sets=3,
            sets_best_of=True
        )

        assert distance.racks == 5
        assert distance.racks_best_of is True
        assert distance.is_multi_set is True
        assert distance.sets == 3
        assert distance.sets_best_of is True
        assert distance.get_winning_racks() == 3  # Per set
        assert distance.get_winning_sets() == 2  # For match

    def test_create_multi_set_best_of_5_sets_best_of_7_racks(self):
        """Create multi-set: best-of-5 sets, each best-of-7 racks."""
        distance = Distance(
            racks=7,
            racks_best_of=True,
            is_multi_set=True,
            sets=5,
            sets_best_of=True
        )

        assert distance.get_winning_racks() == 4
        assert distance.get_winning_sets() == 3

    def test_create_multi_set_exact_4_sets_best_of_3_racks(self):
        """Create multi-set: exactly-4 sets, each best-of-3 racks."""
        distance = Distance(
            racks=3,
            racks_best_of=True,
            is_multi_set=True,
            sets=4,
            sets_best_of=False
        )

        assert distance.racks == 3
        assert distance.sets == 4
        assert distance.racks_best_of is True
        assert distance.sets_best_of is False
        assert distance.get_winning_racks() == 2
        assert distance.get_winning_sets() == 4  # Play all 4 sets

    def test_create_multi_set_exact_2_sets_exact_3_racks(self):
        """Create multi-set: exactly-2 sets, each exactly-3 racks."""
        distance = Distance(
            racks=3,
            racks_best_of=False,
            is_multi_set=True,
            sets=2,
            sets_best_of=False
        )

        assert distance.racks == 3
        assert distance.sets == 2
        assert distance.racks_best_of is False
        assert distance.sets_best_of is False
        assert distance.get_winning_racks() == 3
        assert distance.get_winning_sets() == 2

    def test_create_multi_set_best_of_3_sets_exact_2_racks(self):
        """Create multi-set: best-of-3 sets, each exactly-2 racks."""
        distance = Distance(
            racks=2,
            racks_best_of=False,
            is_multi_set=True,
            sets=3,
            sets_best_of=True
        )

        assert distance.get_winning_racks() == 2
        assert distance.get_winning_sets() == 2


class TestDistanceValidation:
    """Test Distance validation rules."""

    def test_reject_zero_racks(self):
        """Reject distance with 0 racks."""
        with pytest.raises(ValueError, match="racks must be positive"):
            Distance(racks=0, racks_best_of=True)

    def test_reject_negative_racks(self):
        """Reject distance with negative racks."""
        with pytest.raises(ValueError, match="racks must be positive"):
            Distance(racks=-5, racks_best_of=True)

    def test_reject_zero_sets(self):
        """Reject distance with 0 sets."""
        with pytest.raises(ValueError, match="sets must be positive"):
            Distance(racks=5, is_multi_set=True, sets=0)

    def test_reject_even_best_of_racks(self):
        """Reject even number for best-of racks."""
        with pytest.raises(ValueError, match="best_of racks must be odd"):
            Distance(racks=6, racks_best_of=True)

    def test_reject_even_best_of_sets(self):
        """Reject even number for best-of sets."""
        with pytest.raises(ValueError, match="best_of sets must be odd"):
            Distance(racks=5, is_multi_set=True, sets=4, sets_best_of=True)

    def test_accept_even_exact_racks(self):
        """Accept even number for exact racks."""
        distance = Distance(racks=6, racks_best_of=False)
        assert distance.racks == 6
        assert distance.get_winning_racks() == 6

    def test_accept_even_exact_sets(self):
        """Accept even number for exact sets."""
        distance = Distance(
            racks=5,
            is_multi_set=True,
            sets=4,
            sets_best_of=False
        )
        assert distance.sets == 4
        assert distance.get_winning_sets() == 4

    def test_reject_single_set_with_sets_not_1(self):
        """Reject single-set distance with sets != 1."""
        with pytest.raises(ValueError, match="sets must be 1 for single-set"):
            Distance(racks=5, is_multi_set=False, sets=3)


class TestDistanceDisplayStrings:
    """Test human-readable display strings."""

    def test_display_single_set_best_of_7(self):
        """Display string for best-of-7 single-set."""
        distance = Distance(racks=7, racks_best_of=True)
        assert distance.to_display_string() == "Best of 7 racks"

    def test_display_single_set_exact_4(self):
        """Display string for exactly-4 single-set."""
        distance = Distance(racks=4, racks_best_of=False)
        assert distance.to_display_string() == "Exactly 4 racks"

    def test_display_multi_set_best_of_3_sets_best_of_5_racks(self):
        """Display: best-of-3 sets, each best-of-5 racks."""
        distance = Distance(
            racks=5,
            racks_best_of=True,
            is_multi_set=True,
            sets=3,
            sets_best_of=True
        )
        expected = "Best of 3 sets, each set best of 5 racks"
        assert distance.to_display_string() == expected

    def test_display_multi_set_exact_4_sets_best_of_3_racks(self):
        """Display: exactly-4 sets, each best-of-3 racks."""
        distance = Distance(
            racks=3,
            racks_best_of=True,
            is_multi_set=True,
            sets=4,
            sets_best_of=False
        )
        expected = "Exactly 4 sets, each set best of 3 racks"
        assert distance.to_display_string() == expected

    def test_display_multi_set_best_of_5_sets_exact_2_racks(self):
        """Display: best-of-5 sets, each exactly-2 racks."""
        distance = Distance(
            racks=2,
            racks_best_of=False,
            is_multi_set=True,
            sets=5,
            sets_best_of=True
        )
        expected = "Best of 5 sets, each set exactly 2 racks"
        assert distance.to_display_string() == expected

    def test_display_multi_set_exact_2_sets_exact_3_racks(self):
        """Display: exactly-2 sets, each exactly-3 racks."""
        distance = Distance(
            racks=3,
            racks_best_of=False,
            is_multi_set=True,
            sets=2,
            sets_best_of=False
        )
        expected = "Exactly 2 sets, each set exactly 3 racks"
        assert distance.to_display_string() == expected


class TestDistanceImmutability:
    """Test that Distance is immutable (frozen dataclass)."""

    def test_cannot_modify_racks(self):
        """Cannot modify racks after creation."""
        distance = Distance(racks=7, racks_best_of=True)
        with pytest.raises(AttributeError):
            distance.racks = 5  # type: ignore

    def test_cannot_modify_is_multi_set(self):
        """Cannot modify is_multi_set after creation."""
        distance = Distance(racks=5, is_multi_set=False)
        with pytest.raises(AttributeError):
            distance.is_multi_set = True  # type: ignore


class TestDistanceFactoryMethods:
    """Test factory methods for creating Distance from models."""

    def test_from_gara_best_of_7(self):
        """Create Distance from gara with best-of-7."""
        # Mock gara object
        class MockGara:
            distance = 7
            best_of = True

        gara = MockGara()
        distance = Distance.from_gara(gara)

        assert distance.racks == 7
        assert distance.racks_best_of is True
        assert distance.is_multi_set is False
        assert distance.get_winning_racks() == 4

    def test_from_gara_exact_4(self):
        """Create Distance from gara with exactly-4."""
        class MockGara:
            distance = 4
            best_of = False

        gara = MockGara()
        distance = Distance.from_gara(gara)

        assert distance.racks == 4
        assert distance.racks_best_of is False
        assert distance.get_winning_racks() == 4

    def test_from_match_single_set(self):
        """Create Distance from single-set match."""
        class MockGara:
            distance = 5
            best_of = True

        class MockMatch:
            is_multi_set = False
            gara = MockGara()

        match = MockMatch()
        distance = Distance.from_match(match)

        assert distance.racks == 5
        assert distance.is_multi_set is False
        assert distance.get_winning_racks() == 3

    def test_from_match_multi_set(self):
        """Create Distance from multi-set match."""
        class MockGara:
            distance = 5
            best_of = True

        class MockMatch:
            is_multi_set = True
            match_distance = 3
            gara = MockGara()

        match = MockMatch()
        distance = Distance.from_match(match)

        assert distance.racks == 5
        assert distance.is_multi_set is True
        assert distance.sets == 3
        assert distance.get_winning_racks() == 3
        assert distance.get_winning_sets() == 2

    def test_from_set_best_of_5(self):
        """Create Distance from Set with best-of-5."""
        class MockSet:
            distance = 5
            best_of = True

        set_obj = MockSet()
        distance = Distance.from_set(set_obj)

        assert distance.racks == 5
        assert distance.racks_best_of is True
        assert distance.is_multi_set is False
        assert distance.get_winning_racks() == 3
