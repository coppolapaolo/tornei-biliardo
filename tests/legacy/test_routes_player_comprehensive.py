"""
Comprehensive tests for routes/player.py - Part 1
Targeting 276 statements with 196 missed (29% coverage) for maximum impact toward 90% goal.
"""

from unittest.mock import Mock, patch
from datetime import datetime

from models.status_enum import MatchStatus, ProvaStatus


class TestMatchProposalRoutes:
    """Tests for individual match proposal routes."""

    @patch("routes.player.render_template")
    @patch("routes.player.IndividualMatchService")
    @patch("routes.player.current_user")
    def test_match_proposals_route(self, mock_user, mock_service, mock_render):
        """Test match proposals listing route."""
        mock_user.id = 1
        mock_proposals = {"created": [], "invited": [], "available": []}
        mock_service.get_user_proposals.return_value = mock_proposals
        mock_render.return_value = "proposals_template"

        from routes.player import match_proposals

        result = match_proposals()

        assert result == "proposals_template"
        mock_service.get_user_proposals.assert_called_once_with(1)
        mock_render.assert_called_once_with(
            "player/match_proposals.html", proposals=mock_proposals
        )

    @patch("routes.player.render_template")
    @patch("routes.player.BilliardHall")
    @patch("routes.player.User")
    @patch("routes.player.current_user")
    @patch("routes.player.request")
    def test_create_match_proposal_get(
        self, mock_request, mock_user, mock_user_class, mock_hall, mock_render
    ):
        """Test GET request to create match proposal."""
        mock_user.id = 1
        mock_request.method = "GET"
        mock_users = [Mock(id=2), Mock(id=3)]
        mock_locations = [Mock(id=1), Mock(id=2)]

        mock_user_class.query.filter.return_value.all.return_value = mock_users
        mock_hall.query.all.return_value = mock_locations
        mock_render.return_value = "create_template"

        from routes.player import create_match_proposal

        result = create_match_proposal()

        assert result == "create_template"
        mock_render.assert_called_once_with(
            "player/create_match_proposal.html",
            users=mock_users,
            locations=mock_locations,
        )

    @patch("routes.player.redirect")
    @patch("routes.player.url_for")
    @patch("routes.player.flash")
    @patch("routes.player.IndividualMatchService")
    @patch("routes.player.current_user")
    @patch("routes.player.request")
    def test_create_match_proposal_post_direct_success(
        self,
        mock_request,
        mock_user,
        mock_service,
        mock_flash,
        mock_url_for,
        mock_redirect,
    ):
        """Test successful POST request for direct match proposal."""
        mock_user.id = 1
        mock_request.method = "POST"
        mock_request.form = Mock()
        mock_request.form.get.side_effect = lambda key, default=None: {
            "proposal_type": "direct",
            "location": "Test Hall",
            "scheduled_at": "2024-12-25T15:00:00",
            "discipline": "palla_8",
            "distance": "5",
            "break_rule": "alternate",
            "description": "Test match",
            "entry_fee": "10.0",
        }.get(key, default)
        mock_request.form.getlist = Mock(return_value=["2", "3"])

        mock_proposal = Mock(id=123)
        mock_service.create_direct_proposal.return_value = mock_proposal
        mock_url_for.return_value = "/match-proposals"
        mock_redirect.return_value = "redirect_response"

        from routes.player import create_match_proposal

        result = create_match_proposal()

        assert result == "redirect_response"
        mock_service.create_direct_proposal.assert_called_once()
        mock_flash.assert_called_once_with(
            "Match proposal created successfully! ID: 123"
        )

    @patch("routes.player.redirect")
    @patch("routes.player.url_for")
    @patch("routes.player.flash")
    @patch("routes.player.IndividualMatchService")
    @patch("routes.player.current_user")
    @patch("routes.player.request")
    def test_create_match_proposal_post_open_success(
        self,
        mock_request,
        mock_user,
        mock_service,
        mock_flash,
        mock_url_for,
        mock_redirect,
    ):
        """Test successful POST request for open match proposal."""
        mock_user.id = 1
        mock_request.method = "POST"
        mock_request.form = Mock()
        mock_request.form.get.side_effect = lambda key, default=None: {
            "proposal_type": "open",
            "location": "Test Hall",
            "scheduled_at": "2024-12-25T15:00:00Z",
            "discipline": "palla_9",
            "distance": "7",
            "break_rule": "winner",
            "description": "Open match",
            "entry_fee": "",
        }.get(key, default)
        mock_request.form.getlist = Mock(return_value=[])

        mock_proposal = Mock(id=456)
        mock_service.create_open_proposal.return_value = mock_proposal
        mock_url_for.return_value = "/match-proposals"
        mock_redirect.return_value = "redirect_response"

        from routes.player import create_match_proposal

        result = create_match_proposal()

        assert result == "redirect_response"
        mock_service.create_open_proposal.assert_called_once()
        mock_flash.assert_called_once_with(
            "Match proposal created successfully! ID: 456"
        )

    @patch("routes.player.render_template")
    @patch("routes.player.BilliardHall")
    @patch("routes.player.User")
    @patch("routes.player.flash")
    @patch("routes.player.current_user")
    @patch("routes.player.request")
    def test_create_match_proposal_post_missing_location(
        self,
        mock_request,
        mock_user,
        mock_flash,
        mock_user_class,
        mock_hall,
        mock_render,
    ):
        """Test POST request with missing location."""
        mock_user.id = 1
        mock_request.method = "POST"
        mock_request.form = Mock()
        mock_request.form.get.side_effect = lambda key, default=None: {
            "proposal_type": "open",
            "location": "",
            "scheduled_at": "2024-12-25T15:00:00",
        }.get(key, default)

        mock_users = [Mock()]
        mock_locations = [Mock()]
        mock_user_class.query.filter.return_value.all.return_value = mock_users
        mock_hall.query.all.return_value = mock_locations
        mock_render.return_value = "create_template"

        from routes.player import create_match_proposal

        result = create_match_proposal()

        assert result == "create_template"
        mock_flash.assert_called_with("Location is required", "error")

    @patch("routes.player.redirect")
    @patch("routes.player.url_for")
    @patch("routes.player.flash")
    @patch("routes.player.IndividualMatchService")
    @patch("routes.player.current_user")
    def test_accept_match_proposal_success(
        self, mock_user, mock_service, mock_flash, mock_url_for, mock_redirect
    ):
        """Test successful match proposal acceptance."""
        mock_user.id = 1
        mock_match = Mock(id=789)
        mock_service.accept_proposal.return_value = mock_match
        mock_url_for.return_value = "/match-proposals"
        mock_redirect.return_value = "redirect_response"

        from routes.player import accept_match_proposal

        result = accept_match_proposal(123)

        assert result == "redirect_response"
        mock_service.accept_proposal.assert_called_once_with(1, 123)
        mock_flash.assert_called_once_with("Match proposal accepted! Match ID: 789")

    @patch("routes.player.redirect")
    @patch("routes.player.url_for")
    @patch("routes.player.flash")
    @patch("routes.player.IndividualMatchService")
    @patch("routes.player.current_user")
    def test_reject_match_proposal_success(
        self, mock_user, mock_service, mock_flash, mock_url_for, mock_redirect
    ):
        """Test successful match proposal rejection."""
        mock_user.id = 1
        mock_url_for.return_value = "/match-proposals"
        mock_redirect.return_value = "redirect_response"

        from routes.player import reject_match_proposal

        result = reject_match_proposal(123)

        assert result == "redirect_response"
        mock_service.reject_invitation.assert_called_once_with(1, 123)
        mock_flash.assert_called_once_with("Match proposal rejected.")

    @patch("routes.player.redirect")
    @patch("routes.player.url_for")
    @patch("routes.player.flash")
    @patch("routes.player.MatchProposalService")
    @patch("routes.player.current_user")
    def test_cancel_match_proposal_success(
        self, mock_user, mock_service, mock_flash, mock_url_for, mock_redirect
    ):
        """Test successful match proposal cancellation."""
        mock_user.id = 1
        mock_url_for.return_value = "/match-proposals"
        mock_redirect.return_value = "redirect_response"

        from routes.player import cancel_match_proposal

        result = cancel_match_proposal(123)

        assert result == "redirect_response"
        mock_service.cancel_proposal.assert_called_once_with(123, 1)
        mock_flash.assert_called_once_with("Match proposal cancelled.")


