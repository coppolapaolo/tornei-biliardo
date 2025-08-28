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

    @patch("routes.admin.competition.Tournament")
    @patch("routes.admin.competition.db")
    def test_create_prova_standalone_get(
        self, mock_db, mock_tournament, client, admin_user
    ):
        """Test the GET request for create_prova_standalone route."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Setup mocks
        mock_tournament.query.filter_by.return_value.all.return_value = []

        # Test the route using Flask test client
        with patch("routes.admin.competition.render_template") as mock_render:
            mock_render.return_value = "Rendered template"
            response = client.get("/admin/prova/create_standalone")
            assert response.status_code == 200
            mock_render.assert_called_once()

    @patch("routes.admin.competition.Tournament")
    @patch("routes.admin.competition.db")
    def test_create_prova_post_standalone_redirect(
        self, mock_db, mock_tournament, client, admin_user
    ):
        """Test the POST request for create_prova route with standalone option."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Setup mocks
        mock_tournament.query.filter_by.return_value.all.return_value = []

        # Test form data that triggers standalone redirect
        form_data = {"tournament_id": "standalone"}

        with patch("routes.admin.competition.redirect") as mock_redirect:
            mock_redirect.return_value = "Redirect response"
            response = client.post("/admin/prova/create", data=form_data)
            # Should redirect to create_standalone
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    @patch("routes.admin.competition.Tournament")
    @patch("routes.admin.competition.db")
    @patch("routes.admin.competition.ProvaService")
    def test_create_prova_standalone_post_success(
        self, mock_prova_service, mock_db, mock_tournament, client, admin_user
    ):
        """Test the POST request for create_prova_standalone route with valid data."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock tournament
        mock_tournament_instance = MagicMock()
        mock_tournament_instance.id = 1
        mock_tournament_instance.is_active = True
        mock_tournament_instance.directors_association = []
        mock_tournament.query.filter_by.return_value.all.return_value = [
            mock_tournament_instance
        ]
        mock_db.session.get.return_value = mock_tournament_instance

        # Mock Prova query to return None (no existing prova)
        with patch("routes.admin.competition.Prova") as mock_prova:
            mock_prova.query.filter_by.return_value.first.return_value = None

            # Test form data
            form_data = {
                "tournament_id": "1",
                "number": "1",
                "name": "Test Prova",
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
                response = client.post("/admin/prova/create_standalone", data=form_data)
                # Verify the service was called
                mock_prova_service.create_prova.assert_called_once()
                assert (
                    response.status_code == 200
                )  # We're mocking redirect, so it returns our mock

    @patch("routes.admin.competition.Prova")
    @patch("routes.admin.competition.db")
    def test_edit_prova_get(self, mock_db, mock_prova, client, admin_user):
        """Test the GET request for edit_prova route."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock prova
        mock_prova_instance = MagicMock()
        mock_prova_instance.id = 1
        mock_prova_instance.can_be_modified.return_value = True
        mock_db.session.get.return_value = mock_prova_instance

        with patch("routes.admin.competition.render_template") as mock_render:
            mock_render.return_value = "Rendered template"
            response = client.get("/admin/prova/1/edit")
            assert response.status_code == 200
            mock_render.assert_called_once()

    @patch("routes.admin.competition.ProvaService")
    @patch("routes.admin.competition.Prova")
    @patch("routes.admin.competition.db")
    def test_edit_prova_post_success(
        self, mock_db, mock_prova, mock_prova_service, client, admin_user
    ):
        """Test the POST request for edit_prova route with valid data."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock prova
        mock_prova_instance = MagicMock()
        mock_prova_instance.id = 1
        mock_prova_instance.can_be_modified.return_value = True
        mock_prova_instance.tournament_id = 1
        mock_db.session.get.return_value = mock_prova_instance

        # Mock ProvaService
        mock_prova_service.update_prova.return_value = None

        # Test form data
        form_data = {
            "name": "Updated Prova",
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
            response = client.post("/admin/prova/1/edit", data=form_data)
            # Verify the service was called
            mock_prova_service.update_prova.assert_called_once()
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    @patch("routes.admin.competition.Prova")
    @patch("routes.admin.competition.db")
    def test_prova_detail(self, mock_db, mock_prova, client, admin_user):
        """Test the prova_detail route."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock prova
        mock_prova_instance = MagicMock()
        mock_prova_instance.id = 1
        mock_db.session.get.return_value = mock_prova_instance

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

            response = client.get("/admin/prova/1")
            assert response.status_code == 200
            mock_render.assert_called_once()

    @patch("routes.admin.competition.ProvaService")
    @patch("routes.admin.competition.Prova")
    @patch("routes.admin.competition.db")
    def test_delete_prova(
        self, mock_db, mock_prova, mock_prova_service, client, admin_user
    ):
        """Test the delete_prova route."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock prova
        mock_prova_instance = MagicMock()
        mock_prova_instance.id = 1
        mock_prova_instance.tournament_id = 1
        mock_prova_instance.number = 1
        mock_db.session.get.return_value = mock_prova_instance

        # Mock ProvaService
        mock_prova_service.delete_prova.return_value = None

        with patch("routes.admin.competition.flash"), patch(
            "routes.admin.competition.redirect"
        ) as mock_redirect:
            mock_redirect.return_value = "Redirect response"
            response = client.post("/admin/prova/1/delete")
            # Verify the service was called
            mock_prova_service.delete_prova.assert_called_once_with(1)
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    @patch("routes.admin.competition.ProvaService")
    @patch("routes.admin.competition.Prova")
    @patch("routes.admin.competition.db")
    def test_open_inscriptions(
        self, mock_db, mock_prova, mock_prova_service, client, admin_user
    ):
        """Test the open_inscriptions route."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock prova
        mock_prova_instance = MagicMock()
        mock_prova_instance.id = 1
        mock_db.session.get.return_value = mock_prova_instance

        # Mock ProvaService
        mock_prova_service.open_inscriptions.return_value = None

        # Test form data
        form_data = {
            "inscription_start_utc": "2023-01-01T10:00:00",
            "inscription_end_utc": "2023-01-05T18:00:00",
        }

        with patch("routes.admin.competition.flash"), patch(
            "routes.admin.competition.redirect"
        ) as mock_redirect:
            mock_redirect.return_value = "Redirect response"
            response = client.post("/admin/prova/1/open_inscriptions", data=form_data)
            # Verify the service was called
            mock_prova_service.open_inscriptions.assert_called_once()
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    @patch("routes.admin.competition.ProvaService")
    @patch("routes.admin.competition.Prova")
    @patch("routes.admin.competition.db")
    def test_start_first_round(
        self, mock_db, mock_prova, mock_prova_service, client, admin_user
    ):
        """Test the start_first_round route."""
        # Setup session for authentication
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock prova
        mock_prova_instance = MagicMock()
        mock_prova_instance.id = 1
        mock_db.session.get.return_value = mock_prova_instance

        # Mock ProvaService
        mock_prova_service.start_first_round.return_value = None

        with patch("routes.admin.competition.flash"), patch(
            "routes.admin.competition.redirect"
        ) as mock_redirect:
            mock_redirect.return_value = "Redirect response"
            response = client.post("/admin/prova/1/start_first_round")
            # Verify the service was called
            mock_prova_service.start_first_round.assert_called_once_with(1)
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock


if __name__ == "__main__":
    pytest.main([__file__])
