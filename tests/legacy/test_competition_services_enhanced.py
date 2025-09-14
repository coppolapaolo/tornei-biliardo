"""
Comprehensive enhanced tests for models/competition/services.py
Targeting 101 missed statements to improve coverage toward 90% goal.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date, datetime

from models.competition.services import (
    GaraService,
    ProvaStateMachine,
    InscriptionService,
)
from models.competition.models import Gara
from models.status_enum import GaraStatus
from models.exceptions import InvalidTransitionError


class TestProvaStateMachineEnhanced:
    """Enhanced tests for ProvaStateMachine targeting missed statements."""

    @patch("models.competition.services.db")
    def test_require_valid_status(self, mock_db):
        """Test _require method with valid expected status."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.SETUP.value

        # Should not raise exception when status matches
        ProvaStateMachine._require(mock_gara, GaraStatus.SETUP)

    @patch("models.competition.services.db")
    def test_require_invalid_status(self, mock_db):
        """Test _require method with invalid status transition."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.PLAYING.value

        with pytest.raises(InvalidTransitionError, match="Transizione non ammessa"):
            ProvaStateMachine._require(mock_gara, GaraStatus.SETUP)

    @patch("models.competition.services.db")
    def test_require_none_status_defaults_to_setup(self, mock_db):
        """Test _require method when gara.status is None (defaults to SETUP)."""
        mock_gara = Mock()
        mock_gara.status = None

        # Should work when expecting SETUP and status is None (defaults to SETUP)
        ProvaStateMachine._require(mock_gara, GaraStatus.SETUP)

    @patch("models.competition.services.db")
    def test_to_inscription_success(self, mock_db):
        """Test successful transition from setup to inscription."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.SETUP.value

        result = ProvaStateMachine.to_inscription(mock_gara)

        assert result == mock_gara
        assert mock_gara.status == GaraStatus.INSCRIPTION.value
        mock_db.session.add.assert_called_once_with(mock_gara)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_to_inscription_updated_at_compat(self, mock_db):
        """Test to_inscription with updated_at compatibility."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.SETUP.value
        # Mock updated_at attribute that doesn't exist initially
        mock_gara.updated_at = None

        result = ProvaStateMachine.to_inscription(mock_gara)

        assert result == mock_gara
        assert mock_gara.status == GaraStatus.INSCRIPTION.value

    @patch("models.competition.services.db")
    def test_reopen_setup_success(self, mock_db):
        """Test successful transition from inscription back to setup."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.INSCRIPTION.value

        result = ProvaStateMachine.reopen_setup(mock_gara)

        assert result == mock_gara
        assert mock_gara.status == GaraStatus.SETUP.value
        mock_db.session.add.assert_called_once_with(mock_gara)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_start_playing_insufficient_inscriptions(self, mock_db):
        """Test start_playing with insufficient inscriptions."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.INSCRIPTION.value
        mock_gara.inscriptions = [Mock()]  # Only 1 inscription, needs >= 2

        with pytest.raises(
            InvalidTransitionError, match="Numero iscritti insufficiente"
        ):
            ProvaStateMachine.start_playing(mock_gara)

    @patch("models.competition.services.db")
    def test_start_playing_inscriptions_exception_handling(self, mock_db):
        """Test start_playing when inscriptions relationship raises exception."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.INSCRIPTION.value
        # Mock inscriptions to raise exception (simulates missing relationship)
        mock_gara.inscriptions = Mock(
            side_effect=Exception("Relationship not available")
        )

        # Should proceed without checking count when relationship fails
        result = ProvaStateMachine.start_playing(mock_gara)

        assert result == mock_gara
        assert mock_gara.status == GaraStatus.PLAYING.value

    @patch("models.competition.services.db")
    def test_start_playing_with_current_round_initialization(self, mock_db):
        """Test start_playing with current_round initialization."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.INSCRIPTION.value
        mock_gara.inscriptions = [Mock(), Mock(), Mock()]  # 3 inscriptions
        mock_gara.current_round = None

        result = ProvaStateMachine.start_playing(mock_gara)

        assert result == mock_gara
        assert mock_gara.status == GaraStatus.PLAYING.value
        # Should attempt to set current_round to 1
        assert mock_gara.current_round == 1

    @patch("models.competition.services.db")
    def test_start_playing_current_round_exception_handling(self, mock_db):
        """Test start_playing when setting current_round raises exception."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.INSCRIPTION.value
        mock_gara.inscriptions = [Mock(), Mock()]  # 2 inscriptions
        mock_gara.current_round = 0

        # Mock setattr to raise exception
        def mock_setattr(obj, name, value):
            if name == "current_round":
                raise Exception("Cannot set current_round")

        with patch("builtins.setattr", side_effect=mock_setattr):
            result = ProvaStateMachine.start_playing(mock_gara)

            assert result == mock_gara
            assert mock_gara.status == GaraStatus.PLAYING.value

    @patch("models.competition.services.db")
    def test_complete_success(self, mock_db):
        """Test successful transition from playing to completed."""
        mock_gara = Mock()
        mock_gara.status = GaraStatus.PLAYING.value

        result = ProvaStateMachine.complete(mock_gara)

        assert result == mock_gara
        assert mock_gara.status == GaraStatus.COMPLETED.value
        mock_db.session.add.assert_called_once_with(mock_gara)
        mock_db.session.commit.assert_called_once()