class TestPlayerDashboardAndProvaRoutes:
    """Tests for player dashboard and prova-related routes."""

    @patch("routes.player.redirect")
    @patch("routes.player.url_for")
    def test_dashboard_redirect(self, mock_url_for, mock_redirect):
        """Test dashboard route redirects to main dashboard."""
        mock_url_for.return_value = "/dashboard"
        mock_redirect.return_value = "redirect_response"

        from routes.player import dashboard

        result = dashboard()

        assert result == "redirect_response"
        mock_url_for.assert_called_once_with("dashboard.dashboard")

    @patch("routes.player.abort")
    @patch("routes.player.db")
    @patch("routes.player.current_user")
    def test_prova_detail_not_found(self, mock_user, mock_db, mock_abort):
        """Test prova detail when prova not found."""
        mock_user.id = 1
        mock_db.session.get.return_value = None

        from routes.player import prova_detail

        prova_detail(999)

        mock_abort.assert_called_once_with(404)

    @patch("routes.player.redirect")
    @patch("routes.player.url_for")
    @patch("routes.player.flash")
    @patch("routes.player.Inscription")
    @patch("routes.player.db")
    @patch("routes.player.current_user")
    def test_prova_detail_not_inscribed(
        self,
        mock_user,
        mock_db,
        mock_inscription,
        mock_flash,
        mock_url_for,
        mock_redirect,
    ):
        """Test prova detail when user not inscribed."""
        mock_user.id = 1
        mock_prova = Mock(id=123)
        mock_db.session.get.return_value = mock_prova
        mock_inscription.query.filter_by.return_value.first.return_value = None
        mock_url_for.return_value = "/dashboard"
        mock_redirect.return_value = "redirect_response"

        from routes.player import prova_detail

        result = prova_detail(123)

        assert result == "redirect_response"
        mock_flash.assert_called_once_with("Non sei iscritto a questa prova.", "error")

    @patch("routes.player.render_template")
    @patch("routes.player.Match")
    @patch("routes.player.Inscription")
    @patch("routes.player.db")
    @patch("routes.player.current_user")
    def test_prova_detail_success(
        self, mock_user, mock_db, mock_inscription, mock_match, mock_render
    ):
        """Test successful prova detail view."""
        mock_user.id = 1
        mock_prova = Mock(id=123)
        mock_db.session.get.return_value = mock_prova
        mock_db.or_ = Mock()

        mock_inscription_obj = Mock()
        mock_inscription.query.filter_by.return_value.first.return_value = (
            mock_inscription_obj
        )

        mock_matches = [Mock(), Mock()]
        mock_match.query.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = (
            mock_matches
        )
        mock_render.return_value = "prova_detail_template"

        from routes.player import prova_detail

        result = prova_detail(123)

        assert result == "prova_detail_template"
        mock_render.assert_called_once_with(
            "player/prova_detail.html",
            prova=mock_prova,
            inscription=mock_inscription_obj,
            matches=mock_matches,
        )

    @patch("routes.player.redirect")
    @patch("routes.player.url_for")
    @patch("routes.player.flash")
    @patch("routes.player.db")
    @patch("routes.player.Inscription")
    @patch("routes.player.datetime")
    @patch("routes.player.Prova")
    @patch("routes.player.current_user")
    def test_inscribe_to_prova_success(
        self,
        mock_user,
        mock_prova_class,
        mock_datetime,
        mock_inscription_class,
        mock_db,
        mock_flash,
        mock_url_for,
        mock_redirect,
    ):
        """Test successful prova inscription."""
        mock_user.id = 1
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.INSCRIPTION.value
        mock_prova.number = 3
        mock_prova.tournament_id = 456
        mock_prova_class.query.get_or_404.return_value = mock_prova

        mock_now = datetime(2024, 1, 22, 10, 0, 0)
        mock_datetime.utcnow.return_value = mock_now
        mock_prova.inscription_start = datetime(2024, 1, 20, 9, 0, 0)
        mock_prova.inscription_end = datetime(2024, 1, 25, 18, 0, 0)

        mock_inscription_class.query.filter_by.return_value.first.return_value = None

        mock_url_for.return_value = "/dashboard"
        mock_redirect.return_value = "redirect_response"

        from routes.player import inscribe_to_prova

        result = inscribe_to_prova(123)

        assert result == "redirect_response"
        mock_db.session.add.assert_called_once()
        mock_db.session.commit.assert_called_once()
        mock_flash.assert_called_once_with("Iscrizione alla Prova 3 completata!")


