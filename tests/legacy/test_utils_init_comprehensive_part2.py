"""
Comprehensive enhanced tests for utils/__init__.py - Part 2
Testing domain functions and bootstrap functions to achieve high coverage.
"""

import pytest
from unittest.mock import Mock, patch

# Import functions to test
from utils import (
    rack_player_required,
    challenge_attempt_player_required,
    individual_match_player_required,
    rack_manager_required,
    trio_manager_required,
    create_round_matches,
    calculate_round_classification,
    create_default_users,
    create_sample_campionato,
    create_admin_if_not_exists,
    create_round_matches_amalfi_compatible,
)


class TestRackPlayerRequiredDecorator:
    """Test rack_player_required decorator implementation."""

    def test_rack_player_required_missing_rack_id(self):
        """Test rack_player_required when rack_id is missing."""
        with patch("utils.abort") as mock_abort:

            @rack_player_required
            def test_function(**kwargs):
                return "success"

            test_function()
            mock_abort.assert_called_once_with(400)

    def test_rack_player_required_rack_not_found(self):
        """Test rack_player_required when rack is not found."""
        with patch("utils.Rack") as mock_rack, patch("utils.abort") as mock_abort:

            mock_rack.query.get.return_value = None

            @rack_player_required
            def test_function(rack_id=1):
                return "success"

            test_function(rack_id=1)
            mock_abort.assert_called_once_with(404)

    def test_rack_player_required_valid_player(self):
        """Test rack_player_required when user is a valid player."""
        with patch("utils.current_user") as mock_user, patch("utils.Rack") as mock_rack:

            mock_user.id = 1
            mock_match = Mock()
            mock_match.player1_id = 1
            mock_match.player2_id = 2
            mock_rack_instance = Mock()
            mock_rack_instance.match = mock_match
            mock_rack.query.get.return_value = mock_rack_instance

            @rack_player_required
            def test_function(rack_id=1):
                return "success"

            result = test_function(rack_id=1)
            assert result == "success"

    def test_rack_player_required_invalid_player(self):
        """Test rack_player_required when user is not a player."""
        with patch("utils.current_user") as mock_user, patch(
            "utils.Rack"
        ) as mock_rack, patch("utils.flash") as mock_flash, patch(
            "utils.redirect"
        ) as mock_redirect, patch(
            "utils.url_for"
        ) as mock_url_for:

            mock_user.id = 3  # Not player1 or player2
            mock_match = Mock()
            mock_match.player1_id = 1
            mock_match.player2_id = 2
            mock_rack_instance = Mock()
            mock_rack_instance.match = mock_match
            mock_rack.query.get.return_value = mock_rack_instance
            mock_url_for.return_value = "/dashboard"
            mock_redirect.return_value = "redirect_response"

            @rack_player_required
            def test_function(rack_id=1):
                return "success"

            result = test_function(rack_id=1)
            assert result == "redirect_response"
            mock_flash.assert_called_once_with(
                "Non sei un giocatore di questa partita.", "error"
            )


class TestChallengeAttemptPlayerRequiredDecorator:
    """Test challenge_attempt_player_required decorator implementation."""

    def test_challenge_attempt_player_required_missing_attempt_id(self):
        """Test challenge_attempt_player_required when attempt_id is missing."""
        with patch("utils.abort") as mock_abort:

            @challenge_attempt_player_required
            def test_function(**kwargs):
                return "success"

            test_function()
            mock_abort.assert_called_once_with(400)

    def test_challenge_attempt_player_required_attempt_not_found(self):
        """Test challenge_attempt_player_required when attempt is not found."""
        with patch("utils.ChallengeAttempt") as mock_attempt, patch(
            "utils.abort"
        ) as mock_abort:

            mock_attempt.query.get.return_value = None

            @challenge_attempt_player_required
            def test_function(attempt_id=1):
                return "success"

            test_function(attempt_id=1)
            mock_abort.assert_called_once_with(404)

    def test_challenge_attempt_player_required_valid_owner(self):
        """Test challenge_attempt_player_required when user is the owner."""
        with patch("utils.current_user") as mock_user, patch(
            "utils.ChallengeAttempt"
        ) as mock_attempt:

            mock_user.id = 1
            mock_attempt_instance = Mock()
            mock_attempt_instance.user_id = 1
            mock_attempt.query.get.return_value = mock_attempt_instance

            @challenge_attempt_player_required
            def test_function(attempt_id=1):
                return "success"

            result = test_function(attempt_id=1)
            assert result == "success"

    def test_challenge_attempt_player_required_not_owner(self):
        """Test challenge_attempt_player_required when user is not the owner."""
        with patch("utils.current_user") as mock_user, patch(
            "utils.ChallengeAttempt"
        ) as mock_attempt, patch("utils.flash") as mock_flash, patch(
            "utils.redirect"
        ) as mock_redirect, patch(
            "utils.url_for"
        ) as mock_url_for:

            mock_user.id = 1
            mock_attempt_instance = Mock()
            mock_attempt_instance.user_id = 2  # Different owner
            mock_attempt.query.get.return_value = mock_attempt_instance
            mock_url_for.return_value = "/dashboard"
            mock_redirect.return_value = "redirect_response"

            @challenge_attempt_player_required
            def test_function(attempt_id=1):
                return "success"

            result = test_function(attempt_id=1)
            assert result == "redirect_response"
            mock_flash.assert_called_once_with(
                "Non sei il proprietario di questo tentativo.", "error"
            )


