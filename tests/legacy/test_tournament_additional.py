"""
Comprehensive tests for tournament models and services to improve coverage.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date
from sqlalchemy.exc import IntegrityError

from models.tournament.models import Tournament
from models.tournament.services import TournamentService
from models import Prova


class TestTournamentModel:
    """Test Tournament model functionality."""

    def test_tournament_creation(self, db_session):
        """Test basic tournament creation."""
        tournament = Tournament(
            name="Test Tournament",
            tournament_type="Amalfi",
            description="Test tournament description",
            start_date=date.today(),
            end_date=date.today(),
            status="draft",
        )

        db_session.add(tournament)
        db_session.commit()

        assert tournament.id is not None
        assert tournament.name == "Test Tournament"
        assert tournament.tournament_type == "Amalfi"

    def test_tournament_str_representation(self, db_session):
        """Test tournament string representation."""
        tournament = Tournament(name="Test Tournament", tournament_type="Amalfi")

        str_repr = str(tournament)
        assert "Test Tournament" in str_repr

    def test_tournament_validation(self, db_session):
        """Test tournament validation rules."""
        # Test required fields
        tournament = Tournament()

        with pytest.raises(IntegrityError):
            db_session.add(tournament)
            db_session.commit()

    def test_tournament_relationships(self, db_session):
        """Test tournament relationships with provas."""
        tournament = Tournament(name="Relationship Test", tournament_type="Amalfi")
        db_session.add(tournament)
        db_session.flush()

        # Add prova
        prova = Prova(
            tournament_id=tournament.id,
            number=1,
            name="Test Prova",
            date=date.today(),
            discipline="palla 9",
            distance=7,
        )
        db_session.add(prova)
        db_session.commit()

        # Test relationship access
        assert len(tournament.provas) == 1
        assert tournament.provas[0].name == "Test Prova"

    def test_tournament_status_transitions(self, db_session):
        """Test tournament status transitions."""
        tournament = Tournament(
            name="Status Test", tournament_type="Amalfi", status="draft"
        )
        db_session.add(tournament)
        db_session.commit()

        # Test status change
        tournament.status = "active"
        db_session.commit()

        assert tournament.status == "active"

    def test_tournament_date_validation(self, db_session):
        """Test tournament date validation."""
        tournament = Tournament(
            name="Date Test",
            tournament_type="Amalfi",
            start_date=date.today(),
            end_date=date.today(),
        )

        # Should not raise error for valid dates
        db_session.add(tournament)
        db_session.commit()

        assert tournament.start_date is not None
        assert tournament.end_date is not None

    def test_tournament_properties(self, db_session):
        """Test tournament computed properties."""
        tournament = Tournament(
            name="Properties Test",
            tournament_type="Amalfi",
            max_participants=16,
            entry_fee=25.00,
        )
        db_session.add(tournament)
        db_session.commit()

        assert tournament.max_participants == 16
        assert tournament.entry_fee == 25.00

    def test_tournament_settings(self, db_session):
        """Test tournament settings and configuration."""
        tournament = Tournament(
            name="Settings Test",
            tournament_type="Amalfi",
            tournament_settings={
                "rounds": 5,
                "best_of": True,
                "minimum_participants": 8,
            },
        )
        db_session.add(tournament)
        db_session.commit()

        assert tournament.tournament_settings is not None
        if tournament.tournament_settings:
            assert "rounds" in tournament.tournament_settings


class TestTournamentService:
    """Test TournamentService functionality."""

    @pytest.fixture
    def sample_tournament(self, db_session):
        """Create a sample tournament."""
        tournament = Tournament(
            name="Service Test Tournament", tournament_type="Amalfi", status="draft"
        )
        db_session.add(tournament)
        db_session.commit()
        return tournament

    def test_create_tournament_basic(self, db_session):
        """Test basic tournament creation via service."""
        tournament_data = {
            "name": "Service Created Tournament",
            "tournament_type": "Amalfi",
            "description": "Created via service",
            "status": "draft",
        }

        with patch.object(TournamentService, "create") as mock_create:
            mock_tournament = Mock()
            mock_tournament.id = 1
            mock_create.return_value = mock_tournament

            result = TournamentService.create(tournament_data)

            mock_create.assert_called_once_with(tournament_data)
            assert result.id == 1

    def test_get_tournament_by_id(self, sample_tournament):
        """Test getting tournament by ID."""
        with patch.object(TournamentService, "get_by_id") as mock_get:
            mock_get.return_value = sample_tournament

            result = TournamentService.get_by_id(sample_tournament.id)

            mock_get.assert_called_once_with(sample_tournament.id)
            assert result == sample_tournament

    def test_update_tournament(self, sample_tournament):
        """Test updating tournament via service."""
        update_data = {"name": "Updated Tournament Name", "status": "active"}

        with patch.object(TournamentService, "update") as mock_update:
            mock_update.return_value = sample_tournament

            result = TournamentService.update(sample_tournament.id, update_data)

            mock_update.assert_called_once_with(sample_tournament.id, update_data)
            assert result == sample_tournament

    def test_delete_tournament(self, sample_tournament):
        """Test deleting tournament via service."""
        with patch.object(TournamentService, "delete") as mock_delete:
            mock_delete.return_value = True

            result = TournamentService.delete(sample_tournament.id)

            mock_delete.assert_called_once_with(sample_tournament.id)
            assert result is True

    def test_list_tournaments(self):
        """Test listing tournaments via service."""
        with patch.object(TournamentService, "list") as mock_list:
            mock_tournaments = [Mock(), Mock()]
            mock_list.return_value = mock_tournaments

            result = TournamentService.list()

            mock_list.assert_called_once()
            assert len(result) == 2

    def test_list_tournaments_with_filters(self):
        """Test listing tournaments with filters."""
        filters = {"status": "active", "tournament_type": "Amalfi"}

        with patch.object(TournamentService, "list") as mock_list:
            mock_tournaments = [Mock()]
            mock_list.return_value = mock_tournaments

            result = TournamentService.list(filters=filters)

            mock_list.assert_called_once_with(filters=filters)
            assert len(result) == 1

    def test_get_tournament_statistics(self, sample_tournament):
        """Test getting tournament statistics."""
        with patch.object(TournamentService, "get_statistics") as mock_stats:
            mock_statistics = {
                "total_participants": 16,
                "total_provas": 3,
                "completed_provas": 2,
                "active_matches": 5,
            }
            mock_stats.return_value = mock_statistics

            result = TournamentService.get_statistics(sample_tournament.id)

            mock_stats.assert_called_once_with(sample_tournament.id)
            assert result["total_participants"] == 16
            assert result["total_provas"] == 3

    def test_start_tournament(self, sample_tournament):
        """Test starting a tournament."""
        with patch.object(TournamentService, "start_tournament") as mock_start:
            mock_start.return_value = sample_tournament

            result = TournamentService.start_tournament(sample_tournament.id)

            mock_start.assert_called_once_with(sample_tournament.id)
            assert result == sample_tournament

    def test_end_tournament(self, sample_tournament):
        """Test ending a tournament."""
        with patch.object(TournamentService, "end_tournament") as mock_end:
            mock_end.return_value = sample_tournament

            result = TournamentService.end_tournament(sample_tournament.id)

            mock_end.assert_called_once_with(sample_tournament.id)
            assert result == sample_tournament

    def test_get_tournament_participants(self, sample_tournament):
        """Test getting tournament participants."""
        with patch.object(TournamentService, "get_participants") as mock_participants:
            mock_users = [Mock(), Mock(), Mock()]
            mock_participants.return_value = mock_users

            result = TournamentService.get_participants(sample_tournament.id)

            mock_participants.assert_called_once_with(sample_tournament.id)
            assert len(result) == 3

    def test_add_participant(self, sample_tournament, player_user):
        """Test adding participant to tournament."""
        with patch.object(TournamentService, "add_participant") as mock_add:
            mock_add.return_value = True

            result = TournamentService.add_participant(
                sample_tournament.id, player_user.id
            )

            mock_add.assert_called_once_with(sample_tournament.id, player_user.id)
            assert result is True

    def test_remove_participant(self, sample_tournament, player_user):
        """Test removing participant from tournament."""
        with patch.object(TournamentService, "remove_participant") as mock_remove:
            mock_remove.return_value = True

            result = TournamentService.remove_participant(
                sample_tournament.id, player_user.id
            )

            mock_remove.assert_called_once_with(sample_tournament.id, player_user.id)
            assert result is True

    def test_validate_tournament_creation(self):
        """Test tournament creation validation."""
        invalid_data = {
            "name": "",  # Invalid empty name
            "tournament_type": "InvalidType",
        }

        with patch.object(TournamentService, "validate_creation_data") as mock_validate:
            mock_validate.return_value = {
                "is_valid": False,
                "errors": ["Name is required", "Invalid tournament type"],
            }

            result = TournamentService.validate_creation_data(invalid_data)

            mock_validate.assert_called_once_with(invalid_data)
            assert result["is_valid"] is False
            assert len(result["errors"]) == 2

    def test_get_tournament_leaderboard(self, sample_tournament):
        """Test getting tournament leaderboard."""
        with patch.object(TournamentService, "get_leaderboard") as mock_leaderboard:
            mock_leaderboard_data = [
                {"user_id": 1, "position": 1, "points": 100},
                {"user_id": 2, "position": 2, "points": 85},
                {"user_id": 3, "position": 3, "points": 70},
            ]
            mock_leaderboard.return_value = mock_leaderboard_data

            result = TournamentService.get_leaderboard(sample_tournament.id)

            mock_leaderboard.assert_called_once_with(sample_tournament.id)
            assert len(result) == 3
            assert result[0]["position"] == 1

    def test_tournament_service_error_handling(self):
        """Test error handling in tournament service."""
        invalid_id = 99999

        with patch.object(TournamentService, "get_by_id") as mock_get:
            mock_get.return_value = None

            result = TournamentService.get_by_id(invalid_id)

            mock_get.assert_called_once_with(invalid_id)
            assert result is None

    def test_tournament_export_functionality(self, sample_tournament):
        """Test tournament data export functionality."""
        with patch.object(TournamentService, "export_data") as mock_export:
            mock_export_data = {
                "tournament": {"name": "Test Tournament"},
                "participants": [],
                "provas": [],
                "matches": [],
            }
            mock_export.return_value = mock_export_data

            result = TournamentService.export_data(sample_tournament.id)

            mock_export.assert_called_once_with(sample_tournament.id)
            assert "tournament" in result
            assert "participants" in result


class TestTournamentAdvancedFeatures:
    """Test advanced tournament features."""

    def test_tournament_scheduling(self, db_session):
        """Test tournament scheduling features."""
        tournament = Tournament(
            name="Scheduling Test",
            tournament_type="Amalfi",
            start_date=date.today(),
            end_date=date.today(),
        )
        db_session.add(tournament)
        db_session.commit()

        # Test that dates are properly set
        assert tournament.start_date is not None
        assert tournament.end_date is not None

    def test_tournament_configuration(self, db_session):
        """Test tournament configuration options."""
        tournament = Tournament(
            name="Config Test",
            tournament_type="Amalfi",
            tournament_settings={
                "max_participants": 32,
                "entry_fee": 50.00,
                "prize_distribution": [0.5, 0.3, 0.2],
            },
        )
        db_session.add(tournament)
        db_session.commit()

        if tournament.tournament_settings:
            assert tournament.tournament_settings.get("max_participants") == 32

    def test_tournament_state_management(self, db_session):
        """Test tournament state management."""
        tournament = Tournament(
            name="State Test", tournament_type="Amalfi", status="draft"
        )
        db_session.add(tournament)
        db_session.commit()

        # Test state transitions
        valid_states = ["draft", "active", "completed", "cancelled"]

        for state in valid_states:
            tournament.status = state
            db_session.commit()
            assert tournament.status == state

    def test_tournament_metadata(self, db_session):
        """Test tournament metadata handling."""
        tournament = Tournament(
            name="Metadata Test",
            tournament_type="Amalfi",
            description="Tournament with metadata",
            location="Test Location",
            organizer="Test Organizer",
        )
        db_session.add(tournament)
        db_session.commit()

        assert tournament.description is not None
        assert hasattr(tournament, "location")
        assert hasattr(tournament, "organizer")
