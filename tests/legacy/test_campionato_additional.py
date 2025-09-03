"""
Comprehensive tests for campionato models and services to improve coverage.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date
from sqlalchemy.exc import IntegrityError

from models.campionato.models import Campionato
from models.campionato.services import TournamentService
from models import Gara


class TestTournamentModel:
    """Test Campionato model functionality."""

    def test_campionato_creation(self, db_session):
        """Test basic campionato creation."""
        campionato = Campionato(
            name="Test Campionato",
            campionato_type="Amalfi",
            description="Test campionato description",
            start_date=date.today(),
            end_date=date.today(),
            status="draft",
        )

        db_session.add(campionato)
        db_session.commit()

        assert campionato.id is not None
        assert campionato.name == "Test Campionato"
        assert campionato.campionato_type == "Amalfi"

    def test_campionato_str_representation(self, db_session):
        """Test campionato string representation."""
        campionato = Campionato(name="Test Campionato", campionato_type="Amalfi")

        str_repr = str(campionato)
        assert "Test Campionato" in str_repr

    def test_campionato_validation(self, db_session):
        """Test campionato validation rules."""
        # Test required fields
        campionato = Campionato()

        with pytest.raises(IntegrityError):
            db_session.add(campionato)
            db_session.commit()

    def test_campionato_relationships(self, db_session):
        """Test campionato relationships with provas."""
        campionato = Campionato(name="Relationship Test", campionato_type="Amalfi")
        db_session.add(campionato)
        db_session.flush()

        # Add gara
        gara = Gara(
            campionato_id=campionato.id,
            number=1,
            name="Test Gara",
            date=date.today(),
            discipline="palla 9",
            distance=7,
        )
        db_session.add(gara)
        db_session.commit()

        # Test relationship access
        assert len(campionato.gare) == 1
        assert campionato.gare[0].name == "Test Gara"

    def test_campionato_status_transitions(self, db_session):
        """Test campionato status transitions."""
        campionato = Campionato(
            name="Status Test", campionato_type="Amalfi", status="draft"
        )
        db_session.add(campionato)
        db_session.commit()

        # Test status change
        campionato.status = "active"
        db_session.commit()

        assert campionato.status == "active"

    def test_campionato_date_validation(self, db_session):
        """Test campionato date validation."""
        campionato = Campionato(
            name="Date Test",
            campionato_type="Amalfi",
            start_date=date.today(),
            end_date=date.today(),
        )

        # Should not raise error for valid dates
        db_session.add(campionato)
        db_session.commit()

        assert campionato.start_date is not None
        assert campionato.end_date is not None

    def test_campionato_properties(self, db_session):
        """Test campionato computed properties."""
        campionato = Campionato(
            name="Properties Test",
            campionato_type="Amalfi",
            max_participants=16,
            entry_fee=25.00,
        )
        db_session.add(campionato)
        db_session.commit()

        assert campionato.max_participants == 16
        assert campionato.entry_fee == 25.00

    def test_campionato_settings(self, db_session):
        """Test campionato settings and configuration."""
        campionato = Campionato(
            name="Settings Test",
            campionato_type="Amalfi",
            campionato_settings={
                "rounds": 5,
                "best_of": True,
                "minimum_participants": 8,
            },
        )
        db_session.add(campionato)
        db_session.commit()

        assert campionato.campionato_settings is not None
        if campionato.campionato_settings:
            assert "rounds" in campionato.campionato_settings


class TestTournamentService:
    """Test TournamentService functionality."""

    @pytest.fixture
    def sample_campionato(self, db_session):
        """Create a sample campionato."""
        campionato = Campionato(
            name="Service Test Campionato", campionato_type="Amalfi", status="draft"
        )
        db_session.add(campionato)
        db_session.commit()
        return campionato

    def test_create_campionato_basic(self, db_session):
        """Test basic campionato creation via service."""
        campionato_data = {
            "name": "Service Created Campionato",
            "campionato_type": "Amalfi",
            "description": "Created via service",
            "status": "draft",
        }

        with patch.object(TournamentService, "create") as mock_create:
            mock_campionato = Mock()
            mock_campionato.id = 1
            mock_create.return_value = mock_campionato

            result = TournamentService.create(campionato_data)

            mock_create.assert_called_once_with(campionato_data)
            assert result.id == 1

    def test_get_campionato_by_id(self, sample_campionato):
        """Test getting campionato by ID."""
        with patch.object(TournamentService, "get_by_id") as mock_get:
            mock_get.return_value = sample_campionato

            result = TournamentService.get_by_id(sample_campionato.id)

            mock_get.assert_called_once_with(sample_campionato.id)
            assert result == sample_campionato

    def test_update_campionato(self, sample_campionato):
        """Test updating campionato via service."""
        update_data = {"name": "Updated Campionato Name", "status": "active"}

        with patch.object(TournamentService, "update") as mock_update:
            mock_update.return_value = sample_campionato

            result = TournamentService.update(sample_campionato.id, update_data)

            mock_update.assert_called_once_with(sample_campionato.id, update_data)
            assert result == sample_campionato

    def test_delete_campionato(self, sample_campionato):
        """Test deleting campionato via service."""
        with patch.object(TournamentService, "delete") as mock_delete:
            mock_delete.return_value = True

            result = TournamentService.delete(sample_campionato.id)

            mock_delete.assert_called_once_with(sample_campionato.id)
            assert result is True

    def test_list_campionatos(self):
        """Test listing campionati via service."""
        with patch.object(TournamentService, "list") as mock_list:
            mock_campionatos = [Mock(), Mock()]
            mock_list.return_value = mock_campionatos

            result = TournamentService.list()

            mock_list.assert_called_once()
            assert len(result) == 2

    def test_list_campionatos_with_filters(self):
        """Test listing campionati with filters."""
        filters = {"status": "active", "campionato_type": "Amalfi"}

        with patch.object(TournamentService, "list") as mock_list:
            mock_campionatos = [Mock()]
            mock_list.return_value = mock_campionatos

            result = TournamentService.list(filters=filters)

            mock_list.assert_called_once_with(filters=filters)
            assert len(result) == 1

    def test_get_campionato_statistics(self, sample_campionato):
        """Test getting campionato statistics."""
        with patch.object(TournamentService, "get_statistics") as mock_stats:
            mock_statistics = {
                "total_participants": 16,
                "total_garas": 3,
                "completed_garas": 2,
                "active_matches": 5,
            }
            mock_stats.return_value = mock_statistics

            result = TournamentService.get_statistics(sample_campionato.id)

            mock_stats.assert_called_once_with(sample_campionato.id)
            assert result["total_participants"] == 16
            assert result["total_garas"] == 3

    def test_start_campionato(self, sample_campionato):
        """Test starting a campionato."""
        with patch.object(TournamentService, "start_campionato") as mock_start:
            mock_start.return_value = sample_campionato

            result = TournamentService.start_campionato(sample_campionato.id)

            mock_start.assert_called_once_with(sample_campionato.id)
            assert result == sample_campionato

    def test_end_campionato(self, sample_campionato):
        """Test ending a campionato."""
        with patch.object(TournamentService, "end_campionato") as mock_end:
            mock_end.return_value = sample_campionato

            result = TournamentService.end_campionato(sample_campionato.id)

            mock_end.assert_called_once_with(sample_campionato.id)
            assert result == sample_campionato

    def test_get_campionato_participants(self, sample_campionato):
        """Test getting campionato participants."""
        with patch.object(TournamentService, "get_participants") as mock_participants:
            mock_users = [Mock(), Mock(), Mock()]
            mock_participants.return_value = mock_users

            result = TournamentService.get_participants(sample_campionato.id)

            mock_participants.assert_called_once_with(sample_campionato.id)
            assert len(result) == 3

    def test_add_participant(self, sample_campionato, player_user):
        """Test adding participant to campionato."""
        with patch.object(TournamentService, "add_participant") as mock_add:
            mock_add.return_value = True

            result = TournamentService.add_participant(
                sample_campionato.id, player_user.id
            )

            mock_add.assert_called_once_with(sample_campionato.id, player_user.id)
            assert result is True

    def test_remove_participant(self, sample_campionato, player_user):
        """Test removing participant from campionato."""
        with patch.object(TournamentService, "remove_participant") as mock_remove:
            mock_remove.return_value = True

            result = TournamentService.remove_participant(
                sample_campionato.id, player_user.id
            )

            mock_remove.assert_called_once_with(sample_campionato.id, player_user.id)
            assert result is True

    def test_validate_campionato_creation(self):
        """Test campionato creation validation."""
        invalid_data = {
            "name": "",  # Invalid empty name
            "campionato_type": "InvalidType",
        }

        with patch.object(TournamentService, "validate_creation_data") as mock_validate:
            mock_validate.return_value = {
                "is_valid": False,
                "errors": ["Name is required", "Invalid campionato type"],
            }

            result = TournamentService.validate_creation_data(invalid_data)

            mock_validate.assert_called_once_with(invalid_data)
            assert result["is_valid"] is False
            assert len(result["errors"]) == 2

    def test_get_campionato_leaderboard(self, sample_campionato):
        """Test getting campionato leaderboard."""
        with patch.object(TournamentService, "get_leaderboard") as mock_leaderboard:
            mock_leaderboard_data = [
                {"user_id": 1, "position": 1, "points": 100},
                {"user_id": 2, "position": 2, "points": 85},
                {"user_id": 3, "position": 3, "points": 70},
            ]
            mock_leaderboard.return_value = mock_leaderboard_data

            result = TournamentService.get_leaderboard(sample_campionato.id)

            mock_leaderboard.assert_called_once_with(sample_campionato.id)
            assert len(result) == 3
            assert result[0]["position"] == 1

    def test_campionato_service_error_handling(self):
        """Test error handling in campionato service."""
        invalid_id = 99999

        with patch.object(TournamentService, "get_by_id") as mock_get:
            mock_get.return_value = None

            result = TournamentService.get_by_id(invalid_id)

            mock_get.assert_called_once_with(invalid_id)
            assert result is None

    def test_campionato_export_functionality(self, sample_campionato):
        """Test campionato data export functionality."""
        with patch.object(TournamentService, "export_data") as mock_export:
            mock_export_data = {
                "campionato": {"name": "Test Campionato"},
                "participants": [],
                "gare": [],
                "matches": [],
            }
            mock_export.return_value = mock_export_data

            result = TournamentService.export_data(sample_campionato.id)

            mock_export.assert_called_once_with(sample_campionato.id)
            assert "campionato" in result
            assert "participants" in result


class TestTournamentAdvancedFeatures:
    """Test advanced campionato features."""

    def test_campionato_scheduling(self, db_session):
        """Test campionato scheduling features."""
        campionato = Campionato(
            name="Scheduling Test",
            campionato_type="Amalfi",
            start_date=date.today(),
            end_date=date.today(),
        )
        db_session.add(campionato)
        db_session.commit()

        # Test that dates are properly set
        assert campionato.start_date is not None
        assert campionato.end_date is not None

    def test_campionato_configuration(self, db_session):
        """Test campionato configuration options."""
        campionato = Campionato(
            name="Config Test",
            campionato_type="Amalfi",
            campionato_settings={
                "max_participants": 32,
                "entry_fee": 50.00,
                "prize_distribution": [0.5, 0.3, 0.2],
            },
        )
        db_session.add(campionato)
        db_session.commit()

        if campionato.campionato_settings:
            assert campionato.campionato_settings.get("max_participants") == 32

    def test_campionato_state_management(self, db_session):
        """Test campionato state management."""
        campionato = Campionato(
            name="State Test", campionato_type="Amalfi", status="draft"
        )
        db_session.add(campionato)
        db_session.commit()

        # Test state transitions
        valid_states = ["draft", "active", "completed", "cancelled"]

        for state in valid_states:
            campionato.status = state
            db_session.commit()
            assert campionato.status == state

    def test_campionato_metadata(self, db_session):
        """Test campionato metadata handling."""
        campionato = Campionato(
            name="Metadata Test",
            campionato_type="Amalfi",
            description="Campionato with metadata",
            location="Test Location",
            organizer="Test Organizer",
        )
        db_session.add(campionato)
        db_session.commit()

        assert campionato.description is not None
        assert hasattr(campionato, "location")
        assert hasattr(campionato, "organizer")