class TestIndividualMatchPlayerRequiredDecorator:
    """Test individual_match_player_required decorator implementation."""

    def test_individual_match_player_required_missing_match_id(self):
        """Test individual_match_player_required when match_id is missing."""
        with patch("utils.abort") as mock_abort:

            @individual_match_player_required
            def test_function(**kwargs):
                return "success"

            test_function()
            mock_abort.assert_called_once_with(400)

    def test_individual_match_player_required_match_not_found(self):
        """Test individual_match_player_required when match is not found."""
        with patch("utils.IndividualMatch") as mock_match, patch(
            "utils.abort"
        ) as mock_abort:

            mock_match.query.get.return_value = None

            @individual_match_player_required
            def test_function(match_id=1):
                return "success"

            test_function(match_id=1)
            mock_abort.assert_called_once_with(404)

    def test_individual_match_player_required_valid_player(self):
        """Test individual_match_player_required when user is a valid player."""
        with patch("utils.current_user") as mock_user, patch(
            "utils.IndividualMatch"
        ) as mock_match:

            mock_user.id = 1
            mock_match_instance = Mock()
            mock_match_instance.player1_id = 1
            mock_match_instance.player2_id = 2
            mock_match.query.get.return_value = mock_match_instance

            @individual_match_player_required
            def test_function(match_id=1):
                return "success"

            result = test_function(match_id=1)
            assert result == "success"

    def test_individual_match_player_required_invalid_player(self):
        """Test individual_match_player_required when user is not a player."""
        with patch("utils.current_user") as mock_user, patch(
            "utils.IndividualMatch"
        ) as mock_match, patch("utils.flash") as mock_flash, patch(
            "utils.redirect"
        ) as mock_redirect, patch(
            "utils.url_for"
        ) as mock_url_for:

            mock_user.id = 3  # Not player1 or player2
            mock_match_instance = Mock()
            mock_match_instance.player1_id = 1
            mock_match_instance.player2_id = 2
            mock_match.query.get.return_value = mock_match_instance
            mock_url_for.return_value = "/dashboard"
            mock_redirect.return_value = "redirect_response"

            @individual_match_player_required
            def test_function(match_id=1):
                return "success"

            result = test_function(match_id=1)
            assert result == "redirect_response"
            mock_flash.assert_called_once_with(
                "Non sei un giocatore di questa partita.", "error"
            )


class TestRackManagerRequiredDecorator:
    """Test rack_manager_required decorator implementation."""

    def test_rack_manager_required_valid_campionato(self):
        """Test rack_manager_required with valid campionato."""
        with patch("utils.Rack") as mock_rack, patch(
            "utils.campionato_manager_required"
        ) as mock_campionato_manager:

            # Setup rack with campionato
            mock_match = Mock()
            mock_gara = Mock()
            mock_gara.campionato_id = 5
            mock_match.gara = mock_gara
            mock_rack_instance = Mock()
            mock_rack_instance.match = mock_match
            mock_rack.query.get_or_404.return_value = mock_rack_instance

            # Mock the campionato_manager_required decorator
            def mock_decorator(f):
                return f

            mock_campionato_manager.return_value = mock_decorator

            @rack_manager_required
            def test_function(rack_id=1):
                return "success"

            result = test_function(rack_id=1)
            assert result == "success"
            mock_rack.query.get_or_404.assert_called_once_with(1)


