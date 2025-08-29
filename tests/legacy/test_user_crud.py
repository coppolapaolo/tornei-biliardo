"""
Test user creation and deletion functionality.

Tests the basic CRUD operations for User model, focusing on:
- User creation with different roles
- User password functionality
- User deletion (both hard and soft delete)
- User anonymization
- Database integrity after operations
"""

import pytest
from models import User


class TestUserCreation:
    """Test user creation functionality."""

    def test_create_player_user(self, db_session):
        """Test creating a basic player user."""
        user = User(username="test_player", email="player@test.com", role="player")
        user.set_password("testpassword123")

        db_session.add(user)
        db_session.commit()

        # Verify user was created
        assert user.id is not None
        assert user.username == "test_player"
        assert user.email == "player@test.com"
        assert user.role == "player"
        assert user.is_player is True
        assert user.is_admin is False
        assert user.is_director is False

        # Verify password was set correctly
        assert user.check_password("testpassword123") is True
        assert user.check_password("wrongpassword") is False

        # Verify user is active (not soft deleted)
        assert user.is_active is True
        assert user.deleted_at is None

    def test_create_director_user(self, db_session):
        """Test creating a director user."""
        user = User(
            username="test_director", email="director@test.com", role="director"
        )
        user.set_password("directorpass123")

        db_session.add(user)
        db_session.commit()

        # Verify role-specific properties
        assert user.is_director is True
        assert user.is_player is False
        assert user.is_admin is False
        assert user.can_view_admin_panel() is False

    def test_create_admin_user(self, db_session):
        """Test creating an admin user."""
        user = User(username="test_admin", email="admin@test.com", role="admin")
        user.set_password("adminpass123")

        db_session.add(user)
        db_session.commit()

        # Verify admin-specific properties
        assert user.is_admin is True
        assert user.is_player is False
        assert user.is_director is False
        assert user.can_view_admin_panel() is True

    def test_create_user_with_optional_fields(self, db_session):
        """Test creating a user with optional fields."""
        user = User(
            username="full_user",
            email="full@test.com",
            role="player",
            phone="1234567890",
        )
        user.set_password("password123")

        db_session.add(user)
        db_session.commit()

        assert user.phone == "1234567890"
        assert user.email == "full@test.com"

    def test_username_uniqueness(self, db_session):
        """Test that usernames must be unique."""
        user1 = User(username="duplicate_user", email="user1@test.com", role="player")
        user1.set_password("password123")
        db_session.add(user1)
        db_session.commit()

        # Try to create another user with same username
        user2 = User(username="duplicate_user", email="user2@test.com", role="player")
        user2.set_password("password123")
        db_session.add(user2)

        # Should raise integrity error
        with pytest.raises(
            Exception
        ):  # SQLAlchemy will raise IntegrityError or similar
            db_session.commit()

    def test_encrypted_email_behavior(self, db_session):
        """Test that email encryption works properly."""
        user = User(
            username="encrypted_user", email="encrypted@test.com", role="player"
        )
        user.set_password("password123")
        db_session.add(user)
        db_session.commit()

        # Verify that we can retrieve the email correctly
        # (EncryptedString should handle encryption/decryption transparently)
        retrieved_user = User.query.filter_by(username="encrypted_user").first()
        assert retrieved_user.email == "encrypted@test.com"

    def test_null_emails_allowed(self, db_session):
        """Test that multiple users can have null emails (common SQL behavior)."""
        user1 = User(username="user_null1", email=None, role="player")
        user1.set_password("password123")
        db_session.add(user1)
        db_session.commit()

        # Another user with null email should be allowed
        user2 = User(username="user_null2", email=None, role="player")
        user2.set_password("password123")
        db_session.add(user2)
        db_session.commit()  # Should not raise an exception

        assert user1.email is None
        assert user2.email is None


class TestUserDeletion:
    """Test user deletion functionality."""

    def test_hard_delete_user(self, db_session):
        """Test hard deletion of a user."""
        user = User(username="delete_me", email="delete@test.com", role="player")
        user.set_password("password123")

        db_session.add(user)
        db_session.commit()

        user_id = user.id

        # Verify user exists
        assert db_session.get(User, user_id) is not None

        # Hard delete using BaseModel method
        user.delete()

        # Verify user is completely removed
        assert db_session.get(User, user_id) is None

    def test_soft_delete_anonymize_user(self, db_session):
        """Test soft deletion and anonymization of a user."""
        user = User(
            username="anonymize_me",
            email="anonymize@test.com",
            role="player",
            phone="1234567890",
        )
        user.set_password("password123")

        db_session.add(user)
        db_session.commit()

        user_id = user.id
        original_username = user.username

        # Perform anonymization (soft delete)
        user.anonymize()
        db_session.commit()

        # Verify user still exists but is anonymized
        anonymized_user = db_session.get(User, user_id)
        assert anonymized_user is not None

        # Verify anonymization
        assert anonymized_user.deleted_at is not None
        assert anonymized_user.previous_username == original_username
        assert anonymized_user.username.startswith("deleted-")
        assert str(user_id) in anonymized_user.username
        assert anonymized_user.email is None
        assert anonymized_user.phone is None
        assert anonymized_user.password_hash == "!deleted!"

        # Verify user is no longer active
        assert anonymized_user.is_active is False

    def test_anonymize_already_deleted_user(self, db_session):
        """Test anonymizing a user that's already been soft deleted."""
        user = User(username="already_deleted", email="already@test.com", role="player")
        user.set_password("password123")

        db_session.add(user)
        db_session.commit()

        # First anonymization
        user.anonymize()
        db_session.commit()

        first_deleted_at = user.deleted_at
        first_username = user.username

        # Second anonymization should not change deleted_at
        user.anonymize()
        db_session.commit()

        assert user.deleted_at == first_deleted_at
        # Username should remain the same (based on original deleted_at)
        assert user.username == first_username

    def test_delete_user_with_relationships(self, db_session):
        """Test deleting a user that might have relationships."""
        user = User(
            username="user_with_relations", email="relations@test.com", role="player"
        )
        user.set_password("password123")

        db_session.add(user)
        db_session.commit()

        user_id = user.id

        # Test that user can be deleted even if it has relationships
        # (Note: The actual handling of relationships depends on
        # your foreign key constraints)
        user.delete()

        # Verify deletion
        assert db_session.get(User, user_id) is None


