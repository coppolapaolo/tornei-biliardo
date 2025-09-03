"""
Test module for models/matchmaking/strategies/round_robin.py
"""

import pytest
from unittest.mock import Mock, patch
from models.matchmaking.strategies.round_robin import RoundRobinStrategy


class TestRoundRobinStrategy:
    """Test cases for RoundRobinStrategy class."""

    def test_strategy_initialization(self):
        """Test RoundRobinStrategy initialization."""
        strategy = RoundRobinStrategy()
        assert strategy.strategy_name == "round_robin"
        assert strategy.name == "round_robin"
        assert strategy.display_name == "Round Robin"
        assert (
            strategy.description
            == "Round Robin campionato where everyone plays everyone else"
        )
        assert strategy.min_players == 3
        assert strategy.max_players == 16
        assert strategy.supports_byes is True
        assert strategy.requires_classification is False

    def test_validate_with_insufficient_players(self):
        """Test validate method with insufficient players."""
        strategy = RoundRobinStrategy()

        # Create a mock gara object with only 1 player
        mock_gara = Mock()
        mock_inscription = Mock()
        mock_inscription.status = "confirmed"
        mock_inscription.user_id = 1
        mock_gara.inscriptions = [mock_inscription]

        result = strategy.validate(mock_gara)

        # Verify the result
        assert result.ok is False
        assert "Round Robin requires at least 3 players" in result.messages

    def test_validate_with_sufficient_players(self):
        """Test validate method with sufficient players."""
        strategy = RoundRobinStrategy()

        # Create a mock gara object with 4 players
        mock_gara = Mock()
        mock_inscriptions = []
        for i in range(4):
            mock_inscription = Mock()
            mock_inscription.status = "confirmed"
            mock_inscription.user_id = i + 1
            mock_inscriptions.append(mock_inscription)
        mock_gara.inscriptions = mock_inscriptions
        mock_gara.rounds_count = 5  # 4 players need 3 rounds, but we have 5

        result = strategy.validate(mock_gara)

        # Verify the result
        assert result.ok is True
        assert result.messages == ()

    def test_validate_with_too_few_rounds(self):
        """Test validate method with insufficient rounds."""
        strategy = RoundRobinStrategy()

        # Create a mock gara object with 6 players but only 3 rounds
        mock_gara = Mock()
        mock_inscriptions = []
        for i in range(6):
            mock_inscription = Mock()
            mock_inscription.status = "confirmed"
            mock_inscription.user_id = i + 1
            mock_inscriptions.append(mock_inscription)
        mock_gara.inscriptions = mock_inscriptions
        mock_gara.rounds_count = 3  # 6 players need 5 rounds

        result = strategy.validate(mock_gara)

        # Verify the result
        assert result.ok is False
        assert "Round Robin requires 5 rounds, but gara has 3" in result.messages

    def test_validate_with_exception(self):
        """Test validate method when an exception occurs."""
        strategy = RoundRobinStrategy()

        # Create a mock gara object that will cause an exception
        mock_gara = Mock()
        # Instead of deleting inscriptions, let's mock getattr to raise an exception
        with patch("builtins.getattr", side_effect=AttributeError("test error")):
            result = strategy.validate(mock_gara)

            # Verify the result
            assert result.ok is False
            assert "Validation error:" in result.messages[0]

    def test_preview(self):
        """Test preview method."""
        strategy = RoundRobinStrategy()

        # Create a mock gara object
        mock_gara = Mock()
        round_number = 1

        # Mock the _generate_round_pairings method
        with patch.object(strategy, "_generate_round_pairings") as mock_generate:
            mock_generate.return_value = []

            result = strategy.preview(mock_gara, round_number)

            # Verify the result
            assert result == []
            mock_generate.assert_called_once_with(mock_gara, round_number)

    def test_propose(self):
        """Test propose method."""
        strategy = RoundRobinStrategy()

        # Create a mock gara object
        mock_gara = Mock()
        round_number = 1

        # Mock the _generate_round_pairings method
        with patch.object(strategy, "_generate_round_pairings") as mock_generate:
            mock_generate.return_value = []

            result = strategy.propose(mock_gara, round_number)

            # Verify the result
            assert result == []
            mock_generate.assert_called_once_with(mock_gara, round_number)

    def test_generate_round_pairings_with_insufficient_players(self):
        """Test _generate_round_pairings method with insufficient players."""
        strategy = RoundRobinStrategy()

        # Create a mock gara object with only 1 player
        mock_gara = Mock()
        mock_inscription = Mock()
        mock_inscription.status = "confirmed"
        mock_inscription.user_id = 1
        mock_gara.inscriptions = [mock_inscription]
        round_number = 1

        result = strategy._generate_round_pairings(mock_gara, round_number)

        # Verify the result
        assert result == []

    def test_generate_round_robin_schedule_with_even_players(self):
        """Test _generate_round_robin_schedule method with even number of players."""
        strategy = RoundRobinStrategy()

        player_ids = [1, 2, 3, 4]
        result = strategy._generate_round_robin_schedule(player_ids)

        # For 4 players, we should have 3 rounds
        assert len(result) == 3

        # Each round should have 2 pairings
        for round_pairings in result:
            assert len(round_pairings) == 2

        # All players should appear in each round
        for round_pairings in result:
            players_in_round = set()
            for pairing in round_pairings:
                players_in_round.update(pairing)
            assert players_in_round == {1, 2, 3, 4}

    def test_generate_round_robin_schedule_with_odd_players(self):
        """Test _generate_round_robin_schedule method with odd number of players."""
        strategy = RoundRobinStrategy()

        player_ids = [1, 2, 3]
        result = strategy._generate_round_robin_schedule(player_ids)

        # For 3 players, we should have 3 rounds
        assert len(result) == 3

        # Each round should have 2 pairings (one with a bye)
        for round_pairings in result:
            assert len(round_pairings) == 2

        # Check that byes are handled correctly
        bye_count = 0
        for round_pairings in result:
            for pairing in round_pairings:
                if len(pairing) == 1:  # Bye
                    bye_count += 1

        # Should have 3 byes total (one per round)
        assert bye_count == 3

    def test_get_total_rounds_needed(self):
        """Test get_total_rounds_needed method."""
        strategy = RoundRobinStrategy()

        # Test with even number of players
        assert strategy.get_total_rounds_needed(4) == 3  # 4-1 = 3
        assert strategy.get_total_rounds_needed(6) == 5  # 6-1 = 5

        # Test with odd number of players
        assert strategy.get_total_rounds_needed(3) == 3  # 3 (odd)
        assert strategy.get_total_rounds_needed(5) == 5  # 5 (odd)

        # Test edge cases
        assert strategy.get_total_rounds_needed(0) == 0
        assert strategy.get_total_rounds_needed(1) == 0
        assert strategy.get_total_rounds_needed(2) == 1

    def test_get_matches_per_player(self):
        """Test get_matches_per_player method."""
        strategy = RoundRobinStrategy()

        # Each player plays against all other players
        assert strategy.get_matches_per_player(3) == 2  # 3-1 = 2
        assert strategy.get_matches_per_player(4) == 3  # 4-1 = 3
        assert strategy.get_matches_per_player(5) == 4  # 5-1 = 4

        # Edge cases
        assert strategy.get_matches_per_player(0) == 0
        assert strategy.get_matches_per_player(1) == 0

    def test_get_metrics(self):
        """Test get_metrics method."""
        strategy = RoundRobinStrategy()

        result = strategy.get_metrics()

        # Should return None since no metrics collection is implemented
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__])
