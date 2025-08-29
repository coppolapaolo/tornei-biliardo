"""
Simple tests for utils/__init__.py UserPermissions class only.
"""

import pytest
from unittest.mock import patch

from utils import UserPermissions


class TestUserPermissionsDetailed:
    """Test UserPermissions methods for full branch coverage."""

    @patch('utils.current_user')
    def test_can_inscribe_to_prova_all_cases(self, mock_user):
        """Test all branches of can_inscribe_to_prova."""
        # Case 1: Authenticated non-admin (should return True)
        mock_user.is_authenticated = True
        mock_user.is_admin = False
        assert UserPermissions.can_inscribe_to_prova() is True
        
        # Case 2: Authenticated admin (should return False)
        mock_user.is_admin = True
        assert UserPermissions.can_inscribe_to_prova() is False
        
        # Case 3: Unauthenticated (should return False)
        mock_user.is_authenticated = False
        assert UserPermissions.can_inscribe_to_prova() is False

    @patch('utils.current_user')
    def test_can_view_profile_all_cases(self, mock_user):
        """Test all branches of can_view_profile."""
        # Case 1: Authenticated non-admin (should return True)
        mock_user.is_authenticated = True
        mock_user.is_admin = False
        assert UserPermissions.can_view_profile() is True
        
        # Case 2: Authenticated admin (should return False)
        mock_user.is_admin = True
        assert UserPermissions.can_view_profile() is False
        
        # Case 3: Unauthenticated (should return False)
        mock_user.is_authenticated = False
        assert UserPermissions.can_view_profile() is False

    @patch('utils.current_user')
    def test_can_delete_account_all_cases(self, mock_user):
        """Test all branches of can_delete_account."""
        # Case 1: Authenticated non-admin (should return True)
        mock_user.is_authenticated = True
        mock_user.is_admin = False
        assert UserPermissions.can_delete_account() is True
        
        # Case 2: Authenticated admin (should return False)
        mock_user.is_admin = True
        assert UserPermissions.can_delete_account() is False
        
        # Case 3: Unauthenticated (should return False)
        mock_user.is_authenticated = False
        assert UserPermissions.can_delete_account() is False

    @patch('utils.current_user')
    def test_show_admin_management_all_cases(self, mock_user):
        """Test all branches of show_admin_management."""
        # Case 1: Authenticated admin (should return True)
        mock_user.is_authenticated = True
        mock_user.is_admin = True
        assert UserPermissions.show_admin_management() is True
        
        # Case 2: Authenticated non-admin (should return False)
        mock_user.is_admin = False
        assert UserPermissions.show_admin_management() is False
        
        # Case 3: Unauthenticated (should return False)
        mock_user.is_authenticated = False
        assert UserPermissions.show_admin_management() is False

    @patch('utils.current_user')
    def test_show_director_management_all_cases(self, mock_user):
        """Test all branches of show_director_management."""
        # Case 1: Authenticated director (should return True)
        mock_user.is_authenticated = True
        mock_user.is_director = True
        assert UserPermissions.show_director_management() is True
        
        # Case 2: Authenticated non-director (should return False)
        mock_user.is_director = False
        assert UserPermissions.show_director_management() is False
        
        # Case 3: Unauthenticated (should return False)
        mock_user.is_authenticated = False
        assert UserPermissions.show_director_management() is False

    @patch('utils.current_user')
    def test_get_default_dashboard_all_cases(self, mock_user):
        """Test all branches of get_default_dashboard."""
        # Case 1: Authenticated admin
        mock_user.is_authenticated = True
        mock_user.is_admin = True
        assert UserPermissions.get_default_dashboard() == "admin.dashboard"
        
        # Case 2: Authenticated non-admin (player)
        mock_user.is_admin = False
        assert UserPermissions.get_default_dashboard() == "player.dashboard"
        
        # Case 3: Unauthenticated
        mock_user.is_authenticated = False
        assert UserPermissions.get_default_dashboard() == "main.index"