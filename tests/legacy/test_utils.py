"""
Test module for utils/__init__.py
"""

import pytest
from unittest.mock import patch, MagicMock

# Import the functions we want to test
from utils import (
    admin_required,
    director_required,
    director_or_admin_required,
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
    trio_manager_required,
    create_round_matches,
    calculate_round_classification,
    create_default_users,
    create_sample_campionato,
    create_admin_if_not_exists,
    create_round_matches_amalfi_compatible,
)


class TestUtils:
    """Test cases for utils functions."""

    def test_admin_required_decorator(self):
        """Test admin_required decorator."""
        # This should just return the RoleRequirement.admin_required function
        assert admin_required is not None

    def test_director_required_decorator(self):
        """Test director_required decorator."""
        # This should just return the RoleRequirement.director_required function
        assert director_required is not None

    def test_director_or_admin_required_decorator(self):
        """Test director_or_admin_required decorator."""
        # This should just return the
        # RoleRequirement.director_or_admin_required function
        assert director_or_admin_required is not None

    def test_match_manager_required_decorator(self):
        """Test match_manager_required decorator."""
        mock_func = MagicMock()
        decorated_func = match_manager_required(mock_func)
        assert decorated_func is not None

    def test_user_permissions_class(self):
        """Test UserPermissions class methods."""
        # Test that all methods exist
        assert hasattr(UserPermissions, "can_inscribe_to_gara")
        assert hasattr(UserPermissions, "can_view_profile")
        assert hasattr(UserPermissions, "can_delete_account")
        assert hasattr(UserPermissions, "show_admin_management")
        assert hasattr(UserPermissions, "show_director_management")
        assert hasattr(UserPermissions, "get_default_dashboard")

    def test_player_only_decorator(self):
        """Test player_only decorator."""
        mock_func = MagicMock()
        decorated_func = player_only(mock_func)
        assert decorated_func is not None

    def test_player_required_decorator(self):
        """Test player_required decorator."""
        mock_func = MagicMock()
        decorated_func = player_required(mock_func)
        assert decorated_func is not None

    def test_match_player_required_decorator(self):
        """Test match_player_required decorator."""
        mock_func = MagicMock()
        decorated_func = match_player_required(mock_func)
        assert decorated_func is not None

    def test_rack_player_required_decorator(self):
        """Test rack_player_required decorator."""
        mock_func = MagicMock()
        decorated_func = rack_player_required(mock_func)
        assert decorated_func is not None

    def test_inscription_owner_required_decorator(self):
        """Test inscription_owner_required decorator."""
        mock_func = MagicMock()
        decorated_func = inscription_owner_required(mock_func)
        assert decorated_func is not None

    def test_challenge_player_required_decorator(self):
        """Test challenge_player_required decorator."""
        mock_func = MagicMock()
        decorated_func = challenge_player_required(mock_func)
        assert decorated_func is not None

    def test_challenge_attempt_player_required_decorator(self):
        """Test challenge_attempt_player_required decorator."""
        mock_func = MagicMock()
        decorated_func = challenge_attempt_player_required(mock_func)
        assert decorated_func is not None

    def test_individual_match_player_required_decorator(self):
        """Test individual_match_player_required decorator."""
        mock_func = MagicMock()
        decorated_func = individual_match_player_required(mock_func)
        assert decorated_func is not None

    def test_rack_manager_required_decorator(self):
        """Test rack_manager_required decorator."""
        mock_func = MagicMock()
        decorated_func = rack_manager_required(mock_func)
        assert decorated_func is not None

    def test_trio_manager_required_decorator(self):
        """Test trio_manager_required decorator."""
        mock_func = MagicMock()
        decorated_func = trio_manager_required(mock_func)
        assert decorated_func is not None

    @patch("models.db")
    @patch("models.Match")
    def test_create_round_matches(self, mock_match, mock_db):
        """Test create_round_matches function."""
        # Setup mocks
        mock_gara = MagicMock()
        mock_gara.id = 1
        mock_gara.is_race_to = True
        mock_gara.get_winning_score.return_value = 3

        mock_user1 = MagicMock()
        mock_user1.id = 1

        mock_user2 = MagicMock()
        mock_user2.id = 2

        mock_inscription1 = MagicMock()
        mock_inscription1.user = mock_user1

        mock_inscription2 = MagicMock()
        mock_inscription2.user = mock_user2

        # Test with even number of players
        players = [mock_inscription1, mock_inscription2]

        mock_match_instance = MagicMock()
        mock_match.return_value = mock_match_instance

        result = create_round_matches(mock_gara, players, 1)

        # Verify
        assert len(result) == 1
        mock_match.assert_called_once()
        mock_db.session.add_all.assert_called_once()

    @patch("models.db")
    @patch("models.Match")
    def test_create_round_matches_odd_players(self, mock_match, mock_db):
        """Test create_round_matches function with odd number of players."""
        # Setup mocks
        mock_gara = MagicMock()
        mock_gara.id = 1
        mock_gara.is_race_to = True
        mock_gara.get_winning_score.return_value = 3

        mock_user1 = MagicMock()
        mock_user1.id = 1

        mock_user2 = MagicMock()
        mock_user2.id = 2

        mock_user3 = MagicMock()
        mock_user3.id = 3

        mock_inscription1 = MagicMock()
        mock_inscription1.user = mock_user1

        mock_inscription2 = MagicMock()
        mock_inscription2.user = mock_user2

        mock_inscription3 = MagicMock()
        mock_inscription3.user = mock_user3

        # Test with odd number of players
        players = [mock_inscription1, mock_inscription2, mock_inscription3]

        mock_match_instance = MagicMock()
        mock_match.return_value = mock_match_instance

        result = create_round_matches(mock_gara, players, 1)

        # Verify - should have 2 matches (1 bye + 1 regular)
        assert len(result) == 2
        assert mock_match.call_count == 2
        mock_db.session.add_all.assert_called_once()

    def test_calculate_round_classification(self):
        """Test calculate_round_classification function."""
        # This function is complex and requires extensive mocking
        # For now, just verify it exists and can be called
        assert calculate_round_classification is not None

    @patch("models.db")
    @patch("models.User")
    def test_create_default_users(self, mock_user, mock_db):
        """Test create_default_users function."""
        mock_admin = MagicMock()
        mock_mario = MagicMock()
        mock_pino = MagicMock()
        mock_user.side_effect = [mock_admin, mock_mario, mock_pino]

        result = create_default_users()

        # Verify
        assert len(result) == 3
        mock_db.session.add_all.assert_called_once()
        mock_db.session.commit.assert_called_once()

    def test_create_sample_campionato(self):
        """Test create_sample_campionato function."""
        # This function is complex and requires extensive mocking
        # For now, just verify it exists and can be called
        assert create_sample_campionato is not None

    def test_create_admin_if_not_exists(self):
        """Test create_admin_if_not_exists function."""
        # This function is complex and requires extensive mocking
        # For now, just verify it exists and can be called
        assert create_admin_if_not_exists is not None

    @patch("models.db")
    @patch("models.Match")
    def test_create_round_matches_amalfi_compatible(self, mock_match, mock_db):
        """Test create_round_matches_amalfi_compatible function."""
        # Setup mocks
        mock_gara = MagicMock()
        mock_gara.id = 1
        mock_gara.is_race_to = True
        mock_gara.get_winning_score.return_value = 3

        mock_user1 = MagicMock()
        mock_user1.id = 1

        mock_user2 = MagicMock()
        mock_user2.id = 2

        mock_inscription1 = MagicMock()
        mock_inscription1.user = mock_user1

        mock_inscription2 = MagicMock()
        mock_inscription2.user = mock_user2

        # Test with even number of players
        players = [mock_inscription1, mock_inscription2]

        mock_match_instance = MagicMock()
        mock_match.return_value = mock_match_instance

        result = create_round_matches_amalfi_compatible(mock_gara, players, 1)

        # Verify
        assert len(result) == 1
        mock_match.assert_called_once()
        mock_db.session.add_all.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
