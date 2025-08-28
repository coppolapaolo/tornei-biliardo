"""
Test module for models/dashboard/services.py
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import date, datetime
from sqlalchemy.orm import joinedload

from models.dashboard.services import (
    DashboardService,
    _role_truthy,
    _compute_user_stats,
    CapabilityVM,
    DashboardVM,
)
from models.tournament.models import Tournament, TournamentDirector
from models.competition.models import Prova, Inscription
from models.match.models import Match as TournamentMatch
from models.user.models import User
from models.status_enum import ProvaStatus, MatchStatus
from models.individual_match.models import IndividualMatch
from models.location.models import PlayerAvailability


class TestDashboardServiceHelpers:
    """Test cases for helper functions."""

    def test_role_truthy_with_true_bool(self):
        """Test _role_truthy with a true boolean value."""
        user = Mock()
        user.test_attr = True
        result = _role_truthy(user, "test_attr")
        assert result is True

    def test_role_truthy_with_false_bool(self):
        """Test _role_truthy with a false boolean value."""
        user = Mock()
        user.test_attr = False
        result = _role_truthy(user, "test_attr")
        assert result is False

    def test_role_truthy_with_callable_returning_true(self):
        """Test _role_truthy with a callable that returns True."""
        user = Mock()
        user.test_attr = Mock(return_value=True)
        result = _role_truthy(user, "test_attr")
        assert result is True

    def test_role_truthy_with_callable_returning_false(self):
        """Test _role_truthy with a callable that returns False."""
        user = Mock()
        user.test_attr = Mock(return_value=False)
        result = _role_truthy(user, "test_attr")
        assert result is False

    def test_role_truthy_with_none(self):
        """Test _role_truthy with None value."""
        user = Mock()
        user.test_attr = None
        result = _role_truthy(user, "test_attr")
        assert result is False

    def test_role_truthy_with_non_callable_exception(self):
        """Test _role_truthy with a non-callable that raises TypeError."""
        user = Mock()
        user.test_attr = True  # Not callable, but we try to call it
        # We can't easily mock this case, so we'll test the fallback behavior
        # by patching callable to return False for True
        with patch("models.dashboard.services.callable", return_value=False):
            result = _role_truthy(user, "test_attr")
            assert result is True

    def test_compute_user_stats_no_matches(self):
        """Test _compute_user_stats with no matches."""
        with patch("models.dashboard.services.db") as mock_db:
            # Mock query to return 0 count for both total and won matches
            mock_query = Mock()
            mock_query.count.return_value = 0
            mock_db.session.query.return_value.filter.return_value = mock_query

            result = _compute_user_stats(1)

            assert result["total_matches"] == 0
            assert result["won_matches"] == 0
            assert result["win_percentage"] == 0.0

    def test_compute_user_stats_with_matches(self):
        """Test _compute_user_stats with matches."""
        with patch("models.dashboard.services.db") as mock_db:
            # Mock total matches query
            mock_total_query = Mock()
            mock_total_query.count.return_value = 10
            # Mock won matches query
            mock_won_query = Mock()
            mock_won_query.count.return_value = 7

            # Set up the query chain
            def query_side_effect(*args, **kwargs):
                if args and args[0] == TournamentMatch:
                    return mock_total_query
                return mock_total_query

            mock_db.session.query.side_effect = query_side_effect

            # Mock filter behavior
            mock_total_query.filter.return_value = mock_total_query
            mock_total_query.filter.return_value.count.return_value = 10
            mock_won_query.filter.return_value.count.return_value = 7

            # Mock the or_ filter for won matches
            with patch("models.dashboard.services.or_"):
                result = _compute_user_stats(1)

                assert result["total_matches"] == 10
                assert result["won_matches"] == 7
                assert result["win_percentage"] == 70.0

    def test_capability_vm_default_values(self):
        """Test CapabilityVM default values."""
        caps = CapabilityVM()
        assert caps.can_create_tournament is False
        assert caps.can_create_standalone is False
        assert caps.can_register_self is True

    def test_capability_vm_custom_values(self):
        """Test CapabilityVM with custom values."""
        caps = CapabilityVM(
            can_create_tournament=True,
            can_create_standalone=True,
            can_register_self=False,
        )
        assert caps.can_create_tournament is True
        assert caps.can_create_standalone is True
        assert caps.can_register_self is False


class TestDashboardServiceQueryHelpers:
    """Test cases for query helper methods."""

    def test_tournaments_q(self):
        """Test _tournaments_q method."""
        with patch("models.dashboard.services.db") as mock_db:
            mock_query = Mock()
            mock_db.session.query.return_value.options.return_value.order_by.return_value = (
                mock_query
            )

            result = DashboardService._tournaments_q()

            assert result == mock_query
            mock_db.session.query.assert_called_once_with(Tournament)
            mock_db.session.query.return_value.options.assert_called_once()
            mock_db.session.query.return_value.options.return_value.order_by.assert_called_once()

    def test_managed_tournaments_q(self):
        """Test _managed_tournaments_q method."""
        with patch("models.dashboard.services.db") as mock_db:
            mock_query = Mock()
            mock_db.session.query.return_value.join.return_value.filter.return_value.options.return_value.order_by.return_value = (
                mock_query
            )

            result = DashboardService._managed_tournaments_q(1)

            assert result == mock_query
            mock_db.session.query.assert_called_once_with(Tournament)

    def test_standalone_q(self):
        """Test _standalone_q method."""
        with patch("models.dashboard.services.db") as mock_db:
            mock_query = Mock()
            mock_db.session.query.return_value.filter.return_value.order_by.return_value = (
                mock_query
            )

            result = DashboardService._standalone_q()

            assert result == mock_query
            mock_db.session.query.assert_called_once_with(Prova)

    def test_annotate_provas_with_flags_empty_list(self):
        """Test _annotate_provas_with_flags with empty list."""
        result = DashboardService._annotate_provas_with_flags([])
        assert result == []

    def test_annotate_provas_with_flags_none(self):
        """Test _annotate_provas_with_flags with None."""
        result = DashboardService._annotate_provas_with_flags(None)
        assert result == []

    def test_annotate_provas_with_flags_with_provas(self):
        """Test _annotate_provas_with_flags with provas."""
        mock_prova = Mock()
        mock_prova.get_real_status.return_value = ProvaStatus.INSCRIPTION.value

        result = DashboardService._annotate_provas_with_flags([mock_prova])

        assert len(result) == 1
        assert mock_prova.is_inscription_open is True

    def test_standalone_available_for_user(self):
        """Test _standalone_available_for_user method."""
        with patch("models.dashboard.services.db") as mock_db:
            mock_query = Mock()
            mock_query.filter.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value = mock_query

            # Mock subquery
            mock_subquery = Mock()
            mock_subquery.scalar_subquery.return_value = "subquery_result"
            mock_db.session.query.return_value.where.return_value.scalar_subquery.return_value = (
                "subquery_result"
            )

            result = DashboardService._standalone_available_for_user(1)

            assert result == []
            mock_db.session.query.assert_called()

    def test_standalone_available_for_user_with_exclude_director(self):
        """Test _standalone_available_for_user method with exclude_director_id."""
        with patch("models.dashboard.services.db") as mock_db:
            mock_query = Mock()
            mock_query.filter.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value = mock_query

            # Mock subquery
            mock_subquery = Mock()
            mock_subquery.scalar_subquery.return_value = "subquery_result"
            mock_db.session.query.return_value.where.return_value.scalar_subquery.return_value = (
                "subquery_result"
            )

            result = DashboardService._standalone_available_for_user(
                1, exclude_director_id=2
            )

            assert result == []
            mock_db.session.query.assert_called()


class TestDashboardServiceSelectorHelpers:
    """Test cases for selector helper methods."""

    def test_build_selector_items_empty(self):
        """Test _build_selector_items with empty collections."""
        result = DashboardService._build_selector_items(
            [], [], selected_tournament_id=None, selected_prova_id=None
        )
        assert result == []

    def test_build_selector_items_with_tournaments_and_provas(self):
        """Test _build_selector_items with tournaments and provas."""
        mock_tournament = Mock()
        mock_tournament.id = 1
        mock_tournament.name = "Test Tournament"

        mock_prova = Mock()
        mock_prova.id = 1
        mock_prova.name = "Test Prova"
        mock_prova.date = date(2023, 1, 1)

        # Mock the provas relationship on tournament
        mock_tournament.provas = []

        result = DashboardService._build_selector_items(
            [mock_tournament], [mock_prova], selected_tournament_id=None, selected_prova_id=None
        )

        assert len(result) == 2
        # Check that both items are present
        kinds = [item["kind"] for item in result]
        assert "t" in kinds  # tournament
        assert "p" in kinds  # prova

    def test_caps_for_admin_user(self):
        """Test _caps_for with admin user."""
        mock_user = Mock()
        mock_user.is_admin = True
        mock_user.is_director = False

        result = DashboardService._caps_for(mock_user)

        assert result.can_create_tournament is True
        assert result.can_create_standalone is True
        assert result.can_register_self is False

    def test_caps_for_director_user(self):
        """Test _caps_for with director user."""
        mock_user = Mock()
        mock_user.is_admin = False
        mock_user.is_director = True

        result = DashboardService._caps_for(mock_user)

        assert result.can_create_tournament is True
        assert result.can_create_standalone is True
        assert result.can_register_self is True

    def test_caps_for_player_user(self):
        """Test _caps_for with player user."""
        mock_user = Mock()
        mock_user.is_admin = False
        mock_user.is_director = False

        result = DashboardService._caps_for(mock_user)

        assert result.can_create_tournament is False
        assert result.can_create_standalone is False
        assert result.can_register_self is True


class TestDashboardServicePlayerSections:
    """Test cases for player section builder methods."""

    def test_build_player_sections_no_selected_tournament(self):
        """Test _build_player_sections with no selected tournament."""
        result = DashboardService._build_player_sections(1, None)

        assert result["available_provas"] == []
        assert result["my_inscriptions"] == []
        assert result["current_matches"] == []
        assert result["recent_matches"] == []

    def test_build_player_sections_with_selected_tournament(self):
        """Test _build_player_sections with selected tournament."""
        with patch("models.dashboard.services.db") as mock_db:
            mock_tournament = Mock()
            mock_tournament.id = 1

            # Mock available provas query
            mock_prova_query = Mock()
            mock_prova_query.filter.return_value.order_by.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value = mock_prova_query

            # Mock inscriptions query
            mock_inscription_query = Mock()
            mock_inscription_query.join.return_value.filter.return_value.options.return_value.order_by.return_value.all.return_value = (
                []
            )
            mock_db.session.query.return_value.join.return_value = mock_inscription_query

            # Mock matches queries
            mock_match_query = Mock()
            mock_match_query.join.return_value.filter.return_value.order_by.return_value.all.return_value = (
                []
            )
            mock_match_query.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                []
            )
            mock_db.session.query.return_value.join.return_value.filter.return_value = (
                mock_match_query
            )

            result = DashboardService._build_player_sections(1, mock_tournament)

            assert isinstance(result["available_provas"], list)
            assert isinstance(result["my_inscriptions"], list)
            assert isinstance(result["current_matches"], list)
            assert isinstance(result["recent_matches"], list)


class TestDashboardServiceIndividualMatchSections:
    """Test cases for individual match section builder methods."""

    def test_build_individual_match_sections(self):
        """Test _build_individual_match_sections method."""
        with patch("models.dashboard.services.db") as mock_db:
            # Mock IndividualMatchService
            with patch(
                "models.dashboard.services.IndividualMatchService"
            ) as mock_individual_match_service:
                mock_individual_match_service.get_user_proposals.return_value = {
                    "created": [],
                    "received": [],
                    "available": [],
                }

                # Mock IndividualMatch query
                mock_match_query = Mock()
                mock_match_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                    []
                )
                mock_db.session.query.return_value = mock_match_query

                # Mock PlayerAvailability query
                mock_availability_query = Mock()
                mock_availability_query.filter_by.return_value.all.return_value = []
                mock_db.session.query.return_value.filter_by.return_value = (
                    mock_availability_query
                )

                result = DashboardService._build_individual_match_sections(1)

                assert "match_proposals" in result
                assert "individual_matches" in result
                assert "match_opportunities" in result


class TestDashboardServiceMainMethods:
    """Test cases for main DashboardService methods."""

    def test_for_admin(self):
        """Test for_admin method."""
        with patch("models.dashboard.services.db") as mock_db:
            # Mock tournament query
            mock_tournament_query = Mock()
            mock_tournament_query.all.return_value = []
            mock_db.session.query.return_value.options.return_value.order_by.return_value = (
                mock_tournament_query
            )

            # Mock prova query
            mock_prova_query = Mock()
            mock_prova_query.filter.return_value.order_by.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value = mock_prova_query

            result = DashboardService.for_admin()

            assert isinstance(result, DashboardVM)
            assert result.title == "Dashboard Amministratore"
            assert result.can_manage_directors is True
            assert result.can_inscribe is False

    def test_for_director_user_not_found(self):
        """Test for_director method when user is not found."""
        with patch("models.dashboard.services.db") as mock_db:
            mock_db.session.get.return_value = None

            with pytest.raises(ValueError, match="Utente non trovato"):
                DashboardService.for_director(999)

    def test_for_director_success(self):
        """Test for_director method success case."""
        with patch("models.dashboard.services.db") as mock_db:
            # Mock user
            mock_user = Mock()
            mock_user.id = 1
            mock_user.is_admin = False
            mock_user.is_director = True

            # Mock db.session.get for user
            mock_db.session.get.return_value = mock_user

            # Mock tournament queries
            mock_tournament_query = Mock()
            mock_tournament_query.all.return_value = []
            mock_tournament_query.join.return_value.filter.return_value.options.return_value.order_by.return_value.all.return_value = (
                []
            )
            mock_db.session.query.return_value.options.return_value.order_by.return_value = (
                mock_tournament_query
            )
            mock_db.session.query.return_value.join.return_value = mock_tournament_query

            # Mock prova query
            mock_prova_query = Mock()
            mock_prova_query.filter.return_value.order_by.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value = mock_prova_query

            # Mock inscription query
            mock_inscription_query = Mock()
            mock_inscription_query.join.return_value.filter.return_value.options.return_value.order_by.return_value.all.return_value = (
                []
            )
            mock_db.session.query.return_value.join.return_value.filter.return_value = (
                mock_inscription_query
            )

            # Mock match queries
            mock_match_query = Mock()
            mock_match_query.join.return_value.filter.return_value.order_by.return_value.all.return_value = (
                []
            )
            mock_match_query.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                []
            )
            mock_db.session.query.return_value.join.return_value.filter.return_value = (
                mock_match_query
            )

            # Mock TournamentDirector query
            mock_td_query = Mock()
            mock_td_query.filter_by.return_value.first.return_value = None
            mock_db.session.query.return_value.filter_by.return_value = mock_td_query

            # Mock IndividualMatchService
            with patch(
                "models.dashboard.services.IndividualMatchService"
            ) as mock_individual_match_service:
                mock_individual_match_service.get_user_proposals.return_value = {
                    "created": [],
                    "received": [],
                    "available": [],
                }

                # Mock IndividualMatch query
                mock_individual_match_query = Mock()
                mock_individual_match_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                    []
                )
                mock_db.session.query.return_value = mock_individual_match_query

                # Mock PlayerAvailability query
                mock_availability_query = Mock()
                mock_availability_query.filter_by.return_value.all.return_value = []
                mock_db.session.query.return_value.filter_by.return_value = (
                    mock_availability_query
                )

                # Mock _compute_user_stats
                with patch(
                    "models.dashboard.services._compute_user_stats"
                ) as mock_compute_stats:
                    mock_compute_stats.return_value = {
                        "total_matches": 0,
                        "won_matches": 0,
                        "win_percentage": 0.0,
                    }

                    result = DashboardService.for_director(1)

                    assert isinstance(result, DashboardVM)
                    assert result.title == "Dashboard Direttore"
                    assert result.user_stats is not None

    def test_for_player_user_not_found(self):
        """Test for_player method when user is not found."""
        with patch("models.dashboard.services.db") as mock_db:
            mock_db.session.get.return_value = None

            with pytest.raises(ValueError, match="Utente non trovato"):
                DashboardService.for_player(999)

    def test_for_player_success(self):
        """Test for_player method success case."""
        with patch("models.dashboard.services.db") as mock_db:
            # Mock user
            mock_user = Mock()
            mock_user.id = 1
            mock_user.is_admin = False
            mock_user.is_director = False

            # Mock db.session.get for user
            mock_db.session.get.return_value = mock_user

            # Mock tournament queries
            mock_tournament_query = Mock()
            mock_tournament_query.all.return_value = []
            mock_db.session.query.return_value.options.return_value.order_by.return_value = (
                mock_tournament_query
            )

            # Mock prova query
            mock_prova_query = Mock()
            mock_prova_query.filter.return_value.order_by.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value = mock_prova_query

            # Mock inscription query
            mock_inscription_query = Mock()
            mock_inscription_query.join.return_value.filter.return_value.options.return_value.order_by.return_value.all.return_value = (
                []
            )
            mock_db.session.query.return_value.join.return_value.filter.return_value = (
                mock_inscription_query
            )

            # Mock match queries
            mock_match_query = Mock()
            mock_match_query.join.return_value.filter.return_value.order_by.return_value.all.return_value = (
                []
            )
            mock_match_query.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                []
            )
            mock_db.session.query.return_value.join.return_value.filter.return_value = (
                mock_match_query
            )

            # Mock IndividualMatchService
            with patch(
                "models.dashboard.services.IndividualMatchService"
            ) as mock_individual_match_service:
                mock_individual_match_service.get_user_proposals.return_value = {
                    "created": [],
                    "received": [],
                    "available": [],
                }

                # Mock IndividualMatch query
                mock_individual_match_query = Mock()
                mock_individual_match_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                    []
                )
                mock_db.session.query.return_value = mock_individual_match_query

                # Mock PlayerAvailability query
                mock_availability_query = Mock()
                mock_availability_query.filter_by.return_value.all.return_value = []
                mock_db.session.query.return_value.filter_by.return_value = (
                    mock_availability_query
                )

                # Mock _compute_user_stats
                with patch(
                    "models.dashboard.services._compute_user_stats"
                ) as mock_compute_stats:
                    mock_compute_stats.return_value = {
                        "total_matches": 0,
                        "won_matches": 0,
                        "win_percentage": 0.0,
                    }

                    result = DashboardService.for_player(1)

                    assert isinstance(result, DashboardVM)
                    assert result.title == "Dashboard Giocatore"
                    assert result.user_stats is not None
                    assert result.can_inscribe is True


if __name__ == "__main__":
    pytest.main([__file__])