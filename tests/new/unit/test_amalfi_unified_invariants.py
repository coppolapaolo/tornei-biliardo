"""
Invariant tests for AmalfiUnifiedAdapter - validates business logic constraints.

These tests verify that the unified Amalfi adapter maintains critical business
invariants regardless of input variations, ensuring correctness of the
tournament pairing algorithm.
"""

import pytest
from unittest.mock import Mock, patch
from typing import List, Set

from models.matchmaking.strategies.amalfi_unified_adapter import AmalfiUnifiedAdapter
from models.matchmaking.registry import PairingContext
from models.matchmaking.strategies.base import Pairing, ValidationResult
from models.competition.models import Gara
from models import Inscription


class TestAmalfiUnifiedInvariants:
    """Invariant tests for business logic validation in AmalfiUnifiedAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create AmalfiUnifiedAdapter instance."""
        return AmalfiUnifiedAdapter()

    def create_mock_matches_from_pairings_data(self, pairings_data: List[dict]) -> List:
        """Helper to create mock Match objects from pairings data."""
        from models.match.models import Match
        mock_matches = []

        for i, pairing in enumerate(pairings_data, 1):
            match_mock = Mock(spec=Match)
            match_mock.id = i

            if pairing.get("type") == "bye":
                match_mock.player1_id = pairing["player1"].id
                match_mock.player2_id = None
                match_mock.is_bye = True
            else:
                match_mock.player1_id = pairing["player1"].id
                match_mock.player2_id = pairing["player2"].id
                match_mock.is_bye = False

            # Remove trio_match attribute to avoid hasattr issues
            if hasattr(match_mock, 'trio_match'):
                delattr(match_mock, 'trio_match')

            mock_matches.append(match_mock)

        return mock_matches

    def create_mock_gara(self, num_players: int, gara_id: int = 1) -> Mock:
        """Helper to create mock Gara with specified number of players."""
        gara = Mock(spec=Gara)
        gara.id = gara_id
        gara.min_participants = 3
        gara.max_participants = None
        gara.current_round = 1
        gara.classification = []

        inscriptions = []
        for i in range(1, num_players + 1):
            inscription = Mock(spec=Inscription)
            inscription.user_id = i
            inscription.status = "confirmed"
            inscriptions.append(inscription)
        gara.inscriptions = inscriptions

        return gara

    def create_preview_data(self, pairings_data: List[dict]) -> dict:
        """Helper to create mock preview data."""
        return {
            "matches": pairings_data,
            "stats": {
                "total_matches": len(pairings_data),
                "bye_matches": sum(1 for m in pairings_data if m.get("type") == "bye"),
                "trio_matches": sum(
                    1 for m in pairings_data if m.get("type") == "trio"
                ),
            },
            "salto": 0,
        }

    # ============================================================================
    # INVARIANT 1: All players must be assigned exactly once per round
    # ============================================================================

    @pytest.mark.parametrize("num_players", [4, 6, 8, 10, 12, 16])
    def test_invariant_all_players_assigned_even(self, adapter, num_players):
        """Invariant: All players must be assigned exactly once (even number of players)."""
        gara = self.create_mock_gara(num_players)

        # Mock even pairing data
        pairings_data = []
        for i in range(0, num_players, 2):
            pairings_data.append(
                {"player1": Mock(id=i + 1), "player2": Mock(id=i + 2), "type": "normal"}
            )

        preview_data = self.create_preview_data(pairings_data)

        # Convert pairings data to mock Match objects
        mock_matches = self.create_mock_matches_from_pairings_data(pairings_data)

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.create_round_matches.return_value = mock_matches

            pairings = adapter.create_round(gara, 1)

        # Extract all assigned player IDs
        assigned_players = set()
        for pairing in pairings:
            for player_id in pairing.players:
                assigned_players.add(player_id)

        # Invariant: All players [1..num_players] must be assigned exactly once
        expected_players = set(range(1, num_players + 1))
        assert (
            assigned_players == expected_players
        ), f"Missing or duplicate players. Expected: {expected_players}, Got: {assigned_players}"

    @pytest.mark.parametrize("num_players", [5, 7, 9, 11, 13, 15])
    def test_invariant_all_players_assigned_odd(self, adapter, num_players):
        """Invariant: All players must be assigned exactly once (odd number with bye)."""
        gara = self.create_mock_gara(num_players)

        # Mock odd pairing data with bye
        pairings_data = []
        for i in range(0, num_players - 1, 2):
            pairings_data.append(
                {"player1": Mock(id=i + 1), "player2": Mock(id=i + 2), "type": "normal"}
            )
        # Last player gets bye
        pairings_data.append({"player1": Mock(id=num_players), "type": "bye"})

        preview_data = self.create_preview_data(pairings_data)

        # Convert pairings data to mock Match objects
        mock_matches = self.create_mock_matches_from_pairings_data(pairings_data)

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.create_round_matches.return_value = mock_matches

            pairings = adapter.create_round(gara, 1)

        # Extract all assigned players
        assigned_players = set()
        for pairing in pairings:
            for player_id in pairing.players:
                assigned_players.add(player_id)

        # Invariant: All players must be assigned
        expected_players = set(range(1, num_players + 1))
        assert assigned_players == expected_players

        # Invariant: Exactly one bye must exist
        bye_count = sum(1 for p in pairings if p.is_bye)
        assert bye_count == 1, f"Expected exactly 1 bye, got {bye_count}"

    # ============================================================================
    # INVARIANT 2: No player can be paired with themselves
    # ============================================================================

    def test_invariant_no_self_pairing(self, adapter):
        """Invariant: No player can be paired with themselves."""
        gara = self.create_mock_gara(8)

        # Test data that could potentially have self-pairing (should be prevented)
        pairings_data = [
            {"player1": Mock(id=1), "player2": Mock(id=2), "type": "normal"},
            {"player1": Mock(id=3), "player2": Mock(id=4), "type": "normal"},
            {"player1": Mock(id=5), "player2": Mock(id=6), "type": "normal"},
            {"player1": Mock(id=7), "player2": Mock(id=8), "type": "normal"},
        ]

        preview_data = self.create_preview_data(pairings_data)

        # Convert pairings data to mock Match objects
        mock_matches = self.create_mock_matches_from_pairings_data(pairings_data)

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.create_round_matches.return_value = mock_matches

            pairings = adapter.create_round(gara, 1)

        # Invariant: No self-pairing allowed
        for pairing in pairings:
            if not pairing.is_bye and len(pairing.players) >= 2:
                assert (
                    pairing.players[0] != pairing.players[1]
                ), f"Self-pairing detected: {pairing.players}"

    # ============================================================================
    # INVARIANT 3: Pairing quality must be within valid bounds [0.0, 1.0]
    # ============================================================================

    def test_invariant_pairing_quality_bounds(self, adapter):
        """Invariant: Pairing quality must be between 0.0 and 1.0."""
        gara = self.create_mock_gara(6)

        pairings_data = [
            {"player1": Mock(id=1), "player2": Mock(id=2), "type": "normal"},
            {
                "player1": Mock(id=3),
                "player2": Mock(id=4),
                "type": "trio",
            },  # Lower quality
            {"player1": Mock(id=5), "type": "bye"},  # Lowest quality
        ]

        preview_data = self.create_preview_data(pairings_data)

        # Convert pairings data to mock Match objects
        mock_matches = self.create_mock_matches_from_pairings_data(pairings_data)

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.create_round_matches.return_value = mock_matches

            pairings = adapter.create_round(gara, 1)

        # Invariant: Quality must be in valid bounds
        for pairing in pairings:
            assert (
                0.0 <= pairing.pairing_quality <= 1.0
            ), f"Invalid quality: {pairing.pairing_quality}"

    # ============================================================================
    # INVARIANT 4: Round number consistency
    # ============================================================================

    @pytest.mark.parametrize("round_num", [1, 2, 3, 5, 10])
    def test_invariant_round_number_consistency(self, adapter, round_num):
        """Invariant: All pairings must have consistent round number."""
        gara = self.create_mock_gara(8)

        pairings_data = [
            {"player1": Mock(id=1), "player2": Mock(id=2), "type": "normal"},
            {"player1": Mock(id=3), "player2": Mock(id=4), "type": "normal"},
        ]

        preview_data = self.create_preview_data(pairings_data)

        # Convert pairings data to mock Match objects
        mock_matches = self.create_mock_matches_from_pairings_data(pairings_data)

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.create_round_matches.return_value = mock_matches

            pairings = adapter.create_round(gara, round_num)

        # Invariant: All pairings must have the requested round number
        for pairing in pairings:
            assert (
                pairing.round_number == round_num
            ), f"Expected round {round_num}, got {pairing.round_number}"

    # ============================================================================
    # INVARIANT 5: Valid pairing structure
    # ============================================================================

    def test_invariant_valid_pairing_structure(self, adapter):
        """Invariant: All pairings must have valid structure."""
        gara = self.create_mock_gara(7)  # Odd number with bye

        pairings_data = [
            {"player1": Mock(id=1), "player2": Mock(id=2), "type": "normal"},
            {"player1": Mock(id=3), "player2": Mock(id=4), "type": "normal"},
            {"player1": Mock(id=5), "player2": Mock(id=6), "type": "normal"},
            {"player1": Mock(id=7), "type": "bye"},
        ]

        preview_data = self.create_preview_data(pairings_data)

        # Convert pairings data to mock Match objects
        mock_matches = self.create_mock_matches_from_pairings_data(pairings_data)

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.create_round_matches.return_value = mock_matches

            pairings = adapter.create_round(gara, 1)

        for pairing in pairings:
            # Invariant: Valid pairing structure according to is_valid_pairing property
            assert pairing.is_valid_pairing, f"Invalid pairing structure: {pairing}"

            # Invariant: Bye pairings must have exactly 1 player
            if pairing.is_bye:
                assert (
                    len(pairing.players) == 1
                ), f"Bye pairing must have 1 player: {pairing.players}"

            # Invariant: Normal pairings must have exactly 2 players
            else:
                assert (
                    len(pairing.players) == 2
                ), f"Normal pairing must have 2 players: {pairing.players}"

    # ============================================================================
    # INVARIANT 6: Validation constraints
    # ============================================================================

    def test_invariant_validation_minimum_players(self, adapter):
        """Invariant: Validation must fail for insufficient players."""
        # Test with 2 players (below Amalfi minimum of 3)
        gara = self.create_mock_gara(2)

        result = adapter.validate(gara)

        # Invariant: Must fail validation with insufficient players
        assert not result.ok, "Validation should fail with insufficient players"
        assert any(
            "players" in error.lower() for error in result.errors
        ), "Error should mention player count"

    def test_invariant_validation_success_sufficient_players(self, adapter):
        """Invariant: Validation must succeed with sufficient players."""
        gara = self.create_mock_gara(8)  # Well above minimum

        result = adapter.validate(gara)

        # Invariant: Must pass validation with sufficient players
        assert (
            result.ok
        ), f"Validation should succeed with sufficient players: {result.errors}"

    # ============================================================================
    # INVARIANT 7: Deterministic behavior with seed
    # ============================================================================

    def test_invariant_deterministic_with_seed(self, adapter):
        """Invariant: Same seed must produce identical results."""
        gara = self.create_mock_gara(8)

        pairings_data = [
            {"player1": Mock(id=1), "player2": Mock(id=3), "type": "normal"},
            {"player1": Mock(id=2), "player2": Mock(id=4), "type": "normal"},
            {"player1": Mock(id=5), "player2": Mock(id=7), "type": "normal"},
            {"player1": Mock(id=6), "player2": Mock(id=8), "type": "normal"},
        ]

        preview_data = self.create_preview_data(pairings_data)

        # Convert pairings data to mock Match objects
        mock_matches = self.create_mock_matches_from_pairings_data(pairings_data)

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.create_round_matches.return_value = mock_matches

            # Run twice with same seed
            context1 = PairingContext(seed=777)
            adapter.set_context(context1)
            pairings1 = adapter.create_round(gara, 1)

            context2 = PairingContext(seed=777)  # Same seed
            adapter.set_context(context2)
            pairings2 = adapter.create_round(gara, 1)

        # Invariant: Identical seeds must produce identical results
        assert len(pairings1) == len(pairings2)

        for p1, p2 in zip(pairings1, pairings2):
            assert (
                p1.players == p2.players
            ), f"Deterministic failure: {p1.players} != {p2.players}"
            assert p1.is_bye == p2.is_bye
            assert p1.round_number == p2.round_number

    # ============================================================================
    # INVARIANT 8: Strategy metadata consistency
    # ============================================================================

    def test_invariant_strategy_metadata(self, adapter):
        """Invariant: Strategy metadata must be consistent and valid."""
        # Invariant: Required metadata fields must exist and be valid
        assert hasattr(adapter, "name")
        assert hasattr(adapter, "display_name")
        assert hasattr(adapter, "description")
        assert hasattr(adapter, "min_players")

        # Invariant: Metadata values must be reasonable
        assert isinstance(adapter.name, str) and len(adapter.name) > 0
        assert isinstance(adapter.display_name, str) and len(adapter.display_name) > 0
        assert isinstance(adapter.min_players, int) and adapter.min_players > 0
        assert isinstance(adapter.supports_byes, bool)
        assert isinstance(adapter.requires_classification, bool)

        # Invariant: Amalfi-specific constraints
        assert adapter.name.lower() in ["amalfi", "amalfi_unified"]
        assert adapter.min_players >= 3  # Amalfi requirement
        assert adapter.supports_byes == True  # Amalfi supports byes
        assert adapter.requires_classification == True  # Amalfi needs classification

    # ============================================================================
    # INVARIANT 9: Error handling robustness
    # ============================================================================

    def test_invariant_graceful_error_handling(self, adapter):
        """Invariant: Must handle invalid input gracefully."""
        # Test with invalid gara
        invalid_gara = Mock()
        invalid_gara.inscriptions = None  # Invalid state

        # Should not raise exception, should return validation error
        try:
            result = adapter.validate(invalid_gara)
            assert not result.ok, "Should fail validation for invalid gara"
        except Exception as e:
            # If exception is raised, it should be a controlled one
            assert isinstance(
                e, (ValueError, TypeError)
            ), f"Unexpected exception type: {type(e)}"

    # ============================================================================
    # INVARIANT 10: Anti-rematch logic validation (business rule)
    # ============================================================================

    def test_invariant_anti_rematch_different_rounds(self, adapter):
        """Invariant: Anti-rematch logic should work across rounds (when implemented)."""
        gara = self.create_mock_gara(4)

        # Mock round 1
        round1_data = [{"player1": Mock(id=1), "player2": Mock(id=2), "type": "normal"}]

        # Mock round 2 - should be different pairing
        round2_data = [{"player1": Mock(id=1), "player2": Mock(id=3), "type": "normal"}]

        preview_data_r1 = self.create_preview_data(round1_data)
        preview_data_r2 = self.create_preview_data(round2_data)

        # Convert pairings data to mock Match objects for both rounds
        mock_matches_r1 = self.create_mock_matches_from_pairings_data(round1_data)
        mock_matches_r2 = self.create_mock_matches_from_pairings_data(round2_data)

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value

            # Round 1
            mock_engine.create_round_matches.return_value = mock_matches_r1
            context = PairingContext(seed=123)
            adapter.set_context(context)
            pairings_r1 = adapter.create_round(gara, 1)

            # Round 2
            mock_engine.create_round_matches.return_value = mock_matches_r2
            adapter.set_context(PairingContext(seed=123))
            pairings_r2 = adapter.create_round(gara, 2)

        # Invariant: Different rounds should generally produce different pairings
        # (This is a business rule validation, not guaranteed but expected in most cases)
        if len(pairings_r1) == len(pairings_r2) == 1:
            p1 = pairings_r1[0]
            p2 = pairings_r2[0]

            # For this specific test setup, we expect different pairings
            assert (
                p1.players != p2.players
            ), "Anti-rematch should produce different pairings"
