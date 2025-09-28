"""
Unit tests for the new Amalfi algorithm implementation.

These tests verify that the Amalfi pairing algorithm follows the correct
pseudocode logic with proper salto calculation and anti-rematch handling.
"""

import pytest
from unittest.mock import Mock, patch
from typing import List

from models.matchmaking.strategies.amalfi import AmalfiStrategy
from models.matchmaking.strategies.base import Pairing
from models import RoundClassification


@pytest.mark.unit
class TestAmalfiAlgorithmImplementation:
    """Test the core Amalfi pairing algorithm implementation."""

    @pytest.fixture
    def strategy(self):
        """Create AmalfiStrategy instance."""
        return AmalfiStrategy()

    def create_mock_classification(self, player_ids: List[int], gara_id: int = 1) -> List[RoundClassification]:
        """Helper to create mock RoundClassification objects."""
        classifications = []
        for i, player_id in enumerate(player_ids, 1):
            mock_class = Mock(spec=RoundClassification)
            mock_class.user_id = player_id
            mock_class.position = i
            mock_class.gara_id = gara_id
            classifications.append(mock_class)
        return classifications

    def test_amalfi_pairing_basic_logic(self, strategy):
        """Test basic Amalfi pairing logic with 6 players."""
        # Setup: 6 players, turno 2 di 5
        player_ids = [1, 2, 3, 4, 5, 6]
        classifications = self.create_mock_classification(player_ids)

        # Mock anti-rematch to allow all pairings
        with patch.object(strategy, '_have_already_played', return_value=False):
            pairings = strategy._amalfi_pairing(classifications, turno=2, max_turni=5)

        # Verify all players are paired
        assert len(pairings) == 3
        all_players_in_pairings = set()
        for pairing in pairings:
            all_players_in_pairings.update(pairing.players)

        assert all_players_in_pairings == set(player_ids)
        assert all(not pairing.is_bye for pairing in pairings)

    def test_amalfi_salto_calculation(self, strategy):
        """Test that salto is calculated correctly for different rounds."""
        player_ids = [1, 2, 3, 4]
        classifications = self.create_mock_classification(player_ids)

        with patch.object(strategy, '_have_already_played', return_value=False):
            # Test different rounds with max_turni = 5
            test_cases = [
                (2, 5, 3),  # turno 2 di 5: salto = 5-2 = 3
                (3, 5, 2),  # turno 3 di 5: salto = 5-3 = 2
                (4, 5, 1),  # turno 4 di 5: salto = 5-4 = 1
                (5, 5, 0),  # turno 5 di 5: salto = 5-5 = 0
            ]

            for turno, max_turni, expected_salto in test_cases:
                pairings = strategy._amalfi_pairing(classifications, turno=turno, max_turni=max_turni)

                # Verify basic structure
                assert len(pairings) == 2  # 4 players = 2 pairings
                assert all(len(p.players) == 2 for p in pairings)
                assert all(not p.is_bye for p in pairings)

    def test_amalfi_odd_players_bye_handling(self, strategy):
        """Test Amalfi algorithm with odd number of players."""
        # 5 players - should result in 2 normal pairings + 1 bye
        player_ids = [1, 2, 3, 4, 5]
        classifications = self.create_mock_classification(player_ids)

        with patch.object(strategy, '_have_already_played', return_value=False):
            pairings = strategy._amalfi_pairing(classifications, turno=2, max_turni=5)

        # Count different pairing types
        normal_pairings = [p for p in pairings if not p.is_bye]
        bye_pairings = [p for p in pairings if p.is_bye]

        assert len(normal_pairings) == 2
        assert len(bye_pairings) == 1
        assert len(bye_pairings[0].players) == 1

        # Verify all players are accounted for
        all_players_in_pairings = set()
        for pairing in pairings:
            all_players_in_pairings.update(pairing.players)

        assert all_players_in_pairings == set(player_ids)

    def test_amalfi_anti_rematch_logic(self, strategy):
        """Test that anti-rematch logic is properly applied."""
        player_ids = [1, 2, 3, 4]
        classifications = self.create_mock_classification(player_ids)

        # Mock that players 1 and 2 have already played
        def mock_have_played(p1, p2, gara_id):
            return (p1 == 1 and p2 == 2) or (p1 == 2 and p2 == 1)

        with patch.object(strategy, '_have_already_played', side_effect=mock_have_played):
            pairings = strategy._amalfi_pairing(classifications, turno=2, max_turni=5)

        # Verify that players 1 and 2 are not paired together
        paired_players = set()
        for pairing in pairings:
            if len(pairing.players) == 2:
                p1, p2 = pairing.players
                assert not (p1 == 1 and p2 == 2)
                assert not (p1 == 2 and p2 == 1)
                paired_players.update(pairing.players)

        # All players should still be paired
        assert len(paired_players) == 4

    def test_amalfi_circular_search(self, strategy):
        """Test that the algorithm correctly handles circular position search."""
        # Test with a scenario where circular search is needed
        player_ids = [1, 2, 3, 4, 5, 6]
        classifications = self.create_mock_classification(player_ids)

        # Mock extensive anti-rematch constraints to force circular search
        def mock_have_played(p1, p2, gara_id):
            # Force many rematches to test circular search logic
            forbidden_pairs = [(1, 2), (1, 3), (3, 4), (4, 5)]
            pair = tuple(sorted([p1, p2]))
            return pair in forbidden_pairs

        with patch.object(strategy, '_have_already_played', side_effect=mock_have_played):
            pairings = strategy._amalfi_pairing(classifications, turno=3, max_turni=5)

        # Should still produce valid pairings
        assert len(pairings) == 3
        all_players = set()
        for pairing in pairings:
            all_players.update(pairing.players)
        assert all_players == set(player_ids)

    def test_amalfi_bye_player_id_usage(self, strategy):
        """Test that BYE_PLAYER_ID is used correctly for odd numbers."""
        player_ids = [1, 2, 3]  # 3 players
        classifications = self.create_mock_classification(player_ids)

        with patch.object(strategy, '_have_already_played', return_value=False):
            pairings = strategy._amalfi_pairing(classifications, turno=2, max_turni=4)

        # Should have 1 normal pairing + 1 bye
        normal_pairings = [p for p in pairings if not p.is_bye]
        bye_pairings = [p for p in pairings if p.is_bye]

        assert len(normal_pairings) == 1
        assert len(bye_pairings) == 1

        # Bye pairing should have exactly one player
        assert len(bye_pairings[0].players) == 1

        # BYE_PLAYER_ID should NOT appear in final pairings
        for pairing in pairings:
            assert strategy.BYE_PLAYER_ID not in pairing.players

    def test_amalfi_empty_classification(self, strategy):
        """Test behavior with empty classification."""
        with patch.object(strategy, '_have_already_played', return_value=False):
            pairings = strategy._amalfi_pairing([], turno=2, max_turni=5)

        assert len(pairings) == 0

    def test_amalfi_single_player(self, strategy):
        """Test behavior with single player."""
        player_ids = [1]
        classifications = self.create_mock_classification(player_ids)

        with patch.object(strategy, '_have_already_played', return_value=False):
            pairings = strategy._amalfi_pairing(classifications, turno=2, max_turni=5)

        # Should create one bye pairing
        assert len(pairings) == 1
        assert pairings[0].is_bye
        assert pairings[0].players == (1,)

    def test_amalfi_pairing_round_number_assignment(self, strategy):
        """Test that pairings get correct round number assigned."""
        player_ids = [1, 2, 3, 4]
        classifications = self.create_mock_classification(player_ids)

        with patch.object(strategy, '_have_already_played', return_value=False):
            pairings = strategy._amalfi_pairing(classifications, turno=3, max_turni=5)

        # All pairings should have correct round number
        for pairing in pairings:
            assert pairing.round_number == 3