"""
Test module for routes/individual_match.py
"""

import pytest
from unittest.mock import patch, MagicMock


class TestIndividualMatchRoutes:
    """Test cases for individual match routes."""

    def test_dashboard_route(self, client, player_user):
        """Test individual match dashboard route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the IndividualMatchService and render_template to avoid template errors
        with patch(
            "routes.individual_match.IndividualMatchService"
        ) as mock_service, patch(
            "routes.individual_match.render_template"
        ) as mock_render:
            mock_service.get_user_dashboard_data.return_value = {
                "available_challenges": [],
                "favorite_challenges": [],
                "completed_challenges": [],
            }
            mock_render.return_value = "Rendered template"

            response = client.get("/match/")

            # Verify the service method was called
            mock_service.get_user_dashboard_data.assert_called_once_with(player_user.id)
            assert response.status_code == 200

    def test_proposal_list_route(self, client, player_user):
        """Test match proposal list route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the MatchProposalService and render_template
        with patch(
            "routes.individual_match.MatchProposalService"
        ) as mock_service, patch(
            "routes.individual_match.render_template"
        ) as mock_render:
            mock_service.get_user_proposals.return_value = {
                "active_proposals": [],
                "past_proposals": [],
            }
            mock_render.return_value = "Rendered template"

            response = client.get("/match/proposals")

            # Verify the service method was called
            mock_service.get_user_proposals.assert_called_once_with(player_user.id)
            assert response.status_code == 200

    def test_create_proposal_get_route(self, client, player_user):
        """Test create proposal GET route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock render_template to avoid template errors
        with patch("routes.individual_match.render_template") as mock_render:
            mock_render.return_value = "Rendered template"

            response = client.get("/match/proposals/create")
            assert response.status_code == 200

    def test_create_proposal_post_route(self, client, player_user):
        """Test create proposal POST route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the MatchProposalService and redirect
        with patch(
            "routes.individual_match.MatchProposalService"
        ) as mock_service, patch(
            "routes.individual_match.redirect"
        ) as mock_redirect, patch(
            "routes.individual_match.url_for"
        ) as mock_url_for, patch(
            "routes.individual_match.flash"
        ):
            mock_proposal = MagicMock()
            mock_proposal.id = 1
            mock_service.create_proposal.return_value = mock_proposal
            mock_redirect.return_value = "Redirect response"
            mock_url_for.return_value = "/match/proposals/1"  # Mock the URL

            # Test form data
            form_data = {
                "proposal_type": "DIRECT",
                "location": "Test Location",
                "scheduled_at": "2023-06-15T14:00:00+00:00",
                "expires_hours": "24",
                "discipline": "palla_8",
                "distance": "5",
                "best_of": "true",
                "break_rule": "alternate",
                "description": "Test match",
                "entry_fee": "10.0",
                "invited_user_ids": ["2", "3"],
            }

            response = client.post("/match/proposals/create", data=form_data)

            # Verify the service method was called
            mock_service.create_proposal.assert_called_once()
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    def test_accept_proposal_route(self, client, player_user):
        """Test accept proposal route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the MatchProposalService and redirect
        with patch(
            "routes.individual_match.MatchProposalService"
        ) as mock_service, patch(
            "routes.individual_match.redirect"
        ) as mock_redirect, patch(
            "routes.individual_match.flash"
        ):
            mock_match = MagicMock()
            mock_match.id = 1
            mock_service.accept_proposal.return_value = mock_match
            mock_redirect.return_value = "Redirect response"

            response = client.post("/match/proposals/1/accept")

            # Verify the service method was called
            mock_service.accept_proposal.assert_called_once_with(1, player_user.id)
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    def test_cancel_proposal_route(self, client, player_user):
        """Test cancel proposal route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the MatchProposalService and redirect
        with patch(
            "routes.individual_match.MatchProposalService"
        ) as mock_service, patch(
            "routes.individual_match.redirect"
        ) as mock_redirect, patch(
            "routes.individual_match.flash"
        ):
            mock_service.cancel_proposal.return_value = None
            mock_redirect.return_value = "Redirect response"

            response = client.post("/match/proposals/1/cancel")

            # Verify the service method was called
            mock_service.cancel_proposal.assert_called_once_with(1, player_user.id)
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    def test_match_list_route(self, client, player_user):
        """Test match list route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the IndividualMatchService and render_template
        with patch(
            "routes.individual_match.IndividualMatchService"
        ) as mock_service, patch(
            "routes.individual_match.render_template"
        ) as mock_render:
            mock_service.get_user_matches.return_value = []
            mock_render.return_value = "Rendered template"

            response = client.get("/match/matches")

            # Verify the service method was called
            mock_service.get_user_matches.assert_called_once_with(player_user.id)
            assert response.status_code == 200

    def test_match_detail_route(self, client, player_user):
        """Test match detail route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the IndividualMatch and render_template
        with patch(
            "routes.individual_match.IndividualMatch"
        ) as mock_match_class, patch(
            "routes.individual_match.render_template"
        ) as mock_render:
            mock_match = MagicMock()
            mock_match.id = 1
            mock_match.player1_id = player_user.id
            mock_match.player2_id = 2
            mock_match_class.query.get_or_404.return_value = mock_match
            mock_render.return_value = "Rendered template"

            response = client.get("/match/matches/1")

            # Verify the match was retrieved
            mock_match_class.query.get_or_404.assert_called_once_with(1)
            assert response.status_code == 200

    def test_start_match_route(self, client, player_user):
        """Test start match route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the IndividualMatchService and redirect
        with patch(
            "routes.individual_match.IndividualMatchService"
        ) as mock_service, patch(
            "routes.individual_match.redirect"
        ) as mock_redirect, patch(
            "routes.individual_match.flash"
        ):
            mock_match = MagicMock()
            mock_service.start_match.return_value = mock_match
            mock_redirect.return_value = "Redirect response"

            response = client.post("/match/matches/1/start")

            # Verify the service method was called
            mock_service.start_match.assert_called_once_with(1, player_user.id)
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    def test_submit_rack_result_route(self, client, player_user):
        """Test submit rack result route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the IndividualMatchService and redirect
        with patch(
            "routes.individual_match.IndividualMatchService"
        ) as mock_service, patch(
            "routes.individual_match.redirect"
        ) as mock_redirect, patch(
            "routes.individual_match.flash"
        ):
            mock_rack = MagicMock()
            mock_rack.rack_number = 1
            mock_rack.winner_id = player_user.id
            mock_service.submit_rack_result.return_value = mock_rack
            mock_redirect.return_value = "Redirect response"

            # Test form data
            form_data = {"winner_id": str(player_user.id), "rack_number": "1"}

            response = client.post("/match/matches/1/racks", data=form_data)

            # Verify the service method was called
            mock_service.submit_rack_result.assert_called_once()
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    def test_complete_match_route(self, client, player_user):
        """Test complete match route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the IndividualMatchService and redirect
        with patch(
            "routes.individual_match.IndividualMatchService"
        ) as mock_service, patch(
            "routes.individual_match.redirect"
        ) as mock_redirect, patch(
            "routes.individual_match.flash"
        ):
            mock_match = MagicMock()
            mock_match.winner_id = player_user.id
            mock_match.player1_score = 3
            mock_match.player2_score = 2
            mock_service.complete_match.return_value = mock_match
            mock_redirect.return_value = "Redirect response"

            # Test form data
            form_data = {"winner_id": str(player_user.id)}

            response = client.post("/match/matches/1/complete", data=form_data)

            # Verify the service method was called
            mock_service.complete_match.assert_called_once()
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    def test_cancel_match_route(self, client, player_user):
        """Test cancel match route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the IndividualMatchService and redirect
        with patch(
            "routes.individual_match.IndividualMatchService"
        ) as mock_service, patch(
            "routes.individual_match.redirect"
        ) as mock_redirect, patch(
            "routes.individual_match.flash"
        ):
            mock_service.cancel_match.return_value = None
            mock_redirect.return_value = "Redirect response"

            response = client.post("/match/matches/1/cancel")

            # Verify the service method was called
            mock_service.cancel_match.assert_called_once_with(1, player_user.id)
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    def test_manage_availability_get_route(self, client, player_user):
        """Test manage availability GET route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the IndividualMatchService and render_template
        with patch(
            "routes.individual_match.IndividualMatchService"
        ) as mock_service, patch(
            "routes.individual_match.render_template"
        ) as mock_render:
            mock_service.get_user_availability.return_value = {"availability": []}
            mock_render.return_value = "Rendered template"

            response = client.get("/match/availability")

            # Verify the service method was called
            mock_service.get_user_availability.assert_called_once_with(player_user.id)
            assert response.status_code == 200

    def test_manage_availability_post_route(self, client, player_user):
        """Test manage availability POST route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the IndividualMatchService and redirect
        with patch(
            "routes.individual_match.IndividualMatchService"
        ) as mock_service, patch(
            "routes.individual_match.redirect"
        ) as mock_redirect, patch(
            "routes.individual_match.render_template"
        ) as mock_render, patch(
            "routes.individual_match.flash"
        ):
            mock_service.update_user_availability.return_value = None
            mock_redirect.return_value = "Redirect response"
            mock_render.return_value = "Rendered template"  # Mock template rendering

            # Test form data - send as JSON to trigger request.get_json() path
            json_data = {"availability": []}

            response = client.post(
                "/match/availability", json=json_data, content_type="application/json"
            )

            # Verify the service method was called
            mock_service.update_user_availability.assert_called_once()
            assert (
                response.status_code == 200
            )  # We're mocking redirect, so it returns our mock

    def test_user_statistics_route(self, client, player_user):
        """Test user statistics route."""
        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)
            sess["_fresh"] = True

        # Mock the IndividualMatchService and render_template
        with patch(
            "routes.individual_match.IndividualMatchService"
        ) as mock_service, patch(
            "routes.individual_match.render_template"
        ) as mock_render:
            mock_service.get_user_statistics.return_value = {
                "total_matches": 10,
                "wins": 7,
                "losses": 3,
                "win_rate": 70.0,
            }
            mock_render.return_value = "Rendered template"

            response = client.get("/match/statistics")

            # Verify the service method was called
            mock_service.get_user_statistics.assert_called_once_with(player_user.id)
            assert response.status_code == 200

    def test_admin_overview_route(self, client, admin_user):
        """Test admin overview route."""
        # Login as admin using Flask-Login's session setup
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)
            sess["_fresh"] = True

        # Mock the login_required and admin_required decorators,
        # IndividualMatchService and render_template
        with patch("flask_login.login_required") as mock_login_required, patch(
            "utils.admin_required"
        ) as mock_admin_required, patch(
            "routes.individual_match.IndividualMatchService"
        ) as mock_service, patch(
            "routes.individual_match.render_template"
        ) as mock_render:
            # Make the decorators simply call the function (like in challenge routes)
            mock_login_required.return_value = lambda f: f
            mock_admin_required.return_value = lambda f: f
            mock_service.get_admin_overview.return_value = {
                "total_proposals": 20,
                "total_matches": 15,
                "active_matches": 5,
            }
            mock_render.return_value = "Rendered template"

            response = client.get("/match/admin/overview")

            # Verify the service method was called
            mock_service.get_admin_overview.assert_called_once()
            assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__])