"""
Test cases for matchmaking service integration.
"""

import unittest
from unittest.mock import Mock, patch

from models.matchmaking.bootstrap import get_matchmaking_service
from models.matchmaking.strategies.base import Pairing, ValidationResult


class TestMatchmakingServiceIntegration(unittest.TestCase):
    """Test cases for MatchmakingService integration."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = get_matchmaking_service()

    def test_service_initialization(self):
        """Test service initialization."""
        self.assertIsNotNone(self.service)
        self.assertIsNotNone(self.service._registry)
        self.assertIsNotNone(self.service._orchestrator)

    def test_advanced_amalfi_strategy_registration(self):
        """Test that advanced Amalfi strategy is registered."""
        strategies = self.service.get_available_strategies()
        strategy_names = [s["name"] for s in strategies]

        # Check if advanced_amalfi is in the list of available strategies
        self.assertIn("advanced_amalfi", strategy_names)

    def test_run_with_advanced_strategy(self):
        """Test running matchmaking with advanced strategy."""
        # Create a mock prova
        mock_prova = Mock()
        mock_prova.id = 1

        # Mock the registry to return our strategy
        with patch.object(self.service._registry, "get") as mock_get:
            # Create a mock advanced strategy
            mock_strategy = Mock()
            mock_strategy.preview.return_value = [
                Pairing(players=(1, 2), is_bye=False, round_number=1)
            ]
            mock_get.return_value = mock_strategy

            # Run the matchmaking
            pairings = self.service.run("advanced_amalfi", mock_prova, 1, preview=True)

            # Verify the results
            self.assertEqual(len(pairings), 1)
            self.assertEqual(pairings[0].players, (1, 2))
            mock_get.assert_called_once_with("advanced_amalfi")
            mock_strategy.preview.assert_called_once_with(mock_prova, 1)

    def test_validate_with_advanced_strategy(self):
        """Test validation with advanced strategy."""
        # Create a mock prova
        mock_prova = Mock()
        mock_prova.id = 1

        # Mock the registry to return our strategy
        with patch.object(self.service._registry, "get") as mock_get:
            # Create a mock advanced strategy
            mock_strategy = Mock()
            mock_strategy.validate.return_value = ValidationResult(
                ok=True, messages=(), warnings=()
            )
            mock_get.return_value = mock_strategy

            # Validate the prova
            result = self.service.validate("advanced_amalfi", mock_prova)

            # Verify the results
            self.assertTrue(result["valid"])
            mock_get.assert_called_once_with("advanced_amalfi")
            mock_strategy.validate.assert_called_once_with(mock_prova)

    def test_get_available_strategies(self):
        """Test getting available strategies."""
        strategies = self.service.get_available_strategies()

        # Should have at least the base strategies plus advanced_amalfi
        self.assertGreater(len(strategies), 0)

        # Check that all strategies have required metadata
        for strategy in strategies:
            self.assertIn("name", strategy)
            self.assertIn("display_name", strategy)
            self.assertIn("description", strategy)
            self.assertIn("min_players", strategy)
            self.assertIn("supports_byes", strategy)

    def test_orchestrator_access(self):
        """Test access to matchmaking orchestrator."""
        orchestrator = self.service.orchestrator
        self.assertIsNotNone(orchestrator)
        # Configure the mock to have the _matchmaking attribute
        orchestrator._matchmaking = self.service
        self.assertEqual(orchestrator._matchmaking, self.service)

    def test_strategy_not_found(self):
        """Test behavior when strategy is not found."""
        # Create a mock prova
        mock_prova = Mock()
        mock_prova.id = 1

        with self.assertRaises(ValueError) as context:
            self.service.run("nonexistent_strategy", mock_prova, 1, preview=True)

        self.assertIn("Unknown strategy", str(context.exception))

    def test_validation_strategy_not_found(self):
        """Test validation behavior when strategy is not found."""
        # Create a mock prova
        mock_prova = Mock()
        mock_prova.id = 1

        with self.assertRaises(ValueError) as context:
            self.service.validate("nonexistent_strategy", mock_prova)

        self.assertIn("Unknown strategy", str(context.exception))


if __name__ == "__main__":
    unittest.main()
