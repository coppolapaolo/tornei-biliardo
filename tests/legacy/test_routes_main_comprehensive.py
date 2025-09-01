"""
Comprehensive tests for routes/main.py
Targeting 66 statements with 0% coverage for continued progress toward 90% goal.
"""

import pytest
from unittest.mock import Mock, patch

from routes.main import _role_truthy


class TestRoleTruthyHelper:
    """Tests for the _role_truthy helper function."""

    def test_role_truthy_none_attribute(self):
        """Test _role_truthy when attribute is None."""
        user = Mock()
        user.some_attr = None

        result = _role_truthy(user, "some_attr")

        assert result is False

    def test_role_truthy_missing_attribute(self):
        """Test _role_truthy when attribute doesn't exist."""
        user = Mock()
        del user.some_attr  # Ensure attribute doesn't exist

        result = _role_truthy(user, "nonexistent_attr")

        assert result is False

    def test_role_truthy_callable_true(self):
        """Test _role_truthy with callable that returns True."""
        user = Mock()
        user.some_method = Mock(return_value=True)

        result = _role_truthy(user, "some_method")

        assert result is True
        user.some_method.assert_called_once()

    def test_role_truthy_callable_false(self):
        """Test _role_truthy with callable that returns False."""
        user = Mock()
        user.some_method = Mock(return_value=False)

        result = _role_truthy(user, "some_method")

        assert result is False

    def test_role_truthy_callable_exception(self):
        """Test _role_truthy when callable raises TypeError."""
        user = Mock()
        user.some_method = Mock(side_effect=TypeError("Cannot call"))

        result = _role_truthy(user, "some_method")

        assert result is False  # Should fallback to bool(val)

    def test_role_truthy_non_callable_true(self):
        """Test _role_truthy with non-callable truthy value."""
        user = Mock()
        user.some_attr = "truthy_string"

        result = _role_truthy(user, "some_attr")

        assert result is True

    def test_role_truthy_non_callable_false(self):
        """Test _role_truthy with non-callable falsy value."""
        user = Mock()
        user.some_attr = ""

        result = _role_truthy(user, "some_attr")

        assert result is False


