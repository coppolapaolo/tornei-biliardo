"""
Test module for routes/admin.py compatibility layer
"""

import pytest

# Import the admin blueprint
from routes.admin import admin_bp


class TestAdminCompatibility:
    """Test cases for admin compatibility layer."""

    def test_admin_blueprint_exists(self):
        """Test that the admin blueprint exists."""
        assert admin_bp is not None
        assert hasattr(admin_bp, "name")
        assert admin_bp.name == "admin"

    def test_admin_blueprint_url_prefix(self):
        """Test that the admin blueprint has the correct URL prefix."""
        assert hasattr(admin_bp, "url_prefix")
        assert admin_bp.url_prefix == "/admin"


if __name__ == "__main__":
    pytest.main([__file__])