class TestMatchAndRackRoutes:
    """Tests for match detail and rack-related routes."""

    @patch("routes.player.abort")
    @patch("routes.player.db")
    def test_match_detail_not_found(self, mock_db, mock_abort):
        """Test match detail when match not found."""
        mock_db.session.get.return_value = None

        from routes.player import match_detail

        match_detail(999)

        mock_abort.assert_called_once_with(404)

    @patch("routes.player.render_template")
    @patch("routes.player.Rack")
    @patch("routes.player.db")
    def test_match_detail_success(self, mock_db, mock_rack, mock_render):
        """Test successful match detail view."""
        mock_match = Mock(id=123)
        mock_db.session.get.return_value = mock_match

        mock_racks = [Mock(), Mock()]
        mock_rack.query.filter_by.return_value.order_by.return_value.all.return_value = (
            mock_racks
        )
        mock_render.return_value = "match_detail_template"

        from routes.player import match_detail

        result = match_detail(123)

        assert result == "match_detail_template"
        mock_render.assert_called_once_with(
            "player/match_detail.html", match=mock_match, racks=mock_racks
        )

    @patch("routes.player.jsonify")
    @patch("routes.player.RackService")
    @patch("routes.player.request")
    @patch("routes.player.db")
    @patch("routes.player.current_user")
    def test_report_rack_result_success(
        self, mock_user, mock_db, mock_request, mock_service, mock_jsonify
    ):
        """Test successful rack result reporting."""
        mock_user.id = 1
        mock_match = Mock()
        mock_match.player1_id = 1
        mock_match.player2_id = 2
        mock_db.session.get.return_value = mock_match

        mock_request.form = {"winner_id": "2"}
        mock_result = {"success": True, "rack_id": 456}
        mock_service.add_rack_with_score_update.return_value = mock_result
        mock_jsonify.return_value = "json_response"

        from routes.player import report_rack_result

        result = report_rack_result(123)

        assert result == "json_response"
        mock_service.add_rack_with_score_update.assert_called_once_with(
            match_id=123, winner_id=2, reported_by_id=1, validated_by_admin=False
        )

    @patch("routes.player.jsonify")
    @patch("routes.player.flash")
    @patch("routes.player.redirect")
    @patch("routes.player.url_for")
    @patch("routes.player.request")
    @patch("routes.player.db")
    @patch("routes.player.current_user")
    def test_report_rack_result_invalid_winner(
        self,
        mock_user,
        mock_db,
        mock_request,
        mock_url_for,
        mock_redirect,
        mock_flash,
        mock_jsonify,
    ):
        """Test rack result reporting with invalid winner."""
        mock_user.id = 1
        mock_match = Mock()
        mock_match.player1_id = 2
        mock_match.player2_id = 3
        mock_db.session.get.return_value = mock_match

        mock_request.form = {"winner_id": "4"}  # Invalid winner
        mock_url_for.return_value = "/match/123"
        mock_redirect.return_value = "redirect_response"

        from routes.player import report_rack_result

        result = report_rack_result(123)

        assert result == "redirect_response"
        mock_flash.assert_called_once_with("Giocatore non valido.", "error")


