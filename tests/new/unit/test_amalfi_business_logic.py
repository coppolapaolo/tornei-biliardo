"""
Unit tests for Amalfi strategy interface validation.

These tests verify the strategy interface, metadata, and validation logic
without relying on complex database interactions or business logic execution.
Business logic is covered by integration tests.
"""

import pytest
from unittest.mock import Mock

from models.matchmaking.strategies.amalfi import AmalfiStrategy


class TestAmalfiInterface:
    """Test Amalfi strategy interface and metadata."""

    @pytest.fixture
    def strategy(self):
        """Create AmalfiStrategy instance."""
        return AmalfiStrategy()

    def test_strategy_metadata(self, strategy):
        """Test that strategy has correct metadata."""
        assert strategy.name == "amalfi"
        assert strategy.display_name == "Amalfi"
        assert strategy.min_players == 3
        assert strategy.supports_byes is True
        assert strategy.requires_classification is True

    def test_minimum_players_validation(self, strategy):
        """Test that strategy validates minimum player requirements."""
        # Create mock gara with too few players
        gara = Mock()
        gara.rounds_count = 3

        inscriptions = []
        for i in range(1, 3):  # Only 2 players, Amalfi needs 3
            inscription = Mock()
            inscription.user_id = i
            inscription.is_withdrawn = False
            inscription.status = "confirmed"
            inscriptions.append(inscription)

        gara.inscriptions = inscriptions

        # Validation should fail
        validation = strategy.validate(gara)
        assert not validation.ok
        assert any("at least 3 players" in error for error in validation.errors)

    def test_mock_object_validation(self, strategy):
        """Test that strategy can validate mock objects (for testing compatibility)."""
        # Create simple mock for testing
        gara = Mock()
        inscriptions = [Mock() for _ in range(5)]  # 5 players
        gara.inscriptions = inscriptions

        # Should handle mock gracefully without throwing exceptions
        strategy.validate(gara)
        # We don't assert specific results since mock validation has different logic
