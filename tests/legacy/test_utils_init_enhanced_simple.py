"""
Enhanced tests for utils/__init__.py focusing on achievable coverage improvements.
"""

import pytest
from unittest.mock import Mock, patch

# Import functions to test
from utils import (
    UserPermissions,
    create_round_matches,
    calculate_round_classification,
    create_default_users,
    create_sample_campionato,
    create_admin_if_not_exists,
    create_round_matches_amalfi_compatible,
)


class TestUserPermissionsDetailed:
    """Detailed tests for UserPermissions static methods to achieve coverage."""

    @patch("utils.current_user")
    def test_can_inscribe_to_gara_all_cases(self, mock_user):
        """Test all branches of can_inscribe_to_gara."""
        # Case 1: Authenticated non-admin (should return True)
        mock_user.is_authenticated = True
        mock_user.is_admin = False
        assert UserPermissions.can_inscribe_to_gara() is True

        # Case 2: Authenticated admin (should return False)
        mock_user.is_admin = True
        assert UserPermissions.can_inscribe_to_gara() is False

        # Case 3: Unauthenticated (should return False)
        mock_user.is_authenticated = False
        assert UserPermissions.can_inscribe_to_gara() is False

    @patch("utils.current_user")
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

    @patch("utils.current_user")
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

    @patch("utils.current_user")
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

    @patch("utils.current_user")
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

    @patch("utils.current_user")
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


class TestCreateRoundMatchesDetailed:
    """Detailed tests for create_round_matches function."""

    @patch("utils.db")
    @patch("utils.Match")
    def test_create_round_matches_even_players(self, mock_match_class, mock_db):
        """Test create_round_matches with even number of players."""
        # Setup gara
        mock_gara = Mock()
        mock_gara.id = 1

        # Setup players
        mock_player1 = Mock()
        mock_player1.id = 1
        mock_player2 = Mock()
        mock_player2.id = 2
        players = [mock_player1, mock_player2]

        # Mock Match instances
        mock_match = Mock()
        mock_match_class.return_value = mock_match

        matches = create_round_matches(mock_gara, players, 1)

        # Verify results
        assert len(matches) == 1
        assert matches[0] == mock_match
        mock_db.session.add_all.assert_called_once_with(matches)

        # Verify Match was created with correct parameters
        mock_match_class.assert_called_once_with(
            gara_id=1,
            round_number=1,
            player1_id=1,
            player2_id=2,
        )

    @patch("utils.db")
    @patch("utils.Match")
    def test_create_round_matches_odd_players_with_bye(self, mock_match_class, mock_db):
        """Test create_round_matches with odd number of players (creates bye)."""
        # Setup gara
        mock_gara = Mock()
        mock_gara.id = 1
        mock_gara.best_of = True
        mock_gara.get_winning_score.return_value = 5
        mock_gara.distance = 7

        # Setup players (odd number)
        mock_player1 = Mock()
        mock_player1.id = 1
        mock_player2 = Mock()
        mock_player2.id = 2
        mock_player3 = Mock()
        mock_player3.id = 3
        players = [mock_player1, mock_player2, mock_player3]

        # Mock Match instances
        mock_bye_match = Mock()
        mock_regular_match = Mock()
        mock_match_class.side_effect = [mock_bye_match, mock_regular_match]

        matches = create_round_matches(mock_gara, players, 1)

        # Verify results
        assert len(matches) == 2
        assert mock_bye_match in matches
        assert mock_regular_match in matches
        mock_db.session.add_all.assert_called_once_with(matches)

        # Verify Match calls
        assert mock_match_class.call_count == 2

    @patch("utils.db")
    @patch("utils.Match")
    @patch("utils.Inscription")
    def test_create_round_matches_with_inscriptions(
        self, mock_inscription_class, mock_match_class, mock_db
    ):
        """Test create_round_matches with Inscription objects (extracts users)."""
        # Setup gara
        mock_gara = Mock()
        mock_gara.id = 1

        # Setup inscriptions with users
        mock_user1 = Mock()
        mock_user1.id = 1
        mock_user2 = Mock()
        mock_user2.id = 2

        mock_inscription1 = Mock()
        mock_inscription1.user = mock_user1
        mock_inscription2 = Mock()
        mock_inscription2.user = mock_user2

        inscriptions = [mock_inscription1, mock_inscription2]

        # Mock Match
        mock_match = Mock()
        mock_match_class.return_value = mock_match

        matches = create_round_matches(mock_gara, inscriptions, 1)

        # Verify results
        assert len(matches) == 1
        mock_db.session.add_all.assert_called_once_with(matches)

        # Verify Match was created with user IDs extracted from inscriptions
        mock_match_class.assert_called_once_with(
            gara_id=1,
            round_number=1,
            player1_id=1,
            player2_id=2,
        )

    @patch("utils.db")
    @patch("utils.Match")
    def test_create_round_matches_odd_players_distance_mode(
        self, mock_match_class, mock_db
    ):
        """Test create_round_matches with odd players when gara is not best_of."""
        # Setup gara
        mock_gara = Mock()
        mock_gara.id = 1
        mock_gara.best_of = False  # Distance mode
        mock_gara.distance = 7

        # Setup players (odd number)
        mock_player1 = Mock()
        mock_player1.id = 1
        players = [mock_player1]

        # Mock Match instances
        mock_bye_match = Mock()
        mock_match_class.return_value = mock_bye_match

        matches = create_round_matches(mock_gara, players, 1)

        # Verify bye match created with distance score
        assert len(matches) == 1
        mock_match_class.assert_called_once_with(
            gara_id=1,
            round_number=1,
            player1_id=1,
            is_bye=True,
            player1_score=7,  # Should use distance, not get_winning_score
            winner_id=1,
            status="completed",
        )


