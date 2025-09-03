"""
Test module for models/matchmaking/bindings/amalfi_binding.py
"""

import pytest
from unittest.mock import Mock, patch
from models.matchmaking.bindings.amalfi_binding import (
    validate_gara,
    _extract_pairing_from_match,
    propose_pairings,
)


class TestAmalfiBinding:
    """Test cases for amalfi_binding module."""

    def test_validate_gara_with_valid_data(self):
        """Test validate_gara with valid data."""
        # Create a mock gara object
        mock_gara = Mock()

        # Mock the validate_amalfi_configuration function
        with patch(
            "models.matchmaking.bindings.amalfi_binding.validate_amalfi_configuration"
        ) as mock_validate:
            mock_validate.return_value = {
                "is_valid": True,
                "errors": [],
                "warnings": [],
            }

            result = validate_gara(mock_gara)

            # Verify the result
            assert result == (True, ())
            mock_validate.assert_called_once_with(mock_gara)

    def test_validate_gara_with_errors(self):
        """Test validate_gara with errors."""
        # Create a mock gara object
        mock_gara = Mock()

        # Mock the validate_amalfi_configuration function
        with patch(
            "models.matchmaking.bindings.amalfi_binding.validate_amalfi_configuration"
        ) as mock_validate:
            mock_validate.return_value = {
                "is_valid": False,
                "errors": ["Error 1", "Error 2"],
                "warnings": [],
            }

            result = validate_gara(mock_gara)

            # Verify the result
            assert result == (False, ("Error 1", "Error 2"))
            mock_validate.assert_called_once_with(mock_gara)

    def test_validate_gara_with_warnings(self):
        """Test validate_gara with warnings."""
        # Create a mock gara object
        mock_gara = Mock()

        # Mock the validate_amalfi_configuration function
        with patch(
            "models.matchmaking.bindings.amalfi_binding.validate_amalfi_configuration"
        ) as mock_validate:
            mock_validate.return_value = {
                "is_valid": True,
                "errors": [],
                "warnings": ["Warning 1", "Warning 2"],
            }

            result = validate_gara(mock_gara)

            # Verify the result
            assert result == (True, ("Warning 1", "Warning 2"))
            mock_validate.assert_called_once_with(mock_gara)

    def test_validate_gara_with_errors_and_warnings(self):
        """Test validate_gara with both errors and warnings."""
        # Create a mock gara object
        mock_gara = Mock()

        # Mock the validate_amalfi_configuration function
        with patch(
            "models.matchmaking.bindings.amalfi_binding.validate_amalfi_configuration"
        ) as mock_validate:
            mock_validate.return_value = {
                "is_valid": False,
                "errors": ["Error 1"],
                "warnings": ["Warning 1"],
            }

            result = validate_gara(mock_gara)

            # Verify the result
            assert result == (False, ("Error 1", "Warning 1"))
            mock_validate.assert_called_once_with(mock_gara)

    def test_extract_pairing_from_match_bye(self):
        """Test _extract_pairing_from_match with a bye match."""
        # Create a mock match object for a bye
        mock_match = Mock()
        mock_match.is_bye = True
        mock_match.player1_id = 1

        result = _extract_pairing_from_match(mock_match)

        # Verify the result
        assert result == (1,)

    def test_extract_pairing_from_match_standard(self):
        """Test _extract_pairing_from_match with a standard match."""
        # Create a mock match object for a standard match
        mock_match = Mock()
        mock_match.is_bye = False
        mock_match.is_trio = False
        mock_match.player1_id = 1
        mock_match.player2_id = 2

        result = _extract_pairing_from_match(mock_match)

        # Verify the result
        assert result == (1, 2)

    def test_extract_pairing_from_match_trio_with_player3_id(self):
        """Test _extract_pairing_from_match with a trio match that has player3_id."""
        # Create a mock match object for a trio match
        mock_match = Mock()
        mock_match.is_bye = False
        mock_match.is_trio = True
        mock_match.player1_id = 1
        mock_match.player2_id = 2
        mock_match.player3_id = 3

        result = _extract_pairing_from_match(mock_match)

        # Verify the result
        assert result == (1, 2, 3)

    def test_extract_pairing_from_match_trio_with_trio_match(self):
        """Test _extract_pairing_from_match with a trio match that has trio_match."""
        # Create a mock trio_match object
        mock_trio_match = Mock()
        mock_trio_match.player3_id = 3

        # Create a mock match object for a trio match
        mock_match = Mock()
        mock_match.is_bye = False
        mock_match.is_trio = True
        mock_match.player1_id = 1
        mock_match.player2_id = 2
        mock_match.player3_id = None
        mock_match.trio_match = mock_trio_match

        result = _extract_pairing_from_match(mock_match)

        # Verify the result
        assert result == (1, 2, 3)

    def test_extract_pairing_from_match_trio_without_player3(self):
        """Test _extract_pairing_from_match with a trio match without player3_id."""
        # Create a mock match object for a trio match without player3_id
        mock_match = Mock()
        mock_match.is_bye = False
        mock_match.is_trio = True
        mock_match.player1_id = 1
        mock_match.player2_id = 2
        mock_match.player3_id = None
        mock_match.trio_match = None

        # This should raise a RuntimeError
        with pytest.raises(
            RuntimeError, match="Trio match senza player3_id non supportato dal binding"
        ):
            _extract_pairing_from_match(mock_match)

    def test_propose_pairings(self):
        """Test propose_pairings function."""
        # Create a mock gara object
        mock_gara = Mock()
        round_number = 1

        # Create mock matches
        mock_match1 = Mock()
        mock_match1.is_bye = False
        mock_match1.is_trio = False
        mock_match1.player1_id = 1
        mock_match1.player2_id = 2

        mock_match2 = Mock()
        mock_match2.is_bye = True
        mock_match2.player1_id = 3

        # Mock the create_amalfi_round_matches function
        with patch(
            "models.matchmaking.bindings.amalfi_binding.create_amalfi_round_matches"
        ) as mock_create:
            mock_create.return_value = [mock_match1, mock_match2]

            result = propose_pairings(mock_gara, round_number)

            # Verify the result
            assert result == [(1, 2), (3,)]
            mock_create.assert_called_once_with(mock_gara, round_number)


if __name__ == "__main__":
    pytest.main([__file__])
