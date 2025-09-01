"""
Comprehensive enhanced tests for models/competition/services.py
Targeting 101 missed statements to improve coverage toward 90% goal.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date, datetime

from models.competition.services import (
    ProvaService,
    ProvaStateMachine,
    InscriptionService,
)
from models.competition.models import Prova
from models.status_enum import ProvaStatus
from models.exceptions import InvalidTransitionError


class TestProvaStateMachineEnhanced:
    """Enhanced tests for ProvaStateMachine targeting missed statements."""

    @patch("models.competition.services.db")
    def test_require_valid_status(self, mock_db):
        """Test _require method with valid expected status."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.SETUP.value

        # Should not raise exception when status matches
        ProvaStateMachine._require(mock_prova, ProvaStatus.SETUP)

    @patch("models.competition.services.db")
    def test_require_invalid_status(self, mock_db):
        """Test _require method with invalid status transition."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.PLAYING.value

        with pytest.raises(InvalidTransitionError, match="Transizione non ammessa"):
            ProvaStateMachine._require(mock_prova, ProvaStatus.SETUP)

    @patch("models.competition.services.db")
    def test_require_none_status_defaults_to_setup(self, mock_db):
        """Test _require method when prova.status is None (defaults to SETUP)."""
        mock_prova = Mock()
        mock_prova.status = None

        # Should work when expecting SETUP and status is None (defaults to SETUP)
        ProvaStateMachine._require(mock_prova, ProvaStatus.SETUP)

    @patch("models.competition.services.db")
    def test_to_inscription_success(self, mock_db):
        """Test successful transition from setup to inscription."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.SETUP.value

        result = ProvaStateMachine.to_inscription(mock_prova)

        assert result == mock_prova
        assert mock_prova.status == ProvaStatus.INSCRIPTION.value
        mock_db.session.add.assert_called_once_with(mock_prova)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_to_inscription_updated_at_compat(self, mock_db):
        """Test to_inscription with updated_at compatibility."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.SETUP.value
        # Mock updated_at attribute that doesn't exist initially
        mock_prova.updated_at = None

        result = ProvaStateMachine.to_inscription(mock_prova)

        assert result == mock_prova
        assert mock_prova.status == ProvaStatus.INSCRIPTION.value

    @patch("models.competition.services.db")
    def test_reopen_setup_success(self, mock_db):
        """Test successful transition from inscription back to setup."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.INSCRIPTION.value

        result = ProvaStateMachine.reopen_setup(mock_prova)

        assert result == mock_prova
        assert mock_prova.status == ProvaStatus.SETUP.value
        mock_db.session.add.assert_called_once_with(mock_prova)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_start_playing_insufficient_inscriptions(self, mock_db):
        """Test start_playing with insufficient inscriptions."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.INSCRIPTION.value
        mock_prova.inscriptions = [Mock()]  # Only 1 inscription, needs >= 2

        with pytest.raises(
            InvalidTransitionError, match="Numero iscritti insufficiente"
        ):
            ProvaStateMachine.start_playing(mock_prova)

    @patch("models.competition.services.db")
    def test_start_playing_inscriptions_exception_handling(self, mock_db):
        """Test start_playing when inscriptions relationship raises exception."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.INSCRIPTION.value
        # Mock inscriptions to raise exception (simulates missing relationship)
        mock_prova.inscriptions = Mock(
            side_effect=Exception("Relationship not available")
        )

        # Should proceed without checking count when relationship fails
        result = ProvaStateMachine.start_playing(mock_prova)

        assert result == mock_prova
        assert mock_prova.status == ProvaStatus.PLAYING.value

    @patch("models.competition.services.db")
    def test_start_playing_with_current_round_initialization(self, mock_db):
        """Test start_playing with current_round initialization."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.INSCRIPTION.value
        mock_prova.inscriptions = [Mock(), Mock(), Mock()]  # 3 inscriptions
        mock_prova.current_round = None

        result = ProvaStateMachine.start_playing(mock_prova)

        assert result == mock_prova
        assert mock_prova.status == ProvaStatus.PLAYING.value
        # Should attempt to set current_round to 1
        assert mock_prova.current_round == 1

    @patch("models.competition.services.db")
    def test_start_playing_current_round_exception_handling(self, mock_db):
        """Test start_playing when setting current_round raises exception."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.INSCRIPTION.value
        mock_prova.inscriptions = [Mock(), Mock()]  # 2 inscriptions
        mock_prova.current_round = 0

        # Mock setattr to raise exception
        def mock_setattr(obj, name, value):
            if name == "current_round":
                raise Exception("Cannot set current_round")

        with patch("builtins.setattr", side_effect=mock_setattr):
            result = ProvaStateMachine.start_playing(mock_prova)

            assert result == mock_prova
            assert mock_prova.status == ProvaStatus.PLAYING.value

    @patch("models.competition.services.db")
    def test_complete_success(self, mock_db):
        """Test successful transition from playing to completed."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.PLAYING.value

        result = ProvaStateMachine.complete(mock_prova)

        assert result == mock_prova
        assert mock_prova.status == ProvaStatus.COMPLETED.value
        mock_db.session.add.assert_called_once_with(mock_prova)
        mock_db.session.commit.assert_called_once()


class TestProvaServiceEnhanced:
    """Enhanced tests for ProvaService targeting missed statements."""

    @patch("models.competition.services.db")
    @patch("models.competition.services.Prova")
    def test_create_prova_without_tournament_or_director(
        self, mock_prova_class, mock_db
    ):
        """Test create_prova raises error when neither tournament_id nor director_id provided."""
        with pytest.raises(
            ValueError, match="Una Prova deve avere un tournament_id o un director_id"
        ):
            ProvaService.create_prova(
                number=1,
                name="Test Prova",
                date=date.today(),
                discipline="palla_8",
                distance=5,
            )

    @patch("models.competition.services.db")
    @patch("models.competition.services.Prova")
    def test_create_prova_with_tournament_id(self, mock_prova_class, mock_db):
        """Test create_prova with tournament_id."""
        mock_prova = Mock()
        mock_prova_class.return_value = mock_prova

        result = ProvaService.create_prova(
            number=1,
            name="Test Prova",
            date=date.today(),
            discipline="palla_8",
            distance=5,
            tournament_id=1,
            extra_field="extra_value",
        )

        assert result == mock_prova
        mock_prova_class.assert_called_once()
        mock_db.session.add.assert_called_once_with(mock_prova)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    @patch("models.competition.services.Prova")
    def test_create_prova_with_director_id(self, mock_prova_class, mock_db):
        """Test create_prova with director_id (standalone prova)."""
        mock_prova = Mock()
        mock_prova_class.return_value = mock_prova

        result = ProvaService.create_prova(
            number=1,
            name="Test Prova",
            date=date.today(),
            discipline="palla_8",
            distance=5,
            director_id=1,
        )

        assert result == mock_prova
        mock_db.session.add.assert_called_once_with(mock_prova)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_get_prova_by_id_success(self, mock_db):
        """Test get_prova_by_id returns prova when found."""
        mock_prova = Mock()
        mock_db.session.get.return_value = mock_prova

        result = ProvaService.get_prova_by_id(1)

        assert result == mock_prova
        mock_db.session.get.assert_called_once_with(Prova, 1)

    @patch("models.competition.services.db")
    def test_get_prova_by_id_not_found(self, mock_db):
        """Test get_prova_by_id returns None when not found."""
        mock_db.session.get.return_value = None

        result = ProvaService.get_prova_by_id(1)

        assert result is None

    @patch("models.competition.services.db")
    def test_update_prova_not_found(self, mock_db):
        """Test update_prova raises error when prova not found."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Prova 1 non trovata"):
            ProvaService.update_prova(1, name="New Name")

    @patch("models.competition.services.db")
    def test_update_prova_cannot_be_modified(self, mock_db):
        """Test update_prova raises error when prova cannot be modified."""
        mock_prova = Mock()
        mock_prova.can_be_modified.return_value = False
        mock_db.session.get.return_value = mock_prova

        with pytest.raises(ValueError, match="Impossibile modificare la prova"):
            ProvaService.update_prova(1, name="New Name")

    @patch("models.competition.services.db")
    def test_update_prova_success_with_date_str(self, mock_db):
        """Test update_prova success with date_str field."""
        mock_prova = Mock()
        mock_prova.can_be_modified.return_value = True
        mock_db.session.get.return_value = mock_prova

        result = ProvaService.update_prova(
            1, name="New Name", discipline="new_discipline", date_str="2024-12-25"
        )

        assert result == mock_prova
        assert mock_prova.name == "New Name"
        assert mock_prova.discipline == "new_discipline"
        assert mock_prova.date == date(2024, 12, 25)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_update_prova_skip_nonexistent_fields(self, mock_db):
        """Test update_prova skips fields that don't exist on the model."""
        mock_prova = Mock()
        mock_prova.can_be_modified.return_value = True
        mock_db.session.get.return_value = mock_prova

        # Mock hasattr to return False for 'nonexistent_field'
        original_hasattr = hasattr

        def mock_hasattr(obj, name):
            if name == "nonexistent_field":
                return False
            return original_hasattr(obj, name)

        with patch("builtins.hasattr", side_effect=mock_hasattr):
            result = ProvaService.update_prova(
                1, name="New Name", nonexistent_field="should_be_ignored"
            )

        assert result == mock_prova
        assert mock_prova.name == "New Name"
        # nonexistent_field should not be set

    @patch("models.competition.services.db")
    def test_delete_prova_not_found(self, mock_db):
        """Test delete_prova raises error when prova not found."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Prova 1 non trovata"):
            ProvaService.delete_prova(1)

    @patch("models.competition.services.db")
    def test_delete_prova_cannot_be_deleted(self, mock_db):
        """Test delete_prova raises error when prova cannot be deleted."""
        mock_prova = Mock()
        mock_prova.can_be_deleted.return_value = False
        mock_db.session.get.return_value = mock_prova

        with pytest.raises(ValueError, match="Impossibile cancellare la prova"):
            ProvaService.delete_prova(1)

    @patch("models.competition.services.db")
    def test_delete_prova_success(self, mock_db):
        """Test delete_prova success."""
        mock_prova = Mock()
        mock_prova.can_be_deleted.return_value = True
        mock_db.session.get.return_value = mock_prova

        ProvaService.delete_prova(1)

        mock_db.session.delete.assert_called_once_with(mock_prova)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.ProvaStateMachine.to_inscription")
    @patch("models.competition.services.db")
    def test_open_inscriptions_invalid_dates(self, mock_db, mock_to_inscription):
        """Test open_inscriptions with invalid date range."""
        start_date = datetime(2024, 1, 10)
        end_date = datetime(2024, 1, 5)  # End before start

        with pytest.raises(
            ValueError, match="La data di inizio deve essere precedente"
        ):
            ProvaService.open_inscriptions(1, start_date, end_date)

    @patch("models.competition.services.ProvaStateMachine.to_inscription")
    @patch("models.competition.services.db")
    def test_open_inscriptions_prova_not_found(self, mock_db, mock_to_inscription):
        """Test open_inscriptions when prova not found."""
        mock_db.session.get.return_value = None
        start_date = datetime(2024, 1, 5)
        end_date = datetime(2024, 1, 10)

        with pytest.raises(ValueError, match="Prova 1 non trovata"):
            ProvaService.open_inscriptions(1, start_date, end_date)

    @patch("models.competition.services.ProvaStateMachine.to_inscription")
    @patch("models.competition.services.db")
    def test_open_inscriptions_success(self, mock_db, mock_to_inscription):
        """Test open_inscriptions success."""
        mock_prova = Mock()
        mock_db.session.get.return_value = mock_prova
        mock_to_inscription.return_value = mock_prova

        start_date = datetime(2024, 1, 5)
        end_date = datetime(2024, 1, 10)

        result = ProvaService.open_inscriptions(1, start_date, end_date)

        assert result == mock_prova
        assert mock_prova.inscription_start == start_date
        assert mock_prova.inscription_end == end_date
        mock_to_inscription.assert_called_once_with(mock_prova)

    @patch("models.competition.services.ProvaStateMachine")
    @patch("models.competition.services.db")
    @patch("models.competition.services.datetime")
    def test_modify_inscription_dates_prova_not_found(
        self, mock_datetime, mock_db, mock_state_machine
    ):
        """Test modify_inscription_dates when prova not found."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Prova 1 non trovata"):
            ProvaService.modify_inscription_dates(
                1, datetime(2024, 1, 5), datetime(2024, 1, 10)
            )

    @patch("models.competition.services.ProvaStateMachine")
    @patch("models.competition.services.db")
    @patch("models.competition.services.datetime")
    def test_modify_inscription_dates_cannot_modify(
        self, mock_datetime, mock_db, mock_state_machine
    ):
        """Test modify_inscription_dates when dates cannot be modified."""
        mock_prova = Mock()
        mock_prova.can_modify_inscription_dates.return_value = False
        mock_db.session.get.return_value = mock_prova

        with pytest.raises(ValueError, match="Impossibile modificare le date"):
            ProvaService.modify_inscription_dates(
                1, datetime(2024, 1, 5), datetime(2024, 1, 10)
            )

    @patch("models.competition.services.ProvaStateMachine")
    @patch("models.competition.services.db")
    @patch("models.competition.services.datetime")
    def test_modify_inscription_dates_invalid_range(
        self, mock_datetime, mock_db, mock_state_machine
    ):
        """Test modify_inscription_dates with invalid date range."""
        mock_prova = Mock()
        mock_prova.can_modify_inscription_dates.return_value = True
        mock_db.session.get.return_value = mock_prova

        with pytest.raises(
            ValueError, match="La data di inizio deve essere precedente"
        ):
            ProvaService.modify_inscription_dates(
                1, datetime(2024, 1, 10), datetime(2024, 1, 5)  # Start after end
            )

    @patch("models.competition.services.ProvaStateMachine")
    @patch("models.competition.services.db")
    @patch("models.competition.services.datetime")
    def test_modify_inscription_dates_future_start(
        self, mock_datetime, mock_db, mock_state_machine
    ):
        """Test modify_inscription_dates with future start date (reopen setup)."""
        mock_now = datetime(2024, 1, 1)
        mock_datetime.utcnow.return_value = mock_now

        mock_prova = Mock()
        mock_prova.can_modify_inscription_dates.return_value = True
        mock_db.session.get.return_value = mock_prova
        mock_state_machine.reopen_setup.return_value = mock_prova

        start_date = datetime(2024, 1, 5)  # Future
        end_date = datetime(2024, 1, 10)

        result = ProvaService.modify_inscription_dates(1, start_date, end_date)

        assert result == mock_prova
        assert mock_prova.inscription_start == start_date
        assert mock_prova.inscription_end == end_date
        mock_state_machine.reopen_setup.assert_called_once_with(mock_prova)

    @patch("models.competition.services.ProvaStateMachine")
    @patch("models.competition.services.db")
    @patch("models.competition.services.datetime")
    def test_modify_inscription_dates_current_period(
        self, mock_datetime, mock_db, mock_state_machine
    ):
        """Test modify_inscription_dates within current inscription period."""
        mock_now = datetime(2024, 1, 7)  # Between start and end
        mock_datetime.utcnow.return_value = mock_now

        mock_prova = Mock()
        mock_prova.can_modify_inscription_dates.return_value = True
        mock_db.session.get.return_value = mock_prova
        mock_state_machine.to_inscription.return_value = mock_prova

        start_date = datetime(2024, 1, 5)
        end_date = datetime(2024, 1, 10)

        result = ProvaService.modify_inscription_dates(1, start_date, end_date)

        assert result == mock_prova
        mock_state_machine.to_inscription.assert_called_once_with(mock_prova)

    @patch("models.competition.services.create_round_matches")
    @patch("models.competition.services.ProvaStateMachine.start_playing")
    @patch("models.competition.services.db")
    @patch("models.competition.services.random")
    def test_start_first_round_prova_not_found(
        self, mock_random, mock_db, mock_start_playing, mock_create_matches
    ):
        """Test start_first_round when prova not found."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Prova 1 non trovata"):
            ProvaService.start_first_round(1)

    @patch("models.competition.services.create_round_matches")
    @patch("models.competition.services.ProvaStateMachine.start_playing")
    @patch("models.competition.services.db")
    @patch("models.competition.services.random")
    def test_start_first_round_already_started(
        self, mock_random, mock_db, mock_start_playing, mock_create_matches
    ):
        """Test start_first_round when prova already started."""
        mock_prova = Mock()
        mock_prova.current_round = 1  # Already started
        mock_db.session.get.return_value = mock_prova

        with pytest.raises(ValueError, match="La prova è già iniziata"):
            ProvaService.start_first_round(1)

    @patch("models.competition.services.create_round_matches")
    @patch("models.competition.services.ProvaStateMachine.start_playing")
    @patch("models.competition.services.db")
    @patch("models.competition.services.random")
    def test_start_first_round_insufficient_participants(
        self, mock_random, mock_db, mock_start_playing, mock_create_matches
    ):
        """Test start_first_round with insufficient participants."""
        mock_prova = Mock()
        mock_prova.current_round = 0
        mock_prova.min_participants = 4
        mock_db.session.get.return_value = mock_prova

        # Mock only 2 inscriptions, need 4
        mock_inscriptions = [Mock(), Mock()]
        mock_db.session.query.return_value.filter_by.return_value.all.return_value = (
            mock_inscriptions
        )

        with pytest.raises(ValueError, match="Servono almeno 4 iscritti"):
            ProvaService.start_first_round(1)


class TestInscriptionServiceEnhanced:
    """Enhanced tests for InscriptionService targeting missed statements."""

    @patch("models.competition.services.db")
    @patch("models.competition.services.Inscription")
    def test_inscribe_user_existing_inscription(self, mock_inscription_class, mock_db):
        """Test inscribe_user when inscription already exists."""
        mock_existing = Mock()
        mock_db.session.query.return_value.filter_by.return_value.first.return_value = (
            mock_existing
        )

        result = InscriptionService.inscribe_user(1, 1)

        assert result == mock_existing
        # Should not create new inscription
        mock_inscription_class.assert_not_called()
        mock_db.session.add.assert_not_called()
        mock_db.session.commit.assert_not_called()

    @patch("models.competition.services.db")
    @patch("models.competition.services.Inscription")
    def test_inscribe_user_new_inscription(self, mock_inscription_class, mock_db):
        """Test inscribe_user creating new inscription."""
        mock_db.session.query.return_value.filter_by.return_value.first.return_value = (
            None
        )
        mock_new_inscription = Mock()
        mock_inscription_class.return_value = mock_new_inscription

        result = InscriptionService.inscribe_user(1, 1)

        assert result == mock_new_inscription
        mock_inscription_class.assert_called_once_with(user_id=1, prova_id=1)
        mock_db.session.add.assert_called_once_with(mock_new_inscription)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_uninscribe_user_inscription_found(self, mock_db):
        """Test uninscribe_user when inscription exists."""
        mock_inscription = Mock()
        mock_db.session.query.return_value.filter_by.return_value.first.return_value = (
            mock_inscription
        )

        result = InscriptionService.uninscribe_user(1, 1)

        assert result is True
        mock_db.session.delete.assert_called_once_with(mock_inscription)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_uninscribe_user_inscription_not_found(self, mock_db):
        """Test uninscribe_user when inscription doesn't exist."""
        mock_db.session.query.return_value.filter_by.return_value.first.return_value = (
            None
        )

        result = InscriptionService.uninscribe_user(1, 1)

        assert result is False
        mock_db.session.delete.assert_not_called()
        mock_db.session.commit.assert_not_called()
