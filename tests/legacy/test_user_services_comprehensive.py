"""
Comprehensive tests for models/user/services.py
Targeting 253 statements with 124 missed (51% coverage) for maximum impact toward 90% goal.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from models.user.services import (
    UserService,
    DirectorRequestService,
    UserStatsService,
    UserDeletionService,
)
from models.user.role_enum import UserRole
from models.base import utc_now


class TestUserService:
    """Comprehensive tests for UserService."""

    @patch("models.user.services.db")
    @patch("models.user.services.User")
    def test_create_user_success(self, mock_user_class, mock_db):
        """Test successful user creation."""
        # Mock no existing admin
        mock_user_class.query.filter_by.return_value.filter.return_value.count.return_value = (
            0
        )

        # Mock no existing username
        mock_user_class.query.filter.return_value.first.side_effect = [None, None]

        # Mock no existing users for email check
        mock_user_class.query.all.return_value = []

        mock_user = Mock()
        mock_user_class.return_value = mock_user

        result = UserService.create_user(
            username="testuser",
            email="test@example.com",
            password="password123",
            role="player",
            phone="1234567890",
        )

        assert result == mock_user
        mock_user_class.assert_called_once_with(
            username="testuser",
            email="test@example.com",
            role="player",
            phone="1234567890",
        )
        mock_user.set_password.assert_called_once_with("password123")
        mock_db.session.add.assert_called_once_with(mock_user)
        mock_db.session.flush.assert_called_once()

    @patch("models.user.services.User")
    def test_create_user_admin_already_exists(self, mock_user_class):
        """Test user creation fails when admin already exists."""
        mock_user_class.query.filter_by.return_value.filter.return_value.count.return_value = (
            1
        )

        with pytest.raises(ValueError, match="Esiste già un amministratore attivo"):
            UserService.create_user(
                username="admin2",
                email="admin2@example.com",
                password="password123",
                role="admin",
            )

    def test_create_user_invalid_role(self):
        """Test user creation with invalid role."""
        with pytest.raises(ValueError, match="Invalid role"):
            UserService.create_user(
                username="test",
                email="test@example.com",
                password="password123",
                role="invalid_role",
            )

    def test_create_user_missing_username(self):
        """Test user creation with missing username."""
        with pytest.raises(ValueError, match="Username is required"):
            UserService.create_user(
                username="", email="test@example.com", password="password123"
            )

    def test_create_user_missing_email(self):
        """Test user creation with missing email."""
        with pytest.raises(ValueError, match="Email is required"):
            UserService.create_user(username="test", email="", password="password123")

    def test_create_user_short_password(self):
        """Test user creation with short password."""
        with pytest.raises(ValueError, match="Password must be at least 6 characters"):
            UserService.create_user(
                username="test", email="test@example.com", password="123"
            )

    @patch("models.user.services.User")
    def test_create_user_username_exists(self, mock_user_class):
        """Test user creation with existing username."""
        # Mock no admin exists
        mock_user_class.query.filter_by.return_value.filter.return_value.count.return_value = (
            0
        )

        # Mock existing username
        mock_existing_user = Mock()
        mock_user_class.query.filter.return_value.first.return_value = (
            mock_existing_user
        )

        with pytest.raises(ValueError, match="Username 'testuser' already exists"):
            UserService.create_user(
                username="testuser", email="test@example.com", password="password123"
            )

    @patch("models.user.services.User")
    def test_create_user_email_exists(self, mock_user_class):
        """Test user creation with existing email."""
        # Mock no admin and no username conflict
        mock_user_class.query.filter_by.return_value.filter.return_value.count.return_value = (
            0
        )
        mock_user_class.query.filter.return_value.first.return_value = None

        # Mock existing user with same email
        mock_existing_user = Mock()
        mock_existing_user.email = "test@example.com"
        mock_user_class.query.all.return_value = [mock_existing_user]

        with pytest.raises(ValueError, match="Email 'test@example.com' already exists"):
            UserService.create_user(
                username="testuser", email="test@example.com", password="password123"
            )

    @patch("models.user.services.db")
    @patch("models.user.services.User")
    def test_update_user_success(self, mock_user_class, mock_db):
        """Test successful user update."""
        mock_user = Mock()
        mock_user.username = "olduser"
        mock_user.email = "old@example.com"
        mock_db.session.get.return_value = mock_user

        # Mock no conflicts
        mock_user_class.query.filter.return_value.first.return_value = None
        mock_user_class.query.all.return_value = []

        result = UserService.update_user(
            user_id=123, username="newuser", email="new@example.com", phone="9876543210"
        )

        assert result == mock_user
        assert mock_user.username == "newuser"
        assert mock_user.email == "new@example.com"
        assert mock_user.phone == "9876543210"

    @patch("models.user.services.db")
    def test_update_user_not_found(self, mock_db):
        """Test user update with non-existent user."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="User not found"):
            UserService.update_user(user_id=999, username="newuser")

    @patch("models.user.services.db")
    @patch("models.user.services.User")
    def test_update_user_username_conflict(self, mock_user_class, mock_db):
        """Test user update with username conflict."""
        mock_user = Mock()
        mock_user.username = "olduser"
        mock_user.id = 123
        mock_db.session.get.return_value = mock_user

        # Mock username conflict
        mock_conflicting_user = Mock()
        mock_user_class.query.filter.return_value.first.return_value = (
            mock_conflicting_user
        )

        with pytest.raises(ValueError, match="Username 'conflictuser' already exists"):
            UserService.update_user(user_id=123, username="conflictuser")

    @patch("models.user.services.db")
    def test_change_password_success(self, mock_db):
        """Test successful password change."""
        mock_user = Mock()
        mock_user.check_password.return_value = True
        mock_db.session.get.return_value = mock_user

        result = UserService.change_password(123, "oldpass", "newpassword123")

        assert result is True
        mock_user.check_password.assert_called_once_with("oldpass")
        mock_user.set_password.assert_called_once_with("newpassword123")

    @patch("models.user.services.db")
    def test_change_password_user_not_found(self, mock_db):
        """Test password change with non-existent user."""
        mock_db.session.get.return_value = None

        result = UserService.change_password(999, "oldpass", "newpass123")

        assert result is False

    @patch("models.user.services.db")
    def test_change_password_wrong_old_password(self, mock_db):
        """Test password change with wrong old password."""
        mock_user = Mock()
        mock_user.check_password.return_value = False
        mock_db.session.get.return_value = mock_user

        result = UserService.change_password(123, "wrongpass", "newpass123")

        assert result is False

    @patch("models.user.services.db")
    def test_change_password_short_new_password(self, mock_db):
        """Test password change with short new password."""
        mock_user = Mock()
        mock_user.check_password.return_value = True
        mock_db.session.get.return_value = mock_user

        # The actual implementation returns False for short passwords rather than raising
        result = UserService.change_password(123, "oldpass", "123")
        assert result is False

    @patch("models.user.services.db")
    def test_change_password_exception_handling(self, mock_db):
        """Test password change with exception."""
        mock_user = Mock()
        mock_user.check_password.side_effect = Exception("Database error")
        mock_db.session.get.return_value = mock_user

        result = UserService.change_password(123, "oldpass", "newpass123")

        assert result is False

    @patch("models.user.services.datetime")
    @patch("models.user.services.db")
    def test_promote_to_director_success(self, mock_db, mock_datetime):
        """Test successful promotion to director."""
        mock_now = datetime(2024, 1, 15, 12, 0, 0)
        mock_utc_now.return_value = mock_now

        mock_user = Mock()
        mock_user.role = UserRole.PLAYER.value
        mock_db.session.get.return_value = mock_user

        result = UserService.promote_to_director(123, 456)

        assert result is True
        assert mock_user.role == UserRole.DIRECTOR.value
        assert mock_user.promoted_to_director_by_id == 456
        assert mock_user.promoted_to_director_at == mock_now

    @patch("models.user.services.db")
    def test_promote_to_director_user_not_found(self, mock_db):
        """Test promotion with non-existent user."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="User not found"):
            UserService.promote_to_director(999, 456)

    @patch("models.user.services.db")
    def test_promote_to_director_already_director(self, mock_db):
        """Test promotion of user who is already director."""
        mock_user = Mock()
        mock_user.role = UserRole.DIRECTOR.value
        mock_db.session.get.return_value = mock_user

        with pytest.raises(ValueError, match="User is already a director or admin"):
            UserService.promote_to_director(123, 456)

    @patch("models.user.services.db")
    def test_soft_delete_user_success(self, mock_db):
        """Test successful user soft deletion."""
        mock_user = Mock()
        mock_db.session.get.return_value = mock_user

        UserService.soft_delete_user(123)

        mock_user.soft_delete.assert_called_once()

    @patch("models.user.services.db")
    def test_soft_delete_user_not_found(self, mock_db):
        """Test soft deletion with non-existent user."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="User not found"):
            UserService.soft_delete_user(999)

    @patch("models.user.services.Match")
    @patch("models.user.services.Inscription")
    @patch("models.user.services.db")
    def test_get_user_stats(self, mock_db, mock_inscription, mock_match):
        """Test getting user statistics."""
        mock_user = Mock()
        mock_db.session.get.return_value = mock_user

        mock_inscription.query.filter_by.return_value.count.return_value = 5

        # Mock separate query objects for total matches and wins
        mock_total_query = Mock()
        mock_total_query.count.return_value = 10

        mock_wins_query = Mock()
        mock_wins_query.count.return_value = 7

        # Side effect returns different queries based on call order
        mock_match.query.filter.side_effect = [mock_total_query, mock_wins_query]

        result = UserService.get_user_stats(123)

        assert result["total_matches"] == 10
        assert result["won_matches"] == 7
        assert result["win_percentage"] == 70.0
        assert result["inscription_count"] == 5
        assert result["losses_count"] == 3

    @patch("models.user.services.db")
    def test_get_user_stats_user_not_found(self, mock_db):
        """Test get user stats with non-existent user."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="User not found"):
            UserService.get_user_stats(999)

    @patch("models.user.services.db")
    def test_can_view_admin_panel_admin(self, mock_db):
        """Test admin panel access for admin user."""
        mock_user = Mock()
        mock_user.role = UserRole.ADMIN.value
        mock_db.session.get.return_value = mock_user

        result = UserService.can_view_admin_panel(123)

        assert result is True

    @patch("models.user.services.db")
    def test_can_view_admin_panel_director(self, mock_db):
        """Test admin panel access for director user."""
        mock_user = Mock()
        mock_user.role = UserRole.DIRECTOR.value
        mock_db.session.get.return_value = mock_user

        result = UserService.can_view_admin_panel(123)

        assert result is False  # Only admins allowed

    @patch("models.user.services.User")
    def test_authenticate_user_success(self, mock_user_class):
        """Test successful user authentication."""
        mock_user = Mock()
        mock_user.check_password.return_value = True
        mock_user_class.query.filter.return_value.first.return_value = mock_user

        result = UserService.authenticate_user("testuser", "password123")

        assert result == mock_user
        mock_user.check_password.assert_called_once_with("password123")

    @patch("models.user.services.User")
    def test_authenticate_user_wrong_password(self, mock_user_class):
        """Test authentication with wrong password."""
        mock_user = Mock()
        mock_user.check_password.return_value = False
        mock_user_class.query.filter.return_value.first.return_value = mock_user

        result = UserService.authenticate_user("testuser", "wrongpass")

        assert result is None

    @patch("models.user.services.User")
    def test_authenticate_user_not_found(self, mock_user_class):
        """Test authentication with non-existent user."""
        mock_user_class.query.filter.return_value.first.return_value = None

        result = UserService.authenticate_user("nonexistent", "password123")

        assert result is None

    @patch("models.user.services.User")
    def test_get_user_by_username(self, mock_user_class):
        """Test getting user by username."""
        mock_user = Mock()
        mock_user_class.query.filter.return_value.first.return_value = mock_user

        result = UserService.get_user_by_username("testuser")

        assert result == mock_user

    @patch("models.user.services.User")
    def test_get_user_by_email(self, mock_user_class):
        """Test getting user by email."""
        mock_user = Mock()
        mock_user.email = "test@example.com"
        mock_user_class.query.all.return_value = [mock_user]

        result = UserService.get_user_by_email("test@example.com")

        assert result == mock_user

    @patch("models.user.services.User")
    def test_get_user_by_email_not_found(self, mock_user_class):
        """Test getting user by email when not found."""
        mock_user_class.query.all.return_value = []

        result = UserService.get_user_by_email("notfound@example.com")

        assert result is None

    @patch("models.user.services.User")
    def test_get_all_users(self, mock_user_class):
        """Test getting all users."""
        mock_users = [Mock(), Mock(), Mock()]
        mock_user_class.query.all.return_value = mock_users

        result = UserService.get_all_users()

        assert result == mock_users

    @patch("models.user.services.User")
    def test_get_users_by_role(self, mock_user_class):
        """Test getting users by role."""
        mock_users = [Mock(), Mock()]
        mock_user_class.query.filter_by.return_value.all.return_value = mock_users

        result = UserService.get_users_by_role("director")

        assert result == mock_users
        mock_user_class.query.filter_by.assert_called_once_with(role="director")

    @patch("models.user.services.db")
    @patch("models.user.services.DirectorRequest")
    def test_request_director_promotion_success(self, mock_request_class, mock_db):
        """Test successful director promotion request."""
        mock_user = Mock()
        mock_user.role = UserRole.PLAYER.value
        mock_db.session.get.return_value = mock_user

        mock_request_class.query.filter_by.return_value.first.return_value = None

        mock_request = Mock()
        mock_request_class.return_value = mock_request

        result = UserService.request_director_promotion(123, "I want to be director")

        assert result == mock_request
        mock_request_class.assert_called_once_with(
            user_id=123, notes="I want to be director"
        )
        mock_db.session.add.assert_called_once_with(mock_request)
        mock_db.session.commit.assert_called_once()

    @patch("models.user.services.db")
    def test_request_director_promotion_user_not_found(self, mock_db):
        """Test director promotion request with non-existent user."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="User not found"):
            UserService.request_director_promotion(999)

    @patch("models.user.services.db")
    def test_request_director_promotion_already_director(self, mock_db):
        """Test director promotion request for user who is already director."""
        mock_user = Mock()
        mock_user.role = UserRole.DIRECTOR.value
        mock_db.session.get.return_value = mock_user

        with pytest.raises(ValueError, match="User is already a director or admin"):
            UserService.request_director_promotion(123)

    @patch("models.user.services.DirectorRequest")
    @patch("models.user.services.db")
    def test_request_director_promotion_pending_exists(
        self, mock_db, mock_request_class
    ):
        """Test director promotion request when pending request exists."""
        mock_user = Mock()
        mock_user.role = UserRole.PLAYER.value
        mock_db.session.get.return_value = mock_user

        mock_existing_request = Mock()
        mock_request_class.query.filter_by.return_value.first.return_value = (
            mock_existing_request
        )

        with pytest.raises(
            ValueError, match="User already has a pending director request"
        ):
            UserService.request_director_promotion(123)


