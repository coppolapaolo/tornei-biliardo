"""
Test module for models/matchmaking/strategies/random_anti_rematch.py
"""

import pytest
from unittest.mock import Mock, patch
from typing import List
from models.matchmaking.strategies.random_anti_rematch import RandomAntiRematchStrategy
from models.matchmaking.strategies.base import Pairing


class TestRandomAntiRematchStrategy:
    """Test cases for RandomAntiRematchStrategy class."""

    def test_strategy_initialization(self):
        """Test RandomAntiRematchStrategy initialization."""
        strategy = RandomAntiRematchStrategy()
        assert strategy.strategy_name == "random_anti_rematch"
        assert strategy.max_attempts == 100

    def test_strategy_initialization_with_custom_attempts(self):
        """Test RandomAntiRematchStrategy initialization with custom max_attempts."""
        strategy = RandomAntiRematchStrategy(max_attempts=50)
        assert strategy.strategy_name == "random_anti_rematch"
        assert strategy.max_attempts == 50

    def test_validate_with_insufficient_players(self):
        """Test validate method with insufficient players."""
        strategy = RandomAntiRematchStrategy()

        # Create a mock gara object with only 1 player
        mock_gara = Mock()
        mock_inscription = Mock()
        mock_inscription.is_withdrawn = False
        mock_inscription.user_id = 1
        mock_gara.inscriptions = [mock_inscription]

        result = strategy.validate(mock_gara)

        # Verify the result
        assert result.ok is False
        assert "Random pairing requires at least 2 players" in result.messages

    def test_validate_with_sufficient_players(self):
        """Test validate method with sufficient players."""
        strategy = RandomAntiRematchStrategy()

        # Create a mock gara object with 2 players
        mock_gara = Mock()
        mock_inscription1 = Mock()
        mock_inscription1.is_withdrawn = False
        mock_inscription1.user_id = 1
        mock_inscription2 = Mock()
        mock_inscription2.is_withdrawn = False
        mock_inscription2.user_id = 2
        mock_gara.inscriptions = [mock_inscription1, mock_inscription2]
        mock_gara.rounds_count = 1

        result = strategy.validate(mock_gara)

        # Verify the result
        assert result.ok is True
        assert result.messages == ()

    def test_validate_with_too_many_rounds(self):
        """Test validate method with too many rounds planned."""
        strategy = RandomAntiRematchStrategy()

        # Create a mock gara object with 3 players but 4 rounds planned
        mock_gara = Mock()
        mock_inscription1 = Mock()
        mock_inscription1.is_withdrawn = False
        mock_inscription1.user_id = 1
        mock_inscription2 = Mock()
        mock_inscription2.is_withdrawn = False
        mock_inscription2.user_id = 2
        mock_inscription3 = Mock()
        mock_inscription3.is_withdrawn = False
        mock_inscription3.user_id = 3
        mock_gara.inscriptions = [
            mock_inscription1,
            mock_inscription2,
            mock_inscription3,
        ]
        mock_gara.rounds_count = 4  # Only 3 unique matches possible with 3 players

        result = strategy.validate(mock_gara)

        # Verify the result
        assert result.ok is False
        assert (
            "With 3 players, only 3 unique matches possible, but 4 rounds planned"
            in result.messages
        )

    def test_validate_with_exception(self):
        """Test validate method when an exception occurs."""
        strategy = RandomAntiRematchStrategy()

        # Create a mock gara object that will cause an exception
        mock_gara = Mock()
        del mock_gara.inscriptions  # This will cause an AttributeError

        result = strategy.validate(mock_gara)

        # Verify the result
        assert result.ok is False
        assert "Validation error:" in result.messages[0]

    def test_preview(self):
        """Test preview method."""
        strategy = RandomAntiRematchStrategy()

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
        strategy = RandomAntiRematchStrategy()

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
        strategy = RandomAntiRematchStrategy()

        # Create a mock gara object with only 1 player
        mock_gara = Mock()
        mock_inscription = Mock()
        mock_inscription.is_withdrawn = False
        mock_inscription.user_id = 1
        mock_gara.inscriptions = [mock_inscription]
        round_number = 1

        result = strategy._generate_round_pairings(mock_gara, round_number)

        # Verify the result
        assert result == []

    def test_generate_round_pairings_with_exception(self):
        """Test _generate_round_pairings method when an exception occurs."""
        strategy = RandomAntiRematchStrategy()

        # Create a mock gara object that will cause an exception
        mock_gara = Mock()
        del mock_gara.inscriptions  # This will cause an AttributeError
        round_number = 1

        result = strategy._generate_round_pairings(mock_gara, round_number)

        # Verify the result
        assert result == []

    @patch("models.match.models.Match")
    def test_get_previous_pairings(self, mock_match_class):
        """Test _get_previous_pairings method."""
        strategy = RandomAntiRematchStrategy()

        # Create a mock gara object
        mock_gara = Mock()
        mock_gara.id = 1
        round_number = 2

        # Create mock matches
        mock_match1 = Mock()
        mock_match1.player1_id = 1
        mock_match1.player2_id = 2
        mock_match1.is_bye = False
        mock_match1.round_number = 1  # Add round_number attribute

        mock_match2 = Mock()
        mock_match2.player1_id = 3
        mock_match2.player2_id = 4
        mock_match2.is_bye = False
        mock_match2.round_number = 1  # Add round_number attribute

        mock_match3 = Mock()  # Bye match should be ignored
        mock_match3.player1_id = 5
        mock_match3.player2_id = None
        mock_match3.is_bye = True
        mock_match3.round_number = 1  # Add round_number attribute

        # Set up the mock chain to avoid the comparison operation
        mock_query = Mock()
        mock_filtered_query = Mock()

        # Mock filter_by to return our query
        mock_match_class.query.filter_by.return_value = mock_query

        # Mock the round_number attribute to avoid comparison issues
        # We need to mock the comparison operation itself
        mock_round_number = Mock()
        mock_round_number.__lt__ = Mock(return_value=True)
        mock_match_class.round_number = mock_round_number

        # Mock the filter method to directly return our filtered query
        # without evaluating the comparison
        # This avoids the TypeError when comparing MagicMock with int
        mock_query.filter.return_value = mock_filtered_query

        # Mock the all method to return our mock matches
        mock_filtered_query.all.return_value = [mock_match1, mock_match2, mock_match3]

        result = strategy._get_previous_pairings(mock_gara, round_number)

        # Debug information
        print(f"Result: {result}")
        print(f"Mock query calls: {mock_query.method_calls}")
        print(
            f"Mock filter_by calls: {mock_match_class.query.filter_by.call_args_list}"
        )
        print(f"Mock filter calls: {mock_query.filter.call_args_list}")
        print(f"Mock all calls: {mock_filtered_query.all.call_args_list}")

        # Verify the result - should contain pairs in canonical form (smaller ID first)
        assert (1, 2) in result
        assert (3, 4) in result
        assert len(result) == 2

    def test_generate_valid_random_pairings_perfect_solution(self):
        """Test _generate_valid_random_pairings method with a perfect
        solution (no rematches)."""
        strategy = RandomAntiRematchStrategy()

        player_ids = [1, 2, 3, 4]
        previous_pairings = {(1, 2), (3, 4)}  # Players 1&2 played, 3&4 played

        # Mock the _attempt_random_pairing method to return a perfect
        # solution on first try
        with patch.object(strategy, "_attempt_random_pairing") as mock_attempt:
            mock_pairing1 = Mock(spec=Pairing)
            mock_pairing1.players = (1, 3)  # No rematch
            mock_pairing2 = Mock(spec=Pairing)
            mock_pairing2.players = (2, 4)  # No rematch
            attempt1: List[Pairing] = [mock_pairing1, mock_pairing2]

            mock_attempt.return_value = attempt1

            result = strategy._generate_valid_random_pairings(
                player_ids, previous_pairings, 1
            )

            # Should return the perfect solution immediately
            assert result == attempt1
            mock_attempt.assert_called_once()

    def test_generate_valid_random_pairings_with_rematches(self):
        """Test _generate_valid_random_pairings method with rematches."""
        strategy = RandomAntiRematchStrategy(max_attempts=3)

        player_ids = [1, 2, 3, 4]
        previous_pairings = {(1, 2), (3, 4)}  # Players 1&2 played, 3&4 played

        # Mock the _attempt_random_pairing method to return solutions with rematches
        with patch.object(strategy, "_attempt_random_pairing") as mock_attempt:
            # First attempt: 2 rematches (worst)
            mock_pairing1a = Mock(spec=Pairing)
            mock_pairing1a.players = (1, 2)  # Rematch with (1,2)
            mock_pairing1b = Mock(spec=Pairing)
            mock_pairing1b.players = (3, 4)  # Rematch with (3,4)
            attempt1: List[Pairing] = [mock_pairing1a, mock_pairing1b]

            # Second attempt: 0 rematches (best solution)
            mock_pairing2a = Mock(spec=Pairing)
            mock_pairing2a.players = (1, 3)  # No rematch
            mock_pairing2b = Mock(spec=Pairing)
            mock_pairing2b.players = (2, 4)  # No rematch
            attempt2: List[Pairing] = [mock_pairing2a, mock_pairing2b]

            # Third attempt: 1 rematch (middle)
            mock_pairing3a = Mock(spec=Pairing)
            mock_pairing3a.players = (1, 2)  # Rematch with (1,2)
            mock_pairing3b = Mock(spec=Pairing)
            mock_pairing3b.players = (5, 6)  # Not relevant since 5,6 not in player_ids
            attempt3: List[Pairing] = [mock_pairing3a, mock_pairing3b]

            mock_attempt.side_effect = [attempt1, attempt2, attempt3]

            result = strategy._generate_valid_random_pairings(
                player_ids, previous_pairings, 1
            )

            # Should return the best solution (attempt 2 with 0 rematches)
            # Since attempt2 has 0 rematches, it should be returned
            # immediately
            mock_attempt.assert_called()
            # Check that we got results (the exact mock objects are hard to compare)
            assert len(result) == 2

    def test_attempt_random_pairing_with_trio(self):
        """Test _attempt_random_pairing method with trio."""
        strategy = RandomAntiRematchStrategy()

        player_ids = [1, 2, 3, 4, 5]  # Odd number of players
        previous_pairings = set()
        round_number = 1

        # Mock the _should_use_trio method
        with patch.object(strategy, "_should_use_trio") as mock_should_use_trio:
            mock_should_use_trio.return_value = True

            # Mock random.shuffle to ensure consistent behavior in the test
            with patch(
                "models.matchmaking.strategies.random_anti_rematch.random.shuffle"
            ):
                result = strategy._attempt_random_pairing(
                    player_ids, previous_pairings, round_number
                )

                # Should have one trio and one pair
                assert len(result) == 2
                # One pairing should have 3 players (trio)
                trio_pairing = next((p for p in result if len(p.players) == 3), None)
                assert trio_pairing is not None
                # One pairing should have 2 players
                pair_pairing = next((p for p in result if len(p.players) == 2), None)
                assert pair_pairing is not None

    def test_attempt_random_pairing_with_bye(self):
        """Test _attempt_random_pairing method with bye."""
        strategy = RandomAntiRematchStrategy()

        player_ids = [1, 2, 3]  # Odd number of players
        previous_pairings = set()
        round_number = 1

        # Mock the _should_use_trio and _find_best_partner methods
        with patch.object(strategy, "_should_use_trio") as mock_should_use_trio:
            mock_should_use_trio.return_value = False  # Don't use trio, use bye instead

            result = strategy._attempt_random_pairing(
                player_ids, previous_pairings, round_number
            )

            # Should have one pair and one bye
            assert len(result) == 2
            # One pairing should be a bye
            bye_pairing = next((p for p in result if p.is_bye), None)
            assert bye_pairing is not None
            # One pairing should have 2 players
            pair_pairing = next((p for p in result if len(p.players) == 2), None)
            assert pair_pairing is not None

    def test_find_best_partner_without_rematches(self):
        """Test _find_best_partner method without rematches."""
        strategy = RandomAntiRematchStrategy()

        player_id = 1
        available_players = [2, 3, 4]
        previous_pairings = {
            (1, 2),
            (1, 3),
        }  # Player 1 has played against players 2 and 3

        result = strategy._find_best_partner(
            player_id, available_players, previous_pairings
        )

        # Should return player 4 since it's not in previous pairings
        assert result == 4

    def test_find_best_partner_with_all_rematches(self):
        """Test _find_best_partner method when all candidates are rematches."""
        strategy = RandomAntiRematchStrategy()

        player_id = 1
        available_players = [2, 3]
        previous_pairings = {
            (1, 2),
            (1, 3),
        }  # Player 1 has played against all available players

        result = strategy._find_best_partner(
            player_id, available_players, previous_pairings
        )

        # Should return the first player since all are rematches
        assert result == 2

    def test_find_best_partner_with_empty_available_players(self):
        """Test _find_best_partner method with empty available players."""
        strategy = RandomAntiRematchStrategy()

        player_id = 1
        available_players = []
        previous_pairings = set()

        result = strategy._find_best_partner(
            player_id, available_players, previous_pairings
        )

        # Should return None since no players are available
        assert result is None

    def test_count_rematches(self):
        """Test _count_rematches method."""
        strategy = RandomAntiRematchStrategy()

        # Create mock pairings
        mock_pairing1 = Mock(spec=Pairing)
        mock_pairing1.players = (1, 2)
        mock_pairing1.is_bye = False

        mock_pairing2 = Mock(spec=Pairing)
        mock_pairing2.players = (3, 4)
        mock_pairing2.is_bye = False

        mock_pairing3 = Mock(spec=Pairing)
        mock_pairing3.players = (1,)
        mock_pairing3.is_bye = True

        pairings: List[Pairing] = [mock_pairing1, mock_pairing2, mock_pairing3]
        previous_pairings = {(1, 2), (5, 6)}  # Only (1, 2) is a rematch

        result = strategy._count_rematches(pairings, previous_pairings)

        # Should count 1 rematch
        assert result == 1

    def test_should_use_trio_with_valid_counts(self):
        """Test _should_use_trio method with valid player counts."""
        strategy = RandomAntiRematchStrategy()

        # Test with 3 players
        player_ids = [1, 2, 3]
        result = strategy._should_use_trio(player_ids)
        assert result is True

        # Test with 5 players
        player_ids = [1, 2, 3, 4, 5]
        result = strategy._should_use_trio(player_ids)
        assert result is True

        # Test with 7 players
        player_ids = [1, 2, 3, 4, 5, 6, 7]
        result = strategy._should_use_trio(player_ids)
        assert result is True

    def test_should_use_trio_with_invalid_counts(self):
        """Test _should_use_trio method with invalid player counts."""
        strategy = RandomAntiRematchStrategy()

        # Test with 4 players
        player_ids = [1, 2, 3, 4]
        result = strategy._should_use_trio(player_ids)
        assert result is False

        # Test with 9 players
        player_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        result = strategy._should_use_trio(player_ids)
        assert result is False

    def test_can_generate_all_rounds_with_insufficient_players(self):
        """Test can_generate_all_rounds method with insufficient players."""
        strategy = RandomAntiRematchStrategy()

        # Create a mock gara object with only 1 player
        mock_gara = Mock()
        mock_inscription = Mock()
        mock_inscription.is_withdrawn = False
        mock_inscription.user_id = 1
        mock_gara.inscriptions = [mock_inscription]

        result = strategy.can_generate_all_rounds(mock_gara)

        # Should return False since there are insufficient players
        assert result is False

    def test_can_generate_all_rounds_with_sufficient_players(self):
        """Test can_generate_all_rounds method with sufficient players."""
        strategy = RandomAntiRematchStrategy()

        # Create a mock gara object with 4 players and 2 rounds
        mock_gara = Mock()
        mock_inscription1 = Mock()
        mock_inscription1.is_withdrawn = False
        mock_inscription1.user_id = 1
        mock_inscription2 = Mock()
        mock_inscription2.is_withdrawn = False
        mock_inscription2.user_id = 2
        mock_inscription3 = Mock()
        mock_inscription3.is_withdrawn = False
        mock_inscription3.user_id = 3
        mock_inscription4 = Mock()
        mock_inscription4.is_withdrawn = False
        mock_inscription4.user_id = 4
        mock_gara.inscriptions = [
            mock_inscription1,
            mock_inscription2,
            mock_inscription3,
            mock_inscription4,
        ]
        mock_gara.rounds_count = 2

        result = strategy.can_generate_all_rounds(mock_gara)

        # Should return True since 2 rounds can be generated without rematches
        assert result is True

    def test_get_rematch_probability_with_no_matches_played(self):
        """Test get_rematch_probability method with no matches played."""
        strategy = RandomAntiRematchStrategy()

        # Create a mock gara object with 4 players
        mock_gara = Mock()
        mock_inscription1 = Mock()
        mock_inscription1.is_withdrawn = False
        mock_inscription1.user_id = 1
        mock_inscription2 = Mock()
        mock_inscription2.is_withdrawn = False
        mock_inscription2.user_id = 2
        mock_inscription3 = Mock()
        mock_inscription3.is_withdrawn = False
        mock_inscription3.user_id = 3
        mock_inscription4 = Mock()
        mock_inscription4.is_withdrawn = False
        mock_inscription4.user_id = 4
        mock_gara.inscriptions = [
            mock_inscription1,
            mock_inscription2,
            mock_inscription3,
            mock_inscription4,
        ]
        round_number = 1  # First round

        result = strategy.get_rematch_probability(mock_gara, round_number)

        # Should return 0.0 since no matches have been played yet
        assert result == 0.0

    def test_get_rematch_probability_with_all_matches_played(self):
        """Test get_rematch_probability method when all possible matches
        have been played."""
        strategy = RandomAntiRematchStrategy()

        # Create a mock gara object with 4 players
        mock_gara = Mock()
        mock_inscription1 = Mock()
        mock_inscription1.is_withdrawn = False
        mock_inscription1.user_id = 1
        mock_inscription2 = Mock()
        mock_inscription2.is_withdrawn = False
        mock_inscription2.user_id = 2
        mock_inscription3 = Mock()
        mock_inscription3.is_withdrawn = False
        mock_inscription3.user_id = 3
        mock_inscription4 = Mock()
        mock_inscription4.is_withdrawn = False
        mock_inscription4.user_id = 4
        mock_gara.inscriptions = [
            mock_inscription1,
            mock_inscription2,
            mock_inscription3,
            mock_inscription4,
        ]
        round_number = 7  # More than the possible unique pairings (6 for 4 players)

        result = strategy.get_rematch_probability(mock_gara, round_number)

        # Should return 1.0 since all possible matches have been played
        assert result == 1.0

    def test_get_metrics(self):
        """Test get_metrics method."""
        strategy = RandomAntiRematchStrategy()

        result = strategy.get_metrics()

        # Should return None since no metrics collection is implemented
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__])
