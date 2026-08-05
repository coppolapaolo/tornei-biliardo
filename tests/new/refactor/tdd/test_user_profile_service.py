"""
TDD Tests for UserProfileService Decomposition (Task 1.3 - Phase 1)

UserProfileService focuses on core user CRUD operations and authentication:
- create_user(), update_user(), soft_delete_user()
- authenticate_user(), change_password()
- get_user_by_username(), get_user_by_email(), get_all_users(), get_users_by_role()
- get_user_detail_data()

Strategy: Red-Green-Refactor TDD methodology following Task 1.2 patterns
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from models import db
from models.user.models import User
from models.user.role_enum import UserRole


class TestUserProfileServiceTDD:
    """TDD tests for UserProfileService CRUD and authentication operations."""

    def test_create_user_basic_functionality(self, app, db_session):
        """
        RED: Test UserProfileService.create_user() basic user creation.

        Expected behavior:
        - Creates new user with required fields
        - Returns User object with proper attributes
        - Uses @transactional decorator for transaction management
        - Validates required fields and constraints
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Act: create user with basic information
            user = UserProfileService.create_user(
                username="test_player",
                email="test@example.com",
                password="secure123",
                role="player",
            )

            # Assert: user was created properly
            assert user is not None
            assert user.username == "test_player"
            assert user.email == "test@example.com"
            assert user.role == UserRole.PLAYER.value
            assert user.check_password("secure123")

            # Verify it exists in database (transaction committed)
            db_user = db.session.get(User, user.id)
            assert db_user is not None
            assert db_user.username == "test_player"

            # Cleanup
            db.session.delete(user)
            db.session.commit()

    def test_create_user_with_optional_phone(self, app, db_session):
        """
        RED: Test UserProfileService.create_user() with optional phone number.

        Expected behavior:
        - Creates user with phone number
        - Handles None phone gracefully
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Act: create user with phone
            user = UserProfileService.create_user(
                username="phone_user",
                email="phone@example.com",
                password="secure123",
                role="player",
                phone="+39 123 456 7890",
            )

            # Assert: phone was stored properly
            assert user.phone == "+39 123 456 7890"

            # Cleanup
            db.session.delete(user)
            db.session.commit()

    def test_create_user_validates_required_fields(self, app, db_session):
        """
        RED: Test UserProfileService.create_user() input validation.

        Expected behavior:
        - Raises ValueError for missing/invalid username
        - Raises ValueError for missing/invalid email
        - Raises ValueError for short passwords
        - Raises ValueError for invalid roles
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Test missing username
            with pytest.raises(ValueError, match="Username is required"):
                UserProfileService.create_user(
                    "", "test@example.com", "secure123", "player"
                )

            # Test missing email
            with pytest.raises(ValueError, match="Email is required"):
                UserProfileService.create_user("test", "", "secure123", "player")

            # Test short password
            with pytest.raises(
                ValueError, match="Password must be at least 6 characters"
            ):
                UserProfileService.create_user(
                    "test", "test@example.com", "123", "player"
                )

            # Test invalid role
            with pytest.raises(ValueError, match="Invalid role"):
                UserProfileService.create_user(
                    "test", "test@example.com", "secure123", "invalid"
                )

    def test_create_user_prevents_duplicate_email(self, app, db_session):
        """
        RED: Test UserProfileService.create_user() email uniqueness validation.

        Expected behavior:
        - Raises ValueError for duplicate emails (case insensitive)
        - Handles encrypted email field properly
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create first user
            user1 = UserProfileService.create_user(
                username="user1",
                email="test@example.com",
                password="secure123",
                role="player",
            )

            # Attempt duplicate email (case insensitive)
            with pytest.raises(
                ValueError, match="Email 'TEST@EXAMPLE.COM' already exists"
            ):
                UserProfileService.create_user(
                    username="user2",
                    email="TEST@EXAMPLE.COM",
                    password="secure123",
                    role="player",
                )

            # Cleanup
            db.session.delete(user1)
            db.session.commit()

    def test_create_user_admin_uniqueness_constraint(self, app, db_session):
        """
        RED: Test UserProfileService.create_user() admin user uniqueness.

        Expected behavior:
        - Only one active admin user allowed
        - Raises ValueError when attempting to create second admin
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create first admin
            admin1 = UserProfileService.create_user(
                username="admin1",
                email="admin1@example.com",
                password="secure123",
                role="admin",
            )

            # Attempt to create second admin
            with pytest.raises(ValueError, match="Esiste già un amministratore attivo"):
                UserProfileService.create_user(
                    username="admin2",
                    email="admin2@example.com",
                    password="secure123",
                    role="admin",
                )

            # Cleanup
            db.session.delete(admin1)
            db.session.commit()

    def test_update_user_basic_functionality(self, app, db_session):
        """
        RED: Test UserProfileService.update_user() basic update operations.

        Expected behavior:
        - Updates user fields (username, email, phone)
        - Returns updated User object
        - Uses @transactional decorator for transaction management
        - Validates field constraints
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create test user
            user = UserProfileService.create_user(
                username="update_test",
                email="original@example.com",
                password="secure123",
                role="player",
            )

            # Act: update user fields
            updated_user = UserProfileService.update_user(
                user_id=user.id,
                username="updated_username",
                email="updated@example.com",
                phone="+39 987 654 3210",
            )

            # Assert: fields were updated
            assert updated_user.username == "updated_username"
            assert updated_user.email == "updated@example.com"
            assert updated_user.phone == "+39 987 654 3210"

            # Verify changes persist in database
            db_user = db.session.get(User, user.id)
            assert db_user.username == "updated_username"
            assert db_user.email == "updated@example.com"

            # Cleanup
            db.session.delete(updated_user)
            db.session.commit()

    def test_update_user_validates_username_uniqueness(self, app, db_session):
        """
        RED: Test UserProfileService.update_user() username uniqueness validation.

        Expected behavior:
        - Raises ValueError when updating to existing username
        - Allows updating to same username (no change)
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create two users
            user1 = UserProfileService.create_user(
                username="user1",
                email="user1@example.com",
                password="secure123",
                role="player",
            )
            user2 = UserProfileService.create_user(
                username="user2",
                email="user2@example.com",
                password="secure123",
                role="player",
            )

            # Attempt to update user2 to user1's username
            with pytest.raises(ValueError, match="Username 'user1' already exists"):
                UserProfileService.update_user(user_id=user2.id, username="user1")

            # Cleanup
            db.session.delete(user1)
            db.session.delete(user2)
            db.session.commit()

    def test_update_user_prevents_admin_modification(self, app, db_session):
        """
        RED: Test UserProfileService.update_user() admin protection.

        Expected behavior:
        - Raises ValueError when attempting to modify admin user
        - Admin users should be protected from modification
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create admin user
            admin = UserProfileService.create_user(
                username="test_admin",
                email="admin@example.com",
                password="secure123",
                role="admin",
            )

            # Attempt to update admin user
            with pytest.raises(ValueError, match="Cannot modify administrator user"):
                UserProfileService.update_user(
                    user_id=admin.id, username="modified_admin"
                )

            # Cleanup
            db.session.delete(admin)
            db.session.commit()

    def test_update_user_not_found_error(self, app, db_session):
        """
        RED: Test UserProfileService.update_user() error handling.

        Expected behavior:
        - Raises ValueError for non-existent user ID
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Attempt to update non-existent user
            with pytest.raises(ValueError, match="User not found"):
                UserProfileService.update_user(user_id=99999, username="nonexistent")

    def test_change_password_functionality(self, app, db_session):
        """
        RED: Test UserProfileService.change_password() password update.

        Expected behavior:
        - Changes user password after validating old password
        - Returns True on success
        - Uses @transactional decorator for transaction management
        - Validates password requirements
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create test user
            user = UserProfileService.create_user(
                username="password_test",
                email="password@example.com",
                password="oldpass123",
                role="player",
            )

            # Act: change password
            result = UserProfileService.change_password(
                user_id=user.id, old_password="oldpass123", new_password="newpass456"
            )

            # Assert: password was changed
            assert result is True

            # Verify new password works
            db_user = db.session.get(User, user.id)
            assert db_user.check_password("newpass456")
            assert not db_user.check_password("oldpass123")

            # Cleanup
            db.session.delete(user)
            db.session.commit()

    def test_change_password_validates_old_password(self, app, db_session):
        """
        RED: Test UserProfileService.change_password() old password validation.

        Expected behavior:
        - Returns False for incorrect old password
        - Does not change password on validation failure
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create test user
            user = UserProfileService.create_user(
                username="password_validate",
                email="validate@example.com",
                password="correctpass",
                role="player",
            )

            # Act: attempt change with wrong old password
            result = UserProfileService.change_password(
                user_id=user.id, old_password="wrongpass", new_password="newpass456"
            )

            # Assert: password change failed
            assert result is False

            # Verify original password still works
            db_user = db.session.get(User, user.id)
            assert db_user.check_password("correctpass")

            # Cleanup
            db.session.delete(user)
            db.session.commit()

    def test_change_password_validates_new_password_length(self, app, db_session):
        """
        RED: Test UserProfileService.change_password() new password validation.

        Expected behavior:
        - Raises ValueError for passwords shorter than 6 characters
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create test user
            user = UserProfileService.create_user(
                username="password_length",
                email="length@example.com",
                password="oldpass123",
                role="player",
            )

            # Act & Assert: attempt change with short password
            with pytest.raises(
                ValueError, match="New password must be at least 6 characters"
            ):
                UserProfileService.change_password(
                    user_id=user.id, old_password="oldpass123", new_password="123"
                )

            # Cleanup
            db.session.delete(user)
            db.session.commit()

    def test_change_password_prevents_admin_modification(self, app, db_session):
        """
        RED: Test UserProfileService.change_password() admin protection.

        Expected behavior:
        - Raises ValueError when attempting to change admin password
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create admin user
            admin = UserProfileService.create_user(
                username="admin_password",
                email="adminpass@example.com",
                password="adminpass123",
                role="admin",
            )

            # Attempt to change admin password
            with pytest.raises(
                ValueError, match="Cannot change password for administrator user"
            ):
                UserProfileService.change_password(
                    user_id=admin.id,
                    old_password="adminpass123",
                    new_password="newadminpass",
                )

            # Cleanup
            db.session.delete(admin)
            db.session.commit()

    def test_soft_delete_user_functionality(self, app, db_session):
        """
        RED: Test UserProfileService.soft_delete_user() soft deletion.

        Expected behavior:
        - Marks user as deleted without removing from database
        - Uses @transactional decorator for transaction management
        - Preserves user data for audit trail
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create test user
            user = UserProfileService.create_user(
                username="delete_test",
                email="delete@example.com",
                password="secure123",
                role="player",
            )

            user_id = user.id
            assert not user.is_deleted  # Initially not deleted

            # Act: soft delete user
            UserProfileService.soft_delete_user(user_id=user_id)

            # Assert: user was soft deleted
            db_user = db.session.get(User, user_id)
            assert db_user is not None  # Still exists in database
            assert db_user.is_deleted is True  # But marked as deleted

            # Cleanup
            db.session.delete(db_user)
            db.session.commit()

    def test_soft_delete_user_prevents_admin_deletion(self, app, db_session):
        """
        RED: Test UserProfileService.soft_delete_user() admin protection.

        Expected behavior:
        - Raises ValueError when attempting to delete admin user
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create admin user
            admin = UserProfileService.create_user(
                username="admin_delete",
                email="admindelete@example.com",
                password="secure123",
                role="admin",
            )

            # Attempt to delete admin user
            with pytest.raises(ValueError, match="Cannot delete administrator user"):
                UserProfileService.soft_delete_user(user_id=admin.id)

            # Cleanup
            db.session.delete(admin)
            db.session.commit()

    def test_get_user_by_email_functionality(self, app, db_session):
        """
        RED: Test UserProfileService.get_user_by_email() user retrieval.

        Expected behavior:
        - Returns User object for existing email (case insensitive)
        - Returns None for non-existent email
        - Handles encrypted email field properly
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create test user
            user = UserProfileService.create_user(
                username="email_find",
                email="findemail@example.com",
                password="secure123",
                role="player",
            )

            # Test finding existing user by email
            found_user = UserProfileService.get_user_by_email("findemail@example.com")
            assert found_user is not None
            assert found_user.id == user.id

            # Test case insensitive search
            found_user2 = UserProfileService.get_user_by_email("FINDEMAIL@EXAMPLE.COM")
            assert found_user2 is not None
            assert found_user2.id == user.id

            # Test non-existent email
            not_found = UserProfileService.get_user_by_email("nonexistent@example.com")
            assert not_found is None

            # Cleanup
            db.session.delete(user)
            db.session.commit()

    def test_get_all_users_functionality(self, app, db_session):
        """
        RED: Test UserProfileService.get_all_users() user retrieval.

        Expected behavior:
        - Returns list of all users in the system
        - Includes users of all roles
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Count existing users
            initial_count = len(UserProfileService.get_all_users())

            # Create test users
            user1 = UserProfileService.create_user(
                username="all_user1",
                email="all1@example.com",
                password="secure123",
                role="player",
            )
            user2 = UserProfileService.create_user(
                username="all_user2",
                email="all2@example.com",
                password="secure123",
                role="director",
            )

            # Test getting all users
            all_users = UserProfileService.get_all_users()
            assert len(all_users) == initial_count + 2

            user_ids = [u.id for u in all_users]
            assert user1.id in user_ids
            assert user2.id in user_ids

            # Cleanup
            db.session.delete(user1)
            db.session.delete(user2)
            db.session.commit()

    def test_get_users_by_role_functionality(self, app, db_session):
        """
        RED: Test UserProfileService.get_users_by_role() role-based retrieval.

        Expected behavior:
        - Returns list of users with specified role
        - Filters correctly by role
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create users with different roles
            player1 = UserProfileService.create_user(
                username="role_player1",
                email="rp1@example.com",
                password="secure123",
                role="player",
            )
            player2 = UserProfileService.create_user(
                username="role_player2",
                email="rp2@example.com",
                password="secure123",
                role="player",
            )
            director = UserProfileService.create_user(
                username="role_director",
                email="rd@example.com",
                password="secure123",
                role="director",
            )

            # Test getting users by role
            players = UserProfileService.get_users_by_role("player")
            directors = UserProfileService.get_users_by_role("director")

            player_ids = [u.id for u in players]
            director_ids = [u.id for u in directors]

            assert player1.id in player_ids
            assert player2.id in player_ids
            assert director.id not in player_ids

            assert director.id in director_ids
            assert player1.id not in director_ids
            assert player2.id not in director_ids

            # Cleanup
            db.session.delete(player1)
            db.session.delete(player2)
            db.session.delete(director)
            db.session.commit()

    def test_get_user_detail_data_functionality(self, app, db_session):
        """
        RED: Test UserProfileService.get_user_detail_data() comprehensive data retrieval.

        Expected behavior:
        - Returns dictionary with user, inscriptions, matches, classifications
        - Uses @read_only decorator for read operations
        - Optimizes queries for user detail page
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Create test user
            user = UserProfileService.create_user(
                username="detail_user",
                email="detail@example.com",
                password="secure123",
                role="player",
            )

            # Act: get user detail data
            detail_data = UserProfileService.get_user_detail_data(user_id=user.id)

            # Assert: returns proper structure
            assert isinstance(detail_data, dict)
            assert "user" in detail_data
            assert "inscriptions" in detail_data
            assert "matches" in detail_data
            assert "classifications" in detail_data

            assert detail_data["user"].id == user.id
            assert isinstance(detail_data["inscriptions"], list)
            assert isinstance(detail_data["matches"], list)
            assert isinstance(detail_data["classifications"], list)

            # Cleanup
            db.session.delete(user)
            db.session.commit()

    def test_get_user_detail_data_not_found_error(self, app, db_session):
        """
        RED: Test UserProfileService.get_user_detail_data() error handling.

        Expected behavior:
        - Raises ValueError for non-existent user ID
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Attempt to get detail data for non-existent user
            with pytest.raises(ValueError, match="User not found"):
                UserProfileService.get_user_detail_data(user_id=99999)

    def test_transaction_decorator_usage(self, app, db_session):
        """
        RED: Test that UserProfileService methods use @transactional decorator properly.

        Expected behavior:
        - Create/update/delete operations use @transactional
        - Read operations use @read_only
        - Transaction boundaries are respected
        """
        with app.app_context():
            # This test documents expected decorator usage for implementation
            # Implementation should use:
            # - @transactional(domain="user") for create_user, update_user, change_password, soft_delete_user
            # - @read_only(domain="user") for get_user_detail_data
            # - No decorator for simple read operations (authenticate_user, get_user_by_*, get_all_users, get_users_by_role)

            from models.user.services import UserProfileService

            # Test transaction behavior by creating and immediately reading
            user = UserProfileService.create_user(
                username="transaction_test",
                email="transaction@example.com",
                password="secure123",
                role="player",
            )

            # Should be immediately available (transaction committed)
            found_user = UserProfileService.get_user_by_username("transaction_test")
            assert found_user is not None
            assert found_user.id == user.id

            # Cleanup
            db.session.delete(user)
            db.session.commit()

    def test_error_handling_and_rollback_behavior(self, app, db_session):
        """
        RED: Test UserProfileService error handling and transaction rollback.

        Expected behavior:
        - Failed operations should rollback properly
        - No partial data should remain after failures
        - Exceptions should propagate correctly
        """
        with app.app_context():
            from models.user.services import UserProfileService

            # Test that failed user creation doesn't leave partial data
            with pytest.raises(ValueError):
                UserProfileService.create_user(
                    username="",  # Invalid username should fail
                    email="test@example.com",
                    password="secure123",
                    role="player",
                )

            # Verify no user was created with that email
            not_found = UserProfileService.get_user_by_email("test@example.com")
            assert not_found is None
