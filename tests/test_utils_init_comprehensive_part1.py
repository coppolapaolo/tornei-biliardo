"""
Comprehensive enhanced tests for utils/__init__.py - Part 1
Testing decorators and UserPermissions to achieve high coverage.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from flask import Flask
from flask_login import AnonymousUserMixin

# Import functions to test
from utils import (
    prova_manager_required,
    match_manager_required,
    UserPermissions,
    player_only,
    player_required,
    match_player_required,
    rack_player_required,
    inscription_owner_required,
    challenge_player_required,
    challenge_attempt_player_required,
    individual_match_player_required,
    rack_manager_required,
    trio_manager_required
)


@pytest.fixture
def app():
    """Create Flask app for testing."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    return app


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = Mock()
    user.id = 1
    user.is_authenticated = True
    user.is_admin = False
    user.is_director = False
    return user


class TestProvaManagerRequired:
    """Test prova_manager_required decorator implementation."""

    def test_prova_manager_required_decorator_exists(self):
        """Test that prova_manager_required decorator exists and is callable."""
        assert callable(prova_manager_required)
        
        # Test that it can decorate a function
        @prova_manager_required
        def test_function():
            return "success"
        
        assert callable(test_function)


class TestMatchManagerRequired:
    """Test match_manager_required decorator implementation."""

    def test_match_manager_required_decorator_exists(self):
        """Test that match_manager_required decorator exists and is callable."""
        assert callable(match_manager_required)
        
        # Test that it can decorate a function
        @match_manager_required
        def test_function():
            return "success"
        
        assert callable(test_function)


