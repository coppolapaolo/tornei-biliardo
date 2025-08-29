"""
Test module for utils/reset_data.py
"""

from unittest.mock import patch, MagicMock
from utils.reset_data import (
    reset_database_enhanced,
    reset_database_enhanced_cli,
)


class TestResetDataUtils:
    """Test cases for reset_data utilities."""

    @patch("utils.reset_data.db")
    @patch("utils.reset_data.create_admin_if_not_exists")
    def test_reset_database_enhanced(self, mock_create_admin, mock_db):
        """Test reset_database_enhanced function."""
        # Mock the database operations
        mock_db.drop_all.return_value = None
        mock_db.create_all.return_value = None

        # Mock the core reset function
        with patch("utils.reset_data._reset_database_core") as mock_core:
            mock_core.return_value = {"test": "data"}

            result = reset_database_enhanced()

            # Verify the calls
            mock_db.drop_all.assert_called_once()
            mock_db.create_all.assert_called_once()
            mock_core.assert_called_once()
            assert result == {"test": "data"}

    @patch("utils.reset_data.has_app_context")
    @patch("utils.reset_data.create_admin_if_not_exists")
    def test_reset_database_enhanced_cli_with_context(
        self, mock_create_admin, mock_has_context
    ):
        """Test reset_database_enhanced_cli when app context exists."""
        mock_has_context.return_value = True

        with patch("utils.reset_data.reset_database_enhanced") as mock_reset:
            mock_reset.return_value = {"test": "data"}

            reset_database_enhanced_cli()

            mock_reset.assert_called_once()

    @patch("utils.reset_data.has_app_context")
    def test_reset_database_enhanced_cli_without_context(self, mock_has_context):
        """Test reset_database_enhanced_cli when no app context exists."""
        mock_has_context.return_value = False

        # Mock the app creation
        mock_app = MagicMock()
        mock_app_module = MagicMock()
        mock_app_module.create_app.return_value = mock_app

        with patch("importlib.import_module") as mock_import:
            mock_import.return_value = mock_app_module

            with patch("utils.reset_data.reset_database_enhanced") as mock_reset:
                mock_reset.return_value = {"test": "data"}

                reset_database_enhanced_cli()

                mock_import.assert_called_once_with("app")
                mock_app_module.create_app.assert_called_once()
                mock_reset.assert_called_once()
