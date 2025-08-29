"""
Comprehensive tests for models/scoring/strategies.py
Testing all scoring policy implementations to achieve full coverage.
"""

import pytest
from unittest.mock import Mock, patch
from models.scoring.strategies import (
    ClassicScoringPolicy,
    FargoRatingScoringPolicy,
    EloRatingScoringPolicy
)
from models.user.models import User


class TestClassicScoringPolicy:
    """Test ClassicScoringPolicy implementation."""

    @pytest.fixture
    def policy(self):
        """Create a ClassicScoringPolicy instance."""
        return ClassicScoringPolicy()

    @pytest.fixture
    def mock_players(self):
        """Create mock players for testing."""
        players = []
        for i in range(3):
            player = Mock(spec=User)
            player.id = i + 1
            player.username = f"player{i+1}"
            players.append(player)
        return players

    def test_classic_policy_initialization(self, policy):
        """Test ClassicScoringPolicy initialization."""
        assert isinstance(policy, ClassicScoringPolicy)
        assert hasattr(policy, 'calculate_standings')
        assert hasattr(policy, 'get_ranking_criteria')

    def test_get_ranking_criteria(self, policy):
        """Test get_ranking_criteria method."""
        criteria = policy.get_ranking_criteria()
        
        assert isinstance(criteria, list)
        assert "wins" in criteria
        assert "rack_difference" in criteria
        assert "previous_order" in criteria
        assert len(criteria) == 3

    def test_calculate_standings_no_matches(self, policy, mock_players):
        """Test calculate_standings with no matches."""
        match_results = []
        
        standings = policy.calculate_standings(mock_players, match_results)
        
        assert len(standings) == 3
        assert isinstance(standings, list)
        # All players should have 0 wins and 0 rack diff
        for player, stats in standings:
            assert stats["wins"] == 0
            assert stats["rack_diff"] == 0
            assert "previous_order" in stats

    def test_calculate_standings_with_wins(self, policy, mock_players):
        """Test calculate_standings with match results."""
        match_results = [
            {
                "player1_id": 1,
                "player2_id": 2,
                "player1_score": 5,
                "player2_score": 3
            },
            {
                "player1_id": 2,
                "player2_id": 3,
                "player1_score": 4,
                "player2_score": 6
            }
        ]
        
        standings = policy.calculate_standings(mock_players, match_results)
        
        assert len(standings) == 3
        
        # Check that standings are sorted by wins, then rack diff
        winner_found = False
        for player, stats in standings:
            if stats["wins"] > 0:
                winner_found = True
                assert stats["wins"] in [1, 2]  # Should have at least 1 win
                
        assert winner_found

    def test_calculate_standings_tie_breaking(self, policy, mock_players):
        """Test tie-breaking by rack difference."""
        match_results = [
            {
                "player1_id": 1,
                "player2_id": 2,
                "player1_score": 5,
                "player2_score": 3  # Player 1 wins by 2
            },
            {
                "player1_id": 3,
                "player2_id": 1,
                "player1_score": 6,
                "player2_score": 2  # Player 3 wins by 4
            }
        ]
        
        standings = policy.calculate_standings(mock_players, match_results)
        
        # Both player 1 and 3 have 1 win, but player 3 should rank higher due to better rack diff
        player_1_stats = next(stats for player, stats in standings if player.id == 1)
        player_3_stats = next(stats for player, stats in standings if player.id == 3)
        
        assert player_1_stats["wins"] == 1
        assert player_3_stats["wins"] == 1
        assert player_3_stats["rack_diff"] > player_1_stats["rack_diff"]

    def test_calculate_standings_draws(self, policy, mock_players):
        """Test handling of draw matches."""
        match_results = [
            {
                "player1_id": 1,
                "player2_id": 2,
                "player1_score": 5,
                "player2_score": 5  # Draw
            }
        ]
        
        standings = policy.calculate_standings(mock_players, match_results)
        
        # Both players should have 0 wins
        player_1_stats = next(stats for player, stats in standings if player.id == 1)
        player_2_stats = next(stats for player, stats in standings if player.id == 2)
        
        assert player_1_stats["wins"] == 0
        assert player_2_stats["wins"] == 0
        assert player_1_stats["rack_diff"] == 0
        assert player_2_stats["rack_diff"] == 0

    def test_calculate_standings_multiple_matches_same_players(self, policy, mock_players):
        """Test multiple matches between same players."""
        match_results = [
            {
                "player1_id": 1,
                "player2_id": 2,
                "player1_score": 5,
                "player2_score": 3
            },
            {
                "player1_id": 1,
                "player2_id": 2,
                "player1_score": 2,
                "player2_score": 6
            }
        ]
        
        standings = policy.calculate_standings(mock_players, match_results)
        
        player_1_stats = next(stats for player, stats in standings if player.id == 1)
        player_2_stats = next(stats for player, stats in standings if player.id == 2)
        
        assert player_1_stats["wins"] == 1
        assert player_2_stats["wins"] == 1
        # Player 1: (5-3) + (2-6) = 2 - 4 = -2
        # Player 2: (3-5) + (6-2) = -2 + 4 = 2
        assert player_1_stats["rack_diff"] == -2
        assert player_2_stats["rack_diff"] == 2