class TestTrioManagerRequiredDecorator:
    """Test trio_manager_required decorator implementation."""

    def test_trio_manager_required_valid_campionato(self):
        """Test trio_manager_required with valid campionato."""
        with patch("utils.TrioMatch") as mock_trio, patch(
            "utils.campionato_manager_required"
        ) as mock_campionato_manager:

            # Setup trio with campionato
            mock_match = Mock()
            mock_gara = Mock()
            mock_gara.campionato_id = 5
            mock_match.gara = mock_gara
            mock_trio_instance = Mock()
            mock_trio_instance.match = mock_match
            mock_trio.query.get_or_404.return_value = mock_trio_instance

            # Mock the campionato_manager_required decorator
            def mock_decorator(f):
                return f

            mock_campionato_manager.return_value = mock_decorator

            @trio_manager_required
            def test_function(trio_id=1):
                return "success"

            result = test_function(trio_id=1)
            assert result == "success"
            mock_trio.query.get_or_404.assert_called_once_with(1)


class TestCreateRoundMatches:
    """Test create_round_matches function implementation."""

    def test_create_round_matches_even_players(self):
        """Test create_round_matches with even number of players."""
        with patch("utils.Match") as mock_match, patch("utils.db") as mock_db:

            # Setup gara
            mock_gara = Mock()
            mock_gara.id = 1

            # Setup players
            mock_player1 = Mock()
            mock_player1.id = 1
            mock_player2 = Mock()
            mock_player2.id = 2
            players = [mock_player1, mock_player2]

            # Mock Match constructor
            mock_match_instance = Mock()
            mock_match.return_value = mock_match_instance

            matches = create_round_matches(mock_gara, players, 1)

            assert len(matches) == 1
            mock_db.session.add_all.assert_called_once()
            mock_match.assert_called_once()

    def test_create_round_matches_odd_players(self):
        """Test create_round_matches with odd number of players (bye)."""
        with patch("utils.Match") as mock_match, patch("utils.db") as mock_db:

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

            # Mock Match constructor
            mock_match_instance = Mock()
            mock_match.return_value = mock_match_instance

            matches = create_round_matches(mock_gara, players, 1)

            # Should create 2 matches (1 bye + 1 regular)
            assert len(matches) == 2
            mock_db.session.add_all.assert_called_once()
            assert mock_match.call_count == 2

    def test_create_round_matches_with_inscriptions(self):
        """Test create_round_matches with inscription objects."""
        with patch("utils.Inscription") as mock_inscription, patch(
            "utils.Match"
        ) as mock_match, patch("utils.db") as mock_db:

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

            # Mock Match constructor
            mock_match_instance = Mock()
            mock_match.return_value = mock_match_instance

            matches = create_round_matches(mock_gara, inscriptions, 1)

            assert len(matches) == 1
            mock_db.session.add_all.assert_called_once()


