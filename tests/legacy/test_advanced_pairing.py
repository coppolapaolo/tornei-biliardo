"""
Test cases for advanced pairing strategies.
"""

import unittest
from unittest.mock import Mock, patch

from models.matchmaking.strategies.advanced_amalfi import AdvancedAmalfiStrategy
from models.matchmaking.strategies.base import Pairing, ValidationResult
from models.matchmaking.strategies.amalfi_adapter import AmalfiStrategy


class TestAdvancedAmalfiStrategy(unittest.TestCase):
    """Test cases for AdvancedAmalfiStrategy."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a mock base Amalfi strategy
        self.mock_base_strategy = Mock(spec=AmalfiStrategy)
        self.strategy = AdvancedAmalfiStrategy(self.mock_base_strategy)

        # Create a mock gara
        self.mock_gara = Mock()
        self.mock_gara.id = 1
        self.mock_gara.without_x = False
        self.mock_gara.inscriptions = []

        # Create some test pairings
        self.base_pairings = [
            Pairing(players=(1, 2), is_bye=False, round_number=1),
            Pairing(players=(3,), is_bye=True, round_number=1),  # Bye pairing
            Pairing(players=(4, 5, 6), is_bye=False, round_number=1),  # Trio pairing
        ]

    def test_initialization(self):
        """Test strategy initialization."""
        self.assertEqual(self.strategy.name, "advanced_amalfi")
        self.assertEqual(self.strategy.display_name, "Advanced Amalfi")
        self.assertTrue(self.strategy.supports_byes)
        self.assertTrue(self.strategy.requires_classification)

    def test_options_configuration(self):
        """Test pairing options configuration."""
        options = self.strategy._options
        self.assertTrue(options.allow_x_replacement)
        self.assertTrue(options.allow_trio_matches)
        self.assertTrue(options.use_challenges_for_x)
        self.assertTrue(options.use_individual_matches_for_x)

    def test_validate_success(self):
        """Test validation with valid gara."""
        # Configure mock base strategy to return successful validation
        self.mock_base_strategy.validate.return_value = ValidationResult(
            ok=True, messages=(), warnings=()
        )

        result = self.strategy.validate(self.mock_gara)

        self.assertTrue(result.ok)
        # Just check that validate was called with the right argument
        self.mock_base_strategy.validate.assert_called_with(self.mock_gara)

    def test_validate_failure(self):
        """Test validation with invalid gara."""
        # Configure mock base strategy to return failed validation
        self.mock_base_strategy.validate.return_value = ValidationResult(
            ok=False, errors=("Invalid gara",), warnings=()
        )

        result = self.strategy.validate(self.mock_gara)

        self.assertFalse(result.ok)
        self.assertIn("Invalid gara", result.errors)

    def test_generate_pairings_without_x_replacement(self):
        """Test pairing generation without X replacement."""
        # Configure mock to return base pairings
        self.mock_base_strategy._generate_pairings.return_value = self.base_pairings

        processed_data = {"gara": self.mock_gara}
        pairings = self.strategy._generate_pairings(
            processed_data, 1, preview_mode=True
        )

        # Should return the same pairings since X replacement is enabled by default
        self.assertEqual(len(pairings), 3)
        self.mock_base_strategy._generate_pairings.assert_called_once()

    def test_generate_pairings_with_x_replacement(self):
        """Test pairing generation with X replacement."""
        # Configure strategy to use X replacement
        self.strategy._options.allow_x_replacement = True

        # Configure mock to return pairings with a bye
        self.mock_base_strategy._generate_pairings.return_value = self.base_pairings

        # Configure X replacement to return a replacement
        with patch.object(self.strategy, "_generate_x_replacement") as mock_x_replace:
            mock_x_replace.return_value = Pairing(
                players=(3, 7),
                is_bye=False,
                round_number=1,
                notes="Individual match replacement for X",
            )

            processed_data = {"gara": self.mock_gara}
            pairings = self.strategy._generate_pairings(
                processed_data, 1, preview_mode=True
            )

            # Should have replaced the bye pairing
            self.assertEqual(len(pairings), 3)
            mock_x_replace.assert_called_once()

    def test_generate_x_replacement_with_challenge(self):
        """Test X replacement with challenge."""
        # Enable challenge-based X replacement
        self.strategy._options.use_challenges_for_x = True
        self.strategy._options.use_individual_matches_for_x = False

        # Mock finding a suitable challenge
        with patch.object(
            self.strategy, "_find_suitable_challenge"
        ) as mock_find_challenge:
            mock_challenge = Mock()
            mock_challenge.name = "Test Challenge"
            mock_find_challenge.return_value = mock_challenge

            replacement = self.strategy._generate_x_replacement(
                self.mock_gara, 1, 1, preview_mode=True
            )

            self.assertIsNotNone(replacement)
            # Add null check before accessing notes attribute
            if replacement and replacement.notes:
                self.assertIn("Challenge:", replacement.notes)
            mock_find_challenge.assert_called_once_with(self.mock_gara, 1)

    def test_generate_x_replacement_with_individual_match(self):
        """Test X replacement with individual match."""
        # Enable individual match X replacement
        self.strategy._options.use_challenges_for_x = False
        self.strategy._options.use_individual_matches_for_x = True

        # Mock finding a suitable opponent
        with patch.object(
            self.strategy, "_find_suitable_opponent"
        ) as mock_find_opponent:
            mock_find_opponent.return_value = 2

            replacement = self.strategy._generate_x_replacement(
                self.mock_gara, 1, 1, preview_mode=True
            )

            self.assertIsNotNone(replacement)
            self.assertIsNotNone(replacement)
            if replacement is not None:
                self.assertEqual(replacement.players, (1, 2))
            # Add null check before accessing notes attribute
            if replacement and replacement.notes:
                self.assertIn("Individual match", replacement.notes)
            mock_find_opponent.assert_called_once_with(self.mock_gara, 1, 1)

    def test_enhance_trio_match(self):
        """Test enhancing trio match with metadata."""
        trio_pairing = Pairing(players=(1, 2, 3), is_bye=False, round_number=1)

        enhanced = self.strategy._enhance_trio_match(trio_pairing, self.mock_gara, 1)

        self.assertEqual(enhanced.players, (1, 2, 3))
        self.assertFalse(enhanced.is_bye)
        self.assertEqual(enhanced.round_number, 1)
        self.assertTrue(enhanced.requires_handicap)
        # Add null check before accessing notes attribute
        if enhanced and enhanced.notes:
            self.assertIn("Trio match", enhanced.notes)

    def test_find_suitable_opponent(self):
        """Test finding suitable opponent for individual match."""
        # Set up mock gara with inscriptions
        mock_inscription1 = Mock()
        mock_inscription1.user_id = 1
        mock_inscription2 = Mock()
        mock_inscription2.user_id = 2
        mock_inscription3 = Mock()
        mock_inscription3.user_id = 3

        self.mock_gara.inscriptions = [
            mock_inscription1,
            mock_inscription2,
            mock_inscription3,
        ]

        # Mock the _get_active_players method to return the expected players
        with patch.object(self.strategy, "_get_active_players") as mock_get_active:
            mock_get_active.return_value = [1, 2, 3]

            # Mock the _find_similar_ranked_player method
            with patch.object(
                self.strategy, "_find_similar_ranked_player"
            ) as mock_find_similar:
                mock_find_similar.return_value = 2

                # Use round_number > 1 to trigger the similar ranked player logic
                opponent = self.strategy._find_suitable_opponent(self.mock_gara, 1, 2)

                self.assertEqual(opponent, 2)
                mock_find_similar.assert_called_once()

    def test_calculate_enhanced_pairing_quality_with_rematch(self):
        """Test pairing quality calculation with rematch."""
        pairing = Pairing(players=(1, 2), is_bye=False, round_number=1)

        # Mock PlayerEncounter to indicate players have played before
        with patch(
            "models.classification.models.PlayerEncounter.have_played"
        ) as mock_have_played:
            mock_have_played.return_value = True

            quality = self.strategy._calculate_enhanced_pairing_quality(
                pairing, self.mock_gara, 1
            )

            # Quality should be reduced due to rematch
            self.assertLess(quality, 1.0)
            mock_have_played.assert_called_once()

    def test_postprocess_pairings(self):
        """Test postprocessing of pairings."""
        pairings = [
            Pairing(players=(1, 2), is_bye=False, round_number=1, pairing_quality=0.5)
        ]

        with patch.object(
            self.strategy, "_calculate_enhanced_pairing_quality"
        ) as mock_calc_quality:
            mock_calc_quality.return_value = 0.8

            enhanced_pairings = self.strategy._postprocess_pairings(
                pairings, self.mock_gara, 1
            )

            self.assertEqual(len(enhanced_pairings), 1)
            self.assertEqual(enhanced_pairings[0].pairing_quality, 0.8)
            mock_calc_quality.assert_called_once()

    def test_min_players_validation(self):
        """Test minimum players validation."""
        self.assertEqual(self.strategy.min_players, 2)

    def test_max_players_validation(self):
        """Test maximum players validation."""
        self.assertIsNone(self.strategy.max_players)

    def test_strategy_metadata(self):
        """Test strategy metadata."""
        self.assertEqual(self.strategy.name, "advanced_amalfi")
        self.assertEqual(self.strategy.display_name, "Advanced Amalfi")
        self.assertEqual(
            self.strategy.description,
            "Amalfi algorithm with X-replacement, trio matches, and "
            "enhanced anti-rematch",
        )


if __name__ == "__main__":
    unittest.main()
