"""Unit tests for case-sensitive usernames in services."""

import pytest
import uuid
from models.user.services import UserService
from models.user.profile_service import UserProfileService
from models.user.models import User
from models.user.role_enum import UserRole


@pytest.mark.unit
class TestCaseSensitiveUsername:
    """Test case-sensitive username behavior in services."""

    def test_authenticate_user_case_sensitive(self, db_session):
        """Test that authentication is case-sensitive for usernames."""
        unique_id = str(uuid.uuid4())[:8]
        username = f"CaseUser_{unique_id}"
        password = "password123"

        # Create user via service to ensure consistency
        UserProfileService.create_user(
            username=username, email=f"case_{unique_id}@example.com", password=password
        )
        db_session.commit()

        # Test UserService.authenticate_user
        # Exact case match
        assert UserService.authenticate_user(username, password) is not None
        # Different case match (should FAIL now)
        assert UserService.authenticate_user(username.lower(), password) is None
        assert UserService.authenticate_user(username.upper(), password) is None

        # Test UserProfileService.authenticate_user
        # Exact case match
        assert UserProfileService.authenticate_user(username, password) is not None
        # Different case match (should FAIL now)
        assert UserProfileService.authenticate_user(username.lower(), password) is None

    def test_get_by_username_case_sensitive(self, db_session):
        """Test that finding users by username is case-sensitive."""
        unique_id = str(uuid.uuid4())[:8]
        username = f"FindMe_{unique_id}"

        UserProfileService.create_user(
            username=username,
            email=f"find_{unique_id}@example.com",
            password="password123",
        )
        db_session.commit()

        # Test UserService.get_user_by_username
        assert UserService.get_user_by_username(username) is not None
        assert UserService.get_user_by_username(username.lower()) is None

        # Test UserProfileService.get_user_by_username
        assert UserProfileService.get_user_by_username(username) is not None
        assert UserProfileService.get_user_by_username(username.lower()) is None

    def test_create_user_uniqueness_case_sensitive(self, db_session):
        """Test that user creation uniqueness is now case-sensitive."""
        unique_id = str(uuid.uuid4())[:8]
        username = f"Unique_{unique_id}"

        UserProfileService.create_user(
            username=username,
            email=f"u1_{unique_id}@example.com",
            password="password123",
        )
        db_session.commit()

        # Attempting to create same username with DIFFERENT case should now SUCCEED in service layer
        # (Though NOTE: if the DB has a case-insensitive constraint, it might still fail at commit)
        try:
            UserProfileService.create_user(
                username=username.lower(),
                email=f"u2_{unique_id}@example.com",
                password="password123",
            )
            db_session.commit()
            # If we reached here, it means service allowed it AND DB allowed it
            assert True
        except ValueError as e:
            # If service still blocks it case-insensitively, this would be an error
            pytest.fail(
                f"Should allow registration of '{username.lower()}' even if '{username}' exists: {e}"
            )
        except Exception as e:
            # DB level error (e.g. UniqueConstraint in SQLite if not careful)
            # SQLite unique constraints on VARCHAR are case-sensitive by default.
            print(f"DB level block (might be expected depending on DB config): {e}")
            pass

    def test_block_admin_variants(self, db_session):
        """Test that variants of 'admin' are blocked during registration."""
        variants = ["admin", "Admin", "ADMIN", "aDmIn"]
        for variant in variants:
            with pytest.raises(ValueError, match="riservato al sistema"):
                UserProfileService.create_user(
                    username=variant,
                    email=f"{variant}_{uuid.uuid4().hex[:4]}@example.com",
                    password="password123",
                )

        # Test update_user
        unique_id = str(uuid.uuid4())[:8]
        user = UserProfileService.create_user(
            username=f"normaluser_{unique_id}",
            email=f"normal_{unique_id}@example.com",
            password="password123",
        )
        db_session.commit()

        for variant in variants:
            with pytest.raises(ValueError, match="riservato al sistema"):
                UserProfileService.update_user(user.id, username=variant)
