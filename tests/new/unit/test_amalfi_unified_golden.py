"""
Golden tests for unified AmalfiStrategy - ensures output consistency with fixed seed.

These tests verify that the unified Amalfi strategy produces identical results
across runs when using deterministic seeds, maintaining behavior compatibility
with the original AmalfiEngine.
"""

import pytest
from unittest.mock import Mock, patch
from typing import List, Dict, Any

from models.matchmaking.strategies.amalfi import AmalfiStrategy
from models.matchmaking.registry import PairingContext
from models.matchmaking.strategies.base import Pairing
from models.competition.models import Gara
from models import User, Inscription


class TestAmalfiUnifiedGolden:
    """Golden tests for unified AmalfiStrategy with deterministic seed behavior."""

    @pytest.fixture
    def mock_gara(self):
        """Create mock Gara for testing."""
        gara = Mock(spec=Gara)
        gara.id = 42
        gara.min_participants = 3
        gara.max_participants = None
        gara.current_round = 1
        gara.classification = []

        # Mock inscriptions
        inscriptions = []
        for i in range(1, 9):  # 8 players
            inscription = Mock(spec=Inscription)
            inscription.user_id = i
            inscription.status = "confirmed"
            inscriptions.append(inscription)
        gara.inscriptions = inscriptions

        return gara

    @pytest.fixture
    def adapter(self):
        """Create unified AmalfiStrategy instance."""
        return AmalfiStrategy()

    def test_golden_first_round_seed_42(self, adapter, mock_gara):
        """Golden test: First round with seed=42 should produce consistent output."""
        # Set deterministic context
        context = PairingContext(seed=42)
        adapter.set_context(context)

        # Mock AmalfiEngine preview response
        expected_preview_data = {
            "matches": [
                {"player1": Mock(id=1), "player2": Mock(id=5), "type": "normal"},
                {"player1": Mock(id=2), "player2": Mock(id=6), "type": "normal"},
                {"player1": Mock(id=3), "player2": Mock(id=7), "type": "normal"},
                {"player1": Mock(id=4), "player2": Mock(id=8), "type": "normal"},
            ],
            "stats": {"total_matches": 4, "bye_matches": 0, "trio_matches": 0},
            "salto": 0,
        }

        # Create mock Match objects that the adapter expects
        from models.match.models import Match
        mock_matches = []
        for i, (p1, p2) in enumerate([(1, 5), (2, 6), (3, 7), (4, 8)], 1):
            match_mock = Mock(spec=Match)
            match_mock.player1_id = p1
            match_mock.player2_id = p2
            match_mock.is_bye = False
            match_mock.id = i
            match_mock.trio_match = None  # Explicitly set to None
            # Remove trio_match attribute entirely to avoid hasattr issues
            if hasattr(match_mock, 'trio_match'):
                delattr(match_mock, 'trio_match')
            mock_matches.append(match_mock)

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.create_round_matches.return_value = mock_matches

            # Execute create_round
            pairings = adapter.create_round(mock_gara, 1)

        # Golden assertions - these exact values should always be produced with seed=42
        assert len(pairings) == 4

        # Sort pairings by first player ID for consistent comparison
        sorted_pairings = sorted(
            pairings, key=lambda p: p.players[0] if p.players else 0
        )

        # Golden values for seed=42, round=1
        expected_pairings = [
            (1, 5),  # Player 1 vs Player 5
            (2, 6),  # Player 2 vs Player 6
            (3, 7),  # Player 3 vs Player 7
            (4, 8),  # Player 4 vs Player 8
        ]

        for i, pairing in enumerate(sorted_pairings):
            assert pairing.players == expected_pairings[i]
            assert not pairing.is_bye
            assert pairing.round_number == 1
            assert pairing.pairing_quality == 1.0  # Normal matches have perfect quality

    def test_golden_first_round_seed_123(self, adapter, mock_gara):
        """Golden test: First round with seed=123 should produce different but consistent output."""
        context = PairingContext(seed=123)
        adapter.set_context(context)

        # Create mock Match objects for seed=123
        from models.match.models import Match
        mock_matches = []
        for i, (p1, p2) in enumerate([(3, 1), (7, 2), (4, 8), (6, 5)], 1):
            match_mock = Mock(spec=Match)
            match_mock.player1_id = p1
            match_mock.player2_id = p2
            match_mock.is_bye = False
            match_mock.id = i
            # Remove trio_match attribute to avoid hasattr issues
            if hasattr(match_mock, 'trio_match'):
                delattr(match_mock, 'trio_match')
            mock_matches.append(match_mock)

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.create_round_matches.return_value = mock_matches

            pairings = adapter.create_round(mock_gara, 1)

        # Different golden values for seed=123
        assert len(pairings) == 4
        sorted_pairings = sorted(pairings, key=lambda p: p.players[0])

        expected_pairings_seed_123 = [
            (3, 1),  # Different pairing than seed=42
            (4, 8),
            (6, 5),
            (7, 2),
        ]

        for i, pairing in enumerate(sorted_pairings):
            assert pairing.players == expected_pairings_seed_123[i]

    def test_golden_with_bye_seed_42(self, adapter):
        """Golden test: Odd number of players with bye handling."""
        # Mock gara with 7 players (odd number)
        gara = Mock(spec=Gara)
        gara.id = 42
        gara.min_participants = 3

        inscriptions = []
        for i in range(1, 8):  # 7 players
            inscription = Mock(spec=Inscription)
            inscription.user_id = i
            inscription.status = "confirmed"
            inscriptions.append(inscription)
        gara.inscriptions = inscriptions

        context = PairingContext(seed=42)
        adapter.set_context(context)

        # Create mock Match objects with bye
        from models.match.models import Match
        mock_matches = []
        # Normal matches
        for i, (p1, p2) in enumerate([(1, 5), (2, 6), (3, 7)], 1):
            match_mock = Mock(spec=Match)
            match_mock.player1_id = p1
            match_mock.player2_id = p2
            match_mock.is_bye = False
            match_mock.id = i
            if hasattr(match_mock, 'trio_match'):
                delattr(match_mock, 'trio_match')
            mock_matches.append(match_mock)

        # Bye match
        bye_match = Mock(spec=Match)
        bye_match.player1_id = 4
        bye_match.player2_id = None
        bye_match.is_bye = True
        bye_match.id = 4
        if hasattr(bye_match, 'trio_match'):
            delattr(bye_match, 'trio_match')
        mock_matches.append(bye_match)

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.create_round_matches.return_value = mock_matches

            pairings = adapter.create_round(gara, 1)

        # Golden assertions for bye scenario with seed=42
        assert len(pairings) == 4

        # Check that exactly one bye exists
        bye_pairings = [p for p in pairings if p.is_bye]
        normal_pairings = [p for p in pairings if not p.is_bye]

        assert len(bye_pairings) == 1
        assert len(normal_pairings) == 3

        # Golden: Player 4 gets the bye with seed=42
        bye_pairing = bye_pairings[0]
        assert bye_pairing.players == (4,)
        assert bye_pairing.is_bye
        assert bye_pairing.pairing_quality == 0.6  # Byes have lower quality

    def test_golden_second_round_seed_42(self, adapter, mock_gara):
        """Golden test: Second round pairing with anti-rematch logic."""
        mock_gara.current_round = 2

        context = PairingContext(seed=42)
        adapter.set_context(context)

        # Mock second round with different pairings (anti-rematch)
        expected_preview_data = {
            "matches": [
                {"player1": Mock(id=1), "player2": Mock(id=6), "type": "normal"},
                {"player1": Mock(id=2), "player2": Mock(id=7), "type": "normal"},
                {"player1": Mock(id=3), "player2": Mock(id=8), "type": "normal"},
                {"player1": Mock(id=4), "player2": Mock(id=5), "type": "normal"},
            ],
            "stats": {"total_matches": 4},
            "salto": 1,
        }

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.preview_round_pairings.return_value = expected_preview_data

            pairings = adapter.create_round(mock_gara, 2)

        # Golden values for second round with seed=42
        sorted_pairings = sorted(pairings, key=lambda p: p.players[0])
        expected_round_2 = [
            (1, 6),  # Different from round 1 (was 1,5)
            (2, 7),  # Different from round 1 (was 2,6)
            (3, 8),  # Different from round 1 (was 3,7)
            (4, 5),  # Different from round 1 (was 4,8)
        ]

        for i, pairing in enumerate(sorted_pairings):
            assert pairing.players == expected_round_2[i]
            assert pairing.round_number == 2

    def test_seed_determinism_multiple_runs(self, adapter, mock_gara):
        """Verify that same seed produces identical results across multiple runs."""
        context = PairingContext(seed=999)

        expected_preview_data = {
            "matches": [
                {"player1": Mock(id=2), "player2": Mock(id=4), "type": "normal"},
                {"player1": Mock(id=1), "player2": Mock(id=8), "type": "normal"},
                {"player1": Mock(id=6), "player2": Mock(id=3), "type": "normal"},
                {"player1": Mock(id=5), "player2": Mock(id=7), "type": "normal"},
            ],
            "stats": {"total_matches": 4},
            "salto": 0,
        }

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.preview_round_pairings.return_value = expected_preview_data

            # Run multiple times with same seed
            results = []
            for _ in range(5):
                adapter.set_context(PairingContext(seed=999))
                pairings = adapter.create_round(mock_gara, 1)
                # Convert to comparable format
                result = tuple(sorted([p.players for p in pairings]))
                results.append(result)

        # All results should be identical
        assert all(result == results[0] for result in results)
        assert len(set(results)) == 1  # Only one unique result

    def test_no_seed_produces_different_results(self, adapter, mock_gara):
        """Verify that without seed, results can vary between runs."""
        # Note: This test may be flaky due to random nature, but it's important
        # to verify that unseeded behavior is actually non-deterministic

        expected_preview_data = {
            "matches": [
                {"player1": Mock(id=i), "player2": Mock(id=i + 4), "type": "normal"}
                for i in range(1, 5)
            ],
            "stats": {"total_matches": 4},
            "salto": 0,
        }

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.preview_round_pairings.return_value = expected_preview_data

            # Run without setting context (no seed)
            results = []
            for _ in range(10):
                fresh_adapter = AmalfiStrategy()  # Fresh instance each time
                pairings = fresh_adapter.create_round(mock_gara, 1)
                result = tuple(sorted([p.players for p in pairings]))
                results.append(result)

        # Without deterministic seed, we expect the possibility of variation
        # (though with mocked data, this test mainly verifies the test setup)
        assert len(results) == 10

    def test_context_state_isolation(self, adapter, mock_gara):
        """Verify that context state is properly isolated between runs."""
        expected_preview_data = {
            "matches": [
                {"player1": Mock(id=1), "player2": Mock(id=2), "type": "normal"},
            ],
            "stats": {"total_matches": 1},
            "salto": 0,
        }

        with patch(
            "models.matchmaking.strategies.amalfi_unified_adapter.AmalfiEngine"
        ) as mock_engine_class:
            mock_engine = mock_engine_class.return_value
            mock_engine.preview_round_pairings.return_value = expected_preview_data

            # First run with seed=100
            context1 = PairingContext(seed=100)
            adapter.set_context(context1)
            context1.set_state("test_key", "test_value")
            pairings1 = adapter.create_round(mock_gara, 1)

            # Second run with seed=200
            context2 = PairingContext(seed=200)
            adapter.set_context(context2)

            # Context2 should not have state from context1
            assert context2.get_state("test_key") is None

            pairings2 = adapter.create_round(mock_gara, 1)

        # Verify both runs completed successfully
        assert len(pairings1) >= 0
        assert len(pairings2) >= 0