class TestProvaServiceEnhanced:
    """Enhanced tests for GaraService targeting missed statements."""

    @patch("models.competition.services.db")
    @patch("models.competition.services.Gara")
    def test_create_gara_without_campionato_or_director(self, mock_gara_class, mock_db):
        """Test create_gara raises error when neither campionato_id nor director_id provided."""
        with pytest.raises(
            ValueError, match="Una Gara deve avere un campionato_id o un director_id"
        ):
            GaraService.create_gara(
                number=1,
                name="Test Gara",
                date=date.today(),
                discipline="palla_8",
                distance=5,
            )

    @patch("models.competition.services.db")
    @patch("models.competition.services.Gara")
    def test_create_gara_with_campionato_id(self, mock_gara_class, mock_db):
        """Test create_gara with campionato_id."""
        mock_gara = Mock()
        mock_gara_class.return_value = mock_gara

        result = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=date.today(),
            discipline="palla_8",
            distance=5,
            campionato_id=1,
            extra_field="extra_value",
        )

        assert result == mock_gara
        mock_gara_class.assert_called_once()
        mock_db.session.add.assert_called_once_with(mock_gara)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    @patch("models.competition.services.Gara")
    def test_create_gara_with_director_id(self, mock_gara_class, mock_db):
        """Test create_gara with director_id (standalone gara)."""
        mock_gara = Mock()
        mock_gara_class.return_value = mock_gara

        result = GaraService.create_gara(
            number=1,
            name="Test Gara",
            date=date.today(),
            discipline="palla_8",
            distance=5,
            director_id=1,
        )

        assert result == mock_gara
        mock_db.session.add.assert_called_once_with(mock_gara)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_get_gara_by_id_success(self, mock_db):
        """Test get_gara_by_id returns gara when found."""
        mock_gara = Mock()
        mock_db.session.get.return_value = mock_gara

        result = GaraService.get_gara_by_id(1)

        assert result == mock_gara
        mock_db.session.get.assert_called_once_with(Gara, 1)

    @patch("models.competition.services.db")
    def test_get_gara_by_id_not_found(self, mock_db):
        """Test get_gara_by_id returns None when not found."""
        mock_db.session.get.return_value = None

        result = GaraService.get_gara_by_id(1)

        assert result is None

    @patch("models.competition.services.db")
    def test_update_gara_not_found(self, mock_db):
        """Test update_gara raises error when gara not found."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Gara 1 non trovata"):
            GaraService.update_gara(1, name="New Name")

    @patch("models.competition.services.db")
    def test_update_gara_cannot_be_modified(self, mock_db):
        """Test update_gara raises error when gara cannot be modified."""
        mock_gara = Mock()
        mock_gara.can_be_modified.return_value = False
        mock_db.session.get.return_value = mock_gara

        with pytest.raises(ValueError, match="Impossibile modificare la gara"):
            GaraService.update_gara(1, name="New Name")

    @patch("models.competition.services.db")
    def test_update_gara_success_with_date_str(self, mock_db):
        """Test update_gara success with date_str field."""
        mock_gara = Mock()
        mock_gara.can_be_modified.return_value = True
        mock_db.session.get.return_value = mock_gara

        result = GaraService.update_gara(
            1, name="New Name", discipline="new_discipline", date_str="2024-12-25"
        )

        assert result == mock_gara
        assert mock_gara.name == "New Name"
        assert mock_gara.discipline == "new_discipline"
        assert mock_gara.date == date(2024, 12, 25)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_update_gara_skip_nonexistent_fields(self, mock_db):
        """Test update_gara skips fields that don't exist on the model."""
        mock_gara = Mock()
        mock_gara.can_be_modified.return_value = True
        mock_db.session.get.return_value = mock_gara

        # Mock hasattr to return False for 'nonexistent_field'
        original_hasattr = hasattr

        def mock_hasattr(obj, name):
            if name == "nonexistent_field":
                return False
            return original_hasattr(obj, name)

        with patch("builtins.hasattr", side_effect=mock_hasattr):
            result = GaraService.update_gara(
                1, name="New Name", nonexistent_field="should_be_ignored"
            )

        assert result == mock_gara
        assert mock_gara.name == "New Name"
        # nonexistent_field should not be set

    @patch("models.competition.services.db")
    def test_delete_gara_not_found(self, mock_db):
        """Test delete_gara raises error when gara not found."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Gara 1 non trovata"):
            GaraService.delete_gara(1)

    @patch("models.competition.services.db")
    def test_delete_gara_cannot_be_deleted(self, mock_db):
        """Test delete_gara raises error when gara cannot be deleted."""
        mock_gara = Mock()
        mock_gara.can_be_deleted.return_value = False
        mock_db.session.get.return_value = mock_gara

        with pytest.raises(ValueError, match="Impossibile cancellare la gara"):
            GaraService.delete_gara(1)

    @patch("models.competition.services.db")
    def test_delete_gara_success(self, mock_db):
        """Test delete_gara success."""
        mock_gara = Mock()
        mock_gara.can_be_deleted.return_value = True
        mock_db.session.get.return_value = mock_gara

        GaraService.delete_gara(1)

        mock_db.session.delete.assert_called_once_with(mock_gara)
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
            GaraService.open_inscriptions(1, start_date, end_date)

    @patch("models.competition.services.ProvaStateMachine.to_inscription")
    @patch("models.competition.services.db")
    def test_open_inscriptions_gara_not_found(self, mock_db, mock_to_inscription):
        """Test open_inscriptions when gara not found."""
        mock_db.session.get.return_value = None
        start_date = datetime(2024, 1, 5)
        end_date = datetime(2024, 1, 10)

        with pytest.raises(ValueError, match="Gara 1 non trovata"):
            GaraService.open_inscriptions(1, start_date, end_date)

    @patch("models.competition.services.ProvaStateMachine.to_inscription")
    @patch("models.competition.services.db")
    def test_open_inscriptions_success(self, mock_db, mock_to_inscription):
        """Test open_inscriptions success."""
        mock_gara = Mock()
        mock_db.session.get.return_value = mock_gara
        mock_to_inscription.return_value = mock_gara

        start_date = datetime(2024, 1, 5)
        end_date = datetime(2024, 1, 10)

        result = GaraService.open_inscriptions(1, start_date, end_date)

        assert result == mock_gara
        assert mock_gara.inscription_start == start_date
        assert mock_gara.inscription_end == end_date
        mock_to_inscription.assert_called_once_with(mock_gara)

    @patch("models.competition.services.ProvaStateMachine")
    @patch("models.competition.services.db")
    @patch("models.competition.services.datetime")
    def test_modify_inscription_dates_gara_not_found(
        self, mock_datetime, mock_db, mock_state_machine
    ):
        """Test modify_inscription_dates when gara not found."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Gara 1 non trovata"):
            GaraService.modify_inscription_dates(
                1, datetime(2024, 1, 5), datetime(2024, 1, 10)
            )

    @patch("models.competition.services.ProvaStateMachine")
    @patch("models.competition.services.db")
    @patch("models.competition.services.datetime")
    def test_modify_inscription_dates_cannot_modify(
        self, mock_datetime, mock_db, mock_state_machine
    ):
        """Test modify_inscription_dates when dates cannot be modified."""
        mock_gara = Mock()
        mock_gara.can_modify_inscription_dates.return_value = False
        mock_db.session.get.return_value = mock_gara

        with pytest.raises(ValueError, match="Impossibile modificare le date"):
            GaraService.modify_inscription_dates(
                1, datetime(2024, 1, 5), datetime(2024, 1, 10)
            )

    @patch("models.competition.services.ProvaStateMachine")
    @patch("models.competition.services.db")
    @patch("models.competition.services.datetime")
    def test_modify_inscription_dates_invalid_range(
        self, mock_datetime, mock_db, mock_state_machine
    ):
        """Test modify_inscription_dates with invalid date range."""
        mock_gara = Mock()
        mock_gara.can_modify_inscription_dates.return_value = True
        mock_db.session.get.return_value = mock_gara

        with pytest.raises(
            ValueError, match="La data di inizio deve essere precedente"
        ):
            GaraService.modify_inscription_dates(
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

        mock_gara = Mock()
        mock_gara.can_modify_inscription_dates.return_value = True
        mock_db.session.get.return_value = mock_gara
        mock_state_machine.reopen_setup.return_value = mock_gara

        start_date = datetime(2024, 1, 5)  # Future
        end_date = datetime(2024, 1, 10)

        result = GaraService.modify_inscription_dates(1, start_date, end_date)

        assert result == mock_gara
        assert mock_gara.inscription_start == start_date
        assert mock_gara.inscription_end == end_date
        mock_state_machine.reopen_setup.assert_called_once_with(mock_gara)

    @patch("models.competition.services.ProvaStateMachine")
    @patch("models.competition.services.db")
    @patch("models.competition.services.datetime")
    def test_modify_inscription_dates_current_period(
        self, mock_datetime, mock_db, mock_state_machine
    ):
        """Test modify_inscription_dates within current inscription period."""
        mock_now = datetime(2024, 1, 7)  # Between start and end
        mock_datetime.utcnow.return_value = mock_now

        mock_gara = Mock()
        mock_gara.can_modify_inscription_dates.return_value = True
        mock_db.session.get.return_value = mock_gara
        mock_state_machine.to_inscription.return_value = mock_gara

        start_date = datetime(2024, 1, 5)
        end_date = datetime(2024, 1, 10)

        result = GaraService.modify_inscription_dates(1, start_date, end_date)

        assert result == mock_gara
        mock_state_machine.to_inscription.assert_called_once_with(mock_gara)

    @patch("models.competition.services.create_round_matches")
    @patch("models.competition.services.ProvaStateMachine.start_playing")
    @patch("models.competition.services.db")
    @patch("models.competition.services.random")
    def test_start_first_round_gara_not_found(
        self, mock_random, mock_db, mock_start_playing, mock_create_matches
    ):
        """Test start_first_round when gara not found."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Gara 1 non trovata"):
            GaraService.start_first_round(1)

    @patch("models.competition.services.create_round_matches")
    @patch("models.competition.services.ProvaStateMachine.start_playing")
    @patch("models.competition.services.db")
    @patch("models.competition.services.random")
    def test_start_first_round_already_started(
        self, mock_random, mock_db, mock_start_playing, mock_create_matches
    ):
        """Test start_first_round when gara already started."""
        mock_gara = Mock()
        mock_gara.current_round = 1  # Already started
        mock_db.session.get.return_value = mock_gara

        with pytest.raises(ValueError, match="La gara è già iniziata"):
            GaraService.start_first_round(1)

    @patch("models.competition.services.create_round_matches")
    @patch("models.competition.services.ProvaStateMachine.start_playing")
    @patch("models.competition.services.db")
    @patch("models.competition.services.random")
    def test_start_first_round_insufficient_participants(
        self, mock_random, mock_db, mock_start_playing, mock_create_matches
    ):
        """Test start_first_round with insufficient participants."""
        mock_gara = Mock()
        mock_gara.current_round = 0
        mock_gara.min_participants = 4
        mock_db.session.get.return_value = mock_gara

        # Mock only 2 inscriptions, need 4
        mock_inscriptions = [Mock(), Mock()]
        mock_db.session.query.return_value.filter_by.return_value.all.return_value = (
            mock_inscriptions
        )

        with pytest.raises(ValueError, match="Servono almeno 4 iscritti"):
            GaraService.start_first_round(1)


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
        mock_inscription_class.assert_called_once_with(user_id=1, gara_id=1)
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
