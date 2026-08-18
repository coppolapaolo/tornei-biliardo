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

    def test_create_single_set_distance_race_to_7(self):
        """Create single-set race-to-7 distance."""
        distance = Distance(racks=7, is_race_to_racks=True, is_multi_set=False)

        assert distance.racks == 7
        assert distance.is_race_to_racks is True
        assert distance.is_multi_set is False
        assert distance.sets == 1
        assert distance.get_winning_racks() == 7
        assert distance.get_winning_sets() == 1

    def test_create_single_set_distance_race_to_5(self):
        """Create single-set race-to-5 distance."""
        distance = Distance(racks=5, is_race_to_racks=True)

        assert distance.racks == 5
        assert distance.get_winning_racks() == 5
        assert distance.is_multi_set is False

    def test_create_single_set_exact_4_racks(self):
        """Create single-set exactly-4 distance."""
        distance = Distance(racks=4, is_race_to_racks=False, is_multi_set=False)

        assert distance.racks == 4
        assert distance.is_race_to_racks is False
        assert distance.get_winning_racks() == 4  # Play all 4
        assert distance.is_multi_set is False

    def test_create_single_set_exact_3_racks(self):
        """Create single-set exactly-3 distance."""
        distance = Distance(racks=3, is_race_to_racks=False)

        assert distance.racks == 3
        assert distance.is_race_to_racks is False
        assert distance.get_winning_racks() == 3

    def test_create_multi_set_race_to_3_sets_race_to_5_racks(self):
        """Create multi-set: race-to-3 sets, each race-to-5 racks."""
        distance = Distance(
            racks=5,
            is_race_to_racks=True,
            is_multi_set=True,
            sets=3,
            is_race_to_sets=True,
        )

        assert distance.racks == 5
        assert distance.is_race_to_racks is True
        assert distance.is_multi_set is True
        assert distance.sets == 3
        assert distance.is_race_to_sets is True
        assert distance.get_winning_racks() == 5  # Per set
        assert distance.get_winning_sets() == 3  # For match

    def test_create_multi_set_race_to_5_sets_race_to_7_racks(self):
        """Create multi-set: race-to-5 sets, each race-to-7 racks."""
        distance = Distance(
            racks=7,
            is_race_to_racks=True,
            is_multi_set=True,
            sets=5,
            is_race_to_sets=True,
        )

        assert distance.get_winning_racks() == 7
        assert distance.get_winning_sets() == 5

    def test_create_multi_set_exact_4_sets_race_to_3_racks(self):
        """Create multi-set: exactly-4 sets, each race-to-3 racks."""
        distance = Distance(
            racks=3,
            is_race_to_racks=True,
            is_multi_set=True,
            sets=4,
            is_race_to_sets=False,
        )

        assert distance.racks == 3
        assert distance.sets == 4
        assert distance.is_race_to_racks is True
        assert distance.is_race_to_sets is False
        assert distance.get_winning_racks() == 3
        assert distance.get_winning_sets() == 4  # Play all 4 sets

    def test_create_multi_set_exact_2_sets_exact_3_racks(self):
        """Create multi-set: exactly-2 sets, each exactly-3 racks."""
        distance = Distance(
            racks=3,
            is_race_to_racks=False,
            is_multi_set=True,
            sets=2,
            is_race_to_sets=False,
        )

        assert distance.racks == 3
        assert distance.sets == 2
        assert distance.is_race_to_racks is False
        assert distance.is_race_to_sets is False
        assert distance.get_winning_racks() == 3
        assert distance.get_winning_sets() == 2

    def test_create_multi_set_race_to_3_sets_exact_2_racks(self):
        """Create multi-set: race-to-3 sets, each exactly-2 racks."""
        distance = Distance(
            racks=2,
            is_race_to_racks=False,
            is_multi_set=True,
            sets=3,
            is_race_to_sets=True,
        )

        assert distance.get_winning_racks() == 2
        assert distance.get_winning_sets() == 3


class TestDistanceValidation:
    """Test Distance validation rules."""

    def test_reject_zero_racks(self):
        """Reject distance with 0 racks."""
        with pytest.raises(ValueError, match="racks must be positive"):
            Distance(racks=0, is_race_to_racks=True)

    def test_reject_negative_racks(self):
        """Reject distance with negative racks."""
        with pytest.raises(ValueError, match="racks must be positive"):
            Distance(racks=-5, is_race_to_racks=True)

    def test_reject_zero_sets(self):
        """Reject distance with 0 sets."""
        with pytest.raises(ValueError, match="sets must be positive"):
            Distance(racks=5, is_multi_set=True, sets=0)

    # Note: Even numbers ARE allowed in Race-to
    def test_accept_even_race_to_racks(self):
        """Accept even number for race-to racks."""
        distance = Distance(racks=6, is_race_to_racks=True)
        assert distance.racks == 6
        assert distance.get_winning_racks() == 6

    def test_accept_even_race_to_sets(self):
        """Accept even number for race-to sets."""
        distance = Distance(racks=5, is_multi_set=True, sets=4, is_race_to_sets=True)
        assert distance.sets == 4
        assert distance.get_winning_sets() == 4

    def test_accept_even_exact_racks(self):
        """Accept even number for exact racks."""
        distance = Distance(racks=6, is_race_to_racks=False)
        assert distance.racks == 6
        assert distance.get_winning_racks() == 6

    def test_accept_even_exact_sets(self):
        """Accept even number for exact sets."""
        distance = Distance(racks=5, is_multi_set=True, sets=4, is_race_to_racks=False)
        assert distance.sets == 4
        assert distance.get_winning_sets() == 4

    def test_reject_single_set_with_sets_not_1(self):
        """Reject single-set distance with sets != 1."""
        with pytest.raises(ValueError, match="sets must be 1 for single-set"):
            Distance(racks=5, is_multi_set=False, sets=3)


