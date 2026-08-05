"""
Test module for models/competition/services.py
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date
from models.competition.services import (
    GaraService,
    ProvaStateMachine,
    InscriptionService,
)
from models.competition.models import Gara
from models.status_enum import GaraStatus
from models.exceptions import InvalidTransitionError
from models.base import utc_now


class TestProvaStateMachine:
    """Test cases for ProvaStateMachine class."""

    def test_to_inscription_success(self):
        """Test transitioning gara to inscription state successfully."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.SETUP.value

        with patch("models.competition.services.db") as mock_db:
            result = ProvaStateMachine.to_inscription(mock_gara)

            # Verify the gara status was updated
            assert mock_gara.status == GaraStatus.INSCRIPTION.value

            # Verify database operations
            mock_db.session.add.assert_called_once_with(mock_gara)
            mock_db.session.commit.assert_called_once()

            # Verify the result
            assert result == mock_gara

    def test_to_inscription_invalid_transition(self):
        """Test transitioning gara to inscription state with invalid current state."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.PLAYING.value  # Already playing

        # Should raise InvalidTransitionError
        with pytest.raises(InvalidTransitionError):
            ProvaStateMachine.to_inscription(mock_gara)

    def test_reopen_setup_success(self):
        """Test transitioning gara back to setup state successfully."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.INSCRIPTION.value

        with patch("models.competition.services.db") as mock_db:
            result = ProvaStateMachine.reopen_setup(mock_gara)

            # Verify the gara status was updated
            assert mock_gara.status == GaraStatus.SETUP.value

            # Verify database operations
            mock_db.session.add.assert_called_once_with(mock_gara)
            mock_db.session.commit.assert_called_once()

            # Verify the result
            assert result == mock_gara

    def test_start_playing_success(self):
        """Test transitioning gara to playing state successfully."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.INSCRIPTION.value
        mock_gara.inscriptions = [Mock(), Mock()]  # Two inscriptions
        mock_gara.current_round = 0

        with patch("models.competition.services.db") as mock_db:
            result = ProvaStateMachine.start_playing(mock_gara)

            # Verify the gara status was updated
            assert mock_gara.status == GaraStatus.PLAYING.value

            # Verify the current round was set
            assert mock_gara.current_round == 1

            # Verify database operations
            mock_db.session.add.assert_called_once_with(mock_gara)
            mock_db.session.commit.assert_called_once()

            # Verify the result
            assert result == mock_gara

    def test_start_playing_insufficient_inscriptions(self):
        """Test transitioning gara to playing state with insufficient inscriptions."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.INSCRIPTION.value
        mock_gara.inscriptions = [Mock()]  # Only one inscription

        # Should raise InvalidTransitionError
        with pytest.raises(
            InvalidTransitionError, match="Numero iscritti insufficiente"
        ):
            ProvaStateMachine.start_playing(mock_gara)

    def test_complete_success(self):
        """Test transitioning gara to completed state successfully."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.PLAYING.value

        with patch("models.competition.services.db") as mock_db:
            result = ProvaStateMachine.complete(mock_gara)

            # Verify the gara status was updated
            assert mock_gara.status == GaraStatus.COMPLETED.value

            # Verify database operations
            mock_db.session.add.assert_called_once_with(mock_gara)
            mock_db.session.commit.assert_called_once()

            # Verify the result
            assert result == mock_gara


class TestProvaService:
    """Test cases for GaraService class."""

    def test_create_gara_success(self):
        """Test creating a gara successfully."""
        with patch("models.competition.services.db") as mock_db:
            mock_gara = Mock()

            # Mock the Gara constructor
            with patch(
                "models.competition.services.Gara", return_value=mock_gara
            ) as mock_gara_class:
                result = GaraService.create_gara(
                    number=1,
                    name="Test Gara",
                    date=date(2023, 1, 1),
                    discipline="Test Discipline",
                    distance=50,
                    campionato_id=1,
                )

                # Verify the gara was created with correct parameters
                mock_gara_class.assert_called_once_with(
                    number=1,
                    name="Test Gara",
                    date=date(2023, 1, 1),
                    discipline="Test Discipline",
                    distance=50,
                    campionato_id=1,
                    director_id=None,
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_gara)
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result == mock_gara

    def test_create_gara_without_campionato_or_director(self):
        """Test creating a gara without campionato_id or director_id."""
        # Should raise ValueError
        with pytest.raises(ValueError, match="Una Gara deve avere"):
            GaraService.create_gara(
                number=1,
                name="Test Gara",
                date=date(2023, 1, 1),
                discipline="Test Discipline",
                distance=50,
            )

    def test_get_gara_by_id_success(self):
        """Test getting a gara by ID successfully."""
        mock_gara = Mock()

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_gara

            result = GaraService.get_gara_by_id(1)

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Gara, 1)

            # Verify the result
            assert result == mock_gara

    def test_get_gara_by_id_not_found(self):
        """Test getting a gara by ID when not found."""
        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = None

            result = GaraService.get_gara_by_id(1)

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Gara, 1)

            # Verify the result
            assert result is None

    def test_update_gara_success(self):
        """Test updating a gara successfully."""
        mock_gara = Mock()
        mock_gara.can_be_modified.return_value = True

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_gara

            result = GaraService.update_gara(1, name="Updated Name", distance=100)

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Gara, 1)
            mock_db.session.commit.assert_called_once()

            # Verify the gara was updated
            assert mock_gara.name == "Updated Name"
            assert mock_gara.distance == 100

            # Verify the result
            assert result == mock_gara

    def test_update_gara_cannot_be_modified(self):
        """Test updating a gara that cannot be modified."""
        mock_gara = Mock()
        mock_gara.can_be_modified.return_value = False  # Cannot be modified

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_gara

            # Should raise ValueError
            with pytest.raises(ValueError, match="Impossibile modificare la gara"):
                GaraService.update_gara(1, name="Updated Name")

    def test_update_gara_with_date_str(self):
        """Test updating a gara with date string."""
        from datetime import datetime

        mock_gara = Mock()
        mock_gara.can_be_modified.return_value = True

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_gara

            result = GaraService.update_gara(1, date_str="2023-06-15")

            # Verify database operation
            mock_db.session.get.assert_called_once_with(Gara, 1)
            mock_db.session.commit.assert_called_once()

            # Verify the gara was updated with parsed date
            expected_date = datetime.strptime("2023-06-15", "%Y-%m-%d").date()
            assert mock_gara.date == expected_date

            # Verify the result
            assert result == mock_gara

    def test_delete_gara_cannot_be_deleted(self):
        """Test deleting a gara that cannot be deleted."""
        mock_gara = Mock()
        mock_gara.can_be_deleted.return_value = False  # Cannot be deleted

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_gara

            # Should raise ValueError
            with pytest.raises(ValueError, match="Impossibile cancellare la gara"):
                GaraService.delete_gara(1)

    def test_delete_gara_not_found(self):
        """Test deleting a gara when not found."""
        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = None

            # Should raise ValueError
            with pytest.raises(ValueError, match="Gara 1 non trovata"):
                GaraService.delete_gara(1)

    def test_modify_inscription_dates_success_reopen_setup(self):
        """Test modifying inscription dates successfully - reopen setup path."""
        from datetime import datetime

        mock_gara = Mock()
        mock_gara.can_modify_inscription_dates.return_value = True
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 31)

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_gara

            with patch.object(
                ProvaStateMachine, "reopen_setup", return_value=mock_gara
            ) as mock_reopen_setup:
                # Mock utc_now to be before start_date
                with patch("models.competition.services.datetime") as mock_datetime:
                    mock_utc_now.return_value = datetime(2022, 12, 15)  # Before start
                    mock_datetime.side_effect = lambda *args, **kw: datetime(
                        *args, **kw
                    )

                    result = GaraService.modify_inscription_dates(
                        1, start_date, end_date
                    )

                    # Verify database operation
                    mock_db.session.get.assert_called_once_with(Gara, 1)

                    # Verify the gara dates were set
                    assert mock_gara.inscription_start == start_date
                    assert mock_gara.inscription_end == end_date

                    # Verify state machine was called for reopen_setup
                    mock_reopen_setup.assert_called_once_with(mock_gara)

                    # Verify the result
                    assert result == mock_gara

    def test_modify_inscription_dates_success_to_inscription(self):
        """Test modifying inscription dates successfully - to inscription path."""
        from datetime import datetime

        mock_gara = Mock()
        mock_gara.can_modify_inscription_dates.return_value = True
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 31)

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_gara

            with patch.object(
                ProvaStateMachine, "to_inscription", return_value=mock_gara
            ) as mock_to_inscription:
                # Mock utc_now to be between start and end dates
                with patch("models.competition.services.datetime") as mock_datetime:
                    mock_utc_now.return_value = datetime(
                        2023, 1, 15
                    )  # Between start and end
                    mock_datetime.side_effect = lambda *args, **kw: datetime(
                        *args, **kw
                    )

                    result = GaraService.modify_inscription_dates(
                        1, start_date, end_date
                    )

                    # Verify database operation
                    mock_db.session.get.assert_called_once_with(Gara, 1)

                    # Verify the gara dates were set
                    assert mock_gara.inscription_start == start_date
                    assert mock_gara.inscription_end == end_date

                    # Verify state machine was called for to_inscription
                    mock_to_inscription.assert_called_once_with(mock_gara)

                    # Verify the result
                    assert result == mock_gara

    def test_modify_inscription_dates_cannot_modify(self):
        """Test modifying inscription dates when not allowed."""
        from datetime import datetime

        mock_gara = Mock()
        mock_gara.can_modify_inscription_dates.return_value = False  # Cannot modify
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 31)

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_gara

            # Should raise ValueError
            with pytest.raises(ValueError, match="Impossibile modificare le date"):
                GaraService.modify_inscription_dates(1, start_date, end_date)

    def test_modify_inscription_dates_not_found(self):
        """Test modifying inscription dates when gara not found."""
        from datetime import datetime

        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 31)

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = None

            # Should raise ValueError
            with pytest.raises(ValueError, match="Gara 1 non trovata"):
                GaraService.modify_inscription_dates(1, start_date, end_date)

    def test_start_first_round_success(self):
        """Test starting first round successfully."""

        mock_gara = Mock()
        mock_gara.current_round = 0
        mock_gara.min_participants = 2

        mock_inscription1 = Mock()
        mock_inscription2 = Mock()
        mock_inscriptions = [mock_inscription1, mock_inscription2]

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_gara

            # Mock the query for inscriptions
            mock_query = Mock()
            mock_query.all.return_value = mock_inscriptions
            mock_db.session.query.return_value.filter_by.return_value = mock_query

            with patch.object(
                ProvaStateMachine, "start_playing", return_value=mock_gara
            ) as mock_start_playing:
                # Patch the utils module directly
                with patch("utils.create_round_matches") as mock_create_round:
                    result = GaraService.start_first_round(1)

                    # Verify database operations
                    mock_db.session.get.assert_called_once_with(Gara, 1)
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
                    mock_start_playing.assert_called_once_with(mock_gara)

                    # Verify the result
                    assert result == mock_gara
                    assert mock_gara.current_round == 1

    def test_start_first_round_not_found(self):
        """Test starting first round when gara not found."""
        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = None

            # Should raise ValueError
            with pytest.raises(ValueError, match="Gara 1 non trovata"):
                GaraService.start_first_round(1)

    def test_start_first_round_already_started(self):
        """Test starting first round when already started."""
        mock_gara = Mock()
        mock_gara.current_round = 1  # Already started

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_gara

            # Should raise ValueError
            with pytest.raises(ValueError, match="La gara è già iniziata"):
                GaraService.start_first_round(1)

    def test_start_first_round_insufficient_participants(self):
        """Test starting first round with insufficient participants."""
        mock_gara = Mock()
        mock_gara.current_round = 0
        mock_gara.min_participants = 3  # Need 3 participants

        mock_inscription = Mock()  # Only 1 inscription

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_gara

            # Mock the query for inscriptions
            mock_query = Mock()
            mock_query.all.return_value = [mock_inscription]  # Only 1 inscription
            mock_db.session.query.return_value.filter_by.return_value = mock_query

            # Should raise ValueError
            with pytest.raises(
                ValueError, match="Servono almeno 3 iscritti per avviare la gara"
            ):
                GaraService.start_first_round(1)

    def test_validate_gara_data_valid_with_all_fields(self):
        """Test validating gara data with all valid fields."""
        data = {
            "name": "Test Gara",
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

        errors = GaraService.validate_gara_data(data)

        # Verify no errors
        assert errors == {}

    def test_validate_gara_data_invalid_max_participants(self):
        """Test validating gara data with invalid max participants."""
        data = {
            "name": "Test Gara",
            "discipline": "Test Discipline",
            "distance": "50",
            "min_participants": "4",
            "max_participants": "2",  # Less than min_participants
        }

        errors = GaraService.validate_gara_data(data)

        # Verify error for max participants
        assert "max_participants" in errors
        assert ">= min" in errors["max_participants"]

    def test_validate_gara_data_invalid_rounds_count(self):
        """Test validating gara data with invalid rounds count."""
        data = {
            "name": "Test Gara",
            "discipline": "Test Discipline",
            "distance": "50",
            "rounds_count": "0",  # Must be at least 1
        }

        errors = GaraService.validate_gara_data(data)

        # Verify error for rounds count
        assert "rounds_count" in errors
        assert "almeno 1" in errors["rounds_count"]

    def test_validate_gara_data_invalid_date_format(self):
        """Test validating gara data with invalid date format."""
        data = {
            "name": "Test Gara",
            "discipline": "Test Discipline",
            "distance": "50",
            "inscription_start": "invalid-date",
        }

        errors = GaraService.validate_gara_data(data)

        # Verify error for invalid date format
        assert "inscription_start" in errors
        assert "Formato data non valido" in errors["inscription_start"]

    def test_gara_service_state_machine_methods(self):
        """Test GaraService state machine facade methods."""
        mock_gara = Mock()

        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = mock_gara

            # Test to_inscription
            with patch.object(
                ProvaStateMachine, "to_inscription", return_value=mock_gara
            ) as mock_to_inscription:
                result = GaraService.to_inscription(1)
                mock_to_inscription.assert_called_once_with(mock_gara)
                assert result == mock_gara

            # Test reopen_setup
            with patch.object(
                ProvaStateMachine, "reopen_setup", return_value=mock_gara
            ) as mock_reopen_setup:
                result = GaraService.reopen_setup(1)
                mock_reopen_setup.assert_called_once_with(mock_gara)
                assert result == mock_gara

            # Test start_playing
            with patch.object(
                ProvaStateMachine, "start_playing", return_value=mock_gara
            ) as mock_start_playing:
                result = GaraService.start_playing(1)
                mock_start_playing.assert_called_once_with(mock_gara)
                assert result == mock_gara

            # Test complete
            with patch.object(
                ProvaStateMachine, "complete", return_value=mock_gara
            ) as mock_complete:
                result = GaraService.complete(1)
                mock_complete.assert_called_once_with(mock_gara)
                assert result == mock_gara

    def test_gara_service_state_machine_methods_not_found(self):
        """Test GaraService state machine facade methods when gara not found."""
        with patch("models.competition.services.db") as mock_db:
            mock_db.session.get.return_value = None

            # Test to_inscription
            with pytest.raises(ValueError, match="Gara 1 non trovata"):
                GaraService.to_inscription(1)

            # Test reopen_setup
            with pytest.raises(ValueError, match="Gara 1 non trovata"):
                GaraService.reopen_setup(1)

            # Test start_playing
            with pytest.raises(ValueError, match="Gara 1 non trovata"):
                GaraService.start_playing(1)

            # Test complete
            with pytest.raises(ValueError, match="Gara 1 non trovata"):
                GaraService.complete(1)


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
                mock_inscription_class.assert_called_once_with(user_id=1, gara_id=1)

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
