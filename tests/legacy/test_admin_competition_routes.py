"""
Test module for routes/admin/competition.py
"""

import pytest
from unittest.mock import patch, MagicMock


class TestAdminCompetitionRoutes:
    """Test cases for admin competition routes."""

    def test_competition_blueprint_exists(self, client):
        """Test that the competition blueprint exists."""
        # This test ensures the file is imported and executed
        from routes.admin.competition import competition_bp

        assert competition_bp is not None
        assert hasattr(competition_bp, "name")
        assert competition_bp.name == "competition"

    def test_competition_blueprint_has_routes(self, client):
        """Test that the competition blueprint has routes defined."""
        # Check that we have routes defined
        from routes.admin.competition import competition_bp

        assert len(competition_bp.deferred_functions) > 0

    def test_import_competition_module(self, client):
        """Test that the competition module can be imported without errors."""
        # This test ensures the file is imported and executed
        import routes.admin.competition

        assert routes.admin.competition.competition_bp.__class__.__name__ == "Blueprint"

    @patch("routes.admin.competition.Campionato")
    @patch("routes.admin.competition.db")
    def test_create_gara_standalone_get(
        self, mock_db, mock_campionato, client, admin_user
    ):
        """Test the GET request for create_gara_standalone route."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Setup mocks
        mock_campionato.query.filter_by.return_value.all.return_value = []

        # Test the route using Flask test client
        with patch("routes.admin.competition.render_template") as mock_render:
            mock_render.return_value = "Rendered template"
            response = client.get("/admin/gara/create_standalone")
            assert response.status_code == 200
            mock_render.assert_called_once()

    @patch("routes.admin.competition.Campionato")
    @patch("routes.admin.competition.db")
    def test_create_gara_post_standalone_redirect(
        self, mock_db, mock_campionato, client, admin_user
    ):
        """Test the POST request for create_gara route with standalone option."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Setup mocks
        mock_campionato.query.filter_by.return_value.all.return_value = []

        # Test form data that triggers standalone redirect
        form_data = {"campionato_id": "standalone"}

        with patch("routes.admin.competition.redirect") as mock_redirect:
            mock_redirect.return_value = "Redirect response"
            response = client.post("/admin/gara/create", data=form_data)
            # Should redirect to create_standalone
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    @patch("routes.admin.competition.Campionato")
    @patch("routes.admin.competition.db")
    @patch("routes.admin.competition.GaraService")
    def test_create_gara_standalone_post_success(
        self, mock_gara_service, mock_db, mock_campionato, client, admin_user
    ):
        """Test the POST request for create_gara_standalone route with valid data."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock campionato
        mock_campionato_instance = MagicMock()
        mock_campionato_instance.id = 1
        mock_campionato_instance.is_active = True
        mock_campionato_instance.directors_association = []
        mock_campionato.query.filter_by.return_value.all.return_value = [
            mock_campionato_instance
        ]
        mock_db.session.get.return_value = mock_campionato_instance

        # Mock Gara query to return None (no existing gara)
        with patch("routes.admin.competition.Gara") as mock_gara:
            mock_gara.query.filter_by.return_value.first.return_value = None

            # Test form data
            form_data = {
                "campionato_id": "1",
                "number": "1",
                "name": "Test Gara",
                "date": "2023-01-01",
                "location": "Test Location",
                "description": "Test Description",
                "rounds_count": "3",
                "min_participants": "2",
                "max_participants": "10",
                "entry_fee": "0.0",
                "discipline": "Test Discipline",
                "distance": "100",
                "exact_number": "on",
                "withdraw_policy": "exclude",
            }

            with patch("routes.admin.competition.flash"), patch(
                "routes.admin.competition.redirect"
            ) as mock_redirect:
                mock_redirect.return_value = "Redirect response"
                response = client.post("/admin/gara/create_standalone", data=form_data)
                # Verify the service was called
                mock_gara_service.create_gara.assert_called_once()
                assert (
                    response.status_code == 200
                )  # We're mocking redirect, so it returns our mock

    @patch("routes.admin.competition.Gara")
    @patch("routes.admin.competition.db")
    def test_edit_gara_get(self, mock_db, mock_gara, client, admin_user):
        """Test the GET request for edit_gara route."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock gara
        mock_gara_instance = MagicMock()
        mock_gara_instance.id = 1
        mock_gara_instance.can_be_modified.return_value = True
        mock_db.session.get.return_value = mock_gara_instance

        with patch("routes.admin.competition.render_template") as mock_render:
            mock_render.return_value = "Rendered template"
            response = client.get("/admin/gara/1/edit")
            assert response.status_code == 200
            mock_render.assert_called_once()

    @patch("routes.admin.competition.GaraService")
    @patch("routes.admin.competition.Gara")
    @patch("routes.admin.competition.db")
    def test_edit_gara_post_success(
        self, mock_db, mock_gara, mock_gara_service, client, admin_user
    ):
        """Test the POST request for edit_gara route with valid data."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock gara
        mock_gara_instance = MagicMock()
        mock_gara_instance.id = 1
        mock_gara_instance.can_be_modified.return_value = True
        mock_gara_instance.campionato_id = 1
        mock_db.session.get.return_value = mock_gara_instance

        # Mock GaraService
        mock_gara_service.update_gara.return_value = None

        # Test form data
        form_data = {
            "name": "Updated Gara",
            "date": "2023-01-01",
            "location": "Updated Location",
            "description": "Updated Description",
            "rounds_count": "3",
            "min_participants": "2",
            "max_participants": "10",
            "entry_fee": "0.0",
            "discipline": "Updated Discipline",
            "distance": "100",
            "exact_number": "on",
            "withdraw_policy": "exclude",
        }

        with patch("routes.admin.competition.flash"), patch(
            "routes.admin.competition.redirect"
        ) as mock_redirect:
            mock_redirect.return_value = "Redirect response"
            response = client.post("/admin/gara/1/edit", data=form_data)
            # Verify the service was called
            mock_gara_service.update_gara.assert_called_once()
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    @patch("routes.admin.competition.Gara")
    @patch("routes.admin.competition.db")
    def test_gara_detail(self, mock_db, mock_gara, client, admin_user):
        """Test the gara_detail route."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock gara
        mock_gara_instance = MagicMock()
        mock_gara_instance.id = 1
        mock_db.session.get.return_value = mock_gara_instance

        # Mock related objects
        with patch("routes.admin.competition.Inscription") as mock_inscription, patch(
            "routes.admin.competition.Match"
        ) as mock_match, patch(
            "routes.admin.competition.render_template"
        ) as mock_render:
            mock_inscription.query.filter_by.return_value.all.return_value = []
            matches_result = []
            query = mock_match.query
            filtered_query = query.filter_by.return_value
            ordered_query = filtered_query.order_by.return_value
            ordered_query.all.return_value = matches_result
            mock_render.return_value = "Rendered template"

            response = client.get("/admin/gara/1")
            assert response.status_code == 200
            mock_render.assert_called_once()

    @patch("routes.admin.competition.GaraService")
    @patch("routes.admin.competition.Gara")
    @patch("routes.admin.competition.db")
    def test_delete_gara(
        self, mock_db, mock_gara, mock_gara_service, client, admin_user
    ):
        """Test the delete_gara route."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock gara
        mock_gara_instance = MagicMock()
        mock_gara_instance.id = 1
        mock_gara_instance.campionato_id = 1
        mock_gara_instance.number = 1
        mock_db.session.get.return_value = mock_gara_instance

        # Mock GaraService
        mock_gara_service.delete_gara.return_value = None

        with patch("routes.admin.competition.flash"), patch(
            "routes.admin.competition.redirect"
        ) as mock_redirect:
            mock_redirect.return_value = "Redirect response"
            response = client.post("/admin/gara/1/delete")
            # Verify the service was called
            mock_gara_service.delete_gara.assert_called_once_with(1)
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    @patch("routes.admin.competition.GaraService")
    @patch("routes.admin.competition.Gara")
    @patch("routes.admin.competition.db")
    def test_open_inscriptions(
        self, mock_db, mock_gara, mock_gara_service, client, admin_user
    ):
        """Test the open_inscriptions route."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock gara
        mock_gara_instance = MagicMock()
        mock_gara_instance.id = 1
        mock_db.session.get.return_value = mock_gara_instance

        # Mock GaraService
        mock_gara_service.open_inscriptions.return_value = None

        # Test form data
        form_data = {
            "inscription_start_utc": "2023-01-01T10:00:00",
            "inscription_end_utc": "2023-01-05T18:00:00",
        }

        with patch("routes.admin.competition.flash"), patch(
            "routes.admin.competition.redirect"
        ) as mock_redirect:
            mock_redirect.return_value = "Redirect response"
            response = client.post("/admin/gara/1/open_inscriptions", data=form_data)
            # Verify the service was called
            mock_gara_service.open_inscriptions.assert_called_once()
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    @patch("routes.admin.competition.GaraService")
    @patch("routes.admin.competition.Gara")
    @patch("routes.admin.competition.db")
    def test_start_first_round(
        self, mock_db, mock_gara, mock_gara_service, client, admin_user
    ):
        """Test the start_first_round route."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock gara
        mock_gara_instance = MagicMock()
        mock_gara_instance.id = 1
        mock_db.session.get.return_value = mock_gara_instance

        # Mock GaraService
        mock_gara_service.start_first_round.return_value = None

        with patch("routes.admin.competition.flash"), patch(
            "routes.admin.competition.redirect"
        ) as mock_redirect:
            mock_redirect.return_value = "Redirect response"
            response = client.post("/admin/gara/1/start_first_round")
            # Verify the service was called
            mock_gara_service.start_first_round.assert_called_once_with(1)
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock


if __name__ == "__main__":
    pytest.main([__file__])