class TestUserUtilityMethods:
    """Test user utility and helper methods."""

    def test_user_repr(self, db_session):
        """Test user string representation."""
        user = User(username="repr_user", email="repr@test.com", role="admin")
        user.set_password("password123")

        db_session.add(user)
        db_session.commit()

        repr_str = repr(user)
        assert "repr_user" in repr_str
        assert "admin" in repr_str

    def test_user_statistics_empty(self, db_session):
        """Test user statistics for a user with no matches."""
        user = User(username="stats_user", email="stats@test.com", role="player")
        user.set_password("password123")

        db_session.add(user)
        db_session.commit()

        stats = user.get_statistics()

        # Verify empty statistics
        assert stats["total_inscriptions"] == 0
        assert stats["total_matches"] == 0
        assert stats["won_matches"] == 0
        assert stats["lost_matches"] == 0
        assert stats["win_percentage"] == 0
        assert stats["tournaments_played"] == 0
        assert stats["total_racks_won"] == 0
        assert stats["total_racks_played"] == 0
        assert stats["rack_win_percentage"] == 0

    def test_user_save_method(self, db_session):
        """Test user save utility method."""
        user = User(username="save_user", email="save@test.com", role="player")
        user.set_password("password123")

        # Use save method instead of manual add/commit
        saved_user = user.save()

        assert saved_user.id is not None
        assert User.query.filter_by(username="save_user").first() is not None

    def test_user_to_dict(self, db_session):
        """Test user to_dict conversion method."""
        user = User(username="dict_user", email="dict@test.com", role="director")
        user.set_password("password123")

        db_session.add(user)
        db_session.commit()

        user_dict = user.to_dict()

        assert isinstance(user_dict, dict)
        assert user_dict["username"] == "dict_user"
        assert user_dict["email"] == "dict@test.com"
        assert user_dict["role"] == "director"
        assert "id" in user_dict
        assert "created_at" in user_dict
        assert "updated_at" in user_dict

    def test_find_by_id_class_method(self, db_session):
        """Test User.find_by_id class method."""
        user = User(username="find_user", email="find@test.com", role="player")
        user.set_password("password123")

        db_session.add(user)
        db_session.commit()

        user_id = user.id

        # Test find_by_id
        found_user = User.find_by_id(user_id)
        assert found_user is not None
        assert found_user.username == "find_user"

        # Test with non-existent ID
        not_found = User.find_by_id(99999)
        assert not_found is None

    def test_find_all_class_method(self, db_session):
        """Test User.find_all class method."""
        # Create multiple users
        user1 = User(username="user1", email="user1@test.com", role="player")
        user1.set_password("password123")

        user2 = User(username="user2", email="user2@test.com", role="director")
        user2.set_password("password123")

        db_session.add_all([user1, user2])
        db_session.commit()

        # Test find_all
        all_users = User.find_all()
        assert (
            len(all_users) >= 2
        )  # At least our two users (might be more from other tests)

        usernames = [u.username for u in all_users]
        assert "user1" in usernames
        assert "user2" in usernames


class TestUserValidation:
    """Test user validation and edge cases."""

    def test_create_user_missing_required_fields(self, db_session):
        """Test that creating a user without required fields fails."""
        # Missing username should fail
        with pytest.raises(Exception):
            user = User(email="missing@test.com", role="player")
            user.set_password("password123")
            db_session.add(user)
            db_session.commit()

    def test_invalid_role_handling(self, db_session):
        """Test behavior with invalid roles."""
        user = User(
            username="invalid_role_user",
            email="invalid@test.com",
            role="invalid_role",  # Not admin/director/player
        )
        user.set_password("password123")

        db_session.add(user)
        db_session.commit()

        # Should still work but role properties should be False
        assert user.is_admin is False
        assert user.is_director is False
        assert user.is_player is False
        assert user.can_view_admin_panel() is False

    def test_empty_password_handling(self, db_session):
        """Test that empty passwords are handled appropriately."""
        user = User(username="empty_pass_user", email="empty@test.com", role="player")

        # Test with empty string
        user.set_password("")

        db_session.add(user)
        db_session.commit()

        # Should have some hash, even for empty password
        assert user.password_hash != ""
        assert user.password_hash is not None

        # Should be able to check empty password
        assert user.check_password("") is True
        assert user.check_password("something") is False
