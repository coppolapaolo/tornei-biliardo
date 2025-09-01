"""
Additional comprehensive tests for models/competition/services.py
Targeting the remaining 198 missed statements (currently 41% coverage) for maximum impact toward 90% goal.
Focus on uncovered methods and edge cases.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from models.competition.services import (
    ProvaService,
    InscriptionService,
    ProvaStateMachine,
)
from models.status_enum import ProvaStatus
from models.exceptions import InvalidTransitionError


class TestProvaServiceAdditional:
    """Additional tests for ProvaService targeting missed coverage areas."""

    @patch("models.competition.services.db")
    def test_create_amalfi_round_success(self, mock_db):
        """Test successful Amalfi round creation."""
        mock_prova = Mock()
        mock_db.session.get.return_value = mock_prova

        # Mock matches data
        mock_match1 = Mock()
        mock_match1.is_bye = False
        mock_match1.is_trio = False
        mock_match2 = Mock()
        mock_match2.is_bye = True
        mock_match2.is_trio = False
        mock_match3 = Mock()
        mock_match3.is_bye = False
        mock_match3.is_trio = True

        mock_matches = [mock_match1, mock_match2, mock_match3]

        with patch(
            "models.competition.services.create_amalfi_round_matches"
        ) as mock_create:
            # Mock query for matches
            mock_query = Mock()
            mock_query.filter_by.return_value.all.return_value = mock_matches
            mock_db.session.query.return_value = mock_query

            # Mock trio match count
            mock_trio_query = Mock()
            mock_trio_query.join.return_value.filter.return_value.count.return_value = 1
            with patch("models.competition.services.TrioMatch") as mock_trio:
                mock_db.session.query.side_effect = [mock_query, mock_trio_query]

                result = ProvaService.create_amalfi_round(123, 2)

                assert result == (3, 1, 1, 1)  # total, normal, bye, trio
                mock_create.assert_called_once_with(mock_prova, 2)
                mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_create_amalfi_round_prova_not_found(self, mock_db):
        """Test Amalfi round creation with non-existent prova."""
        mock_db.session.get.return_value = None

        with pytest.raises(ValueError, match="Prova 999 non trovata"):
            ProvaService.create_amalfi_round(999, 2)

    @patch("models.competition.services.db")
    def test_create_amalfi_round_exception_handling(self, mock_db):
        """Test Amalfi round creation with exception handling."""
        mock_prova = Mock()
        mock_db.session.get.return_value = mock_prova

        with patch(
            "models.competition.services.create_amalfi_round_matches"
        ) as mock_create:
            mock_create.side_effect = Exception("Amalfi engine error")

            with pytest.raises(
                ValueError, match="Errore durante la creazione del turno"
            ):
                ProvaService.create_amalfi_round(123, 2)

            mock_db.session.rollback.assert_called_once()

    @patch("flask.abort")
    @patch("models.competition.services.db")
    def test_add_trio_rack_trio_not_found(self, mock_db, mock_abort):
        """Test adding trio rack with non-existent trio."""
        mock_db.session.get.return_value = None

        ProvaService.add_trio_rack(999, 123)
        mock_abort.assert_called_once_with(404)

    @patch("models.competition.services.db")
    def test_add_trio_rack_invalid_winner(self, mock_db):
        """Test adding trio rack with invalid winner."""
        mock_trio = Mock()
        mock_trio.player1_id = 1
        mock_trio.player2_id = 2
        mock_trio.player3_id = 3
        mock_db.session.get.return_value = mock_trio

        with pytest.raises(ValueError, match="Vincitore non valido per questo trio"):
            ProvaService.add_trio_rack(123, 999)

    @patch("models.competition.services.db")
    def test_add_trio_rack_success(self, mock_db):
        """Test successful trio rack addition."""
        mock_trio = Mock()
        mock_trio.player1_id = 1
        mock_trio.player2_id = 2
        mock_trio.player3_id = 3
        mock_trio.is_completed = True
        mock_trio.winner_id = 1

        # Mock current state
        mock_player1 = Mock()
        mock_player1.id = 1
        mock_player1.username = "player1"
        mock_player2 = Mock()
        mock_player2.id = 2
        mock_player2.username = "player2"
        mock_waiting = Mock()
        mock_waiting.id = 3
        mock_waiting.username = "player3"

        mock_state = {
            "current_players": [mock_player1, mock_player2],
            "waiting_player": mock_waiting,
            "scores": {"1": 5, "2": 3, "3": 2},
        }
        mock_trio.get_current_state.return_value = mock_state

        mock_db.session.get.return_value = mock_trio

        result = ProvaService.add_trio_rack(123, 1)

        assert result["success"] is True
        assert result["trio_completed"] is True
        assert result["winner_id"] == 1
        assert len(result["current_state"]["current_players"]) == 2
        mock_trio.add_rack_win.assert_called_once_with(1)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_add_trio_rack_exception_handling(self, mock_db):
        """Test trio rack addition with exception handling."""
        mock_trio = Mock()
        mock_trio.player1_id = 1
        mock_trio.player2_id = 2
        mock_trio.player3_id = 3
        mock_trio.add_rack_win.side_effect = Exception("Database error")
        mock_db.session.get.return_value = mock_trio

        with pytest.raises(ValueError, match="Errore durante aggiunta rack"):
            ProvaService.add_trio_rack(123, 1)

        mock_db.session.rollback.assert_called_once()

    @patch("flask.abort")
    @patch("models.competition.services.db")
    def test_reset_trio_not_found(self, mock_db, mock_abort):
        """Test trio reset with non-existent trio."""
        mock_db.session.get.return_value = None

        ProvaService.reset_trio(999)
        mock_abort.assert_called_once_with(404)

    @patch("models.competition.services.MatchService")
    @patch("models.competition.services.db")
    def test_reset_trio_success(self, mock_db, mock_match_service):
        """Test successful trio reset."""
        mock_trio = Mock()
        mock_trio.player1_id = 1
        mock_trio.player2_id = 2
        mock_trio.player3_id = 3
        mock_trio.match_id = 456

        mock_match = Mock()
        mock_trio.match = mock_match

        # Mock match object for direct access
        mock_match_obj = Mock()

        def mock_get_side_effect(model, id):
            if id == 123:  # trio_id
                return mock_trio
            elif id == 456:  # match_id
                return mock_match_obj
            return None

        mock_db.session.get.side_effect = mock_get_side_effect

        ProvaService.reset_trio(123)

        # Verify trio reset
        assert mock_trio.player1_racks == 0
        assert mock_trio.player2_racks == 0
        assert mock_trio.player3_racks == 0
        assert mock_trio.current_player1_id == 1
        assert mock_trio.current_player2_id == 2
        assert mock_trio.waiting_player_id == 3
        assert mock_trio.is_completed is False
        assert mock_trio.winner_id is None

        # Verify match reset
        mock_match_service.reset_to_pending.assert_called_once_with(
            456, clear_validation=True
        )
        assert mock_match_obj.winner_id is None
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.MatchService")
    @patch("models.competition.services.db")
    def test_reset_trio_exception_handling(self, mock_db, mock_match_service):
        """Test trio reset with exception handling."""
        mock_trio = Mock()
        mock_trio.match_id = 456
        mock_match_service.reset_to_pending.side_effect = Exception("Reset error")

        def mock_get_side_effect(model, id):
            if id == 123:
                return mock_trio
            return None

        mock_db.session.get.side_effect = mock_get_side_effect

        with pytest.raises(ValueError, match="Errore durante reset trio"):
            ProvaService.reset_trio(123)

        mock_db.session.rollback.assert_called_once()

    @patch("models.competition.services.select")
    @patch("models.competition.services.TournamentDirector")
    @patch("models.competition.services.db")
    def test_get_director_provas(self, mock_db, mock_td_class, mock_select):
        """Test getting provas for a director."""
        mock_director_id = 123

        # Mock subquery
        mock_subquery = Mock()
        mock_td_query = Mock()
        mock_td_query.filter.return_value.subquery.return_value = mock_subquery
        mock_db.session.query.return_value = mock_td_query

        # Mock main query
        mock_main_query = Mock()
        mock_filtered_query = Mock()
        mock_ordered_query = Mock()
        mock_provas = [Mock(), Mock()]

        mock_main_query.filter.return_value = mock_filtered_query
        mock_filtered_query.order_by.return_value = mock_ordered_query
        mock_ordered_query.all.return_value = mock_provas

        # Set up mock_db.session.query to return different mocks for different calls
        def mock_query_side_effect(model):
            if model == mock_td_class.tournament_id:
                return mock_td_query
            else:  # Prova query
                return mock_main_query

        mock_db.session.query.side_effect = mock_query_side_effect

        result = ProvaService.get_director_provas(mock_director_id)

        assert result == mock_provas

    def test_validate_prova_data_all_valid(self):
        """Test prova data validation with all valid data."""
        data = {
            "name": "Test Prova",
            "discipline": "palla_8",
            "distance": "5",
            "entry_fee": "10.50",
            "number": "1",
            "min_participants": "2",
            "max_participants": "16",
            "inscription_start": "2024-01-15",
            "inscription_end": "2024-01-20",
            "rounds_count": "5",
        }

        errors = ProvaService.validate_prova_data(data)
        assert errors == {}

    def test_validate_prova_data_all_errors(self):
        """Test prova data validation with all possible errors."""
        data = {
            "name": "",
            "discipline": "",
            "distance": "",
            "entry_fee": "-5",
            "number": "0",
            "min_participants": "1",
            "max_participants": "1",  # Less than min
            "inscription_start": "2024-01-20",
            "inscription_end": "2024-01-15",  # Before start
            "rounds_count": "0",
        }

        errors = ProvaService.validate_prova_data(data)

        assert "name" in errors
        assert "discipline" in errors
        assert "distance" in errors
        assert "entry_fee" in errors
        assert "negativa" in errors["entry_fee"]  # Test requirement
        assert "number" in errors
        assert "min_participants" in errors
        assert "max_participants" in errors
        assert ">= min" in errors["max_participants"]  # Test requirement
        assert "inscription_end" in errors  # Test requirement
        assert "rounds_count" in errors

    def test_validate_prova_data_invalid_types(self):
        """Test prova data validation with invalid data types."""
        data = {
            "distance": "not_a_number",
            "entry_fee": "not_a_float",
            "number": "not_an_int",
            "min_participants": "not_an_int",
            "max_participants": "not_an_int",
            "inscription_start": "invalid_date",
            "inscription_end": "invalid_date",
            "rounds_count": "not_an_int",
        }

        errors = ProvaService.validate_prova_data(data)

        assert "distance" in errors
        assert "entry_fee" in errors
        assert "number" in errors
        assert "min_participants" in errors
        assert "max_participants" in errors
        assert "inscription_start" in errors
        assert "inscription_end" in errors
        assert "rounds_count" in errors

    def test_validate_prova_data_optional_fields_empty(self):
        """Test prova data validation with optional fields empty."""
        data = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "5",
            "entry_fee": "",
            "number": "",
            "min_participants": "",  # Should default to 2
            "max_participants": "",
            "inscription_start": "",
            "inscription_end": "",
            "rounds_count": "",
        }

        errors = ProvaService.validate_prova_data(data)

        # Should not have errors for empty optional fields
        assert "entry_fee" not in errors
        assert "number" not in errors
        assert "max_participants" not in errors
        assert "inscription_start" not in errors
        assert "inscription_end" not in errors
        assert "rounds_count" not in errors

        # min_participants defaults to 2, so no error expected
        assert "min_participants" not in errors

    @patch("models.competition.services.db")
    def test_to_inscription_with_dates(self, mock_db):
        """Test ProvaService.to_inscription with date validation."""
        mock_prova = Mock()
        mock_db.session.get.return_value = mock_prova

        start_date = datetime(2024, 1, 15, 10, 0)
        end_date = datetime(2024, 1, 20, 18, 0)

        with patch.object(ProvaStateMachine, "to_inscription") as mock_state_machine:
            mock_state_machine.return_value = mock_prova

            result = ProvaService.to_inscription(123, start_date, end_date)

            assert result == mock_prova
            assert mock_prova.inscription_start == start_date
            assert mock_prova.inscription_end == end_date
            mock_state_machine.assert_called_once_with(mock_prova)

    @patch("models.competition.services.db")
    def test_to_inscription_invalid_dates(self, mock_db):
        """Test ProvaService.to_inscription with invalid date range."""
        mock_prova = Mock()
        mock_db.session.get.return_value = mock_prova

        start_date = datetime(2024, 1, 20, 10, 0)
        end_date = datetime(2024, 1, 15, 18, 0)  # Before start

        with pytest.raises(ValueError, match="data di inizio deve essere precedente"):
            ProvaService.to_inscription(123, start_date, end_date)

    @patch("models.competition.services.ProvaStateMachine")
    @patch("models.competition.services.db")
    def test_reopen_setup_success(self, mock_db, mock_state_machine):
        """Test successful reopen_setup."""
        mock_prova = Mock()
        mock_db.session.get.return_value = mock_prova
        mock_state_machine.reopen_setup.return_value = mock_prova

        result = ProvaService.reopen_setup(123)

        assert result == mock_prova
        mock_state_machine.reopen_setup.assert_called_once_with(mock_prova)

    @patch("models.competition.services.ProvaStateMachine")
    @patch("models.competition.services.db")
    def test_start_playing_success(self, mock_db, mock_state_machine):
        """Test successful start_playing."""
        mock_prova = Mock()
        mock_db.session.get.return_value = mock_prova
        mock_state_machine.start_playing.return_value = mock_prova

        result = ProvaService.start_playing(123)

        assert result == mock_prova
        mock_state_machine.start_playing.assert_called_once_with(mock_prova)

    @patch("models.competition.services.ProvaStateMachine")
    @patch("models.competition.services.db")
    def test_complete_success(self, mock_db, mock_state_machine):
        """Test successful complete."""
        mock_prova = Mock()
        mock_db.session.get.return_value = mock_prova
        mock_state_machine.complete.return_value = mock_prova

        result = ProvaService.complete(123)

        assert result == mock_prova
        mock_state_machine.complete.assert_called_once_with(mock_prova)


class TestProvaStateMachineAdditional:
    """Additional tests for ProvaStateMachine edge cases."""

    def test_require_success(self):
        """Test successful _require check."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.SETUP.value

        # Should not raise
        ProvaStateMachine._require(mock_prova, ProvaStatus.SETUP)

    def test_require_failure(self):
        """Test failed _require check."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.PLAYING.value

        with pytest.raises(InvalidTransitionError, match="Transizione non ammessa"):
            ProvaStateMachine._require(mock_prova, ProvaStatus.SETUP)

    def test_require_none_status_defaults_to_setup(self):
        """Test _require with None status defaults to SETUP."""
        mock_prova = Mock()
        mock_prova.status = None

        # Should not raise since None defaults to SETUP
        ProvaStateMachine._require(mock_prova, ProvaStatus.SETUP)

    @patch("models.competition.services.db")
    def test_start_playing_insufficient_inscriptions(self, mock_db):
        """Test start_playing with insufficient inscriptions."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.INSCRIPTION.value
        mock_prova.inscriptions = [Mock()]  # Only 1 inscription

        with pytest.raises(
            InvalidTransitionError, match="Numero iscritti insufficiente"
        ):
            ProvaStateMachine.start_playing(mock_prova)

    @patch("models.competition.services.db")
    def test_start_playing_with_current_round_handling(self, mock_db):
        """Test start_playing with current_round attribute handling."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.INSCRIPTION.value
        mock_prova.inscriptions = [Mock(), Mock()]  # 2 inscriptions
        mock_prova.current_round = 0

        ProvaStateMachine.start_playing(mock_prova)

        # Verify current_round was set to 1
        assert mock_prova.current_round == 1
        assert mock_prova.status == ProvaStatus.PLAYING.value
        mock_db.session.add.assert_called_once_with(mock_prova)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_start_playing_no_current_round_attribute(self, mock_db):
        """Test start_playing when prova doesn't have current_round attribute."""
        mock_prova = Mock()
        mock_prova.status = ProvaStatus.INSCRIPTION.value
        mock_prova.inscriptions = [Mock(), Mock()]
        # Remove current_round attribute
        delattr(mock_prova, "current_round")

        # Should not raise even without current_round attribute
        ProvaStateMachine.start_playing(mock_prova)

        assert mock_prova.status == ProvaStatus.PLAYING.value