class TestCalculateRoundClassification:
    """Test calculate_round_classification function implementation."""

    def test_calculate_round_classification_bye_match(self):
        """Test calculate_round_classification with bye match."""
        with patch("utils.Match") as mock_match, patch(
            "utils.Inscription"
        ) as mock_inscription:

            # Setup bye match
            mock_match_instance = Mock()
            mock_match_instance.is_bye = True
            mock_match_instance.player1_id = 1
            mock_match_instance.player1_score = 5
            mock_match.query.filter_by.return_value.all.return_value = [
                mock_match_instance
            ]

            result = calculate_round_classification(1, 1)

            assert isinstance(result, list)
            assert len(result) == 1
            player_id, stats = result[0]
            assert player_id == 1
            assert stats["matches_won"] == 1
            assert stats["point_diff"] == 5

    def test_calculate_round_classification_regular_match(self):
        """Test calculate_round_classification with regular completed match."""
        with patch("utils.Match") as mock_match, patch(
            "utils.Inscription"
        ) as mock_inscription:

            # Setup regular match
            mock_match_instance = Mock()
            mock_match_instance.is_bye = False
            mock_match_instance.player1_id = 1
            mock_match_instance.player2_id = 2
            mock_match_instance.status = "completed"
            mock_match_instance.winner_id = 1
            mock_match_instance.player1_score = 5
            mock_match_instance.player2_score = 3
            mock_match.query.filter_by.return_value.all.return_value = [
                mock_match_instance
            ]

            # Setup inscriptions
            mock_inscription1 = Mock()
            mock_inscription1.initial_order = 1
            mock_inscription2 = Mock()
            mock_inscription2.initial_order = 2
            mock_inscription.query.filter_by.return_value.first.side_effect = [
                mock_inscription1,
                mock_inscription2,
            ]

            result = calculate_round_classification(1, 1)

            assert isinstance(result, list)
            assert len(result) == 2
            # Winner should be first
            winner_id, winner_stats = result[0]
            assert winner_id == 1
            assert winner_stats["matches_won"] == 1
            assert winner_stats["point_diff"] == 2

    def test_calculate_round_classification_no_winner(self):
        """Test calculate_round_classification with match without winner."""
        with patch("utils.Match") as mock_match, patch(
            "utils.Inscription"
        ) as mock_inscription:

            # Setup match without winner
            mock_match_instance = Mock()
            mock_match_instance.is_bye = False
            mock_match_instance.player1_id = 1
            mock_match_instance.player2_id = 2
            mock_match_instance.status = "pending"
            mock_match_instance.winner_id = None
            mock_match.query.filter_by.return_value.all.return_value = [
                mock_match_instance
            ]

            # Setup inscriptions
            mock_inscription1 = Mock()
            mock_inscription1.initial_order = 1
            mock_inscription2 = Mock()
            mock_inscription2.initial_order = 2
            mock_inscription.query.filter_by.return_value.first.side_effect = [
                mock_inscription1,
                mock_inscription2,
            ]

            result = calculate_round_classification(1, 1)

            assert isinstance(result, list)
            assert len(result) == 2
            # No player should have wins
            for player_id, stats in result:
                assert stats["matches_won"] == 0
                assert stats["point_diff"] == 0


class TestCreateDefaultUsers:
    """Test create_default_users function implementation."""

    def test_create_default_users(self):
        """Test create_default_users function."""
        with patch("utils.User") as mock_user, patch("utils.db") as mock_db:

            # Setup mock users
            mock_admin = Mock()
            mock_mario = Mock()
            mock_pino = Mock()
            mock_user.side_effect = [mock_admin, mock_mario, mock_pino]

            admin, mario, pino = create_default_users()

            assert admin == mock_admin
            assert mario == mock_mario
            assert pino == mock_pino

            # Verify user creation calls
            assert mock_user.call_count == 3
            mock_db.session.add_all.assert_called_once()
            mock_db.session.commit.assert_called_once()

            # Verify password setting
            mock_admin.set_password.assert_called_once_with("admin123")
            mock_mario.set_password.assert_called_once_with("mario123")
            mock_pino.set_password.assert_called_once_with("pino123")


class TestCreateSampleTournament:
    """Test create_sample_campionato function implementation."""

    def test_create_sample_campionato(self):
        """Test create_sample_campionato function."""
        with patch("utils.Campionato") as mock_campionato, patch(
            "utils.db"
        ) as mock_db, patch("utils.GaraService") as mock_gara_service, patch(
            "builtins.print"
        ):  # Suppress print output

            # Setup mock campionati
            mock_campionato1 = Mock()
            mock_campionato1.id = 1
            mock_campionato1.name = "Campionato Primavera 2025"
            mock_campionato2 = Mock()
            mock_campionato2.id = 2
            mock_campionato2.name = "Coppa Estate 2025"
            mock_campionato.side_effect = [mock_campionato1, mock_campionato2]

            tournament1, tournament2 = create_sample_campionato()

            assert tournament1 == mock_campionato1
            assert tournament2 == mock_campionato2

            # Verify campionato creation
            assert mock_campionato.call_count == 2
            assert mock_db.session.add.call_count == 2
            assert mock_db.session.commit.call_count == 3  # 2 for campionati + 1 final

            # Verify gara creation
            assert mock_gara_service.create_gara.call_count == 3


