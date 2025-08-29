"""
Test module for models/tournament/services.py
"""

import pytest
from unittest.mock import Mock, patch
from models.tournament.services import TournamentService, compute_tournament_status
from models.tournament.models import Tournament
from models.user.role_enum import UserRole
from models.status_enum import TournamentStatus, ProvaStatus


class TestTournamentService:
    """Test cases for TournamentService class."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.tournament_service = TournamentService()

    def test_create_tournament(self):
        """Test creating a tournament successfully."""
        with patch("models.tournament.services.db") as mock_db:
            mock_tournament = Mock()
            mock_tournament.id = 1

            # Mock the Tournament constructor
            with patch(
                "models.tournament.services.Tournament", return_value=mock_tournament
            ) as mock_tournament_class:
                result = self.tournament_service.create_tournament(
                    name="Test Tournament", description="Test Description"
                )

                # Verify the tournament was created with correct parameters
                mock_tournament_class.assert_called_once_with(
                    name="Test Tournament", description="Test Description"
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_tournament)
                mock_db.session.flush.assert_called_once()

                # Verify the result
                assert result == mock_tournament

    def test_create_tournament_with_director_admin_creator(self):
        """Test creating a tournament with admin creator
        (should not be assigned as director)."""
        mock_user = Mock()
        mock_user.is_director = True
        mock_user.is_admin = True

        mock_tournament = Mock()
        mock_tournament.id = 1

        with patch("models.tournament.services.db") as mock_db:
            # Mock db.session.get to return the user
            mock_db.session.get.return_value = mock_user

            # Mock the Tournament constructor
            with patch(
                "models.tournament.services.Tournament", return_value=mock_tournament
            ) as mock_tournament_class:
                result = self.tournament_service.create_tournament_with_director(
                    name="Test Tournament", creator_user_id=1
                )

                # Verify the tournament was created
                mock_tournament_class.assert_called_once()

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_tournament)
                mock_db.session.flush.assert_called_once()

                # Verify no director assignment was made
                assert (
                    mock_db.session.add.call_count == 1
                )  # Only tournament added, no director assignment

                # Verify the result
                assert result == mock_tournament

    def test_create_tournament_with_director_director_creator(self):
        """Test creating a tournament with director creator
        (should be assigned as director)."""
        mock_user = Mock()
        mock_user.is_director = True
        mock_user.is_admin = False
        mock_user.role = UserRole.DIRECTOR.value

        mock_tournament = Mock()
        mock_tournament.id = 1

        mock_assignment = Mock()

        with patch("models.tournament.services.db") as mock_db:
            # Mock db.session.get to return the user
            mock_db.session.get.return_value = mock_user

            # Mock the Tournament constructor
            with patch(
                "models.tournament.services.Tournament", return_value=mock_tournament
            ) as mock_tournament_class:
                # Mock the TournamentDirector constructor from user.models
                with patch(
                    "models.user.models.TournamentDirector",
                    return_value=mock_assignment,
                ) as mock_assignment_class:
                    result = self.tournament_service.create_tournament_with_director(
                        name="Test Tournament", creator_user_id=1
                    )

                    # Verify the tournament was created
                    mock_tournament_class.assert_called_once()

                    # Verify the director assignment was created
                    mock_assignment_class.assert_called_once_with(
                        user_id=1, tournament_id=1, assigned_by_id=1
                    )

                    # Verify database operations
                    assert (
                        mock_db.session.add.call_count == 2
                    )  # Tournament and assignment added
                    mock_db.session.flush.assert_called_once()

                    # Verify the result
                    assert result == mock_tournament

    def test_update_tournament_success(self):
        """Test updating a tournament successfully."""
        mock_tournament = Mock()
        mock_tournament.can_be_modified.return_value = True

        with patch("models.tournament.services.db") as mock_db:
            # Mock db.session.get to return the tournament
            mock_db.session.get.return_value = mock_tournament

            result = self.tournament_service.update_tournament(
                1, name="Updated Name", description="Updated Description"
            )

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Tournament, 1)

            # Verify the tournament was updated
            assert mock_tournament.name == "Updated Name"
            assert mock_tournament.description == "Updated Description"
            assert mock_tournament.updated_at is not None

            # Verify the result
            assert result == mock_tournament

    def test_update_tournament_not_found(self):
        """Test updating a tournament when not found."""
        with patch("models.tournament.services.db") as mock_db:
            # Mock db.session.get to return None
            mock_db.session.get.return_value = None

            # Should raise ValueError
            with pytest.raises(ValueError, match="Tournament not found"):
                self.tournament_service.update_tournament(1, name="Updated Name")

    def test_toggle_active_status(self):
        """Test toggling tournament active status."""
        mock_tournament = Mock()
        mock_tournament.is_active = True

        with patch("models.tournament.services.db") as mock_db:
            # Mock db.session.get to return the tournament
            mock_db.session.get.return_value = mock_tournament

            result = self.tournament_service.toggle_active_status(1)

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Tournament, 1)

            # Verify the status was toggled
            assert mock_tournament.is_active is False
            assert mock_tournament.updated_at is not None

            # Verify the result
            assert result == mock_tournament

    def test_add_director_success(self):
        """Test adding a director to a tournament successfully."""
        mock_user = Mock()
        mock_user.role = UserRole.DIRECTOR.value

        mock_existing = None  # No existing assignment

        mock_assignment = Mock()

        with patch("models.tournament.services.db") as mock_db:
            # Mock db.session.get to return the user
            mock_db.session.get.return_value = mock_user

            # Mock query to return no existing assignment
            mock_query = Mock()
            mock_query.first.return_value = mock_existing

            # Mock the TournamentDirector class and its query methods
            with patch("models.user.models.TournamentDirector") as mock_director_class:
                mock_director_class.query.filter_by.return_value = mock_query
                mock_director_class.return_value = mock_assignment

                result = self.tournament_service.add_director(1, 2, 3)

                # Verify the assignment was created
                mock_director_class.assert_called_once_with(
                    user_id=2, tournament_id=1, assigned_by_id=3
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_assignment)

                # Verify the result
                assert result is True

    def test_add_director_admin_user(self):
        """Test adding an admin as director (should fail)."""
        mock_user = Mock()
        mock_user.role = UserRole.ADMIN.value

        with patch("models.tournament.services.db") as mock_db:
            # Mock db.session.get to return the user
            mock_db.session.get.return_value = mock_user

            # Should raise ValueError
            with pytest.raises(
                ValueError, match="Gli admin non vanno assegnati come direttori"
            ):
                self.tournament_service.add_director(1, 2, 3)

    def test_remove_director_success(self):
        """Test removing a director from a tournament successfully."""
        mock_assignment = Mock()

        with patch("models.tournament.services.db") as mock_db:
            # Mock query to return existing assignment
            mock_query = Mock()
            mock_query.first.return_value = mock_assignment
            with patch("models.user.models.TournamentDirector") as mock_director_class:
                mock_director_class.query.filter_by.return_value = mock_query

                result = self.tournament_service.remove_director(1, 2)

                # Verify database operations
                mock_db.session.delete.assert_called_once_with(mock_assignment)

                # Verify the result
                assert result is True

    def test_remove_director_not_found(self):
        """Test removing a director when not found."""
        mock_existing = None  # No existing assignment

        with patch("models.tournament.services.db") as mock_db:
            # Mock query to return no existing assignment
            mock_query = Mock()
            mock_query.first.return_value = mock_existing
            with patch("models.user.models.TournamentDirector") as mock_director_class:
                mock_director_class.query.filter_by.return_value = mock_query

                result = self.tournament_service.remove_director(1, 2)

                # Verify no deletion occurred
                mock_db.session.delete.assert_not_called()

                # Verify the result
                assert result is False

    def test_get_active_tournaments(self):
        """Test getting active tournaments."""
        mock_tournaments = [Mock(), Mock(), Mock()]

        with patch("models.tournament.services.Tournament") as mock_tournament_class:
            # Mock the query chain
            mock_filtered_query = Mock()
            mock_filtered_query.all.return_value = mock_tournaments

            mock_tournament_class.get_active_tournaments.return_value = (
                mock_filtered_query
            )

            result = self.tournament_service.get_active_tournaments()

            # Verify the query was called correctly
            mock_tournament_class.get_active_tournaments.assert_called_once()
            mock_filtered_query.all.assert_called_once()

            # Verify the result
            assert result == mock_tournaments

    def test_get_tournament_detail_data(self):
        """Test getting tournament detail data."""
        mock_tournament = Mock()
        mock_tournament.directors_association = []

        mock_provas = [Mock(), Mock()]
        mock_directors = [Mock(), Mock()]

        with patch("models.tournament.services.db") as mock_db:
            # Mock db.session.get to return the tournament
            mock_db.session.get.return_value = mock_tournament

            # Mock Prova query from competition.models
            with patch("models.competition.models.Prova") as mock_prova_class:
                mock_prova_filtered_query = Mock()
                mock_prova_filtered_query.order_by().all.return_value = mock_provas

                mock_prova_class.query.filter_by.return_value = (
                    mock_prova_filtered_query
                )

                # Mock User query from user.models
                with patch("models.user.models.User") as mock_user_class:
                    # Create the mock chain for User.query.filter_by().filter()
                    # .order_by().all()
                    mock_filter_by_query = Mock()
                    mock_filter_query = Mock()
                    mock_order_by_query = Mock()

                    # Set up the chain of return values
                    mock_user_class.query.filter_by.return_value = mock_filter_by_query
                    mock_filter_by_query.filter.return_value = mock_filter_query
                    mock_filter_query.order_by.return_value = mock_order_by_query
                    mock_order_by_query.all.return_value = mock_directors

                    result = self.tournament_service.get_tournament_detail_data(1)

                    # Verify database operation
                    mock_db.session.get.assert_called_once_with(Tournament, 1)

                    # Verify the result
                    assert result["tournament"] == mock_tournament
                    assert result["provas"] == mock_provas
                    assert result["candidate_directors"] == mock_directors

    def test_calculate_tournament_status(self):
        """Test calculating tournament status."""
        mock_tournament = Mock()
        mock_tournament.provas = []  # Empty list for this test

        with patch("models.tournament.services.db") as mock_db:
            # Mock db.session.get to return the tournament
            mock_db.session.get.return_value = mock_tournament

            result = self.tournament_service.calculate_tournament_status(1)

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Tournament, 1)

            # Verify compute_tournament_status was called
            assert result is not None


class TestComputeTournamentStatus:
    """Test cases for compute_tournament_status function."""

    def test_compute_tournament_status_no_provas(self):
        """Test computing status for tournament with no provas."""
        mock_tournament = Mock()
        mock_tournament.provas = []

        result = compute_tournament_status(mock_tournament)

        # Should be SETUP when no provas
        assert result == TournamentStatus.SETUP.value

    def test_compute_tournament_status_playing_prova(self):
        """Test computing status when at least one prova is playing."""
        mock_prova1 = Mock()
        mock_prova1.status = ProvaStatus.PLAYING.value

        mock_prova2 = Mock()
        mock_prova2.status = ProvaStatus.SETUP.value

        mock_tournament = Mock()
        mock_tournament.provas = [mock_prova1, mock_prova2]

        result = compute_tournament_status(mock_tournament)

        # Should be IN_PROGRESS when at least one prova is playing
        assert result == TournamentStatus.IN_PROGRESS.value

    def test_compute_tournament_status_inscription_prova(self):
        """Test computing status when at least one prova is in inscription."""
        mock_prova1 = Mock()
        mock_prova1.status = ProvaStatus.INSCRIPTION.value

        mock_prova2 = Mock()
        mock_prova2.status = ProvaStatus.SETUP.value

        mock_tournament = Mock()
        mock_tournament.provas = [mock_prova1, mock_prova2]

        result = compute_tournament_status(mock_tournament)

        # Should be REGISTRATION_OPEN when at least one prova is in inscription
        assert result == TournamentStatus.REGISTRATION_OPEN.value

    def test_compute_tournament_status_all_completed_provas(self):
        """Test computing status when all provas are completed."""
        mock_prova1 = Mock()
        mock_prova1.status = ProvaStatus.COMPLETED.value

        mock_prova2 = Mock()
        mock_prova2.status = ProvaStatus.COMPLETED.value

        mock_tournament = Mock()
        mock_tournament.provas = [mock_prova1, mock_prova2]

        result = compute_tournament_status(mock_tournament)

        # Should be COMPLETED when all provas are completed
        assert result == TournamentStatus.COMPLETED.value

    def test_compute_tournament_status_default_setup(self):
        """Test computing status for default setup case."""
        mock_prova1 = Mock()
        mock_prova1.status = ProvaStatus.SETUP.value

        mock_prova2 = Mock()
        mock_prova2.status = ProvaStatus.SETUP.value

        mock_tournament = Mock()
        mock_tournament.provas = [mock_prova1, mock_prova2]

        result = compute_tournament_status(mock_tournament)

        # Should be SETUP for default case
        assert result == TournamentStatus.SETUP.value