class TestInscriptionServiceAdditional:
    """Additional tests for InscriptionService edge cases."""

    @patch("models.competition.services.db")
    def test_inscribe_user_database_integration(self, mock_db):
        """Test inscribe_user with more realistic database behavior."""
        # Mock existing inscription not found
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = None
        mock_db.session.query.return_value = mock_query

        # Mock new inscription creation
        with patch("models.competition.services.Inscription") as mock_inscription_class:
            mock_inscription = Mock()
            mock_inscription_class.return_value = mock_inscription

            result = InscriptionService.inscribe_user(123, 456)

            assert result == mock_inscription
            mock_inscription_class.assert_called_once_with(user_id=123, prova_id=456)
            mock_db.session.add.assert_called_once_with(mock_inscription)
            mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_uninscribe_user_database_integration(self, mock_db):
        """Test uninscribe_user with more realistic database behavior."""
        mock_inscription = Mock()
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = mock_inscription
        mock_db.session.query.return_value = mock_query

        result = InscriptionService.uninscribe_user(123, 456)

        assert result is True
        mock_db.session.delete.assert_called_once_with(mock_inscription)
        mock_db.session.commit.assert_called_once()

    @patch("models.competition.services.db")
    def test_uninscribe_user_not_found_database_integration(self, mock_db):
        """Test uninscribe_user when inscription not found."""
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = None
        mock_db.session.query.return_value = mock_query

        result = InscriptionService.uninscribe_user(123, 456)

        assert result is False
        mock_db.session.delete.assert_not_called()
        mock_db.session.commit.assert_not_called()