class TestDirectorRequestService:
    """Tests for DirectorRequestService."""

    @patch("models.user.services.db")
    def test_process_request_approve(self, mock_db):
        """Test processing request with approval."""
        mock_admin = Mock()
        mock_admin.is_admin = True

        mock_request = Mock()
        mock_db.session.get.return_value = mock_request

        result = DirectorRequestService.process_request(123, mock_admin, True)

        assert result == mock_request
        mock_request.approve.assert_called_once_with(mock_admin)
        mock_db.session.commit.assert_called_once()

    @patch("models.user.services.db")
    def test_process_request_reject(self, mock_db):
        """Test processing request with rejection."""
        mock_admin = Mock()
        mock_admin.is_admin = True

        mock_request = Mock()
        mock_db.session.get.return_value = mock_request

        result = DirectorRequestService.process_request(123, mock_admin, False)

        assert result == mock_request
        mock_request.reject.assert_called_once_with(mock_admin)

    def test_process_request_not_admin(self):
        """Test processing request by non-admin user."""
        mock_user = Mock()
        mock_user.is_admin = False

        with pytest.raises(
            PermissionError, match="Only administrators can process director requests"
        ):
            DirectorRequestService.process_request(123, mock_user, True)

    @patch("models.user.services.db")
    def test_process_request_not_found(self, mock_db):
        """Test processing non-existent request."""
        mock_admin = Mock()
        mock_admin.is_admin = True
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Director request not found"):
            DirectorRequestService.process_request(999, mock_admin, True)


class TestUserStatsService:
    """Tests for UserStatsService."""

    @patch("models.user.services.db")
    def test_get_user_stats(self, mock_db):
        """Test getting user stats."""
        mock_user = Mock()
        mock_stats = {"total_matches": 10, "wins": 7}
        mock_user.get_statistics.return_value = mock_stats
        mock_db.session.get.return_value = mock_user

        result = UserStatsService.get_user_stats(123)

        assert result == mock_stats
        mock_user.get_statistics.assert_called_once()

    @patch("models.user.services.db")
    def test_get_user_stats_user_not_found(self, mock_db):
        """Test getting stats for non-existent user."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="User not found"):
            UserStatsService.get_user_stats(999)


class TestUserDeletionService:
    """Tests for UserDeletionService."""

    @patch("models.user.services.db")
    def test_delete_user(self, mock_db):
        """Test user deletion."""
        mock_user = Mock()

        UserDeletionService.delete_user(mock_user)

        mock_user.soft_delete.assert_called_once()
        mock_db.session.commit.assert_called_once()