class TestPlayerProfileAndAccountRoutes:
    """Tests for player profile and account management routes."""

    @patch("routes.player.render_template")
    @patch("routes.player.Classification")
    @patch("routes.player.Match")
    @patch("routes.player.Inscription")
    @patch("routes.player.current_user")
    @patch("routes.player.db")
    def test_profile_success(
        self,
        mock_db,
        mock_user,
        mock_inscription,
        mock_match,
        mock_classification,
        mock_render,
    ):
        """Test successful profile view."""
        mock_user.id = 1
        mock_db.or_ = Mock()

        # Mock inscriptions
        mock_inscriptions = [Mock(), Mock(), Mock()]
        mock_inscription.query.filter_by.return_value.join.return_value.join.return_value.order_by.return_value.all.return_value = (
            mock_inscriptions
        )

        # Mock matches
        mock_completed_match1 = Mock()
        mock_completed_match1.status = MatchStatus.COMPLETED.value
        mock_completed_match1.winner_id = 1  # User won

        mock_completed_match2 = Mock()
        mock_completed_match2.status = MatchStatus.COMPLETED.value
        mock_completed_match2.winner_id = 2  # User lost

        mock_pending_match = Mock()
        mock_pending_match.status = MatchStatus.PLAYING.value

        mock_matches = [
            mock_completed_match1,
            mock_completed_match2,
            mock_pending_match,
        ]
        mock_match.query.filter.return_value.join.return_value.join.return_value.order_by.return_value.all.return_value = (
            mock_matches
        )

        # Mock classifications
        mock_classifications = [Mock(), Mock()]
        mock_classification.query.filter_by.return_value.join.return_value.order_by.return_value.all.return_value = (
            mock_classifications
        )

        mock_render.return_value = "profile_template"

        from routes.player import profile

        result = profile()

        assert result == "profile_template"

        # Verify render_template call
        call_args = mock_render.call_args
        assert call_args[0] == ("player/profile.html",)
        kwargs = call_args[1]

        assert kwargs["user"] == mock_user
        assert kwargs["inscriptions"] == mock_inscriptions
        assert kwargs["classifications"] == mock_classifications

        # Check statistics calculation
        stats = kwargs["stats"]
        assert stats["total_inscriptions"] == 3
        assert stats["total_matches"] == 2  # Only completed matches
        assert stats["won_matches"] == 1
        assert stats["lost_matches"] == 1
        assert stats["win_percentage"] == 50.0

    @patch("routes.player.redirect")
    @patch("routes.player.url_for")
    @patch("routes.player.flash")
    @patch("routes.player.db")
    @patch("routes.player.DirectorRequest")
    @patch("routes.player.current_user")
    def test_request_director_success(
        self,
        mock_user,
        mock_director_request,
        mock_db,
        mock_flash,
        mock_url_for,
        mock_redirect,
    ):
        """Test successful director request."""
        mock_user.role = "player"
        mock_user.director_request = None
        mock_url_for.return_value = "/profile"
        mock_redirect.return_value = "redirect_response"

        from routes.player import request_director

        result = request_director()

        assert result == "redirect_response"
        mock_db.session.add.assert_called_once()
        mock_db.session.commit.assert_called_once()
        mock_flash.assert_called_once_with(
            "Richiesta inviata. Sarai contattato dall'amministratore."
        )

    @patch("routes.player.render_template")
    @patch("routes.player.request")
    def test_delete_account_get(self, mock_request, mock_render):
        """Test GET request to delete account page."""
        mock_request.method = "GET"
        mock_render.return_value = "delete_account_template"

        from routes.player import delete_account

        result = delete_account()

        assert result == "delete_account_template"
        mock_render.assert_called_once_with("player/delete_account.html")