class TestFargoRatingScoringPolicy:
    """Test FargoRatingScoringPolicy implementation."""

    @pytest.fixture
    def policy(self):
        """Create a FargoRatingScoringPolicy instance."""
        return FargoRatingScoringPolicy()

    @pytest.fixture
    def mock_players_with_fargo(self):
        """Create mock players with Fargo ratings."""
        players = []
        fargo_ratings = [700, 650, 750]  # Different ratings
        for i, rating in enumerate(fargo_ratings):
            player = Mock(spec=User)
            player.id = i + 1
            player.username = f"player{i+1}"
            player.fargo_rating = rating
            players.append(player)
        return players

    @pytest.fixture
    def mock_players_no_fargo(self):
        """Create mock players without Fargo ratings."""
        players = []
        for i in range(3):
            player = Mock(spec=User)
            player.id = i + 1
            player.username = f"player{i+1}"
            # No fargo_rating attribute
            players.append(player)
        return players

    def test_fargo_policy_initialization(self, policy):
        """Test FargoRatingScoringPolicy initialization."""
        assert isinstance(policy, FargoRatingScoringPolicy)
        assert hasattr(policy, 'calculate_standings')
        assert hasattr(policy, 'get_ranking_criteria')

    def test_get_ranking_criteria(self, policy):
        """Test get_ranking_criteria method."""
        criteria = policy.get_ranking_criteria()
        
        assert isinstance(criteria, list)
        assert "fargo_rating" in criteria
        assert "wins" in criteria
        assert "rack_difference" in criteria
        assert len(criteria) == 3

    def test_calculate_standings_with_fargo_ratings(self, policy, mock_players_with_fargo):
        """Test calculate_standings with Fargo ratings."""
        match_results = []
        
        standings = policy.calculate_standings(mock_players_with_fargo, match_results)
        
        assert len(standings) == 3
        
        # Should be sorted by rating (highest first)
        ratings = [stats["rating"] for player, stats in standings]
        assert ratings == sorted(ratings, reverse=True)
        assert ratings[0] == 750  # Highest rating first

    def test_calculate_standings_without_fargo_ratings(self, policy, mock_players_no_fargo):
        """Test calculate_standings without Fargo ratings (defaults to 0)."""
        match_results = []
        
        standings = policy.calculate_standings(mock_players_no_fargo, match_results)
        
        assert len(standings) == 3
        
        # All should have 0 rating when no fargo_rating attribute
        for player, stats in standings:
            assert stats["rating"] == 0

    def test_calculate_standings_with_matches(self, policy, mock_players_with_fargo):
        """Test calculate_standings with match results and ratings."""
        match_results = [
            {
                "player1_id": 1,
                "player2_id": 3,
                "player1_score": 5,
                "player2_score": 3
            }
        ]
        
        standings = policy.calculate_standings(mock_players_with_fargo, match_results)
        
        # Player 3 should still rank first due to higher rating (750)
        first_player, first_stats = standings[0]
        assert first_stats["rating"] == 750
        
        # Check wins are properly recorded
        player_1_stats = next(stats for player, stats in standings if player.id == 1)
        assert player_1_stats["wins"] == 1

    def test_fargo_tie_breaking_by_wins(self, policy):
        """Test tie-breaking when players have same Fargo rating."""
        # Create players with same rating
        players = []
        for i in range(2):
            player = Mock(spec=User)
            player.id = i + 1
            player.fargo_rating = 700  # Same rating
            players.append(player)
        
        match_results = [
            {
                "player1_id": 1,
                "player2_id": 2,
                "player1_score": 5,
                "player2_score": 3
            }
        ]
        
        standings = policy.calculate_standings(players, match_results)
        
        # Player 1 should rank higher due to more wins
        first_player, first_stats = standings[0]
        assert first_player.id == 1
        assert first_stats["wins"] == 1


