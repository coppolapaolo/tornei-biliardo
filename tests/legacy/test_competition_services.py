"""
Test module for models/competition/services.py
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date
from models.competition.services import (
    ProvaService,
    ProvaStateMachine,
    InscriptionService,
)
from models.competition.models import Prova
from models.status_enum import ProvaStatus
from models.exceptions import InvalidTransitionError


class TestProvaStateMachine:
    """Test cases for ProvaStateMachine class."""

    def test_to_inscription_success(self):
        """Test transitioning prova to inscription state successfully."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.SETUP.value

        with patch("models.competition.services.db") as mock_db:
            result = ProvaStateMachine.to_inscription(mock_prova)

            # Verify the prova status was updated
            assert mock_prova.status == ProvaStatus.INSCRIPTION.value

            # Verify database operations
            mock_db.session.add.assert_called_once_with(mock_prova)
            mock_db.session.commit.assert_called_once()

            # Verify the result
            assert result == mock_prova

    def test_to_inscription_invalid_transition(self):
        """Test transitioning prova to inscription state with invalid current state."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.PLAYING.value  # Already playing

        # Should raise InvalidTransitionError
        with pytest.raises(InvalidTransitionError):
            ProvaStateMachine.to_inscription(mock_prova)

    def test_reopen_setup_success(self):
        """Test transitioning prova back to setup state successfully."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.INSCRIPTION.value

        with patch("models.competition.services.db") as mock_db:
            result = ProvaStateMachine.reopen_setup(mock_prova)

            # Verify the prova status was updated
            assert mock_prova.status == ProvaStatus.SETUP.value

            # Verify database operations
            mock_db.session.add.assert_called_once_with(mock_prova)
            mock_db.session.commit.assert_called_once()

            # Verify the result
            assert result == mock_prova

    def test_start_playing_success(self):
        """Test transitioning prova to playing state successfully."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.INSCRIPTION.value
        mock_prova.inscriptions = [Mock(), Mock()]  # Two inscriptions
        mock_prova.current_round = 0

        with patch("models.competition.services.db") as mock_db:
            result = ProvaStateMachine.start_playing(mock_prova)

            # Verify the prova status was updated
            assert mock_prova.status == ProvaStatus.PLAYING.value

            # Verify the current round was set
            assert mock_prova.current_round == 1

            # Verify database operations
            mock_db.session.add.assert_called_once_with(mock_prova)
            mock_db.session.commit.assert_called_once()

            # Verify the result
            assert result == mock_prova

    def test_start_playing_insufficient_inscriptions(self):
        """Test transitioning prova to playing state with insufficient inscriptions."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.INSCRIPTION.value
        mock_prova.inscriptions = [Mock()]  # Only one inscription

        # Should raise InvalidTransitionError
        with pytest.raises(
            InvalidTransitionError, match="Numero iscritti insufficiente"
        ):
            ProvaStateMachine.start_playing(mock_prova)

    def test_complete_success(self):
        """Test transitioning prova to completed state successfully."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.PLAYING.value

        with patch("models.competition.services.db") as mock_db:
            result = ProvaStateMachine.complete(mock_prova)

            # Verify the prova status was updated
            assert mock_prova.status == ProvaStatus.COMPLETED.value

            # Verify database operations
            mock_db.session.add.assert_called_once_with(mock_prova)
            mock_db.session.commit.assert_called_once()

            # Verify the result
            assert result == mock_prova


class TestProvaService:
    """Test cases for ProvaService class."""

    def test_create_prova_success(self):
        """Test creating a prova successfully."""
        with patch("models.competition.services.db") as mock_db:
            mock_prova = Mock()

            # Mock the Prova constructor
            with patch(
                "models.competition.services.Prova", return_value=mock_prova
            ) as mock_prova_class:
                result = ProvaService.create_prova(
                    number=1,
                    name="Test Prova",
                    date=date(2023, 1, 1),
                    discipline="Test Discipline",
                    distance=50,
                    tournament_id=1,
                )

                # Verify the prova was created with correct parameters
                mock_prova_class.assert_called_once_with(
                    number=1,
                    name="Test Prova",
                    date=date(2023, 1, 1),
                    discipline="Test Discipline",
                    distance=50,
                    tournament_id=1,
                    director_id=None,
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_prova)
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result == mock_prova

    def test_create_prova_without_tournament_or_director(self):
        """Test creating a prova without tournament_id or director_id."""
        # Should raise ValueError
        with pytest.raises(ValueError, match="Una Prova deve avere"):
            ProvaService.create_prova(
                number=1,
                name="Test Prova",
                date=date(2023, 1, 1),
                discipline="Test Discipline",
                distance=50,
            )

    def test_get_prova_by_id_success(self):
        """Test getting a prova by ID successfully."""
        mock_prova = Mock()

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_prova

            result = ProvaService.get_prova_by_id(1)

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Prova, 1)

            # Verify the result
            assert result == mock_prova

    def test_get_prova_by_id_not_found(self):
        """Test getting a prova by ID when not found."""
        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = None

            result = ProvaService.get_prova_by_id(1)

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Prova, 1)

            # Verify the result
            assert result is None

    def test_update_prova_success(self):
        """Test updating a prova successfully."""
        mock_prova = Mock()
        mock_prova.can_be_modified.return_value = True

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_prova

            result = ProvaService.update_prova(1, name="Updated Name", distance=100)

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Prova, 1)
            mock_db.session.commit.assert_called_once()

            # Verify the prova was updated
            assert mock_prova.name == "Updated Name"
            assert mock_prova.distance == 100

            # Verify the result
            assert result == mock_prova

    def test_update_prova_cannot_be_modified(self):
        """Test updating a prova that cannot be modified."""
        mock_prova = Mock()
        mock_prova.can_be_modified.return_value = False  # Cannot be modified

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_prova

            # Should raise ValueError
            with pytest.raises(ValueError, match="Impossibile modificare la prova"):
                ProvaService.update_prova(1, name="Updated Name")

    def test_update_prova_with_date_str(self):
        """Test updating a prova with date string."""
        from datetime import datetime

        mock_prova = Mock()
        mock_prova.can_be_modified.return_value = True

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_prova

            result = ProvaService.update_prova(1, date_str="2023-06-15")

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Prova, 1)
            mock_db.session.commit.assert_called_once()

            # Verify the prova was updated with parsed date
            expected_date = datetime.strptime("2023-06-15", "%Y-%m-%d").date()
            assert mock_prova.date == expected_date

            # Verify the result
            assert result == mock_prova

    def test_delete_prova_cannot_be_deleted(self):
        """Test deleting a prova that cannot be deleted."""
        mock_prova = Mock()
        mock_prova.can_be_deleted.return_value = False  # Cannot be deleted

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_prova

            # Should raise ValueError
            with pytest.raises(ValueError, match="Impossibile cancellare la prova"):
                ProvaService.delete_prova(1)

    def test_delete_prova_not_found(self):
        """Test deleting a prova when not found."""
        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = None

            # Should raise ValueError
            with pytest.raises(ValueError, match="Prova 1 non trovata"):
                ProvaService.delete_prova(1)

    def test_modify_inscription_dates_success_reopen_setup(self):
        """Test modifying inscription dates successfully - reopen setup path."""
        from datetime import datetime

        mock_prova = Mock()
        mock_prova.can_modify_inscription_dates.return_value = True
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 31)

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_prova

            with patch.object(
                ProvaStateMachine, "reopen_setup", return_value=mock_prova
            ) as mock_reopen_setup:
                # Mock datetime.utcnow to be before start_date
                with patch("models.competition.services.datetime") as mock_datetime:
                    mock_datetime.utcnow.return_value = datetime(
                        2022, 12, 15
                    )  # Before start
                    mock_datetime.side_effect = lambda *args, **kw: datetime(
                        *args, **kw
                    )

                    result = ProvaService.modify_inscription_dates(
                        1, start_date, end_date
                    )

                    # Verify database operation
                    mock_db.session.get.assert_called_once_with(Prova, 1)

                    # Verify the prova dates were set
                    assert mock_prova.inscription_start == start_date
                    assert mock_prova.inscription_end == end_date

                    # Verify state machine was called for reopen_setup
                    mock_reopen_setup.assert_called_once_with(mock_prova)

                    # Verify the result
                    assert result == mock_prova

    def test_modify_inscription_dates_success_to_inscription(self):
        """Test modifying inscription dates successfully - to inscription path."""
        from datetime import datetime

        mock_prova = Mock()
        mock_prova.can_modify_inscription_dates.return_value = True
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 31)

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_prova

            with patch.object(
                ProvaStateMachine, "to_inscription", return_value=mock_prova
            ) as mock_to_inscription:
                # Mock datetime.utcnow to be between start and end dates
                with patch("models.competition.services.datetime") as mock_datetime:
                    mock_datetime.utcnow.return_value = datetime(
                        2023, 1, 15
                    )  # Between start and end
                    mock_datetime.side_effect = lambda *args, **kw: datetime(
                        *args, **kw
                    )

                    result = ProvaService.modify_inscription_dates(
                        1, start_date, end_date
                    )

                    # Verify database operation
                    mock_db.session.get.assert_called_once_with(Prova, 1)

                    # Verify the prova dates were set
                    assert mock_prova.inscription_start == start_date
                    assert mock_prova.inscription_end == end_date

                    # Verify state machine was called for to_inscription
                    mock_to_inscription.assert_called_once_with(mock_prova)

                    # Verify the result
                    assert result == mock_prova

    def test_modify_inscription_dates_cannot_modify(self):
        """Test modifying inscription dates when not allowed."""
        from datetime import datetime

        mock_prova = Mock()
        mock_prova.can_modify_inscription_dates.return_value = False  # Cannot modify
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 31)

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_prova

            # Should raise ValueError
            with pytest.raises(ValueError, match="Impossibile modificare le date"):
                ProvaService.modify_inscription_dates(1, start_date, end_date)

    def test_modify_inscription_dates_not_found(self):
        """Test modifying inscription dates when prova not found."""
        from datetime import datetime

        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 31)

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = None

            # Should raise ValueError
            with pytest.raises(ValueError, match="Prova 1 non trovata"):
                ProvaService.modify_inscription_dates(1, start_date, end_date)

    def test_start_first_round_success(self):
        """Test starting first round successfully."""

        mock_prova = Mock()
        mock_prova.current_round = 0
        mock_prova.min_participants = 2

        mock_inscription1 = Mock()
        mock_inscription2 = Mock()
        mock_inscriptions = [mock_inscription1, mock_inscription2]

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_prova

            # Mock the query for inscriptions
            mock_query = Mock()
            mock_query.all.return_value = mock_inscriptions
            mock_db.session.query.return_value.filter_by.return_value = mock_query

            with patch.object(
                ProvaStateMachine, "start_playing", return_value=mock_prova
            ) as mock_start_playing:
                # Patch the utils module directly
                with patch("utils.create_round_matches") as mock_create_round:
                    result = ProvaService.start_first_round(1)

                    # Verify database operations
                    mock_db.session.get.assert_called_once_with(Prova, 1)
                    mock_query.all.assert_called_once()

                    # Verify inscriptions were ordered (we can't verify shuffling easily in tests)
                    # But we can verify that initial_order was set for each inscription
                    assert hasattr(mock_inscription1, "initial_order")
                    assert hasattr(mock_inscription2, "initial_order")
                    # The initial_order values should be 1 and 2 (in some order)
                    initial_orders = [
                        mock_inscription1.initial_order,
                        mock_inscription2.initial_order,
                    ]
                    assert sorted(initial_orders) == [1, 2]

                    # Verify create_round_matches was called
                    mock_create_round.assert_called_once()

                    # Verify state machine was called
                    mock_start_playing.assert_called_once_with(mock_prova)

                    # Verify the result
                    assert result == mock_prova
                    assert mock_prova.current_round == 1

    def test_start_first_round_not_found(self):
        """Test starting first round when prova not found."""
        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = None

            # Should raise ValueError
            with pytest.raises(ValueError, match="Prova 1 non trovata"):
                ProvaService.start_first_round(1)

    def test_start_first_round_already_started(self):
        """Test starting first round when already started."""
        mock_prova = Mock()
        mock_prova.current_round = 1  # Already started

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_prova

            # Should raise ValueError
            with pytest.raises(ValueError, match="La prova è già iniziata"):
                ProvaService.start_first_round(1)

    def test_start_first_round_insufficient_participants(self):
        """Test starting first round with insufficient participants."""
        mock_prova = Mock()
        mock_prova.current_round = 0
        mock_prova.min_participants = 3  # Need 3 participants

        mock_inscription = Mock()  # Only 1 inscription

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_prova

            # Mock the query for inscriptions
            mock_query = Mock()
            mock_query.all.return_value = [mock_inscription]  # Only 1 inscription
            mock_db.session.query.return_value.filter_by.return_value = mock_query

            # Should raise ValueError
            with pytest.raises(
                ValueError, match="Servono almeno 3 iscritti per avviare la prova"
            ):
                ProvaService.start_first_round(1)

    def test_validate_prova_data_valid_with_all_fields(self):
        """Test validating prova data with all valid fields."""
        data = {
            "name": "Test Prova",
            "discipline": "Test Discipline",
            "distance": "50",
            "entry_fee": "10.5",
            "number": "1",
            "min_participants": "2",
            "max_participants": "10",
            "inscription_start": "2023-01-01",
            "inscription_end": "2023-01-31",
            "rounds_count": "3",
        }

        errors = ProvaService.validate_prova_data(data)

        # Verify no errors
        assert errors == {}

    def test_validate_prova_data_invalid_max_participants(self):
        """Test validating prova data with invalid max participants."""
        data = {
            "name": "Test Prova",
            "discipline": "Test Discipline",
            "distance": "50",
            "min_participants": "4",
            "max_participants": "2",  # Less than min_participants
        }

        errors = ProvaService.validate_prova_data(data)

        # Verify error for max participants
        assert "max_participants" in errors
        assert ">= min" in errors["max_participants"]

    def test_validate_prova_data_invalid_rounds_count(self):
        """Test validating prova data with invalid rounds count."""
        data = {
            "name": "Test Prova",
            "discipline": "Test Discipline",
            "distance": "50",
            "rounds_count": "0",  # Must be at least 1
        }

        errors = ProvaService.validate_prova_data(data)

        # Verify error for rounds count
        assert "rounds_count" in errors
        assert "almeno 1" in errors["rounds_count"]

    def test_validate_prova_data_invalid_date_format(self):
        """Test validating prova data with invalid date format."""
        data = {
            "name": "Test Prova",
            "discipline": "Test Discipline",
            "distance": "50",
            "inscription_start": "invalid-date",
        }

        errors = ProvaService.validate_prova_data(data)

        # Verify error for invalid date format
        assert "inscription_start" in errors
        assert "Formato data non valido" in errors["inscription_start"]

    def test_prova_service_state_machine_methods(self):
        """Test ProvaService state machine facade methods."""
        mock_prova = Mock()

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_prova

            # Test to_inscription
            with patch.object(
                ProvaStateMachine, "to_inscription", return_value=mock_prova
            ) as mock_to_inscription:
                result = ProvaService.to_inscription(1)
                mock_to_inscription.assert_called_once_with(mock_prova)
                assert result == mock_prova

            # Test reopen_setup
            with patch.object(
                ProvaStateMachine, "reopen_setup", return_value=mock_prova
            ) as mock_reopen_setup:
                result = ProvaService.reopen_setup(1)
                mock_reopen_setup.assert_called_once_with(mock_prova)
                assert result == mock_prova

            # Test start_playing
            with patch.object(
                ProvaStateMachine, "start_playing", return_value=mock_prova
            ) as mock_start_playing:
                result = ProvaService.start_playing(1)
                mock_start_playing.assert_called_once_with(mock_prova)
                assert result == mock_prova

            # Test complete
            with patch.object(
                ProvaStateMachine, "complete", return_value=mock_prova
            ) as mock_complete:
                result = ProvaService.complete(1)
                mock_complete.assert_called_once_with(mock_prova)
                assert result == mock_prova

    def test_prova_service_state_machine_methods_not_found(self):
        """Test ProvaService state machine facade methods when prova not found."""
        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = None

            # Test to_inscription
            with pytest.raises(ValueError, match="Prova 1 non trovata"):
                ProvaService.to_inscription(1)

            # Test reopen_setup
            with pytest.raises(ValueError, match="Prova 1 non trovata"):
                ProvaService.reopen_setup(1)

            # Test start_playing
            with pytest.raises(ValueError, match="Prova 1 non trovata"):
                ProvaService.start_playing(1)

            # Test complete
            with pytest.raises(ValueError, match="Prova 1 non trovata"):
                ProvaService.complete(1)


class TestInscriptionService:
    """Test cases for InscriptionService class."""

    def test_inscribe_user_new_inscription(self):
        """Test inscribing a user who is not already inscribed."""
        with patch("models.competition.services.db") as mock_db:
            # Mock query to return None (no existing inscription)
            mock_query = Mock()
            mock_query.first.return_value = None
            mock_db.session.query.return_value.filter_by.return_value = mock_query

            mock_inscription = Mock()

            # Mock the Inscription constructor
            with patch(
                "models.competition.services.Inscription", return_value=mock_inscription
            ) as mock_inscription_class:
                result = InscriptionService.inscribe_user(1, 1)

                # Verify the inscription was created with correct parameters
                mock_inscription_class.assert_called_once_with(user_id=1, prova_id=1)

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_inscription)
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result == mock_inscription

    def test_inscribe_user_existing_inscription(self):
        """Test inscribing a user who is already inscribed."""
        mock_existing = Mock()

        with patch("models.competition.services.db") as mock_db:
            # Mock query to return existing inscription
            mock_query = Mock()
            mock_query.first.return_value = mock_existing
            mock_db.session.query.return_value.filter_by.return_value = mock_query

            result = InscriptionService.inscribe_user(1, 1)

            # Verify no new inscription was created
            mock_db.session.add.assert_not_called()
            mock_db.session.commit.assert_not_called()

            # Verify the result is the existing inscription
            assert result == mock_existing

    def test_inscribe_user_with_existing_inscription(self):
        """Test inscribing a user who is already inscribed."""
        mock_existing = Mock()

        with patch("models.competition.services.db") as mock_db:
            # Mock query to return existing inscription
            mock_query = Mock()
            mock_query.first.return_value = mock_existing
            mock_db.session.query.return_value.filter_by.return_value = mock_query

            result = InscriptionService.inscribe_user(1, 1)

            # Verify no new inscription was created
            mock_db.session.add.assert_not_called()
            mock_db.session.commit.assert_not_called()

            # Verify the result is the existing inscription
            assert result == mock_existing

    def test_uninscribe_user_success(self):
        """Test uninscribing a user successfully."""
        mock_inscription = Mock()

        with patch("models.competition.services.db") as mock_db:
            # Mock query to return existing inscription
            mock_query = Mock()
            mock_query.first.return_value = mock_inscription
            mock_db.session.query.return_value.filter_by.return_value = mock_query

            result = InscriptionService.uninscribe_user(1, 1)

            # Verify database operations
            mock_db.session.delete.assert_called_once_with(mock_inscription)
            mock_db.session.commit.assert_called_once()

            # Verify the result
            assert result is True

    def test_uninscribe_user_not_found(self):
        """Test uninscribing a user who is not inscribed."""
        with patch("models.competition.services.db") as mock_db:
            # Mock query to return None (no existing inscription)
            mock_query = Mock()
            mock_query.first.return_value = None
            mock_db.session.query.return_value.filter_by.return_value = mock_query

            result = InscriptionService.uninscribe_user(1, 1)

            # Verify no deletion occurred
            mock_db.session.delete.assert_not_called()
            mock_db.session.commit.assert_not_called()

            # Verify the result
            assert result is False