class TestCalculateRoundClassificationDetailed:
    """Detailed tests for calculate_round_classification function."""

    @patch("utils.Inscription")
    @patch("utils.Match")
    def test_calculate_round_classification_bye_match(
        self, mock_match_class, mock_inscription_class
    ):
        """Test calculate_round_classification with bye match."""
        # Setup bye match
        mock_match = Mock()
        mock_match.is_bye = True
        mock_match.player1_id = 1
        mock_match.player1_score = 5
        mock_match_class.query.filter_by.return_value.all.return_value = [mock_match]

        result = calculate_round_classification(1, 1)

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 1
        player_id, stats = result[0]
        assert player_id == 1
        assert stats["matches_won"] == 1
        assert stats["point_diff"] == 5
        assert stats["initial_order"] == 0

    @patch("utils.Inscription")
    @patch("utils.Match")
    def test_calculate_round_classification_completed_match(
        self, mock_match_class, mock_inscription_class
    ):
        """Test calculate_round_classification with completed regular match."""
        # Setup completed match
        mock_match = Mock()
        mock_match.is_bye = False
        mock_match.player1_id = 1
        mock_match.player2_id = 2
        mock_match.status = "completed"
        mock_match.winner_id = 1
        mock_match.player1_score = 5
        mock_match.player2_score = 3
        mock_match_class.query.filter_by.return_value.all.return_value = [mock_match]

        # Setup inscriptions
        mock_inscription1 = Mock()
        mock_inscription1.initial_order = 1
        mock_inscription2 = Mock()
        mock_inscription2.initial_order = 2
        mock_inscription_class.query.filter_by.return_value.first.side_effect = [
            mock_inscription1,
            mock_inscription2,
        ]

        result = calculate_round_classification(1, 1)

        # Verify results - sorted by wins desc, point_diff desc, initial_order asc
        assert isinstance(result, list)
        assert len(result) == 2

        # Winner should be first
        winner_id, winner_stats = result[0]
        assert winner_id == 1
        assert winner_stats["matches_won"] == 1
        assert winner_stats["point_diff"] == 2  # 5-3 = 2

        # Loser should be second
        loser_id, loser_stats = result[1]
        assert loser_id == 2
        assert loser_stats["matches_won"] == 0
        assert loser_stats["point_diff"] == -2  # 3-5 = -2

    @patch("utils.Inscription")
    @patch("utils.Match")
    def test_calculate_round_classification_incomplete_match(
        self, mock_match_class, mock_inscription_class
    ):
        """Test calculate_round_classification with incomplete match."""
        # Setup incomplete match
        mock_match = Mock()
        mock_match.is_bye = False
        mock_match.player1_id = 1
        mock_match.player2_id = 2
        mock_match.status = "pending"
        mock_match.winner_id = None
        mock_match_class.query.filter_by.return_value.all.return_value = [mock_match]

        # Setup inscriptions
        mock_inscription1 = Mock()
        mock_inscription1.initial_order = 1
        mock_inscription2 = Mock()
        mock_inscription2.initial_order = 2
        mock_inscription_class.query.filter_by.return_value.first.side_effect = [
            mock_inscription1,
            mock_inscription2,
        ]

        result = calculate_round_classification(1, 1)

        # Verify results - no winner, so both have 0 wins and 0 point diff
        assert isinstance(result, list)
        assert len(result) == 2

        for player_id, stats in result:
            assert stats["matches_won"] == 0
            assert stats["point_diff"] == 0

    @patch("utils.Inscription")
    @patch("utils.Match")
    def test_calculate_round_classification_missing_inscription(
        self, mock_match_class, mock_inscription_class
    ):
        """Test calculate_round_classification when inscription is missing."""
        # Setup match
        mock_match = Mock()
        mock_match.is_bye = False
        mock_match.player1_id = 1
        mock_match.player2_id = 2
        mock_match.status = "completed"
        mock_match.winner_id = 1
        mock_match.player1_score = 5
        mock_match.player2_score = 3
        mock_match_class.query.filter_by.return_value.all.return_value = [mock_match]

        # No inscriptions found
        mock_inscription_class.query.filter_by.return_value.first.return_value = None

        result = calculate_round_classification(1, 1)

        # Should still work with default initial_order of 999
        assert isinstance(result, list)
        assert len(result) == 2

        for player_id, stats in result:
            assert stats["initial_order"] == 999