class TestEloRatingScoringPolicy:
    """Test EloRatingScoringPolicy implementation."""

    @pytest.fixture
    def policy(self):
        """Create an EloRatingScoringPolicy instance."""
        return EloRatingScoringPolicy()

    @pytest.fixture
    def mock_players_with_elo(self):
        """Create mock players with Elo ratings."""
        players = []
        elo_ratings = [1800, 1600, 2000]  # Different ratings
        for i, rating in enumerate(elo_ratings):
            player = Mock(spec=User)
            player.id = i + 1
            player.username = f"player{i+1}"
            player.elo_rating = rating
            players.append(player)
        return players

    @pytest.fixture
    def mock_players_no_elo(self):
        """Create mock players without Elo ratings."""
        players = []
        for i in range(3):
            player = Mock(spec=User)
            player.id = i + 1
            player.username = f"player{i+1}"
            # No elo_rating attribute
            players.append(player)
        return players

    def test_elo_policy_initialization(self, policy):
        """Test EloRatingScoringPolicy initialization."""
        assert isinstance(policy, EloRatingScoringPolicy)
        assert hasattr(policy, 'calculate_standings')
        assert hasattr(policy, 'get_ranking_criteria')

    def test_get_ranking_criteria(self, policy):
        """Test get_ranking_criteria method."""
        criteria = policy.get_ranking_criteria()
        
        assert isinstance(criteria, list)
        assert "elo_rating" in criteria
        assert "wins" in criteria
        assert "rack_difference" in criteria
        assert len(criteria) == 3

    def test_calculate_standings_with_elo_ratings(self, policy, mock_players_with_elo):
        """Test calculate_standings with Elo ratings."""
        match_results = []
        
        standings = policy.calculate_standings(mock_players_with_elo, match_results)
        
        assert len(standings) == 3
        
        # Should be sorted by rating (highest first)
        ratings = [stats["rating"] for player, stats in standings]
        assert ratings == sorted(ratings, reverse=True)
        assert ratings[0] == 2000  # Highest rating first

    def test_calculate_standings_without_elo_ratings(self, policy, mock_players_no_elo):
        """Test calculate_standings without Elo ratings (defaults to 0)."""
        match_results = []
        
        standings = policy.calculate_standings(mock_players_no_elo, match_results)
        
        assert len(standings) == 3
        
        # All should have 0 rating when no elo_rating attribute
        for player, stats in standings:
            assert stats["rating"] == 0

    def test_calculate_standings_with_matches(self, policy, mock_players_with_elo):
        """Test calculate_standings with match results and ratings."""
        match_results = [
            {
                "player1_id": 1,
                "player2_id": 3,
                "player1_score": 6,
                "player2_score": 4
            }
        ]
        
        standings = policy.calculate_standings(mock_players_with_elo, match_results)
        
        # Player 3 should still rank first due to higher rating (2000)
        first_player, first_stats = standings[0]
        assert first_stats["rating"] == 2000
        
        # Check wins are properly recorded
        player_1_stats = next(stats for player, stats in standings if player.id == 1)
        assert player_1_stats["wins"] == 1

    def test_elo_tie_breaking_by_wins(self, policy):
        """Test tie-breaking when players have same Elo rating."""
        # Create players with same rating
        players = []
        for i in range(2):
            player = Mock(spec=User)
            player.id = i + 1
            player.elo_rating = 1800  # Same rating
            players.append(player)
        
        match_results = [
            {
                "player1_id": 1,
                "player2_id": 2,
                "player1_score": 7,
                "player2_score": 3
            }
        ]
        
        standings = policy.calculate_standings(players, match_results)
        
        # Player 1 should rank higher due to more wins
        first_player, first_stats = standings[0]
        assert first_player.id == 1
        assert first_stats["wins"] == 1

    def test_elo_tie_breaking_by_rack_diff(self, policy):
        """Test tie-breaking by rack difference when same rating and wins."""
        # Create players with same rating
        players = []
        for i in range(3):
            player = Mock(spec=User)
            player.id = i + 1
            player.elo_rating = 1800  # Same rating
            players.append(player)
        
        match_results = [
            {
                "player1_id": 1,
                "player2_id": 3,
                "player1_score": 8,
                "player2_score": 2  # Player 1 wins by 6
            },
            {
                "player1_id": 2,
                "player2_id": 3,
                "player1_score": 6,
                "player2_score": 4  # Player 2 wins by 2
            }
        ]
        
        standings = policy.calculate_standings(players, match_results)
        
        # Both player 1 and 2 have 1 win, but player 1 has better rack diff
        player_1_stats = next(stats for player, stats in standings if player.id == 1)
        player_2_stats = next(stats for player, stats in standings if player.id == 2)
        
        assert player_1_stats["wins"] == 1
        assert player_2_stats["wins"] == 1
        assert player_1_stats["rack_diff"] > player_2_stats["rack_diff"]