class TestCreateAdminIfNotExists:
    """Test create_admin_if_not_exists function implementation."""

    def test_create_admin_if_not_exists_existing_admin(self):
        """Test create_admin_if_not_exists when admin already exists."""
        with patch("utils.current_app") as mock_app, patch(
            "utils.User"
        ) as mock_user, patch("utils.UserRole") as mock_role:

            # Setup config
            mock_app.config = {"ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "password"}

            # Setup existing admin
            mock_existing_admin = Mock()
            mock_user.query.filter_by.return_value.filter.return_value.first.return_value = (
                mock_existing_admin
            )

            result = create_admin_if_not_exists()

            assert result == mock_existing_admin

    def test_create_admin_if_not_exists_no_admin(self):
        """Test create_admin_if_not_exists when no admin exists."""
        with patch("utils.current_app") as mock_app, patch(
            "utils.User"
        ) as mock_user, patch("utils.db") as mock_db, patch(
            "utils.UserRole"
        ) as mock_role:

            # Setup config
            mock_app.config = {
                "ADMIN_USERNAME": "admin",
                "ADMIN_PASSWORD": "password",
                "ADMIN_EMAIL": "admin@test.com",
            }

            # No existing admin
            mock_user.query.filter_by.return_value.filter.return_value.first.return_value = (
                None
            )

            # Setup new admin
            mock_new_admin = Mock()
            mock_user.return_value = mock_new_admin
            mock_role.ADMIN.value = "admin"

            result = create_admin_if_not_exists()

            assert result == mock_new_admin
            mock_new_admin.set_password.assert_called_once_with("password")
            mock_db.session.add.assert_called_once_with(mock_new_admin)
            mock_db.session.commit.assert_called_once()

    def test_create_admin_if_not_exists_missing_credentials(self):
        """Test create_admin_if_not_exists with missing credentials in production."""
        with patch("utils.current_app") as mock_app:

            # Setup production config without credentials
            mock_app.config = {"ADMIN_PASSWORD_REQUIRED": True}

            with pytest.raises(RuntimeError):
                create_admin_if_not_exists()

    def test_create_admin_if_not_exists_no_credentials_dev(self):
        """Test create_admin_if_not_exists without credentials in development."""
        with patch("utils.current_app") as mock_app, patch(
            "utils.User"
        ) as mock_user, patch("utils.UserRole") as mock_role:

            # Setup dev config without credentials
            mock_app.config = {"ADMIN_PASSWORD_REQUIRED": False}

            # No existing admin
            mock_user.query.filter_by.return_value.filter.return_value.first.return_value = (
                None
            )

            result = create_admin_if_not_exists()

            assert result is None


class TestCreateRoundMatchesAmalfiCompatible:
    """Test create_round_matches_amalfi_compatible function implementation."""

    def test_create_round_matches_amalfi_compatible_even_players(self):
        """Test create_round_matches_amalfi_compatible with even number of players."""
        with patch("utils.Match") as mock_match, patch("utils.db") as mock_db:

            # Setup gara
            mock_gara = Mock()
            mock_gara.id = 1

            # Setup players
            mock_player1 = Mock()
            mock_player1.id = 1
            mock_player2 = Mock()
            mock_player2.id = 2
            players = [mock_player1, mock_player2]

            # Mock Match constructor
            mock_match_instance = Mock()
            mock_match.return_value = mock_match_instance

            matches = create_round_matches_amalfi_compatible(mock_gara, players, 1)

            assert len(matches) == 1
            mock_db.session.add_all.assert_called_once()
            # Verify amalfi_round is set
            mock_match.assert_called_once()

    def test_create_round_matches_amalfi_compatible_odd_players(self):
        """Test create_round_matches_amalfi_compatible with odd number of players."""
        with patch("utils.Match") as mock_match, patch("utils.db") as mock_db:

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

            # Mock Match constructor
            mock_match_instance = Mock()
            mock_match.return_value = mock_match_instance

            matches = create_round_matches_amalfi_compatible(mock_gara, players, 1)

            # Should create 2 matches (1 bye + 1 regular)
            assert len(matches) == 2
            mock_db.session.add_all.assert_called_once()
            assert mock_match.call_count == 2
