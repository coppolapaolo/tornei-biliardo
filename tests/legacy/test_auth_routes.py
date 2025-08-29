"""
Test module for routes/auth.py
"""

import pytest
from unittest.mock import patch, MagicMock


class TestAuthRoutes:
    """Test cases for auth routes."""

    def test_login_get(self, client):
        """Test login route with GET method."""
        response = client.get("/auth/login")
        assert response.status_code == 200

    @patch("routes.auth.UserService")
    @patch("routes.auth.login_user")
    def test_login_post_success(self, mock_login_user, mock_user_service, client):
        """Test login route with POST method - successful login."""
        # Setup mocks
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user_service.authenticate_user.return_value = mock_user

        # Make POST request
        response = client.post(
            "/auth/login", data={"username": "testuser", "password": "testpass"}
        )

        # Verify calls
        mock_user_service.authenticate_user.assert_called_once_with(
            "testuser", "testpass"
        )
        mock_login_user.assert_called_once_with(mock_user)
        assert response.status_code == 302  # Redirect to dashboard

    @patch("routes.auth.UserService")
    @patch("routes.auth.flash")
    def test_login_post_failure(self, mock_flash, mock_user_service, client):
        """Test login route with POST method - failed login."""
        # Setup mocks
        mock_user_service.authenticate_user.return_value = None

        # Make POST request
        response = client.post(
            "/auth/login", data={"username": "testuser", "password": "wrongpass"}
        )

        # Verify calls
        mock_user_service.authenticate_user.assert_called_once_with(
            "testuser", "wrongpass"
        )
        assert mock_flash.called
        assert response.status_code == 200  # Stay on login page

    def test_register_get(self, client):
        """Test register route with GET method."""
        response = client.get("/auth/register")
        assert response.status_code == 200

    @patch("routes.auth.UserService")
    @patch("routes.auth.login_user")
    @patch("routes.auth.flash")
    def test_register_post_success(
        self, mock_flash, mock_login_user, mock_user_service, client
    ):
        """Test register route with POST method - successful registration."""
        # Setup mocks
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user_service.create_user.return_value = mock_user

        # Make POST request
        response = client.post(
            "/auth/register",
            data={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "newpass",
                "phone": "123456789",
            },
        )

        # Verify calls
        mock_user_service.create_user.assert_called_once_with(
            username="newuser",
            email="newuser@example.com",
            password="newpass",
            phone="123456789",
        )
        mock_login_user.assert_called_once_with(mock_user)
        assert mock_flash.called
        assert response.status_code == 302  # Redirect to dashboard

    @patch("routes.auth.UserService")
    @patch("routes.auth.flash")
    def test_register_post_failure(self, mock_flash, mock_user_service, client):
        """Test register route with POST method - failed registration."""
        # Setup mocks
        mock_user_service.create_user.side_effect = ValueError(
            "Username already exists"
        )

        # Make POST request
        response = client.post(
            "/auth/register",
            data={
                "username": "existinguser",
                "email": "existing@example.com",
                "password": "newpass",
                "phone": "123456789",
            },
        )

        # Verify calls
        mock_user_service.create_user.assert_called_once_with(
            username="existinguser",
            email="existing@example.com",
            password="newpass",
            phone="123456789",
        )
        assert mock_flash.called
        assert response.status_code == 200  # Stay on register page

    def test_logout(self, client, player_user):
        """Test logout route."""
        # First login the user by setting session directly
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Make request to logout
        response = client.get("/auth/logout")

        # Should redirect to home page
        assert response.status_code == 302


if __name__ == "__main__":
    pytest.main([__file__])