class TestMainRoutes:
    """Tests for main route handlers."""

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()

    @pytest.fixture
    def app_context(self, app):
        """Create application context."""
        with app.app_context():
            yield app

    def test_index_authenticated_user_redirects(self, client, app_context):
        """Test index route redirects authenticated users to dashboard."""
        with patch("routes.main.current_user") as mock_user, patch(
            "routes.main.redirect"
        ) as mock_redirect, patch("routes.main.url_for") as mock_url_for:

            mock_user.is_authenticated = True
            mock_url_for.return_value = "/dashboard"
            mock_redirect.return_value = "redirect_response"

            # Import and call directly to avoid blueprint registration issues
            from routes.main import index

            result = index()

            assert result == "redirect_response"
            mock_url_for.assert_called_once_with("dashboard.dashboard")
            mock_redirect.assert_called_once_with("/dashboard")

    @patch("routes.main.render_template")
    @patch("routes.main.Tournament")
    @patch("routes.main.current_user")
    def test_index_no_active_tournaments(self, mock_user, mock_tournament, mock_render):
        """Test index route with no active tournaments."""
        mock_user.is_authenticated = False
        mock_tournament.query.filter_by.return_value.order_by.return_value.all.return_value = (
            []
        )
        mock_render.return_value = "no_tournament_template"

        from routes.main import index

        result = index()

        assert result == "no_tournament_template"
        mock_render.assert_called_once_with("no_tournament.html")

    @patch("routes.main.render_template")
    @patch("routes.main.Classification")
    @patch("routes.main.Prova")
    @patch("routes.main.Tournament")
    @patch("routes.main.current_user")
    def test_index_with_active_tournaments(
        self, mock_user, mock_tournament, mock_prova, mock_classification, mock_render
    ):
        """Test index route with active tournaments."""
        mock_user.is_authenticated = False

        # Mock tournaments
        mock_tournament1 = Mock()
        mock_tournament1.id = 1
        mock_tournament1.name = "Tournament 1"
        mock_tournament2 = Mock()
        mock_tournament2.id = 2
        mock_tournament2.name = "Tournament 2"

        mock_tournaments = [mock_tournament1, mock_tournament2]
        mock_tournament.query.filter_by.return_value.order_by.return_value.all.return_value = (
            mock_tournaments
        )

        # Mock upcoming provas
        mock_upcoming_provas = [Mock(), Mock()]
        mock_prova.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            mock_upcoming_provas
        )

        # Mock top classifications
        mock_top_classifications = [Mock(), Mock(), Mock()]
        mock_classification.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            mock_top_classifications
        )

        mock_render.return_value = "index_template"

        from routes.main import index

        result = index()

        assert result == "index_template"

        # Verify render_template was called with expected data
        mock_render.assert_called_once()
        call_args = mock_render.call_args[1]
        assert "tournaments_data" in call_args
        assert "active_tournaments" in call_args
        assert call_args["active_tournaments"] == mock_tournaments
        assert len(call_args["tournaments_data"]) == 2

    @patch("routes.main.Config")
    @patch("routes.main.render_template")
    def test_reset_database_debug_enabled(self, mock_render, mock_config):
        """Test reset_database route when debug mode is enabled."""
        mock_config.DEBUG_MODE = True
        mock_render.return_value = "reset_template"

        from routes.main import reset_database

        result = reset_database()

        assert result == "reset_template"
        mock_render.assert_called_once_with("reset.html")

    @patch("routes.main.Config")
    def test_reset_database_debug_disabled(self, mock_config):
        """Test reset_database route when debug mode is disabled."""
        mock_config.DEBUG_MODE = False

        from routes.main import reset_database

        result = reset_database()

        assert result == ("Reset non disponibile in produzione", 403)

    @patch("routes.main.Config")
    def test_reset_database_confirm_debug_disabled(self, mock_config):
        """Test reset_database_confirm when debug mode is disabled."""
        mock_config.DEBUG_MODE = False

        from routes.main import reset_database_confirm

        result = reset_database_confirm()

        assert result == ("Reset non disponibile in produzione", 403)

    @patch("routes.main.redirect")
    @patch("routes.main.url_for")
    @patch("routes.main.flash")
    @patch("routes.main.request")
    @patch("routes.main.Config")
    def test_reset_database_confirm_wrong_password(
        self, mock_config, mock_request, mock_flash, mock_url_for, mock_redirect
    ):
        """Test reset_database_confirm with wrong password."""
        mock_config.DEBUG_MODE = True
        mock_request.form.get.return_value = "wrong_password"
        mock_url_for.return_value = "/reset"
        mock_redirect.return_value = "redirect_response"

        from routes.main import reset_database_confirm

        result = reset_database_confirm()

        assert result == "redirect_response"
        mock_flash.assert_called_once_with("Password di conferma errata!")
        mock_redirect.assert_called_once_with("/reset")

    @patch("routes.main.redirect")
    @patch("routes.main.url_for")
    @patch("routes.main.flash")
    @patch("routes.main.reset_database_enhanced")
    @patch("routes.main.db")
    @patch("routes.main.logout_user")
    @patch("routes.main.current_user")
    @patch("routes.main.request")
    @patch("routes.main.Config")
    def test_reset_database_confirm_success(
        self,
        mock_config,
        mock_request,
        mock_user,
        mock_logout,
        mock_db,
        mock_reset_enhanced,
        mock_flash,
        mock_url_for,
        mock_redirect,
    ):
        """Test successful database reset confirmation."""
        mock_config.DEBUG_MODE = True
        mock_request.form.get.return_value = "RESET_DB_CONFIRM"
        mock_user.is_authenticated = True
        mock_url_for.return_value = "/"
        mock_redirect.return_value = "redirect_response"

        from routes.main import reset_database_confirm

        result = reset_database_confirm()

        assert result == "redirect_response"
        mock_logout.assert_called_once()
        mock_db.drop_all.assert_called_once()
        mock_db.create_all.assert_called_once()
        mock_reset_enhanced.assert_called_once()

        # Check flash messages
        assert mock_flash.call_count == 2
        flash_calls = [call[0][0] for call in mock_flash.call_args_list]
        assert any("Database resettato con successo" in msg for msg in flash_calls)
        assert any(
            "Sei stato disconnesso automaticamente" in msg for msg in flash_calls
        )

    @patch("routes.main.redirect")
    @patch("routes.main.url_for")
    @patch("routes.main.flash")
    @patch("routes.main.db")
    @patch("routes.main.current_user")
    @patch("routes.main.request")
    @patch("routes.main.Config")
    def test_reset_database_confirm_exception(
        self,
        mock_config,
        mock_request,
        mock_user,
        mock_db,
        mock_flash,
        mock_url_for,
        mock_redirect,
    ):
        """Test database reset with exception handling."""
        mock_config.DEBUG_MODE = True
        mock_request.form.get.return_value = "RESET_DB_CONFIRM"
        mock_user.is_authenticated = False
        mock_db.drop_all.side_effect = Exception("Database error")
        mock_url_for.return_value = "/reset"
        mock_redirect.return_value = "redirect_response"

        from routes.main import reset_database_confirm

        result = reset_database_confirm()

        assert result == "redirect_response"
        mock_flash.assert_called_with("Errore durante il reset: Database error")
        mock_redirect.assert_called_once_with("/reset")

    @patch("routes.main.Config")
    def test_quick_login_debug_disabled(self, mock_config):
        """Test quick_login when debug mode is disabled."""
        mock_config.DEBUG_MODE = False

        from routes.main import quick_login

        result = quick_login("testuser")

        assert result == ("Quick login non disponibile in produzione", 403)

    @patch("routes.main.redirect")
    @patch("routes.main.url_for")
    @patch("routes.main.flash")
    @patch("routes.main.User")
    @patch("routes.main.Config")
    def test_quick_login_user_not_found(
        self, mock_config, mock_user_class, mock_flash, mock_url_for, mock_redirect
    ):
        """Test quick_login when user is not found."""
        mock_config.DEBUG_MODE = True
        mock_user_class.query.filter_by.return_value.first.return_value = None
        mock_url_for.return_value = "/"
        mock_redirect.return_value = "redirect_response"

        from routes.main import quick_login

        result = quick_login("nonexistent")

        assert result == "redirect_response"
        mock_flash.assert_called_once_with("Utente nonexistent non trovato!")
        mock_redirect.assert_called_once_with("/")

    @patch("routes.main.redirect")
    @patch("routes.main.url_for")
    @patch("routes.main.flash")
    @patch("routes.main.login_user")
    @patch("routes.main.User")
    @patch("routes.main.Config")
    def test_quick_login_success(
        self,
        mock_config,
        mock_user_class,
        mock_login_user,
        mock_flash,
        mock_url_for,
        mock_redirect,
    ):
        """Test successful quick login."""
        mock_config.DEBUG_MODE = True
        mock_user = Mock()
        mock_user.username = "testuser"
        mock_user_class.query.filter_by.return_value.first.return_value = mock_user
        mock_url_for.return_value = "/dashboard"
        mock_redirect.return_value = "redirect_response"

        from routes.main import quick_login

        result = quick_login("testuser")

        assert result == "redirect_response"
        mock_login_user.assert_called_once_with(mock_user)
        mock_flash.assert_called_once_with("Quick login effettuato come testuser!")
        mock_redirect.assert_called_once_with("/dashboard")

    @patch("routes.main.redirect")
    @patch("routes.main.url_for")
    @patch("routes.main.flash")
    @patch("routes.main.User")
    @patch("routes.main.Config")
    def test_quick_login_user_query_called_correctly(
        self, mock_config, mock_user_class, mock_flash, mock_url_for, mock_redirect
    ):
        """Test that quick_login queries user correctly."""
        mock_config.DEBUG_MODE = True
        mock_user_class.query.filter_by.return_value.first.return_value = None
        mock_url_for.return_value = "/"
        mock_redirect.return_value = "redirect_response"

        from routes.main import quick_login

        quick_login("testuser")

        mock_user_class.query.filter_by.assert_called_once_with(username="testuser")

    def test_import_statements_coverage(self):
        """Test to ensure import statements are covered."""
        # This test ensures the module imports are covered
        from routes.main import main_bp

        assert main_bp is not None
        assert main_bp.name == "main"
