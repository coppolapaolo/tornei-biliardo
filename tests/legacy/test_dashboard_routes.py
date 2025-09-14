"""
Test module for routes/dashboard.py
"""

import pytest
from unittest.mock import patch, MagicMock


class TestDashboardRoutes:
    """Test cases for dashboard routes."""

    def test_dashboard_admin_user(self, client, admin_user):
        """Test dashboard route for admin user."""
        # Login as admin
        client.post(
            "/auth/login", data={"username": "testadmin", "password": "password"}
        )

        # Mock the DashboardService
        with patch("routes.dashboard.DashboardService") as mock_dashboard_service:
            mock_dashboard_service.for_admin.return_value = {"admin_data": "test"}

            response = client.get("/dashboard")

            # Verify the service method was called
            mock_dashboard_service.for_admin.assert_called_once()
            assert response.status_code == 200

    def test_dashboard_director_user(self, client, director_user):
        """Test dashboard route for director user."""
        # Login as director
        client.post(
            "/auth/login", data={"username": "testdirector", "password": "password"}
        )

        # Mock the DashboardService
        with patch("routes.dashboard.DashboardService") as mock_dashboard_service:
            mock_dashboard_service.for_director.return_value = {"director_data": "test"}

            response = client.get("/dashboard")

            # Verify the service method was called
            mock_dashboard_service.for_director.assert_called_once_with(
                director_user.id, selected_campionato_id=None, selected_gara_id=None
            )
            assert response.status_code == 200

    def test_dashboard_player_user(self, client, player_user):
        """Test dashboard route for player user."""
        # Login as player
        client.post(
            "/auth/login", data={"username": "testplayer", "password": "password"}
        )

        # Mock the DashboardService
        with patch("routes.dashboard.DashboardService") as mock_dashboard_service:
            mock_dashboard_service.for_player.return_value = {"player_data": "test"}

            response = client.get("/dashboard")

            # Verify the service method was called
            mock_dashboard_service.for_player.assert_called_once_with(
                player_user.id, selected_campionato_id=None, selected_gara_id=None
            )
            assert response.status_code == 200

    def test_dashboard_with_campionato_id(self, client, player_user):
        """Test dashboard route with campionato_id parameter."""
        # Login as player
        client.post(
            "/auth/login", data={"username": "testplayer", "password": "password"}
        )

        # Mock the DashboardService
        with patch("routes.dashboard.DashboardService") as mock_dashboard_service:
            mock_dashboard_service.for_player.return_value = {"player_data": "test"}

            response = client.get("/dashboard?campionato_id=123")

            # Verify the service method was called with correct parameters
            mock_dashboard_service.for_player.assert_called_once_with(
                player_user.id, selected_campionato_id=123, selected_gara_id=None
            )
            assert response.status_code == 200

    def test_dashboard_with_gara_id(self, client, player_user):
        """Test dashboard route with gara_id parameter."""
        # Login as player
        client.post(
            "/auth/login", data={"username": "testplayer", "password": "password"}
        )

        # Mock the DashboardService and GaraService
        with patch(
            "routes.dashboard.DashboardService"
        ) as mock_dashboard_service, patch("routes.dashboard.GaraService"):
            mock_dashboard_service.for_player.return_value = {"player_data": "test"}

            response = client.get("/dashboard?gara_id=456")

            # Verify the service method was called with correct parameters
            mock_dashboard_service.for_player.assert_called_once_with(
                player_user.id, selected_campionato_id=None, selected_gara_id=456
            )
            assert response.status_code == 200

    def test_dashboard_with_both_ids_standalone_gara(self, client, player_user):
        """Test dashboard route with both IDs where gara is standalone."""
        # Login as player
        client.post(
            "/auth/login", data={"username": "testplayer", "password": "password"}
        )

        # Mock the services
        with patch(
            "routes.dashboard.DashboardService"
        ) as mock_dashboard_service, patch(
            "routes.dashboard.GaraService"
        ) as mock_gara_service:
            mock_gara_service.get_gara_by_id.return_value = MagicMock(
                campionato_id=None
            )
            mock_dashboard_service.for_player.return_value = {"player_data": "test"}

            response = client.get("/dashboard?campionato_id=123&gara_id=456")

            # Verify the service methods were called
            mock_gara_service.get_gara_by_id.assert_called_once_with(456)
            mock_dashboard_service.for_player.assert_called_once_with(
                player_user.id, selected_campionato_id=None, selected_gara_id=456
            )
            assert response.status_code == 200

    def test_dashboard_with_both_ids_campionato_gara(self, client, player_user):
        """Test dashboard route with both IDs where gara belongs to campionato."""
        # Login as player
        client.post(
            "/auth/login", data={"username": "testplayer", "password": "password"}
        )

        # Mock the services
        with patch(
            "routes.dashboard.DashboardService"
        ) as mock_dashboard_service, patch(
            "routes.dashboard.GaraService"
        ) as mock_gara_service:
            mock_gara_service.get_gara_by_id.return_value = MagicMock(campionato_id=789)
            mock_dashboard_service.for_player.return_value = {"player_data": "test"}

            response = client.get("/dashboard?campionato_id=123&gara_id=456")

            # Verify the service methods were called
            mock_gara_service.get_gara_by_id.assert_called_once_with(456)
            mock_dashboard_service.for_player.assert_called_once_with(
                player_user.id, selected_campionato_id=123, selected_gara_id=None
            )
            assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__])
