"""
Test module for models/campionato/services.py
"""

import pytest
from unittest.mock import Mock, patch
from models.campionato.services import TournamentService, compute_campionato_status
from models.campionato.models import Campionato
from models.user.role_enum import UserRole
from models.status_enum import TournamentStatus, GaraStatus


class TestTournamentService:
    """Test cases for TournamentService class."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.campionato_service = TournamentService()

    def test_create_campionato(self):
        """Test creating a campionato successfully."""
        with patch("models.campionato.services.db") as mock_db:
            mock_campionato = Mock()
            mock_campionato.id = 1

            # Mock the Campionato constructor
            with patch(
                "models.campionato.services.Campionato", return_value=mock_campionato
            ) as mock_campionato_class:
                result = self.campionato_service.create_campionato(
                    name="Test Campionato", description="Test Description"
                )

                # Verify the campionato was created with correct parameters
                mock_campionato_class.assert_called_once_with(
                    name="Test Campionato", description="Test Description"
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_campionato)
                mock_db.session.flush.assert_called_once()

                # Verify the result
                assert result == mock_campionato

    def test_create_campionato_with_director_admin_creator(self):
        """Test creating a campionato with admin creator
        (should not be assigned as director)."""
        mock_user = Mock()
        mock_user.is_director = True
        mock_user.is_admin = True

        mock_campionato = Mock()
        mock_campionato.id = 1

        with patch("models.campionato.services.db") as mock_db:
            # Mock db.session.get to return the user
            mock_db.session.get.return_value = mock_user

            # Mock the Campionato constructor
            with patch(
                "models.campionato.services.Campionato", return_value=mock_campionato
            ) as mock_campionato_class:
                result = self.campionato_service.create_campionato_with_director(
                    name="Test Campionato", creator_user_id=1
                )

                # Verify the campionato was created
                mock_campionato_class.assert_called_once()

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_campionato)
                mock_db.session.flush.assert_called_once()

                # Verify no director assignment was made
                assert (
                    mock_db.session.add.call_count == 1
                )  # Only campionato added, no director assignment

                # Verify the result
                assert result == mock_campionato

    def test_create_campionato_with_director_director_creator(self):
        """Test creating a campionato with director creator
        (should be assigned as director)."""
        mock_user = Mock()
        mock_user.is_director = True
        mock_user.is_admin = False
        mock_user.role = UserRole.DIRECTOR.value

        mock_campionato = Mock()
        mock_campionato.id = 1

        mock_assignment = Mock()

        with patch("models.campionato.services.db") as mock_db:
            # Mock db.session.get to return the user
            mock_db.session.get.return_value = mock_user

            # Mock the Campionato constructor
            with patch(
                "models.campionato.services.Campionato", return_value=mock_campionato
            ) as mock_campionato_class:
                # Mock the TournamentDirector constructor from user.models
                with patch(
                    "models.user.models.TournamentDirector",
                    return_value=mock_assignment,
                ) as mock_assignment_class:
                    result = self.campionato_service.create_campionato_with_director(
                        name="Test Campionato", creator_user_id=1
                    )

                    # Verify the campionato was created
                    mock_campionato_class.assert_called_once()

                    # Verify the director assignment was created
                    mock_assignment_class.assert_called_once_with(
                        user_id=1, campionato_id=1, assigned_by_id=1
                    )

                    # Verify database operations
                    assert (
                        mock_db.session.add.call_count == 2
                    )  # Campionato and assignment added
                    mock_db.session.flush.assert_called_once()

                    # Verify the result
                    assert result == mock_campionato

    def test_update_campionato_success(self):
        """Test updating a campionato successfully."""
        mock_campionato = Mock()
        mock_campionato.can_be_modified.return_value = True

        with patch("models.campionato.services.db") as mock_db:
            # Mock db.session.get to return the campionato
            mock_db.session.get.return_value = mock_campionato

            result = self.campionato_service.update_campionato(
                1, name="Updated Name", description="Updated Description"
            )

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Campionato, 1)

            # Verify the campionato was updated
            assert mock_campionato.name == "Updated Name"
            assert mock_campionato.description == "Updated Description"
            assert mock_campionato.updated_at is not None

            # Verify the result
            assert result == mock_campionato

    def test_update_campionato_not_found(self):
        """Test updating a campionato when not found."""
        with patch("models.campionato.services.db") as mock_db:
            # Mock db.session.get to return None
            mock_db.session.get.return_value = None

            # Should raise ValueError
            with pytest.raises(ValueError, match="Campionato not found"):
                self.campionato_service.update_campionato(1, name="Updated Name")

    def test_toggle_active_status(self):
        """Test toggling campionato active status."""
        mock_campionato = Mock()
        mock_campionato.is_active = True

        with patch("models.campionato.services.db") as mock_db:
            # Mock db.session.get to return the campionato
            mock_db.session.get.return_value = mock_campionato

            result = self.campionato_service.toggle_active_status(1)

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Campionato, 1)

            # Verify the status was toggled
            assert mock_campionato.is_active is False
            assert mock_campionato.updated_at is not None

            # Verify the result
            assert result == mock_campionato

    def test_add_director_success(self):
        """Test adding a director to a campionato successfully."""
        mock_user = Mock()
        mock_user.role = UserRole.DIRECTOR.value

        mock_existing = None  # No existing assignment

        mock_assignment = Mock()

        with patch("models.campionato.services.db") as mock_db:
            # Mock db.session.get to return the user
            mock_db.session.get.return_value = mock_user

            # Mock query to return no existing assignment
            mock_query = Mock()
            mock_query.first.return_value = mock_existing

            # Mock the TournamentDirector class and its query methods
            with patch("models.user.models.TournamentDirector") as mock_director_class:
                mock_director_class.query.filter_by.return_value = mock_query
                mock_director_class.return_value = mock_assignment

                result = self.campionato_service.add_director(1, 2, 3)

                # Verify the assignment was created
                mock_director_class.assert_called_once_with(
                    user_id=2, campionato_id=1, assigned_by_id=3
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_assignment)

                # Verify the result
                assert result is True

    def test_add_director_admin_user(self):
        """Test adding an admin as director (should fail)."""
        mock_user = Mock()
        mock_user.role = UserRole.ADMIN.value

        with patch("models.campionato.services.db") as mock_db:
            # Mock db.session.get to return the user
            mock_db.session.get.return_value = mock_user

            # Should raise ValueError
            with pytest.raises(
                ValueError, match="Gli admin non vanno assegnati come direttori"
            ):
                self.campionato_service.add_director(1, 2, 3)

    def test_remove_director_success(self):
        """Test removing a director from a campionato successfully."""
        mock_assignment = Mock()

        with patch("models.campionato.services.db") as mock_db:
            # Mock query to return existing assignment
            mock_query = Mock()
            mock_query.first.return_value = mock_assignment
            with patch("models.user.models.TournamentDirector") as mock_director_class:
                mock_director_class.query.filter_by.return_value = mock_query

                result = self.campionato_service.remove_director(1, 2)

                # Verify database operations
                mock_db.session.delete.assert_called_once_with(mock_assignment)

                # Verify the result
                assert result is True

    def test_remove_director_not_found(self):
        """Test removing a director when not found."""
        mock_existing = None  # No existing assignment

        with patch("models.campionato.services.db") as mock_db:
            # Mock query to return no existing assignment
            mock_query = Mock()
            mock_query.first.return_value = mock_existing
            with patch("models.user.models.TournamentDirector") as mock_director_class:
                mock_director_class.query.filter_by.return_value = mock_query

                result = self.campionato_service.remove_director(1, 2)

                # Verify no deletion occurred
                mock_db.session.delete.assert_not_called()

                # Verify the result
                assert result is False

    def test_get_active_campionatos(self):
        """Test getting active campionati."""
        mock_campionatos = [Mock(), Mock(), Mock()]

        with patch("models.campionato.services.Campionato") as mock_campionato_class:
            # Mock the query chain
            mock_filtered_query = Mock()
            mock_filtered_query.all.return_value = mock_campionatos

            mock_campionato_class.get_active_campionatos.return_value = (
                mock_filtered_query
            )

            result = self.campionato_service.get_active_campionatos()

            # Verify the query was called correctly
            mock_campionato_class.get_active_campionatos.assert_called_once()
            mock_filtered_query.all.assert_called_once()

            # Verify the result
            assert result == mock_campionatos

    def test_get_campionato_detail_data(self):
        """Test getting campionato detail data."""
        mock_campionato = Mock()
        mock_campionato.directors_association = []

        mock_garas = [Mock(), Mock()]
        mock_directors = [Mock(), Mock()]

        with patch("models.campionato.services.db") as mock_db:
            # Mock db.session.get to return the campionato
            mock_db.session.get.return_value = mock_campionato

            # Mock Gara query from competition.models
            with patch("models.competition.models.Gara") as mock_gara_class:
                mock_gara_filtered_query = Mock()
                mock_gara_filtered_query.order_by().all.return_value = mock_garas

                mock_gara_class.query.filter_by.return_value = (
                    mock_gara_filtered_query
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

                    result = self.campionato_service.get_campionato_detail_data(1)

                    # Verify database operation
                    mock_db.session.get.assert_called_once_with(Campionato, 1)

                    # Verify the result
                    assert result["campionato"] == mock_campionato
                    assert result["gare"] == mock_garas
                    assert result["candidate_directors"] == mock_directors

    def test_calculate_campionato_status(self):
        """Test calculating campionato status."""
        mock_campionato = Mock()
        mock_campionato.gare = []  # Empty list for this test

        with patch("models.campionato.services.db") as mock_db:
            # Mock db.session.get to return the campionato
            mock_db.session.get.return_value = mock_campionato

            result = self.campionato_service.calculate_campionato_status(1)

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Campionato, 1)

            # Verify compute_campionato_status was called
            assert result is not None


class TestComputeTournamentStatus:
    """Test cases for compute_campionato_status function."""

    def test_compute_campionato_status_no_garas(self):
        """Test computing status for campionato with no provas."""
        mock_campionato = Mock()
        mock_campionato.gare = []

        result = compute_campionato_status(mock_campionato)

        # Should be SETUP when no provas
        assert result == TournamentStatus.SETUP.value

    def test_compute_campionato_status_playing_gara(self):
        """Test computing status when at least one gara is playing."""
        mock_gara1 = Mock()
        mock_gara1.status = GaraStatus.PLAYING.value

        mock_gara2 = Mock()
        mock_gara2.status = GaraStatus.SETUP.value

        mock_campionato = Mock()
        mock_campionato.gare = [mock_gara1, mock_gara2]

        result = compute_campionato_status(mock_campionato)

        # Should be IN_PROGRESS when at least one gara is playing
        assert result == TournamentStatus.IN_PROGRESS.value

    def test_compute_campionato_status_inscription_gara(self):
        """Test computing status when at least one gara is in inscription."""
        mock_gara1 = Mock()
        mock_gara1.status = GaraStatus.INSCRIPTION.value

        mock_gara2 = Mock()
        mock_gara2.status = GaraStatus.SETUP.value

        mock_campionato = Mock()
        mock_campionato.gare = [mock_gara1, mock_gara2]

        result = compute_campionato_status(mock_campionato)

        # Should be REGISTRATION_OPEN when at least one gara is in inscription
        assert result == TournamentStatus.REGISTRATION_OPEN.value

    def test_compute_campionato_status_all_completed_garas(self):
        """Test computing status when all provas are completed."""
        mock_gara1 = Mock()
        mock_gara1.status = GaraStatus.COMPLETED.value

        mock_gara2 = Mock()
        mock_gara2.status = GaraStatus.COMPLETED.value

        mock_campionato = Mock()
        mock_campionato.gare = [mock_gara1, mock_gara2]

        result = compute_campionato_status(mock_campionato)

        # Should be COMPLETED when all provas are completed
        assert result == TournamentStatus.COMPLETED.value

    def test_compute_campionato_status_default_setup(self):
        """Test computing status for default setup case."""
        mock_gara1 = Mock()
        mock_gara1.status = GaraStatus.SETUP.value

        mock_gara2 = Mock()
        mock_gara2.status = GaraStatus.SETUP.value

        mock_campionato = Mock()
        mock_campionato.gare = [mock_gara1, mock_gara2]

        result = compute_campionato_status(mock_campionato)

        # Should be SETUP for default case
        assert result == TournamentStatus.SETUP.value
