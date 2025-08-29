"""
Test module for utils/jinja.py
"""

from datetime import datetime
from utils.jinja import display_user_handle
from models.user.models import User


class TestJinjaUtils:
    """Test cases for jinja utilities."""

    def test_display_user_handle_active_user(self):
        """Test display_user_handle with an active user."""
        user = User(username="testuser")
        # Mock the is_deleted property
        user.__dict__["deleted_at"] = None
        result = display_user_handle(user)
        assert "testuser" in str(result)
        assert "🗑️" not in str(result)

    def test_display_user_handle_deleted_user(self):
        """Test display_user_handle with a deleted user."""
        user = User(username="testuser")
        # Mock the is_deleted property
        user.__dict__["deleted_at"] = datetime(2023, 1, 15)
        result = display_user_handle(user)
        assert "🗑️" in str(result)
        assert "<s>testuser</s>" in str(result)
        assert "15/01/2023" in str(result)

    def test_display_user_handle_deleted_user_with_previous_username(self):
        """Test display_user_handle with a deleted user that had a previous username."""
        user = User(username="newname")
        user.__dict__["deleted_at"] = datetime(2023, 1, 15)
        user.previous_username = "oldname"
        result = display_user_handle(user)
        assert "🗑️" in str(result)
        assert "<s>oldname</s>" in str(result)
        assert "15/01/2023" in str(result)

    def test_display_user_handle_deleted_user_no_date(self):
        """Test display_user_handle with a deleted user that has no deletion date."""
        user = User(username="testuser")
        user.__dict__["deleted_at"] = None  # Not deleted
        result = display_user_handle(user)
        assert "🗑️" not in str(result)
        assert "testuser" in str(result)
