"""Unit tests for Jinja template filters.

Tests the Distance/Score formatting filters for template usage.
"""

import pytest
from utils.jinja import format_distance, format_score, format_distance_short
from models.match.distance import Distance
from models.match.score import RackScore, MatchScore


class TestFormatDistanceFilter:
    """Test format_distance Jinja filter."""

    def test_format_distance_single_set_best_of_7(self):
        """Format best-of-7 single-set distance."""
        distance = Distance(racks=7, racks_best_of=True)
        result = format_distance(distance)
        assert str(result) == "Best of 7 racks"

    def test_format_distance_single_set_exact_4(self):
        """Format exactly-4 single-set distance."""
        distance = Distance(racks=4, racks_best_of=False)
        result = format_distance(distance)
        assert str(result) == "Exactly 4 racks"

    def test_format_distance_multi_set(self):
        """Format multi-set distance."""
        distance = Distance(
            racks=5,
            racks_best_of=True,
            is_multi_set=True,
            sets=3,
            sets_best_of=True
        )
        result = format_distance(distance)
        expected = "Best of 3 sets, each set best of 5 racks"
        assert str(result) == expected

    def test_format_distance_with_model_property(self):
        """Format distance from model with distance_config property."""
        # Mock model with distance_config
        class MockGara:
            @property
            def distance_config(self):
                return Distance(racks=7, racks_best_of=True)

        gara = MockGara()
        result = format_distance(gara)
        assert str(result) == "Best of 7 racks"

    def test_format_distance_none_returns_na(self):
        """Format None distance returns N/A."""
        result = format_distance(None)
        assert str(result) == "N/A"

    def test_format_distance_escapes_html(self):
        """Verify HTML escaping in output."""
        from markupsafe import Markup
        distance = Distance(racks=7, racks_best_of=True)
        result = format_distance(distance)
        assert isinstance(result, Markup)


class TestFormatScoreFilter:
    """Test format_score Jinja filter."""

    def test_format_score_rack_score_two_player(self):
        """Format two-player rack score."""
        distance = Distance(racks=7, racks_best_of=True)
        score = RackScore(
            distance=distance,
            player1_racks=4,
            player2_racks=2
        )
        result = format_score(score)
        assert str(result) == "4-2"

    def test_format_score_rack_score_trio(self):
        """Format trio rack score."""
        distance = Distance(racks=5, racks_best_of=True)
        score = RackScore(
            distance=distance,
            player1_racks=2,
            player2_racks=2,
            player3_racks=1
        )
        result = format_score(score)
        assert str(result) == "2-2-1"

    def test_format_score_match_score(self):
        """Format match score (sets)."""
        distance = Distance(
            racks=5,
            is_multi_set=True,
            sets=3,
            racks_best_of=True
        )
        score = MatchScore(
            distance=distance,
            player1_sets=2,
            player2_sets=1
        )
        result = format_score(score)
        assert str(result) == "2-1"

    def test_format_score_with_model_property(self):
        """Format score from model with rack_score property."""
        # Mock model
        class MockMatch:
            @property
            def rack_score(self):
                distance = Distance(racks=7, racks_best_of=True)
                return RackScore(
                    distance=distance,
                    player1_racks=3,
                    player2_racks=2
                )

        match = MockMatch()
        result = format_score(match)
        assert str(result) == "3-2"

    def test_format_score_none_returns_zero_zero(self):
        """Format None score returns 0-0."""
        result = format_score(None)
        assert str(result) == "0-0"

    def test_format_score_escapes_html(self):
        """Verify HTML escaping in output."""
        from markupsafe import Markup
        distance = Distance(racks=7, racks_best_of=True)
        score = RackScore(distance=distance, player1_racks=4, player2_racks=2)
        result = format_score(score)
        assert isinstance(result, Markup)


class TestFormatDistanceShortFilter:
    """Test format_distance_short Jinja filter."""

    def test_format_distance_short_best_of_7(self):
        """Format best-of-7 as BO7."""
        distance = Distance(racks=7, racks_best_of=True)
        result = format_distance_short(distance)
        assert str(result) == "BO7"

    def test_format_distance_short_exact_4(self):
        """Format exactly-4 as X4."""
        distance = Distance(racks=4, racks_best_of=False)
        result = format_distance_short(distance)
        assert str(result) == "X4"

    def test_format_distance_short_with_model(self):
        """Format short distance from model."""
        class MockGara:
            @property
            def distance_config(self):
                return Distance(racks=5, racks_best_of=True)

        gara = MockGara()
        result = format_distance_short(gara)
        assert str(result) == "BO5"

    def test_format_distance_short_none_returns_na(self):
        """Format None distance short returns N/A."""
        result = format_distance_short(None)
        assert str(result) == "N/A"

    def test_format_distance_short_escapes_html(self):
        """Verify HTML escaping in output."""
        from markupsafe import Markup
        distance = Distance(racks=7, racks_best_of=True)
        result = format_distance_short(distance)
        assert isinstance(result, Markup)


class TestFiltersIntegration:
    """Test filters work together in realistic scenarios."""

    def test_single_set_match_complete_flow(self):
        """Test complete flow for single-set match display."""
        distance = Distance(racks=7, racks_best_of=True)
        score = RackScore(
            distance=distance,
            player1_racks=4,
            player2_racks=3
        )

        # Format both
        dist_str = format_distance(distance)
        score_str = format_score(score)
        short_str = format_distance_short(distance)

        assert str(dist_str) == "Best of 7 racks"
        assert str(score_str) == "4-3"
        assert str(short_str) == "BO7"

    def test_multi_set_match_complete_flow(self):
        """Test complete flow for multi-set match display."""
        distance = Distance(
            racks=5,
            racks_best_of=True,
            is_multi_set=True,
            sets=3,
            sets_best_of=True
        )
        match_score = MatchScore(
            distance=distance,
            player1_sets=2,
            player2_sets=0
        )

        dist_str = format_distance(distance)
        score_str = format_score(match_score)

        assert "Best of 3 sets" in str(dist_str)
        assert "best of 5 racks" in str(dist_str)
        assert str(score_str) == "2-0"
