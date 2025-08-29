"""
Test module for models/scoring/strategies.py
"""

import pytest
from unittest.mock import Mock
from models.scoring.strategies import (
    ClassicScoringPolicy,
    FargoRatingScoringPolicy,
    EloRatingScoringPolicy,
)
from models.user.models import User


class TestClassicScoringPolicy:
    """Test cases for ClassicScoringPolicy class."""

    def test_calculate_standings_with_wins(self):
        """Test calculate_standings method with wins."""
        policy = ClassicScoringPolicy()

        # Create mock players
        player1 = Mock(spec=User)
        player1.id = 1
        player2 = Mock(spec=User)
        player2.id = 2
        players = [player1, player2]

        # Create mock match results
        match_results = [
            {"player1_id": 1, "player2_id": 2, "player1_score": 3, "player2_score": 1}
        ]

        result = policy.calculate_standings(players, match_results)

        # Player 1 should be first (more wins)
        assert len(result) == 2
        assert result[0][0].id == 1
        assert result[1][0].id == 2

    def test_calculate_standings_with_rack_difference(self):
        """Test calculate_standings method with rack difference."""
        policy = ClassicScoringPolicy()

        # Create mock players
        player1 = Mock(spec=User)
        player1.id = 1
        player2 = Mock(spec=User)
        player2.id = 2
        players = [player1, player2]

        # Create mock match results with equal wins but different rack differences
        match_results = [
            {"player1_id": 1, "player2_id": 2, "player1_score": 2, "player2_score": 1},
            {"player1_id": 2, "player2_id": 1, "player1_score": 2, "player2_score": 0},
        ]

        result = policy.calculate_standings(players, match_results)

        # Both players have 1 win, but player 2 has better rack difference (+1 vs -1)
        assert len(result) == 2
        assert result[0][0].id == 2
        assert result[1][0].id == 1

    def test_calculate_standings_with_tie_breaker(self):
        """Test calculate_standings method with tie breaker (previous order)."""
        policy = ClassicScoringPolicy()

        # Create mock players
        player1 = Mock(spec=User)
        player1.id = 1
        player2 = Mock(spec=User)
        player2.id = 2
        players = [player1, player2]

        # Create mock match results with equal wins and rack differences
        match_results = []

        result = policy.calculate_standings(players, match_results)

        # Players are tied, so previous order should be used (player 1 first)
        assert len(result) == 2
        assert result[0][0].id == 1
        assert result[1][0].id == 2

    def test_get_ranking_criteria(self):
        """Test get_ranking_criteria method."""
        policy = ClassicScoringPolicy()

        result = policy.get_ranking_criteria()

        # Should return the correct ranking criteria
        assert result == ["wins", "rack_difference", "previous_order"]


class TestFargoRatingScoringPolicy:
    """Test cases for FargoRatingScoringPolicy class."""

    def test_calculate_standings_with_ratings(self):
        """Test calculate_standings method with Fargo ratings."""
        policy = FargoRatingScoringPolicy()

        # Create mock players with Fargo ratings
        player1 = Mock(spec=User)
        player1.id = 1
        player1.fargo_rating = 800
        player2 = Mock(spec=User)
        player2.id = 2
        player2.fargo_rating = 700
        players = [player1, player2]

        # Create mock match results
        match_results = [
            {"player1_id": 1, "player2_id": 2, "player1_score": 1, "player2_score": 2}
        ]

        result = policy.calculate_standings(players, match_results)

        # Player 1 should be first (higher Fargo rating)
        assert len(result) == 2
        assert result[0][0].id == 1
        assert result[1][0].id == 2

    def test_calculate_standings_without_ratings(self):
        """Test calculate_standings method without Fargo ratings."""
        policy = FargoRatingScoringPolicy()

        # Create mock players without Fargo ratings
        player1 = Mock(spec=User)
        player1.id = 1
        delattr(player1, "fargo_rating")
        player2 = Mock(spec=User)
        player2.id = 2
        delattr(player2, "fargo_rating")
        players = [player1, player2]

        # Create mock match results
        match_results = [
            {"player1_id": 1, "player2_id": 2, "player1_score": 3, "player2_score": 1}
        ]

        result = policy.calculate_standings(players, match_results)

        # Player 1 should be first (more wins)
        assert len(result) == 2
        assert result[0][0].id == 1
        assert result[1][0].id == 2

    def test_get_ranking_criteria(self):
        """Test get_ranking_criteria method."""
        policy = FargoRatingScoringPolicy()

        result = policy.get_ranking_criteria()

        # Should return the correct ranking criteria
        assert result == ["fargo_rating", "wins", "rack_difference"]


class TestEloRatingScoringPolicy:
    """Test cases for EloRatingScoringPolicy class."""

    def test_calculate_standings_with_ratings(self):
        """Test calculate_standings method with Elo ratings."""
        policy = EloRatingScoringPolicy()

        # Create mock players with Elo ratings
        player1 = Mock(spec=User)
        player1.id = 1
        player1.elo_rating = 1500
        player2 = Mock(spec=User)
        player2.id = 2
        player2.elo_rating = 1400
        players = [player1, player2]

        # Create mock match results
        match_results = [
            {"player1_id": 1, "player2_id": 2, "player1_score": 1, "player2_score": 2}
        ]

        result = policy.calculate_standings(players, match_results)

        # Player 1 should be first (higher Elo rating)
        assert len(result) == 2
        assert result[0][0].id == 1
        assert result[1][0].id == 2

    def test_calculate_standings_without_ratings(self):
        """Test calculate_standings method without Elo ratings."""
        policy = EloRatingScoringPolicy()

        # Create mock players without Elo ratings
        player1 = Mock(spec=User)
        player1.id = 1
        delattr(player1, "elo_rating")
        player2 = Mock(spec=User)
        player2.id = 2
        delattr(player2, "elo_rating")
        players = [player1, player2]

        # Create mock match results
        match_results = [
            {"player1_id": 1, "player2_id": 2, "player1_score": 3, "player2_score": 1}
        ]

        result = policy.calculate_standings(players, match_results)

        # Player 1 should be first (more wins)
        assert len(result) == 2
        assert result[0][0].id == 1
        assert result[1][0].id == 2

    def test_get_ranking_criteria(self):
        """Test get_ranking_criteria method."""
        policy = EloRatingScoringPolicy()

        result = policy.get_ranking_criteria()

        # Should return the correct ranking criteria
        assert result == ["elo_rating", "wins", "rack_difference"]


if __name__ == "__main__":
    pytest.main([__file__])
