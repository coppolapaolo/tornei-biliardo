"""
Test module for amalfi/engine.py
"""

import pytest
from unittest.mock import patch, MagicMock

# Import the classes we want to test
from amalfi.engine import (
    AmalfiEngine,
    ValidationResult,
    create_amalfi_round_matches,
    get_amalfi_classification,
    validate_amalfi_configuration,
)


class TestAmalfiEngine:
    """Test cases for AmalfiEngine class."""

    def test_amalfi_engine_initialization(self):
        """Test AmalfiEngine initialization."""
        # Create mock prova and tournament
        mock_prova = MagicMock()
        mock_tournament = MagicMock()
        mock_prova.tournament = mock_tournament

        # Create engine instance
        engine = AmalfiEngine(mock_prova)

        assert engine.prova == mock_prova
        assert engine.tournament == mock_tournament

    def test_validation_result_structure(self):
        """Test ValidationResult structure."""
        # Test that ValidationResult has the expected structure
        result: ValidationResult = {
            "is_valid": True,
            "warnings": ["warning1", "warning2"],
            "errors": ["error1"],
        }

        assert result["is_valid"] is True
        assert len(result["warnings"]) == 2
        assert len(result["errors"]) == 1
        assert "warning1" in result["warnings"]
        assert "error1" in result["errors"]


class TestUtilityFunctions:
    """Test cases for utility functions."""

    @patch("amalfi.engine.AmalfiEngine")
    def test_create_amalfi_round_matches(self, mock_engine_class):
        """Test create_amalfi_round_matches function."""
        # Setup mock
        mock_prova = MagicMock()
        mock_engine_instance = MagicMock()
        mock_engine_class.return_value = mock_engine_instance
        mock_matches = [MagicMock(), MagicMock()]
        mock_engine_instance.create_round_matches.return_value = mock_matches

        # Call function
        result = create_amalfi_round_matches(mock_prova, 1)

        # Verify
        mock_engine_class.assert_called_once_with(mock_prova)
        mock_engine_instance.create_round_matches.assert_called_once_with(1)
        assert result == mock_matches

    @patch("amalfi.engine.db")
    def test_get_amalfi_classification(self, mock_db):
        """Test get_amalfi_classification function."""
        # Setup mock
        mock_db.session.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = [  # noqa: E501
            "classification1",
            "classification2",
        ]

        # Call function
        result = get_amalfi_classification(1, 1)

        # Verify
        mock_db.session.query.assert_called()
        assert len(result) == 2
        assert result[0] == "classification1"

    @patch("amalfi.engine.db")
    def test_validate_amalfi_configuration_valid(self, mock_db):
        """Test validate_amalfi_configuration with valid configuration."""
        # Setup mock
        mock_prova = MagicMock()
        mock_prova.min_participants = 3
        mock_prova.rounds_count = 3
        mock_prova.id = 1

        mock_db.session.query.return_value.filter_by.return_value.count.return_value = 5

        # Call function
        result = validate_amalfi_configuration(mock_prova)

        # Verify
        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    @patch("amalfi.engine.db")
    def test_validate_amalfi_configuration_invalid_insufficient_players(self, mock_db):
        """Test validate_amalfi_configuration with insufficient players."""
        # Setup mock
        mock_prova = MagicMock()
        mock_prova.min_participants = 5
        mock_prova.rounds_count = 3
        mock_prova.id = 1

        mock_db.session.query.return_value.filter_by.return_value.count.return_value = 3

        # Call function
        result = validate_amalfi_configuration(mock_prova)

        # Verify
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0
        assert "Servono almeno" in result["errors"][0]

    @patch("amalfi.engine.db")
    def test_validate_amalfi_configuration_too_many_rounds(self, mock_db):
        """Test validate_amalfi_configuration with too many rounds."""
        # Setup mock
        mock_prova = MagicMock()
        mock_prova.min_participants = 3
        mock_prova.rounds_count = 10
        mock_prova.id = 1

        mock_db.session.query.return_value.filter_by.return_value.count.return_value = 4

        # Call function
        result = validate_amalfi_configuration(mock_prova)

        # Verify
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0


if __name__ == "__main__":
    pytest.main([__file__])
