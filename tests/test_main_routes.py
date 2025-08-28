"""
Test module for routes/main.py
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import date


class TestMainRoutes:
    """Test cases for main routes."""

    @patch("routes.main.current_user")
    def test_index_route_authenticated_user(
        self, mock_current_user, client, player_user
    ):
        """Test index route when user is authenticated."""
        # Mock current_user as authenticated
        mock_current_user.is_authenticated = True

        response = client.get("/")
        # Should redirect to dashboard
        assert response.status_code == 302
        assert "/dashboard" in response.location

    @patch("routes.main.current_user")
    @patch("routes.main.Tournament")
    @patch("routes.main.date")
    def test_index_route_unauthenticated_user_no_tournaments(
        self, mock_date, mock_tournament, mock_current_user, client
    ):
        """Test index route when user is not authenticated and no tournaments exist."""
        # Mock current_user as not authenticated
        mock_current_user.is_authenticated = False

        # Mock date.today()
        mock_date.today.return_value = date(2023, 1, 1)

        mock_tournament.query.filter_by.return_value.order_by.return_value.\
            all.return_value = []

        response = client.get("/")
        assert response.status_code == 200
        # Check that the response contains expected content
        assert b"<title>" in response.data.lower()  # Basic HTML check

    @patch("routes.main.Config")
    def test_reset_database_route_non_debug(self, mock_config, client):
        """Test reset database route when not in debug mode."""
        mock_config.DEBUG_MODE = False
        response = client.get("/reset")
        assert response.status_code == 403

    @patch("routes.main.Config")
    def test_reset_database_route_debug(self, mock_config, client):
        """Test reset database route when in debug mode."""
        mock_config.DEBUG_MODE = True
        response = client.get("/reset")
        assert response.status_code == 200
        # Should show reset page
        assert b"reset" in response.data.lower()

    @patch("routes.main.Config")
    def test_reset_database_confirm_non_debug(self, mock_config, client):
        """Test reset database confirm route when not in debug mode."""
        mock_config.DEBUG_MODE = False
        response = client.post("/reset/confirm")
        assert response.status_code == 403

    @patch("routes.main.Config")
    @patch("config.Config")
    def test_reset_database_confirm_debug_incorrect_password(
        self, mock_config_global, mock_config_routes, client
    ):
        """Test reset database confirm route with incorrect password."""
        # Patch both Config imports
        mock_config_routes.DEBUG_MODE = True
        mock_config_global.DEBUG_MODE = True

        response = client.post("/reset/confirm", data={"password": "WRONG_PASSWORD"})
        # Should redirect back to reset page (302)
        assert response.status_code == 302

    @patch("routes.main.Config")
    @patch("config.Config")
    def test_quick_login_non_debug(
        self, mock_config_global, mock_config_routes, client
    ):
        """Test quick login route when not in debug mode."""
        # Patch both Config imports
        mock_config_routes.DEBUG_MODE = False
        mock_config_global.DEBUG_MODE = False
        response = client.get("/debug/login/testuser")
        # Should return 403 Forbidden
        assert response.status_code == 403

    @patch("routes.main.Config")
    @patch("config.Config")
    @patch("routes.main.User")
    @patch("routes.main.flash")
    @patch("routes.main.url_for")
    def test_quick_login_debug_user_not_found(
        self,
        mock_url_for,
        mock_flash,
        mock_user,
        mock_config_global,
        mock_config_routes,
        client,
    ):
        """Test quick login route when user is not found."""
        # Patch both Config imports
        mock_config_routes.DEBUG_MODE = True
        mock_config_global.DEBUG_MODE = True
        mock_user.query.filter_by.return_value.first.return_value = None
        mock_url_for.return_value = "/"

        response = client.get("/debug/login/nonexistentuser")
        # Should redirect back to index
        assert response.status_code == 302
        mock_flash.assert_called_once()

    @patch("routes.main.date")
    @patch("routes.main.Classification")
    @patch("routes.main.Prova")
    @patch("routes.main.Tournament")
    @patch("routes.main.current_user")
    def test_index_route_unauthenticated_user_with_tournaments(
        self,
        mock_current_user,
        mock_tournament,
        mock_prova,
        mock_classification,
        mock_date,
        client,
    ):
        """Test index route when user is not authenticated and tournaments exist."""
        # Mock current_user as not authenticated
        mock_current_user.is_authenticated = False

        # Mock date.today()
        mock_date.today.return_value = date(2023, 1, 1)

        # Create mock tournament
        mock_tournament_obj = MagicMock()
        mock_tournament_obj.id = 1
        mock_tournament_obj.name = "Test Tournament"
        mock_tournament.query.filter_by.return_value.order_by.return_value.\
            all.return_value = [mock_tournament_obj]

        # Create mock prova with proper attributes
        mock_prova_obj = MagicMock()
        mock_prova_obj.date = date(2023, 1, 2)  # Future date
        mock_prova_obj.tournament_id = 1

        # Create a mock query object that will handle the filter method properly
        mock_filtered_query = MagicMock()
        mock_filtered_query.order_by.return_value.limit.return_value.\
            all.return_value = [mock_prova_obj]

        # Patch the filter method to return our mock query object
        # We need to mock the filter method to avoid the comparison issue
        # Mock Prova.date to return a MagicMock that can be compared
        mock_prova_date = MagicMock()
        mock_prova_date.__ge__ = MagicMock(return_value=True)
        mock_prova.date = mock_prova_date

        mock_prova.query.filter.return_value = mock_filtered_query

        # Create mock classification with proper attributes
        mock_classification_obj = MagicMock()
        mock_classification_obj.tournament_id = 1
        mock_classification_obj.position = 1  # Set a concrete value for position

        # Create a mock query object for classification
        mock_classification_filtered_query = MagicMock()
        mock_classification_filtered_query.order_by.return_value.limit.return_value.\
            all.return_value = [mock_classification_obj]

        # Patch the classification filter method to return our mock query object
        mock_classification.query.filter.return_value = (
            mock_classification_filtered_query
        )

        response = client.get("/")
        assert response.status_code == 200
        # Should show index page with tournaments
        assert b"Test Tournament" in response.data


if __name__ == "__main__":
    pytest.main([__file__])
