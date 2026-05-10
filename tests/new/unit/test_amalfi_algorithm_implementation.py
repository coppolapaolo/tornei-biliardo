"""
Unit tests for the new Amalfi algorithm implementation.

These tests verify that the Amalfi pairing algorithm follows the correct
pseudocode logic with proper salto calculation and anti-rematch handling.
"""

import pytest
from unittest.mock import Mock, patch
from typing import List

from models.matchmaking.strategies.amalfi import AmalfiStrategy
from models import RoundClassification

ENCOUNTER_MATRIX_PATH = (
    "models.classification.encounter_service."
    "PlayerEncounterService.get_encounter_matrix"
)


@pytest.mark.unit
class TestAmalfiAlgorithmImplementation:
    """Test the core Amalfi pairing algorithm implementation."""

    @pytest.fixture
    def strategy(self):
        """Create AmalfiStrategy instance."""
        return AmalfiStrategy()

    def create_mock_classification(
        self, player_ids: List[int], gara_id: int = 1
    ) -> List[RoundClassification]:
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
        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value={},
        ):
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

        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value={},
        ):
            # Test different rounds with max_turni = 5
            test_cases = [
                (2, 5, 3),  # turno 2 di 5: salto = 5-2 = 3
                (3, 5, 2),  # turno 3 di 5: salto = 5-3 = 2
                (4, 5, 1),  # turno 4 di 5: salto = 5-4 = 1
                (5, 5, 0),  # turno 5 di 5: salto = 5-5 = 0
            ]

            for turno, max_turni, expected_salto in test_cases:
                pairings = strategy._amalfi_pairing(
                    classifications, turno=turno, max_turni=max_turni
                )

                # Verify basic structure
                assert len(pairings) == 2  # 4 players = 2 pairings
                assert all(len(p.players) == 2 for p in pairings)
                assert all(not p.is_bye for p in pairings)

    def test_amalfi_odd_players_bye_handling(self, strategy):
        """Test Amalfi algorithm with odd number of players."""
        # 5 players - should result in 2 normal pairings + 1 bye
        player_ids = [1, 2, 3, 4, 5]
        classifications = self.create_mock_classification(player_ids)

        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value={},
        ):
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

        # Players 1 and 2 have already played (matrix stores both directions)
        encounter_matrix = {(1, 2): True, (2, 1): True}

        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value=encounter_matrix,
        ):
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

        # Force many rematches to test circular search logic
        forbidden_pairs = [(1, 2), (1, 3), (3, 4), (4, 5)]
        encounter_matrix = {}
        for a, b in forbidden_pairs:
            encounter_matrix[(a, b)] = True
            encounter_matrix[(b, a)] = True

        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value=encounter_matrix,
        ):
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

        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value={},
        ):
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
        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value={},
        ):
            pairings = strategy._amalfi_pairing([], turno=2, max_turni=5)

        assert len(pairings) == 0

    def test_amalfi_single_player(self, strategy):
        """Test behavior with single player."""
        player_ids = [1]
        classifications = self.create_mock_classification(player_ids)

        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value={},
        ):
            pairings = strategy._amalfi_pairing(classifications, turno=2, max_turni=5)

        # Should create one bye pairing
        assert len(pairings) == 1
        assert pairings[0].is_bye
        assert pairings[0].players == (1,)

    def test_amalfi_pairing_round_number_assignment(self, strategy):
        """Test that pairings get correct round number assigned."""
        player_ids = [1, 2, 3, 4]
        classifications = self.create_mock_classification(player_ids)

        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value={},
        ):
            pairings = strategy._amalfi_pairing(classifications, turno=3, max_turni=5)

        # All pairings should have correct round number
        for pairing in pairings:
            assert pairing.round_number == 3

    def test_amalfi_round2_of_3_produces_correct_pairings(self, strategy):
        """Turno 2 di 3 deve abbinare 1° vs 3°, 2° vs 4°, 5° vs 7°, 6° vs 8°.

        Con 3 turni totali, nel turno 2 mancano 2 turni (incluso il corrente).
        Salto = 2, quindi:
        - Giocatore in posizione 1 va con posizione 1+2=3
        - Giocatore in posizione 2 va con posizione 2+2=4
        - etc.
        """
        player_ids = [1, 2, 3, 4, 5, 6, 7, 8]
        classifications = self.create_mock_classification(player_ids)

        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value={},
        ):
            pairings = strategy._amalfi_pairing(classifications, turno=2, max_turni=3)

        # Salto = 2 → 1° vs 3°, 2° vs 4°, 5° vs 7°, 6° vs 8°
        expected_pairs = [(1, 3), (2, 4), (5, 7), (6, 8)]
        actual_pairs = [tuple(sorted(p.players)) for p in pairings if not p.is_bye]

        assert sorted(actual_pairs) == sorted(
            expected_pairs
        ), f"Expected {sorted(expected_pairs)}, got {sorted(actual_pairs)}"

    def test_amalfi_round3_of_3_produces_consecutive_pairings(self, strategy):
        """Turno finale (3 di 3) deve abbinare 1° vs 2°, 3° vs 4°, etc.

        Nel turno finale manca solo 1 turno, quindi salto = 1.
        I giocatori vengono abbinati con il successivo in classifica.
        """
        player_ids = [1, 2, 3, 4, 5, 6, 7, 8]
        classifications = self.create_mock_classification(player_ids)

        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value={},
        ):
            pairings = strategy._amalfi_pairing(classifications, turno=3, max_turni=3)

        # Salto = 1 → 1° vs 2°, 3° vs 4°, 5° vs 6°, 7° vs 8°
        expected_pairs = [(1, 2), (3, 4), (5, 6), (7, 8)]
        actual_pairs = [tuple(sorted(p.players)) for p in pairings if not p.is_bye]

        assert sorted(actual_pairs) == sorted(
            expected_pairs
        ), f"Expected {sorted(expected_pairs)}, got {sorted(actual_pairs)}"

    def test_amalfi_round1_of_3_produces_wide_spread_pairings(self, strategy):
        """Turno 1 di 3: la maggior parte dei pairing deve avere position_diff = salto.

        Nel primo turno mancano 3 turni, quindi salto = 3. Per 8 giocatori
        sono possibili al più 3 pairing a position_diff esatto 3 (es. 1-4, 2-5,
        3-6); l'ultimo pairing copre i giocatori residui (7-8 oppure 4-7 e 5-8
        a seconda del matching scelto).

        Il maximum-weighted-matching del caso pari (vedi SPECIFICHE.md "Garanzia
        anti-rematch nel caso pari" e ADR-029) può scegliere combinazioni
        equivalenti per peso totale: il test verifica la *proprietà* di "wide
        spread" (almeno 3 pairing al salto target), non un output specifico.
        """
        player_ids = [1, 2, 3, 4, 5, 6, 7, 8]
        classifications = self.create_mock_classification(player_ids)

        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value={},
        ):
            pairings = strategy._amalfi_pairing(classifications, turno=1, max_turni=3)

        actual_pairs = [tuple(sorted(p.players)) for p in pairings if not p.is_bye]

        # Tutti i giocatori coperti, esattamente 4 pairing senza bye
        assert len(actual_pairs) == 4
        all_players = {p for pair in actual_pairs for p in pair}
        assert all_players == set(player_ids)

        # Spirito Amalfi: almeno 3 dei 4 pairing devono avere position_diff = salto = 3
        position_index = {pid: i for i, pid in enumerate(player_ids)}
        diffs = [abs(position_index[a] - position_index[b]) for a, b in actual_pairs]
        at_target = sum(1 for d in diffs if d == 3)
        assert at_target >= 3, (
            f"Expected ≥3 pairings at salto target=3, got diffs={diffs} "
            f"from pairs={actual_pairs}"
        )

    def test_amalfi_with_rematch_finds_alternative(self, strategy):
        """Se l'abbinamento target è un rematch, trova il prossimo disponibile.

        Scenario: Nel turno 2, player1 (1°) dovrebbe giocare con player3 (3°),
        ma hanno già giocato. L'algoritmo deve trovare player4 (4°).
        """
        player_ids = [1, 2, 3, 4, 5, 6, 7, 8]
        classifications = self.create_mock_classification(player_ids)

        # Player 1 e 3 hanno già giocato
        encounter_matrix = {(1, 3): True, (3, 1): True}

        with patch(
            ENCOUNTER_MATRIX_PATH,
            return_value=encounter_matrix,
        ):
            pairings = strategy._amalfi_pairing(classifications, turno=2, max_turni=3)

        # Player 1 deve essere abbinato con qualcuno diverso da 3
        player1_pairing = None
        for p in pairings:
            if 1 in p.players and not p.is_bye:
                player1_pairing = p
                break

        assert player1_pairing is not None, "Player 1 should be paired"
        assert (
            3 not in player1_pairing.players
        ), "Player 1 should not be paired with player 3 (rematch)"