class TestScoringPolicyIntegration:
    """Integration tests for all scoring policies."""

    def test_all_policies_have_same_interface(self):
        """Test that all policies implement the same interface."""
        policies = [
            ClassicScoringPolicy(),
            FargoRatingScoringPolicy(),
            EloRatingScoringPolicy()
        ]
        
        for policy in policies:
            assert hasattr(policy, 'calculate_standings')
            assert hasattr(policy, 'get_ranking_criteria')
            assert callable(policy.calculate_standings)
            assert callable(policy.get_ranking_criteria)

    def test_policies_return_consistent_format(self):
        """Test that all policies return standings in consistent format."""
        # Create test data
        players = []
        for i in range(2):
            player = Mock(spec=User)
            player.id = i + 1
            player.fargo_rating = 700 + i * 50
            player.elo_rating = 1600 + i * 100
            players.append(player)
        
        match_results = [
            {
                "player1_id": 1,
                "player2_id": 2,
                "player1_score": 5,
                "player2_score": 3
            }
        ]
        
        policies = [
            ClassicScoringPolicy(),
            FargoRatingScoringPolicy(),
            EloRatingScoringPolicy()
        ]
        
        for policy in policies:
            standings = policy.calculate_standings(players, match_results)
            
            # Check format consistency
            assert isinstance(standings, list)
            assert len(standings) == 2
            
            for player, stats in standings:
                assert hasattr(player, 'id')
                assert isinstance(stats, dict)
                assert "wins" in stats
                assert "rack_diff" in stats

    def test_empty_players_list(self):
        """Test handling of empty players list."""
        policies = [
            ClassicScoringPolicy(),
            FargoRatingScoringPolicy(),
            EloRatingScoringPolicy()
        ]
        
        for policy in policies:
            standings = policy.calculate_standings([], [])
            assert standings == []

    def test_invalid_match_results(self):
        """Test handling of invalid match results."""
        player = Mock(spec=User)
        player.id = 1
        players = [player]
        
        # Invalid match result with missing player
        invalid_results = [
            {
                "player1_id": 1,
                "player2_id": 999,  # Non-existent player
                "player1_score": 5,
                "player2_score": 3
            }
        ]
        
        policies = [
            ClassicScoringPolicy(),
            FargoRatingScoringPolicy(),
            EloRatingScoringPolicy()
        ]
        
        for policy in policies:
            # Should handle gracefully (may raise KeyError or ignore)
            try:
                standings = policy.calculate_standings(players, invalid_results)
                # If it doesn't raise an error, check the result is reasonable
                assert isinstance(standings, list)
            except KeyError:
                # This is also acceptable behavior
                pass

    def test_large_score_differences(self):
        """Test handling of large score differences."""
        players = []
        for i in range(2):
            player = Mock(spec=User)
            player.id = i + 1
            player.fargo_rating = 700
            player.elo_rating = 1600
            players.append(player)
        
        # Very large score difference
        match_results = [
            {
                "player1_id": 1,
                "player2_id": 2,
                "player1_score": 100,
                "player2_score": 0
            }
        ]
        
        policies = [
            ClassicScoringPolicy(),
            FargoRatingScoringPolicy(),
            EloRatingScoringPolicy()
        ]
        
        for policy in policies:
            standings = policy.calculate_standings(players, match_results)
            
            # Winner should have massive rack difference
            winner_stats = standings[0][1]
            assert winner_stats["wins"] == 1
            assert winner_stats["rack_diff"] == 100


class TestPolicySpecificBehavior:
    """Test specific behaviors unique to each policy."""

    def test_classic_policy_previous_order_tiebreaking(self):
        """Test Classic policy uses previous order for tie-breaking."""
        policy = ClassicScoringPolicy()
        
        # Create players in specific order
        players = []
        for i in range(3):
            player = Mock(spec=User)
            player.id = i + 1
            players.append(player)
        
        # No matches - should maintain original order
        standings = policy.calculate_standings(players, [])
        
        # Check that previous_order is used correctly
        for i, (player, stats) in enumerate(standings):
            assert stats["previous_order"] == i

    def test_rating_policies_ignore_previous_order(self):
        """Test that rating-based policies don't use previous order."""
        fargo_policy = FargoRatingScoringPolicy()
        elo_policy = EloRatingScoringPolicy()
        
        players = []
        ratings = [500, 1000]  # Lower rating first in list
        for i, rating in enumerate(ratings):
            player = Mock(spec=User)
            player.id = i + 1
            player.fargo_rating = rating
            player.elo_rating = rating
            players.append(player)
        
        # No matches
        for policy in [fargo_policy, elo_policy]:
            standings = policy.calculate_standings(players, [])
            
            # Higher rated player should be first regardless of list order
            first_player, first_stats = standings[0]
            assert first_stats["rating"] == 1000  # Higher rating