class TestCreateDefaultUsersDetailed:
    """Detailed tests for create_default_users function."""

    @patch("utils.db")
    @patch("utils.User")
    def test_create_default_users_complete(self, mock_user_class, mock_db):
        """Test create_default_users creates all three users correctly."""
        # Setup mock users
        mock_admin = Mock()
        mock_mario = Mock()
        mock_pino = Mock()
        mock_user_class.side_effect = [mock_admin, mock_mario, mock_pino]

        admin, mario, pino = create_default_users()

        # Verify return values
        assert admin == mock_admin
        assert mario == mock_mario
        assert pino == mock_pino

        # Verify User constructor calls
        expected_calls = [
            (("admin", "admin@campionato.com", "admin"), {}),
            (("mario", "mario@test.com", "player"), {}),
            (("pino", "pino@test.com", "player"), {}),
        ]

        actual_calls = [
            (call.args, call.kwargs) for call in mock_user_class.call_args_list
        ]

        # Check that users were created with correct parameters
        assert len(actual_calls) == 3
        assert mock_user_class.call_count == 3

        # Verify password setting
        mock_admin.set_password.assert_called_once_with("admin123")
        mock_mario.set_password.assert_called_once_with("mario123")
        mock_pino.set_password.assert_called_once_with("pino123")

        # Verify database operations
        mock_db.session.add_all.assert_called_once_with(
            [mock_admin, mock_mario, mock_pino]
        )
        mock_db.session.commit.assert_called_once()


class TestCreateSampleTournamentDetailed:
    """Detailed tests for create_sample_campionato function."""

    @patch("builtins.print")  # Suppress print output
    @patch("utils.db")
    @patch("utils.GaraService")
    @patch("utils.Campionato")
    def test_create_sample_campionato_complete(
        self, mock_campionato_class, mock_gara_service, mock_db, mock_print
    ):
        """Test create_sample_campionato creates campionati and proves correctly."""
        # Setup mock campionati
        mock_campionato1 = Mock()
        mock_campionato1.id = 1
        mock_campionato1.name = "Campionato Primavera 2025"
        mock_campionato2 = Mock()
        mock_campionato2.id = 2
        mock_campionato2.name = "Coppa Estate 2025"
        mock_campionato_class.side_effect = [mock_campionato1, mock_campionato2]

        tournament1, tournament2 = create_sample_campionato()

        # Verify return values
        assert tournament1 == mock_campionato1
        assert tournament2 == mock_campionato2

        # Verify Campionato creation
        assert mock_campionato_class.call_count == 2

        # Verify database operations for campionati
        assert mock_db.session.add.call_count == 2
        assert mock_db.session.commit.call_count == 3  # 2 for campionati + 1 final

        # Verify GaraService.create_gara was called 3 times
        assert mock_gara_service.create_gara.call_count == 3

        # Verify print statements
        assert mock_print.call_count >= 3  # At least 3 print calls


