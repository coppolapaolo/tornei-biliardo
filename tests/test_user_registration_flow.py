"""
Integration tests for user registration and authentication flow.

Tests the complete user registration and authentication workflow to ensure
that users can successfully register, authenticate, and access protected resources.
"""

import pytest
from models.user.services import UserService
from models.user.models import User


class TestUserRegistrationFlow:
    """Test suite for user registration and authentication flow."""

    def test_user_registration_creates_user_in_database(self, db_session):
        """Test that user registration creates a user that persists in the database."""
        # Create a user using the service layer
        user = UserService.create_user(
            username="test_persistent_user",
            email="persistent@test.com",
            password="securepassword123",
        )

        # Verify user was created with proper attributes
        assert user.id is not None
        assert user.username == "test_persistent_user"
        assert user.email == "persistent@test.com"
        assert user.check_password("securepassword123") is True
        assert user.is_active is True
        assert user.is_deleted is False

        # Verify user exists in database
        db_user = (
            db_session.query(User).filter_by(username="test_persistent_user").first()
        )
        assert db_user is not None
        assert db_user.id == user.id
        assert db_user.username == "test_persistent_user"
        assert db_user.email == "persistent@test.com"

    def test_user_can_authenticate_after_registration(self, db_session):
        """Test that users can authenticate with their credentials
        after registration."""
        # Register a new user
        user = UserService.create_user(
            username="auth_flow_user",
            email="authflow@test.com",
            password="authflowpassword123",
        )

        # Authenticate with correct credentials
        authenticated_user = UserService.authenticate_user(
            "auth_flow_user", "authflowpassword123"
        )
        assert authenticated_user is not None
        assert authenticated_user.id == user.id
        assert authenticated_user.username == "auth_flow_user"
        assert authenticated_user.is_active is True

    def test_user_authentication_fails_with_wrong_password(self, db_session):
        """Test that authentication fails with incorrect password."""
        # Register a new user
        UserService.create_user(
            username="wrong_pass_user_unique",
            email="wrongpass_unique@test.com",
            password="correctpassword123",
        )

        # Try to authenticate with wrong password
        authenticated_user = UserService.authenticate_user(
            "wrong_pass_user_unique", "wrongpassword123"
        )
        assert authenticated_user is None

    def test_user_authentication_fails_with_nonexistent_user(self, db_session):
        """Test that authentication fails for nonexistent users."""
        authenticated_user = UserService.authenticate_user(
            "nonexistent_user", "anypassword123"
        )
        assert authenticated_user is None

    def test_duplicate_username_registration_fails(self, db_session):
        """Test that registering with a duplicate username fails."""
        # Register first user
        UserService.create_user(
            username="duplicate_test_unique",
            email="first_unique@test.com",
            password="password123",
        )

        # Try to register second user with same username
        with pytest.raises(
            ValueError, match="Username 'duplicate_test_unique' already exists"
        ):
            UserService.create_user(
                username="duplicate_test_unique",
                email="second_unique@test.com",
                password="password123",
            )

    def test_duplicate_email_registration_fails(self, db_session):
        """Test that registering with a duplicate email fails."""
        # Register first user
        UserService.create_user(
            username="first_user_unique",
            email="duplicate_unique@test.com",
            password="password123",
        )

        # Try to register second user with same email
        with pytest.raises(
            ValueError, match="Email 'duplicate_unique@test.com' already exists"
        ):
            UserService.create_user(
                username="second_user_unique",
                email="duplicate_unique@test.com",
                password="password123",
            )

    def test_user_registration_with_minimum_password_length(self, db_session):
        """Test that user registration requires minimum password length."""
        # Try to register with password shorter than 6 characters
        with pytest.raises(ValueError, match="Password must be at least 6 characters"):
            UserService.create_user(
                username="shortpass_user_unique",
                email="shortpass_unique@test.com",
                password="12345",  # Only 5 characters
            )

    def test_user_registration_requires_username(self, db_session):
        """Test that user registration requires a username."""
        with pytest.raises(ValueError, match="Username is required"):
            UserService.create_user(
                username="",  # Empty username
                email="noreq_unique@test.com",
                password="password123",
            )

    def test_user_registration_requires_email(self, db_session):
        """Test that user registration requires an email."""
        with pytest.raises(ValueError, match="Email is required"):
            UserService.create_user(
                username="norequser_unique",
                email="",  # Empty email
                password="password123",
            )
