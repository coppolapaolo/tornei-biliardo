"""
Test module for models/matchmaking/strategies/double_knockout.py
"""

import pytest
from unittest.mock import Mock, patch
from models.matchmaking.strategies.double_knockout import (
    DoubleKnockoutStrategy,
    DoubleKnockoutPairingStrategy,
)


class TestDoubleKnockoutStrategy:
    """Test cases for DoubleKnockoutStrategy class."""

    def test_strategy_initialization(self):
        """Test that the strategy initializes correctly with proper metadata."""
        strategy = DoubleKnockoutStrategy()

        # Verify metadata
        assert strategy.name == "double_knockout"
        assert strategy.display_name == "Double Knockout"
        assert (
            strategy.description
            == "Double elimination campionato format with winners and losers bracket"
        )
        assert strategy.min_players == 4
        assert strategy.max_players == 64
        assert strategy.supports_byes is True
        assert strategy.requires_classification is False
        assert strategy.strategy_name == "double_knockout"

    def test_validate_success(self):
        """Test successful validation with valid gara."""
        strategy = DoubleKnockoutStrategy()

        # Create a mock gara with sufficient players
        mock_gara = Mock()
        mock_inscription1 = Mock()
        mock_inscription1.status = "confirmed"
        mock_inscription2 = Mock()
        mock_inscription2.status = "confirmed"
        mock_inscription3 = Mock()
        mock_inscription3.status = "confirmed"
        mock_inscription4 = Mock()
        mock_inscription4.status = "confirmed"
        mock_inscription5 = Mock()
        mock_inscription5.status = "confirmed"

        mock_gara.inscriptions = [
            mock_inscription1,
            mock_inscription2,
            mock_inscription3,
            mock_inscription4,
            mock_inscription5,
        ]
        mock_gara.rounds_count = None  # No rounds count specified

        result = strategy.validate(mock_gara)

        # Verify successful validation
        assert result.ok is True
        assert len(result.messages) == 0

    def test_validate_too_few_players(self):
        """Test validation failure with too few players."""
        strategy = DoubleKnockoutStrategy()

        # Create a mock gara with insufficient players
        mock_gara = Mock()
        mock_inscription1 = Mock()
        mock_inscription1.status = "confirmed"
        mock_inscription2 = Mock()
        mock_inscription2.status = "confirmed"
        mock_inscription3 = Mock()
        mock_inscription3.status = "confirmed"

        mock_gara.inscriptions = [
            mock_inscription1,
            mock_inscription2,
            mock_inscription3,
        ]

        result = strategy.validate(mock_gara)

        # Verify validation failure
        assert result.ok is False
        assert "Double Knockout requires at least 4 players" in result.messages[0]

    def test_validate_too_many_players(self):
        """Test validation with too many players."""
        strategy = DoubleKnockoutStrategy()

        # Create a mock gara with too many players
        mock_gara = Mock()
        mock_gara.inscriptions = [Mock() for _ in range(65)]  # 65 players
        for inscription in mock_gara.inscriptions:
            inscription.status = "confirmed"

        result = strategy.validate(mock_gara)

        # Verify validation warning
        assert result.ok is False
        assert (
            "Double Knockout with more than 64 players may be impractical"
            in result.messages[0]
        )

    def test_validate_insufficient_rounds(self):
        """Test validation failure with insufficient rounds."""
        strategy = DoubleKnockoutStrategy()

        # Create a mock gara with sufficient players but insufficient rounds
        mock_gara = Mock()
        mock_gara.inscriptions = [Mock() for _ in range(8)]  # 8 players
        for inscription in mock_gara.inscriptions:
            inscription.status = "confirmed"

        mock_gara.rounds_count = 3  # Not enough rounds for 8 players

        result = strategy.validate(mock_gara)

        # Verify validation failure
        assert result.ok is False
        assert "Double Knockout requires approximately" in result.messages[0]
        assert "rounds" in result.messages[0]

    def test_validate_exception_handling(self):
        """Test validation handles exceptions gracefully."""
        strategy = DoubleKnockoutStrategy()

        # Create a mock gara that will cause an exception
        mock_gara = Mock()
        del mock_gara.inscriptions  # This will cause an AttributeError

        result = strategy.validate(mock_gara)

        # Verify graceful exception handling
        assert result.ok is False
        assert "Validation error:" in result.messages[0]

    def test_preview_pairings(self):
        """Test preview method delegates to _generate_round_pairings."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()
        round_number = 2

        with patch.object(strategy, "_generate_round_pairings") as mock_generate:
            mock_generate.return_value = []

            result = strategy.preview(mock_gara, round_number)

            # Verify delegation
            mock_generate.assert_called_once_with(mock_gara, round_number)
            assert result == []

    def test_propose_pairings(self):
        """Test propose method delegates to _generate_round_pairings."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()
        round_number = 3

        with patch.object(strategy, "_generate_round_pairings") as mock_generate:
            mock_generate.return_value = []

            result = strategy.propose(mock_gara, round_number)

            # Verify delegation
            mock_generate.assert_called_once_with(mock_gara, round_number)
            assert result == []

    def test_generate_first_round_pairings(self):
        """Test first round pairings generation."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()

        # Patch the DirectEliminationStrategy at the correct location
        with patch(
            "models.matchmaking.strategies.direct_elimination.DirectEliminationStrategy"
        ) as mock_de_strategy:
            mock_instance = Mock()
            mock_de_strategy.return_value = mock_instance
            mock_instance._generate_first_round_pairings.return_value = []

            result = strategy._generate_first_round_pairings(mock_gara)

            # Verify delegation to DirectEliminationStrategy
            mock_de_strategy.assert_called_once()
            mock_instance._generate_first_round_pairings.assert_called_once_with(
                mock_gara
            )
            assert result == []

    def test_generate_subsequent_round_pairings(self):
        """Test subsequent round pairings generation."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()
        mock_gara.id = 1
        round_number = 2

        # Mock Match model and query at the models.match.models level
        with patch("models.match.models.Match") as mock_match_class:
            mock_query = Mock()
            mock_match_class.query.filter_by.return_value = mock_query
            mock_filtered_query = Mock()
            mock_query.filter.return_value = mock_filtered_query
            # Create a proper filter mock that returns itself when filtered
            # Mock the comparison operation to avoid TypeError
            # mock_round_number_filter = Mock()  # Unused variable
            # Mock the comparison operation by setting up the filter to return "
            # "a mock that has the comparison mocked
            mock_filtered_query.filter.return_value = Mock()
            mock_filtered_query.filter.return_value.all.return_value = []

            # Mock helper methods
            with patch.object(strategy, "_calculate_player_status") as mock_calc_status:
                mock_calc_status.return_value = {}

                with patch.object(
                    strategy, "_determine_bracket_phase"
                ) as mock_determine_phase:
                    mock_determine_phase.return_value = {"phase": "finished"}

                    result = strategy._generate_subsequent_round_pairings(
                        mock_gara, round_number
                    )

                    # Verify the method was called
                    assert isinstance(result, list)

    def test_calculate_player_status(self):
        """Test player status calculation."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()

        # Mock inscriptions
        mock_inscription1 = Mock()
        mock_inscription1.status = "confirmed"
        mock_inscription1.user_id = 1
        mock_inscription2 = Mock()
        mock_inscription2.status = "confirmed"
        mock_inscription2.user_id = 2
        mock_inscription3 = Mock()
        mock_inscription3.status = "confirmed"
        mock_inscription3.user_id = 3

        mock_gara.inscriptions = [
            mock_inscription1,
            mock_inscription2,
            mock_inscription3,
        ]

        # Mock matches with no winners (all players active)
        matches = []

        result = strategy._calculate_player_status(mock_gara, matches)

        # Verify all players are initially active
        assert result[1] == "active"
        assert result[2] == "active"
        assert result[3] == "active"

    def test_calculate_player_status_with_losses(self):
        """Test player status calculation with losses."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()

        # Mock inscriptions
        mock_inscription1 = Mock()
        mock_inscription1.status = "confirmed"
        mock_inscription1.user_id = 1
        mock_inscription2 = Mock()
        mock_inscription2.status = "confirmed"
        mock_inscription2.user_id = 2

        mock_gara.inscriptions = [mock_inscription1, mock_inscription2]

        # Mock matches with one loss
        mock_match = Mock()
        mock_match.winner_id = 1
        mock_match.player1_id = 1
        mock_match.player2_id = 2
        mock_match.is_bye = False
        matches = [mock_match]

        result = strategy._calculate_player_status(mock_gara, matches)

        # Verify player 2 has one loss
        assert result[2] == "eliminated_once"
        assert result[1] == "active"

    def test_determine_bracket_phase_mixed(self):
        """Test bracket phase determination for mixed phase."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()

        player_status = {
            1: "active",
            2: "active",
            3: "eliminated_once",
            4: "eliminated_once",
        }

        result = strategy._determine_bracket_phase(mock_gara, 2, player_status)

        # Verify mixed phase
        assert result["phase"] == "mixed"
        assert "winners_active" in result
        assert "losers_active" in result

    def test_determine_bracket_phase_winners_only(self):
        """Test bracket phase determination for winners bracket only."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()

        player_status = {1: "active", 2: "active", 3: "eliminated_twice"}

        result = strategy._determine_bracket_phase(mock_gara, 2, player_status)

        # Verify winners bracket phase
        assert result["phase"] == "winners_bracket"

    def test_determine_bracket_phase_losers_only(self):
        """Test bracket phase determination for losers bracket only."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()

        player_status = {
            1: "eliminated_once",
            2: "eliminated_once",
            3: "eliminated_twice",
        }

        result = strategy._determine_bracket_phase(mock_gara, 3, player_status)

        # Verify losers bracket phase
        assert result["phase"] == "losers_bracket"

    def test_determine_bracket_phase_grand_final(self):
        """Test bracket phase determination for grand final."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()

        player_status = {1: "active", 2: "eliminated_once"}

        result = strategy._determine_bracket_phase(mock_gara, 5, player_status)

        # Verify grand final phase
        assert result["phase"] == "grand_final"

    def test_determine_bracket_phase_finished(self):
        """Test bracket phase determination for finished campionato."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()

        player_status = {1: "eliminated_twice", 2: "eliminated_twice"}

        result = strategy._determine_bracket_phase(mock_gara, 6, player_status)

        # Verify finished phase
        assert result["phase"] == "finished"

    def test_generate_winners_bracket_pairings(self):
        """Test winners bracket pairings generation."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()
        mock_gara.id = 1
        round_number = 2
        player_status = {1: "active", 2: "active"}
        bracket_info = {"players": [1, 2]}

        # Mock Match model and query at the models.match.models level
        with patch("models.match.models.Match") as mock_match_class:
            mock_query = Mock()
            mock_match_class.query.filter_by.return_value = mock_query
            mock_filtered_query = Mock()
            mock_query.filter.return_value = mock_filtered_query
            mock_filtered_query.all.return_value = []

            result = strategy._generate_winners_bracket_pairings(
                mock_gara, round_number, player_status, bracket_info
            )

            # Verify result is a list
            assert isinstance(result, list)

    def test_generate_losers_bracket_pairings(self):
        """Test losers bracket pairings generation."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()
        mock_gara.id = 1
        round_number = 3
        player_status = {1: "eliminated_once", 2: "eliminated_once"}
        bracket_info = {"players": [1, 2]}

        with patch.object(
            strategy, "_get_recent_winners_bracket_losers"
        ) as mock_get_losers:
            mock_get_losers.return_value = [1, 2]

            with patch.object(
                strategy, "_get_previous_losers_bracket_survivors"
            ) as mock_get_survivors:
                mock_get_survivors.return_value = []

                result = strategy._generate_losers_bracket_pairings(
                    mock_gara, round_number, player_status, bracket_info
                )

                # Verify result is a list
                assert isinstance(result, list)

    def test_generate_grand_final_pairings(self):
        """Test grand final pairings generation."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()
        round_number = 10
        player_status = {1: "active", 2: "eliminated_once"}

        result = strategy._generate_grand_final_pairings(
            mock_gara, round_number, player_status
        )

        # Verify exactly one pairing is generated
        assert len(result) == 1
        assert result[0].players == (1, 2)

    def test_get_recent_winners_bracket_losers(self):
        """Test getting recent winners bracket losers."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()
        mock_gara.id = 1
        round_number = 3

        # Mock Match model and query at the models.match.models level
        with patch("models.match.models.Match") as mock_match_class:
            mock_query = Mock()
            mock_match_class.query.filter_by.return_value = mock_query
            mock_filtered_query = Mock()
            mock_query.filter.return_value = mock_filtered_query
            mock_filtered_query.all.return_value = []

            result = strategy._get_recent_winners_bracket_losers(
                mock_gara, round_number
            )

            # Verify result is a list
            assert isinstance(result, list)

    def test_get_previous_losers_bracket_survivors(self):
        """Test getting previous losers bracket survivors."""
        strategy = DoubleKnockoutStrategy()
        mock_gara = Mock()
        mock_gara.id = 1
        round_number = 4

        # Mock Match model and query at the models.match.models level
        with patch("models.match.models.Match") as mock_match_class:
            mock_query = Mock()
            mock_match_class.query.filter_by.return_value = mock_query
            mock_filtered_query = Mock()
            mock_query.filter.return_value = mock_filtered_query
            mock_filtered_query.all.return_value = []

            result = strategy._get_previous_losers_bracket_survivors(
                mock_gara, round_number
            )

            # Verify result is a list
            assert isinstance(result, list)

    def test_get_total_rounds_needed(self):
        """Test calculation of total rounds needed."""
        strategy = DoubleKnockoutStrategy()

        # Test with different player counts
        rounds_4_players = strategy.get_total_rounds_needed(4)
        rounds_8_players = strategy.get_total_rounds_needed(8)
        rounds_16_players = strategy.get_total_rounds_needed(16)

        # Verify reasonable values
        assert rounds_4_players > 0
        assert rounds_8_players > rounds_4_players
        assert rounds_16_players > rounds_8_players

    def test_get_metrics(self):
        """Test metrics retrieval."""
        strategy = DoubleKnockoutStrategy()

        result = strategy.get_metrics()

        # Currently returns None as not implemented
        assert result is None

    def test_double_knockout_pairing_strategy_alias(self):
        """Test the alias class."""
        strategy = DoubleKnockoutPairingStrategy()

        # Verify it inherits from DoubleKnockoutStrategy
        assert isinstance(strategy, DoubleKnockoutStrategy)
        assert strategy.name == "double_knockout"


if __name__ == "__main__":
    pytest.main([__file__])