class TestCreateAdminIfNotExistsDetailed:
    """Detailed tests for create_admin_if_not_exists function."""

    @patch("utils.UserRole")
    @patch("utils.User")
    @patch("utils.current_app")
    def test_create_admin_if_not_exists_existing_admin(
        self, mock_app, mock_user_class, mock_role
    ):
        """Test create_admin_if_not_exists when admin already exists."""
        # Setup config
        mock_app.config = {"ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "password"}
        mock_role.ADMIN.value = "admin"

        # Setup existing admin
        mock_existing_admin = Mock()
        mock_user_class.query.filter_by.return_value.filter.return_value.first.return_value = (
            mock_existing_admin
        )

        result = create_admin_if_not_exists()

        # Should return existing admin without creating new one
        assert result == mock_existing_admin

    @patch("utils.db")
    @patch("utils.UserRole")
    @patch("utils.User")
    @patch("utils.current_app")
    def test_create_admin_if_not_exists_create_new(
        self, mock_app, mock_user_class, mock_role, mock_db
    ):
        """Test create_admin_if_not_exists when no admin exists."""
        # Setup config
        mock_app.config = {
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD": "password",
            "ADMIN_EMAIL": "admin@test.com",
        }
        mock_role.ADMIN.value = "admin"

        # No existing admin
        mock_user_class.query.filter_by.return_value.filter.return_value.first.return_value = (
            None
        )

        # Setup new admin
        mock_new_admin = Mock()
        mock_user_class.return_value = mock_new_admin

        result = create_admin_if_not_exists()

        # Verify new admin creation
        assert result == mock_new_admin
        mock_new_admin.set_password.assert_called_once_with("password")
        mock_db.session.add.assert_called_once_with(mock_new_admin)
        mock_db.session.commit.assert_called_once()

    @patch("utils.current_app")
    def test_create_admin_if_not_exists_missing_required_config(self, mock_app):
        """Test create_admin_if_not_exists with missing required config."""
        # Setup production config without credentials
        mock_app.config = {"ADMIN_PASSWORD_REQUIRED": True}

        with pytest.raises(RuntimeError, match="Admin bootstrap richiede"):
            create_admin_if_not_exists()

    @patch("utils.UserRole")
    @patch("utils.User")
    @patch("utils.current_app")
    def test_create_admin_if_not_exists_no_config_dev_mode(
        self, mock_app, mock_user_class, mock_role
    ):
        """Test create_admin_if_not_exists without config in development mode."""
        # Setup dev config without credentials
        mock_app.config = {"ADMIN_PASSWORD_REQUIRED": False}
        mock_role.ADMIN.value = "admin"

        # No existing admin
        mock_user_class.query.filter_by.return_value.filter.return_value.first.return_value = (
            None
        )

        result = create_admin_if_not_exists()

        # Should return None without creating admin
        assert result is None


class TestCreateRoundMatchesAmalfiCompatibleDetailed:
    """Detailed tests for create_round_matches_amalfi_compatible function."""

    @patch("utils.db")
    @patch("utils.Match")
    def test_create_round_matches_amalfi_compatible_even_players(
        self, mock_match_class, mock_db
    ):
        """Test create_round_matches_amalfi_compatible with even number of players."""
        # Setup gara
        mock_gara = Mock()
        mock_gara.id = 1

        # Setup players
        mock_player1 = Mock()
        mock_player1.id = 1
        mock_player2 = Mock()
        mock_player2.id = 2
        players = [mock_player1, mock_player2]

        # Mock Match
        mock_match = Mock()
        mock_match_class.return_value = mock_match

        matches = create_round_matches_amalfi_compatible(mock_gara, players, 1)

        # Verify results
        assert len(matches) == 1
        assert matches[0] == mock_match
        mock_db.session.add_all.assert_called_once_with(matches)

        # Verify Match creation includes amalfi_round
        mock_match_class.assert_called_once_with(
            gara_id=1,
            round_number=1,
            player1_id=1,
            player2_id=2,
            amalfi_round=1,  # This is the key difference from regular create_round_matches
        )

    @patch("utils.db")
    @patch("utils.Match")
    def test_create_round_matches_amalfi_compatible_odd_players(
        self, mock_match_class, mock_db
    ):
        """Test create_round_matches_amalfi_compatible with odd number of players."""
        # Setup gara
        mock_gara = Mock()
        mock_gara.id = 1
        mock_gara.best_of = True
        mock_gara.get_winning_score.return_value = 5

        # Setup players (odd number)
        mock_player1 = Mock()
        mock_player1.id = 1
        mock_player2 = Mock()
        mock_player2.id = 2
        mock_player3 = Mock()
        mock_player3.id = 3
        players = [mock_player1, mock_player2, mock_player3]

        # Mock Match instances
        mock_bye_match = Mock()
        mock_regular_match = Mock()
        mock_match_class.side_effect = [mock_bye_match, mock_regular_match]

        matches = create_round_matches_amalfi_compatible(mock_gara, players, 1)

        # Verify results
        assert len(matches) == 2
        assert mock_bye_match in matches
        assert mock_regular_match in matches
        mock_db.session.add_all.assert_called_once_with(matches)

        # Verify both matches include amalfi_round
        assert mock_match_class.call_count == 2

        # Check that all calls included amalfi_round=1
        for call in mock_match_class.call_args_list:
            args, kwargs = call
            assert "amalfi_round" in kwargs
            assert kwargs["amalfi_round"] == 1