class TestDistanceDisplayStrings:
    """Test human-readable display strings."""

    def test_display_single_set_race_to_7(self):
        """Display string for race-to-7 single-set."""
        distance = Distance(racks=7, is_race_to_racks=True)
        assert distance.to_display_string() == "Al 7 triangoli"

    def test_display_single_set_exact_4(self):
        """Display string for exactly-4 single-set."""
        distance = Distance(racks=4, is_race_to_racks=False)
        assert distance.to_display_string() == "Esattamente 4 triangoli"

    def test_display_multi_set_race_to_3_sets_race_to_5_racks(self):
        """Display: race-to-3 sets, each race-to-5 racks."""
        distance = Distance(
            racks=5,
            is_race_to_racks=True,
            is_multi_set=True,
            sets=3,
            is_race_to_sets=True,
        )
        expected = "Al 3 set, ogni set al 5 triangoli"
        assert distance.to_display_string() == expected

    def test_display_multi_set_exact_4_sets_race_to_3_racks(self):
        """Display: exactly-4 sets, each race-to-3 racks."""
        distance = Distance(
            racks=3,
            is_race_to_racks=True,
            is_multi_set=True,
            sets=4,
            is_race_to_sets=False,
        )
        expected = "Esattamente 4 set, ogni set al 3 triangoli"
        assert distance.to_display_string() == expected

    def test_display_multi_set_race_to_5_sets_exact_2_racks(self):
        """Display: race-to-5 sets, each exactly-2 racks."""
        distance = Distance(
            racks=2,
            is_race_to_racks=False,
            is_multi_set=True,
            sets=5,
            is_race_to_sets=True,
        )
        expected = "Al 5 set, ogni set esattamente 2 triangoli"
        assert distance.to_display_string() == expected

    def test_display_multi_set_exact_2_sets_exact_3_racks(self):
        """Display: exactly-2 sets, each exactly-3 racks."""
        distance = Distance(
            racks=3,
            is_race_to_racks=False,
            is_multi_set=True,
            sets=2,
            is_race_to_sets=False,
        )
        expected = "Esattamente 2 set, ogni set esattamente 3 triangoli"
        assert distance.to_display_string() == expected


class TestDistanceImmutability:
    """Test that Distance is immutable (frozen dataclass)."""

    def test_cannot_modify_racks(self):
        """Cannot modify racks after creation."""
        distance = Distance(racks=7, is_race_to_racks=True)
        with pytest.raises(AttributeError):
            distance.racks = 5  # type: ignore

    def test_cannot_modify_is_multi_set(self):
        """Cannot modify is_multi_set after creation."""
        distance = Distance(racks=5, is_multi_set=False)
        with pytest.raises(AttributeError):
            distance.is_multi_set = True  # type: ignore


class TestDistanceFactoryMethods:
    """Test factory methods for creating Distance from models."""

    def test_from_gara_race_to_7(self):
        """Create Distance from gara with race-to-7."""

        # Mock gara object
        class MockGara:
            distance = 7
            is_race_to = True

        gara = MockGara()
        distance = Distance.from_gara(gara)

        assert distance.racks == 7
        assert distance.is_race_to_racks is True
        assert distance.is_multi_set is False
        assert distance.get_winning_racks() == 7

    def test_from_gara_exact_4(self):
        """Create Distance from gara with exactly-4."""

        class MockGara:
            distance = 4
            is_race_to = False

        gara = MockGara()
        distance = Distance.from_gara(gara)

        assert distance.racks == 4
        assert distance.is_race_to_racks is False
        assert distance.get_winning_racks() == 4

    def test_from_match_single_set(self):
        """Create Distance from single-set match.

        Post-ADR-027: Distance.from_match legge match.effective_*. Il mock
        deve esporre quelle property (anche se costanti).
        """

        class MockGara:
            distance = 5
            is_race_to = True
            is_race_to_sets = True

        class MockMatch:
            is_multi_set = False
            match_distance = 5  # popolato da round-creation
            is_race_to = None  # NULL = eredita da gara
            is_race_to_sets = None
            gara = MockGara()
            # Property sintetiche che imitano Match.effective_*
            effective_distance = 5
            effective_is_race_to = True
            effective_is_race_to_sets = True

        match = MockMatch()
        distance = Distance.from_match(match)

        assert distance.racks == 5
        assert distance.is_multi_set is False
        assert distance.get_winning_racks() == 5

    def test_from_match_multi_set(self):
        """Create Distance from multi-set match (post-ADR-027)."""

        class MockGara:
            distance = 5
            is_race_to = True
            is_race_to_sets = True

        class MockMatch:
            is_multi_set = True
            match_distance = 3  # multi-set: numero di set per vincere
            is_race_to = None
            is_race_to_sets = None
            gara = MockGara()
            effective_distance = 5
            effective_is_race_to = True
            effective_is_race_to_sets = True

        match = MockMatch()
        distance = Distance.from_match(match)

        assert distance.racks == 5
        assert distance.is_multi_set is True
        assert distance.sets == 3
        assert distance.get_winning_racks() == 5
        assert distance.get_winning_sets() == 3

    def test_from_set_race_to_5(self):
        """Create Distance from Set with race-to-5."""

        class MockSet:
            distance = 5
            is_race_to = True

        set_obj = MockSet()
        distance = Distance.from_set(set_obj)

        assert distance.racks == 5
        assert distance.is_race_to_racks is True
        assert distance.is_multi_set is False
        assert distance.get_winning_racks() == 5
