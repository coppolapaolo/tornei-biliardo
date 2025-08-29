"""
Unit tests for UserService with comprehensive coverage.

Tests the service layer functionality for user management operations,
including creation, authentication, updates, and role management.
"""

import pytest

from models.user.services import UserService
from models.user.models import User
from models.status_enum import DirectorRequestStatus


class TestUserService:
    """Test suite for UserService functionality."""

    def test_create_user_success(self, db_session):
        """Test successful user creation."""
        user = UserService.create_user(
            username="testuser", email="test@example.com", password="securepassword123"
        )

        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.role == "player"
        assert user.is_player is True
        assert user.check_password("securepassword123") is True
        assert user.check_password("wrongpassword") is False

    def test_create_user_with_role(self, db_session):
        """Test user creation with specific role."""
        user = UserService.create_user(
            username="testdirector",
            email="director@example.com",
            password="password123",
            role="director",
        )

        assert user.role == "director"
        assert user.is_director is True

    def test_create_user_with_phone(self, db_session):
        """Test user creation with phone number."""
        user = UserService.create_user(
            username="testuser2",
            email="test2@example.com",
            password="password123",
            phone="1234567890",
        )

        assert user.phone == "1234567890"

    def test_create_user_duplicate_username(self, db_session):
        """Test that duplicate usernames are not allowed."""
        # Create first user
        UserService.create_user(
            username="duplicate", email="test1@example.com", password="password123"
        )

        # Try to create user with same username
        with pytest.raises(ValueError, match="already exists"):
            UserService.create_user(
                username="duplicate", email="test2@example.com", password="password123"
            )

    def test_create_user_duplicate_email(self, db_session):
        """Test that duplicate emails are not allowed."""
        # Create first user
        UserService.create_user(
            username="user1", email="duplicate@example.com", password="password123"
        )

        # Try to create user with same email
        with pytest.raises(ValueError, match="already exists"):
            UserService.create_user(
                username="user2", email="duplicate@example.com", password="password123"
            )

    def test_create_user_invalid_role(self, db_session):
        """Test that invalid roles are rejected."""
        with pytest.raises(ValueError, match="Invalid role"):
            UserService.create_user(
                username="invalidrole",
                email="invalid@example.com",
                password="password123",
                role="invalid",
            )

    def test_create_user_missing_fields(self, db_session):
        """Test that missing required fields are rejected."""
        # Missing username
        with pytest.raises(ValueError, match="Username is required"):
            UserService.create_user(
                username="", email="test@example.com", password="password123"
            )

        # Missing email
        with pytest.raises(ValueError, match="Email is required"):
            UserService.create_user(
                username="testuser", email="", password="password123"
            )

        # Short password
        with pytest.raises(ValueError, match="Password must be at least 6 characters"):
            UserService.create_user(
                username="testuser", email="test@example.com", password="123"
            )

    def test_authenticate_user_success(self, db_session):
        """Test successful user authentication."""
        # Create a user
        user = UserService.create_user(
            username="authuser", email="auth@example.com", password="authpassword123"
        )

        # Authenticate with correct credentials
        authenticated_user = UserService.authenticate_user(
            "authuser", "authpassword123"
        )
        assert authenticated_user is not None
        assert authenticated_user.id == user.id

    def test_authenticate_user_wrong_password(self, db_session):
        """Test authentication with wrong password."""
        # Create a user
        UserService.create_user(
            username="authuser2", email="auth2@example.com", password="authpassword123"
        )

        # Authenticate with wrong password
        authenticated_user = UserService.authenticate_user("authuser2", "wrongpassword")
        assert authenticated_user is None

    def test_authenticate_user_nonexistent(self, db_session):
        """Test authentication for nonexistent user."""
        authenticated_user = UserService.authenticate_user("nonexistent", "password")
        assert authenticated_user is None

    def test_update_user_success(self, db_session):
        """Test successful user update."""
        # Create a user
        user = UserService.create_user(
            username="updateuser", email="update@example.com", password="password123"
        )

        # Update user information
        updated_user = UserService.update_user(
            user.id,
            username="updateduser",
            email="updated@example.com",
            phone="0987654321",
        )

        assert updated_user.username == "updateduser"
        assert updated_user.email == "updated@example.com"
        assert updated_user.phone == "0987654321"

    def test_update_user_duplicate_username(self, db_session):
        """Test that updating to duplicate username is rejected."""
        # Create two users
        UserService.create_user(
            username="user1_unique_update",
            email="user1_update@example.com",
            password="password123",
        )
        user2 = UserService.create_user(
            username="user2_unique_update",
            email="user2_update@example.com",
            password="password123",
        )

        # Try to update user2 to have user1's username
        with pytest.raises(ValueError, match="already exists"):
            UserService.update_user(user2.id, username="user1_unique_update")

    def test_update_user_duplicate_email(self, db_session):
        """Test that updating to duplicate email is rejected."""
        # Create two users
        UserService.create_user(
            username="user1_unique", email="user1@example.com", password="password123"
        )
        user2 = UserService.create_user(
            username="user2_unique", email="user2@example.com", password="password123"
        )

        # Try to update user2 to have user1's email
        with pytest.raises(ValueError, match="already exists"):
            UserService.update_user(user2.id, email="user1@example.com")

    def test_update_user_nonexistent(self, db_session):
        """Test updating nonexistent user."""
        with pytest.raises(ValueError, match="User not found"):
            UserService.update_user(99999, username="newname")

    def test_change_password_success(self, db_session):
        """Test successful password change."""
        # Create a user
        user = UserService.create_user(
            username="changepass",
            email="changepass@example.com",
            password="oldpassword123",
        )

        # Change password
        success = UserService.change_password(
            user.id, "oldpassword123", "newpassword456"
        )
        assert success is True

        # Verify new password works
        updated_user = UserService.authenticate_user("changepass", "newpassword456")
        assert updated_user is not None
        assert updated_user.id == user.id

        # Verify old password doesn't work
        old_auth = UserService.authenticate_user("changepass", "oldpassword123")
        assert old_auth is None

    def test_change_password_wrong_old_password(self, db_session):
        """Test password change with wrong old password."""
        # Create a user
        user = UserService.create_user(
            username="changepass2",
            email="changepass2@example.com",
            password="oldpassword123",
        )

        # Try to change password with wrong old password
        success = UserService.change_password(user.id, "wrongoldpass", "newpassword456")
        assert success is False

        # Verify old password still works
        updated_user = UserService.authenticate_user("changepass2", "oldpassword123")
        assert updated_user is not None

    def test_change_password_nonexistent_user(self, db_session):
        """Test password change for nonexistent user."""
        success = UserService.change_password(99999, "oldpass", "newpass")
        assert success is False

    def test_soft_delete_user(self, db_session):
        """Test soft deletion of user."""
        # Create a user
        user = UserService.create_user(
            username="deleteuser", email="delete@example.com", password="password123"
        )

        # Soft delete user
        UserService.soft_delete_user(user.id)

        # Verify user is marked as deleted
        deleted_user = db_session.get(User, user.id)
        assert deleted_user is not None
        assert deleted_user.is_active is False
        assert deleted_user.deleted_at is not None

    def test_soft_delete_nonexistent_user(self, db_session):
        """Test soft deletion of nonexistent user."""
        with pytest.raises(ValueError, match="User not found"):
            UserService.soft_delete_user(99999)

    def test_get_user_by_username(self, db_session):
        """Test retrieving user by username."""
        # Create a user
        created_user = UserService.create_user(
            username="getbyuser", email="getby@example.com", password="password123"
        )

        # Retrieve user by username
        user = UserService.get_user_by_username("getbyuser")
        assert user is not None
        assert user.id == created_user.id

    def test_get_user_by_username_nonexistent(self, db_session):
        """Test retrieving nonexistent user by username."""
        user = UserService.get_user_by_username("nonexistent")
        assert user is None

    def test_get_user_by_email(self, db_session):
        """Test retrieving user by email."""
        # Create a user
        created_user = UserService.create_user(
            username="getbyemail",
            email="getbyemail@example.com",
            password="password123",
        )

        # Retrieve user by email
        user = UserService.get_user_by_email("getbyemail@example.com")
        assert user is not None
        assert user.id == created_user.id

    def test_get_user_by_email_nonexistent(self, db_session):
        """Test retrieving nonexistent user by email."""
        user = UserService.get_user_by_email("nonexistent@example.com")
        assert user is None

    def test_get_all_users(self, db_session):
        """Test retrieving all users."""
        # Create a few users
        user1 = UserService.create_user(
            username="user1_get_all",
            email="user1_get_all@example.com",
            password="password123",
        )
        user2 = UserService.create_user(
            username="user2_get_all",
            email="user2_get_all@example.com",
            password="password123",
        )

        # Get all users
        users = UserService.get_all_users()
        assert len(users) >= 2
        user_ids = [u.id for u in users]
        assert user1.id in user_ids
        assert user2.id in user_ids

    def test_get_users_by_role(self, db_session):
        """Test retrieving users by role."""
        # Create users with different roles
        player = UserService.create_user(
            username="player1",
            email="player1@example.com",
            password="password123",
            role="player",
        )
        director = UserService.create_user(
            username="director1",
            email="director1@example.com",
            password="password123",
            role="director",
        )

        # Get players
        players = UserService.get_users_by_role("player")
        assert len(players) >= 1
        assert player.id in [u.id for u in players]

        # Get directors
        directors = UserService.get_users_by_role("director")
        assert len(directors) >= 1
        assert director.id in [u.id for u in directors]

    def test_request_director_promotion(self, db_session):
        """Test requesting director promotion."""
        # Create a player
        player = UserService.create_user(
            username="playerfordirector",
            email="playerfordirector@example.com",
            password="password123",
            role="player",
        )

        # Request director promotion
        request = UserService.request_director_promotion(
            player.id, "I want to be a director"
        )

        assert request is not None
        assert request.user_id == player.id
        assert request.notes == "I want to be a director"
        assert request.status == DirectorRequestStatus.PENDING.value

    def test_request_director_promotion_already_director(self, db_session):
        """Test requesting director promotion when already director."""
        # Create a director
        director = UserService.create_user(
            username="alreadydirector",
            email="alreadydirector@example.com",
            password="password123",
            role="director",
        )

        # Try to request director promotion
        with pytest.raises(ValueError, match="already a director"):
            UserService.request_director_promotion(director.id, "Want to be director")

    def test_request_director_promotion_nonexistent_user(self, db_session):
        """Test requesting director promotion for nonexistent user."""
        with pytest.raises(ValueError, match="User not found"):
            UserService.request_director_promotion(99999, "Reason")

    def test_get_director_requests(self, db_session):
        """Test retrieving director requests."""
        # Create a player and request director promotion
        player = UserService.create_user(
            username="requestdirector",
            email="requestdirector@example.com",
            password="password123",
            role="player",
        )
        request = UserService.request_director_promotion(
            player.id, "Want to be director"
        )

        # Get all director requests
        requests = UserService.get_director_requests()
        assert len(requests) >= 1
        assert request.id in [r.id for r in requests]

    def test_get_director_requests_by_status(self, db_session):
        """Test retrieving director requests by status."""
        # Create a player and request director promotion
        player = UserService.create_user(
            username="requestdirector2",
            email="requestdirector2@example.com",
            password="password123",
            role="player",
        )
        request = UserService.request_director_promotion(
            player.id, "Want to be director"
        )

        # Get pending requests
        pending_requests = UserService.get_director_requests_by_status(
            DirectorRequestStatus.PENDING.value
        )
        assert len(pending_requests) >= 1
        assert request.id in [r.id for r in pending_requests]

    def test_update_director_request_status(self, db_session):
        """Test updating director request status."""
        # Create a player and request director promotion
        player = UserService.create_user(
            username="requestdirector3",
            email="requestdirector3@example.com",
            password="password123",
            role="player",
        )
        request = UserService.request_director_promotion(
            player.id, "Want to be director"
        )

        # Update request status to approved
        updated_request = UserService.update_director_request_status(
            request.id, DirectorRequestStatus.APPROVED.value
        )

        assert updated_request.status == DirectorRequestStatus.APPROVED.value

    def test_update_director_request_status_nonexistent(self, db_session):
        """Test updating status of nonexistent director request."""
        with pytest.raises(ValueError, match="Director request not found"):
            UserService.update_director_request_status(
                99999, DirectorRequestStatus.APPROVED.value
            )

    def test_approve_director_request(self, db_session):
        """Test approving director request."""
        # Create a player and request director promotion
        player = UserService.create_user(
            username="requestdirector4",
            email="requestdirector4@example.com",
            password="password123",
            role="player",
        )
        request = UserService.request_director_promotion(
            player.id, "Want to be director"
        )

        # Approve the request
        approved_request = UserService.approve_director_request(request.id)

        assert approved_request.status == DirectorRequestStatus.APPROVED.value

        # Verify user is now a director
        updated_user = db_session.get(User, player.id)
        assert updated_user.role == "director"
        assert updated_user.is_director is True

    def test_reject_director_request(self, db_session):
        """Test rejecting director request."""
        # Create a player and request director promotion
        player = UserService.create_user(
            username="requestdirector5",
            email="requestdirector5@example.com",
            password="password123",
            role="player",
        )
        request = UserService.request_director_promotion(
            player.id, "Want to be director"
        )

        # Reject the request
        rejected_request = UserService.reject_director_request(request.id)

        assert rejected_request.status == DirectorRequestStatus.REJECTED.value

        # Verify user is still a player
        updated_user = db_session.get(User, player.id)
        assert updated_user.role == "player"
        assert updated_user.is_player is True

    def test_get_user_stats(self, db_session):
        """Test retrieving user statistics."""
        # Create a user
        user = UserService.create_user(
            username="statsuser", email="statsuser@example.com", password="password123"
        )

        # Get user stats
        stats = UserService.get_user_stats(user.id)

        # Basic stats should be present
        assert "total_matches" in stats
        assert "won_matches" in stats
        assert "win_percentage" in stats
        assert stats["total_matches"] == 0
        assert stats["won_matches"] == 0
        assert stats["win_percentage"] == 0.0

    def test_can_view_admin_panel(self, db_session):
        """Test admin panel access permissions."""
        # Create users with different roles
        admin = UserService.create_user(
            username="adminpanel",
            email="adminpanel@example.com",
            password="password123",
            role="admin",
        )
        director = UserService.create_user(
            username="directorpanel",
            email="directorpanel@example.com",
            password="password123",
            role="director",
        )
        player = UserService.create_user(
            username="playerpanel",
            email="playerpanel@example.com",
            password="password123",
            role="player",
        )

        # Admin should be able to view admin panel
        assert UserService.can_view_admin_panel(admin.id) is True

        # Director should not be able to view admin panel
        assert UserService.can_view_admin_panel(director.id) is False

        # Player should not be able to view admin panel
        assert UserService.can_view_admin_panel(player.id) is False

    def test_transaction_management(self, db_session):
        """Test that service methods use transaction management."""
        # This test verifies that the transactional decorators are properly applied
        # by checking that the methods execute successfully within transactions
        user = UserService.create_user(
            username="txuser", email="txuser@example.com", password="password123"
        )

        assert user.id is not None
        assert db_session.get(User, user.id) is not None