class TestUserPermissionsImplementation:
    """Test UserPermissions static methods implementation."""

    def test_can_inscribe_to_prova_authenticated_player(self):
        """Test can_inscribe_to_prova for authenticated non-admin."""
        with patch('utils.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.is_admin = False
            
            result = UserPermissions.can_inscribe_to_prova()
            assert result is True

    def test_can_inscribe_to_prova_admin(self):
        """Test can_inscribe_to_prova for admin."""
        with patch('utils.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.is_admin = True
            
            result = UserPermissions.can_inscribe_to_prova()
            assert result is False

    def test_can_inscribe_to_prova_unauthenticated(self):
        """Test can_inscribe_to_prova for unauthenticated user."""
        with patch('utils.current_user') as mock_user:
            mock_user.is_authenticated = False
            
            result = UserPermissions.can_inscribe_to_prova()
            assert result is False

    def test_can_view_profile_variations(self):
        """Test can_view_profile for different user types."""
        with patch('utils.current_user') as mock_user:
            # Authenticated player
            mock_user.is_authenticated = True
            mock_user.is_admin = False
            assert UserPermissions.can_view_profile() is True
            
            # Admin
            mock_user.is_admin = True
            assert UserPermissions.can_view_profile() is False
            
            # Unauthenticated
            mock_user.is_authenticated = False
            assert UserPermissions.can_view_profile() is False

    def test_can_delete_account_variations(self):
        """Test can_delete_account for different user types."""
        with patch('utils.current_user') as mock_user:
            # Authenticated player
            mock_user.is_authenticated = True
            mock_user.is_admin = False
            assert UserPermissions.can_delete_account() is True
            
            # Admin
            mock_user.is_admin = True
            assert UserPermissions.can_delete_account() is False

    def test_show_admin_management_variations(self):
        """Test show_admin_management for different user types."""
        with patch('utils.current_user') as mock_user:
            # Admin
            mock_user.is_authenticated = True
            mock_user.is_admin = True
            assert UserPermissions.show_admin_management() is True
            
            # Non-admin
            mock_user.is_admin = False
            assert UserPermissions.show_admin_management() is False
            
            # Unauthenticated
            mock_user.is_authenticated = False
            assert UserPermissions.show_admin_management() is False

    def test_show_director_management_variations(self):
        """Test show_director_management for different user types."""
        with patch('utils.current_user') as mock_user:
            # Director
            mock_user.is_authenticated = True
            mock_user.is_director = True
            assert UserPermissions.show_director_management() is True
            
            # Non-director
            mock_user.is_director = False
            assert UserPermissions.show_director_management() is False

    def test_get_default_dashboard_all_types(self):
        """Test get_default_dashboard for all user types."""
        with patch('utils.current_user') as mock_user:
            # Admin
            mock_user.is_authenticated = True
            mock_user.is_admin = True
            assert UserPermissions.get_default_dashboard() == "admin.dashboard"
            
            # Player
            mock_user.is_admin = False
            assert UserPermissions.get_default_dashboard() == "player.dashboard"
            
            # Unauthenticated
            mock_user.is_authenticated = False
            assert UserPermissions.get_default_dashboard() == "main.index"


class TestPlayerOnlyDecorator:
    """Test player_only decorator implementation."""

    def test_player_only_admin_user(self):
        """Test player_only blocks admin access."""
        with patch('utils.current_user') as mock_user, \
             patch('utils.flash') as mock_flash, \
             patch('utils.redirect') as mock_redirect, \
             patch('utils.url_for') as mock_url_for:
            
            mock_user.is_authenticated = True
            mock_user.is_admin = True
            mock_url_for.return_value = "/admin/dashboard"
            mock_redirect.return_value = "redirect_response"
            
            @player_only
            def test_function():
                return "success"
            
            result = test_function()
            assert result == "redirect_response"
            mock_flash.assert_called_once()
            mock_url_for.assert_called_once_with("admin.dashboard")

    def test_player_only_allows_non_admin(self):
        """Test player_only allows non-admin access."""
        with patch('utils.current_user') as mock_user:
            # Player
            mock_user.is_authenticated = True
            mock_user.is_admin = False
            
            @player_only
            def test_function():
                return "success"
            
            result = test_function()
            assert result == "success"
            
            # Unauthenticated
            mock_user.is_authenticated = False
            result = test_function()
            assert result == "success"


class TestPlayerRequiredDecorator:
    """Test player_required decorator implementation."""

    def test_player_required_missing_prova_id(self):
        """Test player_required when prova_id is missing."""
        with patch('utils.abort') as mock_abort:
            
            @player_required
            def test_function(**kwargs):
                return "success"
            
            test_function()
            mock_abort.assert_called_once_with(400)

    def test_player_required_enrolled_player(self):
        """Test player_required when player is enrolled."""
        with patch('utils.current_user') as mock_user, \
             patch('utils.Inscription') as mock_inscription:
            
            mock_user.id = 1
            mock_inscription_instance = Mock()
            mock_inscription.query.filter_by.return_value.first.return_value = mock_inscription_instance
            
            @player_required
            def test_function(prova_id=1):
                return "success"
            
            result = test_function(prova_id=1)
            assert result == "success"
            mock_inscription.query.filter_by.assert_called_once_with(user_id=1, prova_id=1)

    def test_player_required_not_enrolled(self):
        """Test player_required when player is not enrolled."""
        with patch('utils.current_user') as mock_user, \
             patch('utils.Inscription') as mock_inscription, \
             patch('utils.flash') as mock_flash, \
             patch('utils.redirect') as mock_redirect, \
             patch('utils.url_for') as mock_url_for:
            
            mock_user.id = 1
            mock_inscription.query.filter_by.return_value.first.return_value = None
            mock_url_for.return_value = "/dashboard"
            mock_redirect.return_value = "redirect_response"
            
            @player_required
            def test_function(prova_id=1):
                return "success"
            
            result = test_function(prova_id=1)
            assert result == "redirect_response"
            mock_flash.assert_called_once_with("Non sei iscritto a questa prova.", "error")


class TestMatchPlayerRequiredDecorator:
    """Test match_player_required decorator implementation."""

    def test_match_player_required_missing_match_id(self):
        """Test match_player_required when match_id is missing."""
        with patch('utils.abort') as mock_abort:
            
            @match_player_required
            def test_function(**kwargs):
                return "success"
            
            test_function()
            mock_abort.assert_called_once_with(400)

    def test_match_player_required_match_not_found(self):
        """Test match_player_required when match is not found."""
        with patch('utils.Match') as mock_match, \
             patch('utils.abort') as mock_abort:
            
            mock_match.query.get.return_value = None
            
            @match_player_required
            def test_function(match_id=1):
                return "success"
            
            test_function(match_id=1)
            mock_abort.assert_called_once_with(404)

    def test_match_player_required_valid_player(self):
        """Test match_player_required when user is a valid player."""
        with patch('utils.current_user') as mock_user, \
             patch('utils.Match') as mock_match:
            
            mock_user.id = 1
            mock_match_instance = Mock()
            mock_match_instance.player1_id = 1
            mock_match_instance.player2_id = 2
            mock_match.query.get.return_value = mock_match_instance
            
            @match_player_required
            def test_function(match_id=1):
                return "success"
            
            result = test_function(match_id=1)
            assert result == "success"

    def test_match_player_required_invalid_player(self):
        """Test match_player_required when user is not a player in the match."""
        with patch('utils.current_user') as mock_user, \
             patch('utils.Match') as mock_match, \
             patch('utils.flash') as mock_flash, \
             patch('utils.redirect') as mock_redirect, \
             patch('utils.url_for') as mock_url_for:
            
            mock_user.id = 3  # Not player1 or player2
            mock_match_instance = Mock()
            mock_match_instance.player1_id = 1
            mock_match_instance.player2_id = 2
            mock_match.query.get.return_value = mock_match_instance
            mock_url_for.return_value = "/dashboard"
            mock_redirect.return_value = "redirect_response"
            
            @match_player_required
            def test_function(match_id=1):
                return "success"
            
            result = test_function(match_id=1)
            assert result == "redirect_response"
            mock_flash.assert_called_once_with("Non sei un giocatore di questa partita.", "error")


class TestInscriptionOwnerRequiredDecorator:
    """Test inscription_owner_required decorator implementation."""

    def test_inscription_owner_required_missing_inscription_id(self):
        """Test inscription_owner_required when inscription_id is missing."""
        with patch('utils.abort') as mock_abort:
            
            @inscription_owner_required
            def test_function(**kwargs):
                return "success"
            
            test_function()
            mock_abort.assert_called_once_with(400)

    def test_inscription_owner_required_inscription_not_found(self):
        """Test inscription_owner_required when inscription is not found."""
        with patch('utils.Inscription') as mock_inscription, \
             patch('utils.abort') as mock_abort:
            
            mock_inscription.query.get.return_value = None
            
            @inscription_owner_required
            def test_function(inscription_id=1):
                return "success"
            
            test_function(inscription_id=1)
            mock_abort.assert_called_once_with(404)

    def test_inscription_owner_required_valid_owner(self):
        """Test inscription_owner_required when user is the owner."""
        with patch('utils.current_user') as mock_user, \
             patch('utils.Inscription') as mock_inscription:
            
            mock_user.id = 1
            mock_inscription_instance = Mock()
            mock_inscription_instance.user_id = 1
            mock_inscription.query.get.return_value = mock_inscription_instance
            
            @inscription_owner_required
            def test_function(inscription_id=1):
                return "success"
            
            result = test_function(inscription_id=1)
            assert result == "success"

    def test_inscription_owner_required_not_owner(self):
        """Test inscription_owner_required when user is not the owner."""
        with patch('utils.current_user') as mock_user, \
             patch('utils.Inscription') as mock_inscription, \
             patch('utils.flash') as mock_flash, \
             patch('utils.redirect') as mock_redirect, \
             patch('utils.url_for') as mock_url_for:
            
            mock_user.id = 1
            mock_inscription_instance = Mock()
            mock_inscription_instance.user_id = 2  # Different owner
            mock_inscription.query.get.return_value = mock_inscription_instance
            mock_url_for.return_value = "/dashboard"
            mock_redirect.return_value = "redirect_response"
            
            @inscription_owner_required
            def test_function(inscription_id=1):
                return "success"
            
            result = test_function(inscription_id=1)
            assert result == "redirect_response"
            mock_flash.assert_called_once_with("Non sei il proprietario di questa iscrizione.", "error")


class TestChallengePlayerRequiredDecorator:
    """Test challenge_player_required decorator implementation."""

    def test_challenge_player_required_missing_challenge_id(self):
        """Test challenge_player_required when challenge_id is missing."""
        with patch('utils.abort') as mock_abort:
            
            @challenge_player_required
            def test_function(**kwargs):
                return "success"
            
            test_function()
            mock_abort.assert_called_once_with(400)

    def test_challenge_player_required_challenge_not_found(self):
        """Test challenge_player_required when challenge is not found."""
        with patch('utils.Challenge') as mock_challenge, \
             patch('utils.abort') as mock_abort:
            
            mock_challenge.query.get.return_value = None
            
            @challenge_player_required
            def test_function(challenge_id=1):
                return "success"
            
            test_function(challenge_id=1)
            mock_abort.assert_called_once_with(404)

    def test_challenge_player_required_valid_challenge(self):
        """Test challenge_player_required when challenge exists."""
        with patch('utils.Challenge') as mock_challenge:
            
            mock_challenge_instance = Mock()
            mock_challenge.query.get.return_value = mock_challenge_instance
            
            @challenge_player_required
            def test_function(challenge_id=1):
                return "success"
            
            result = test_function(challenge_id=1)
            assert result == "success"