"""Unit tests for campionato management."""

import pytest
from datetime import date, timedelta

from models import User, Campionato
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole
from models.campionato.services import TournamentService
from models.competition.services import GaraService


@pytest.mark.unit
class TestCampionatoModel:
    """Test Campionato model functionality."""

    def test_create_campionato(self, db_session):
        """Test creating a campionato."""
        campionato = Campionato(
            name="Test Tournament",
            campionato_type="Amalfi",
            without_x=False,
            final_playoffs=True,
            challenge_mode=False,
            is_active=True,
        )
        db_session.add(campionato)
        db_session.commit()

        assert campionato.id is not None
        assert campionato.name == "Test Tournament"
        assert campionato.campionato_type == "Amalfi"
        assert campionato.without_x is False
        assert campionato.final_playoffs is True
        assert campionato.challenge_mode is False
        assert campionato.is_active is True
        assert campionato.created_at is not None

    def test_campionato_types(self, db_session):
        """Test different campionato types."""
        types = ["Amalfi", "Round Robin", "Elimination"]

        for ctype in types:
            campionato = Campionato(
                name=f"Test {ctype}", campionato_type=ctype, is_active=True
            )
            db_session.add(campionato)

        db_session.commit()

        saved_campionati = Campionato.query.all()
        assert len(saved_campionati) == 3

        for campionato, expected_type in zip(saved_campionati, types):
            assert campionato.campionato_type == expected_type

    def test_campionato_options(self, db_session):
        """Test campionato boolean options."""
        # Test all combinations of boolean options
        option_combinations = [
            (True, True, True),
            (False, False, False),
            (True, False, True),
            (False, True, False),
        ]

        for without_x, final_playoffs, challenge_mode in option_combinations:
            campionato = Campionato(
                name=f"Test {without_x}_{final_playoffs}_{challenge_mode}",
                campionato_type="Amalfi",
                without_x=without_x,
                final_playoffs=final_playoffs,
                challenge_mode=challenge_mode,
                is_active=True,
            )
            db_session.add(campionato)

        db_session.commit()

        saved_campionati = Campionato.query.all()
        assert len(saved_campionati) == 4

    def test_campionato_can_be_modified(self, db_session):
        """Test campionato modification rules."""
        # Create campionato
        campionato = Campionato(
            name="Modifiable Tournament", campionato_type="Amalfi", is_active=True
        )
        db_session.add(campionato)
        db_session.commit()

        # Initially should be modifiable
        assert campionato.can_be_modified() is True

        # Add a gara with inscriptions
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add(director)
        db_session.commit()

        gara = GaraService.create_gara(
            campionato_id=campionato.id,
            number=1,
            name="Test Competition",
            date=date.today() + timedelta(days=7),
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            best_of=True,
        )

        # Still modifiable without inscriptions
        assert campionato.can_be_modified() is True

        # Add inscription
        player = User(
            username="player", email="player@test.com", role=UserRole.PLAYER.value
        )
        db_session.add(player)
        db_session.commit()

        from models import Inscription

        inscription = Inscription(user_id=player.id, gara_id=gara.id)
        db_session.add(inscription)
        db_session.commit()

        # Now should not be modifiable
        assert campionato.can_be_modified() is False

    def test_campionato_can_be_deleted(self, db_session):
        """Test campionato deletion rules."""
        # Create campionato
        campionato = Campionato(
            name="Deletable Tournament", campionato_type="Amalfi", is_active=True
        )
        db_session.add(campionato)
        db_session.commit()

        # Initially should be deletable
        assert campionato.can_be_deleted() is True

        # Add a gara without inscriptions
        gara = GaraService.create_gara(
            campionato_id=campionato.id,
            number=1,
            name="Test Competition",
            date=date.today() + timedelta(days=7),
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            best_of=True,
        )

        # Still deletable without inscriptions
        assert campionato.can_be_deleted() is True

        # Add inscription
        player = User(
            username="player", email="player@test.com", role=UserRole.PLAYER.value
        )
        db_session.add(player)
        db_session.commit()

        from models import Inscription

        inscription = Inscription(user_id=player.id, gara_id=gara.id)
        db_session.add(inscription)
        db_session.commit()

        # Now should not be deletable
        assert campionato.can_be_deleted() is False


@pytest.mark.unit
class TestTournamentService:
    """Test TournamentService functionality."""

    def test_create_campionato_with_director(self, db_session):
        """Test creating campionato with director assignment."""
        # Create director
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add(director)
        db_session.commit()

        # Create campionato
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Service Test Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
            without_x=True,
            final_playoffs=False,
            challenge_mode=True,
            is_active=True,
        )

        assert campionato is not None
        assert campionato.name == "Service Test Tournament"
        assert campionato.campionato_type == "Amalfi"
        assert campionato.without_x is True
        assert campionato.final_playoffs is False
        assert campionato.challenge_mode is True
        assert campionato.is_active is True

        # Check director assignment was created
        assignment = (
            db_session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == campionato.id,
                DirectorAssignment.user_id == director.id,
            )
            .first()
        )
        assert assignment is not None
        assert assignment.assigned_by_id == director.id

    def test_create_campionato_invalid_user(self, db_session):
        """Test creating campionato with invalid user."""
        tournament_service = TournamentService()

        with pytest.raises(Exception):  # Should raise an error for non-existent user
            tournament_service.create_campionato_with_director(
                name="Invalid User Tournament",
                creator_user_id=99999,
                campionato_type="Amalfi",
            )

    def test_get_campionato_detail_data(self, db_session):
        """Test getting campionato detail data."""
        # Create director and campionato
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add(director)
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Detail Test Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )

        # Add some gare
        _ = GaraService.create_gara(
            campionato_id=campionato.id,
            number=1,
            name="First Competition",
            date=date.today() + timedelta(days=7),
            location="Test Location",
            description="First competition",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            best_of=True,
        )

        _ = GaraService.create_gara(
            campionato_id=campionato.id,
            number=2,
            name="Second Competition",
            date=date.today() + timedelta(days=14),
            location="Test Location",
            description="Second competition",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=20.0,
            discipline="palla 8",
            distance=5,
            best_of=False,
        )

        # Get detail data
        detail_data = tournament_service.get_campionato_detail_data(campionato.id)

        assert "campionato" in detail_data
        assert "gare" in detail_data
        assert "candidate_directors" in detail_data

        assert detail_data["campionato"] == campionato
        assert len(detail_data["gare"]) == 2
        assert len(detail_data["candidate_directors"]) >= 1  # At least the director

    def test_update_campionato(self, db_session):
        """Test updating campionato."""
        # Create director and campionato
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add(director)
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Original Name",
            creator_user_id=director.id,
            campionato_type="Amalfi",
            without_x=False,
            final_playoffs=False,
            challenge_mode=False,
        )

        # Update campionato
        updated_campionato = tournament_service.update_campionato(
            campionato_id=campionato.id,
            name="Updated Name",
            campionato_type="Round Robin",
            without_x=True,
            final_playoffs=True,
            challenge_mode=True,
        )

        assert updated_campionato.name == "Updated Name"
        assert updated_campionato.campionato_type == "Round Robin"
        assert updated_campionato.without_x is True
        assert updated_campionato.final_playoffs is True
        assert updated_campionato.challenge_mode is True

    def test_update_campionato_with_inscriptions(self, db_session):
        """Test updating campionato that has inscriptions (should fail)."""
        # Create director and campionato
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add(director)
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Tournament with Inscriptions",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )

        # Add gara and inscription
        gara = GaraService.create_gara(
            campionato_id=campionato.id,
            number=1,
            name="Competition",
            date=date.today() + timedelta(days=7),
            location="Test Location",
            description="Competition with inscriptions",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            best_of=True,
        )

        player = User(
            username="player", email="player@test.com", role=UserRole.PLAYER.value
        )
        db_session.add(player)
        db_session.commit()

        from models import Inscription

        inscription = Inscription(user_id=player.id, gara_id=gara.id)
        db_session.add(inscription)
        db_session.commit()

        # Try to update - should raise ValueError
        with pytest.raises(ValueError):
            tournament_service.update_campionato(
                campionato_id=campionato.id,
                name="New Name",
                campionato_type="Round Robin",
            )

    def test_delete_campionato(self, db_session):
        """Test deleting campionato."""
        # Create director and campionato
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add(director)
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Tournament to Delete",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )
        campionato_id = campionato.id

        # Delete campionato
        tournament_service.delete_campionato(campionato_id)

        # Check it's deleted
        deleted_campionato = db_session.get(Campionato, campionato_id)
        assert deleted_campionato is None

        # Check director assignment is also deleted
        assignment = (
            db_session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == campionato_id,
            )
            .first()
        )
        assert assignment is None

    def test_delete_campionato_with_inscriptions(self, db_session):
        """Test deleting campionato that has inscriptions (should fail)."""
        # Create director and campionato
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add(director)
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Tournament with Inscriptions",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )

        # Add gara and inscription
        gara = GaraService.create_gara(
            campionato_id=campionato.id,
            number=1,
            name="Competition",
            date=date.today() + timedelta(days=7),
            location="Test Location",
            description="Competition with inscriptions",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            best_of=True,
        )

        player = User(
            username="player", email="player@test.com", role=UserRole.PLAYER.value
        )
        db_session.add(player)
        db_session.commit()

        from models import Inscription

        inscription = Inscription(user_id=player.id, gara_id=gara.id)
        db_session.add(inscription)
        db_session.commit()

        # Try to delete - should raise ValueError
        with pytest.raises(ValueError):
            tournament_service.delete_campionato(campionato.id)

    def test_toggle_active_status(self, db_session):
        """Test toggling campionato active status."""
        # Create director and campionato
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add(director)
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Toggle Test Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
            is_active=True,
        )

        assert campionato.is_active is True

        # Toggle to inactive
        updated_campionato = tournament_service.toggle_active_status(campionato.id)
        assert updated_campionato.is_active is False

        # Toggle back to active
        updated_campionato = tournament_service.toggle_active_status(campionato.id)
        assert updated_campionato.is_active is True

    def test_add_director(self, db_session):
        """Test adding co-director to campionato."""
        # Create directors
        main_director = User(
            username="main_director",
            email="main@test.com",
            role=UserRole.DIRECTOR.value,
        )
        co_director = User(
            username="co_director", email="co@test.com", role=UserRole.DIRECTOR.value
        )
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        db_session.add_all([main_director, co_director, admin])
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Multi-Director Tournament",
            creator_user_id=main_director.id,
            campionato_type="Amalfi",
        )

        # Add co-director
        success = tournament_service.add_director(
            campionato_id=campionato.id, user_id=co_director.id, assigned_by_id=admin.id
        )

        assert success is True

        # Check assignment was created
        assignment = (
            db_session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == campionato.id,
                DirectorAssignment.user_id == co_director.id,
            )
            .first()
        )
        assert assignment is not None
        assert assignment.assigned_by_id == admin.id

    def test_add_director_duplicate(self, db_session):
        """Test adding director who is already assigned."""
        # Create director
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        db_session.add_all([director, admin])
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Duplicate Director Test",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )

        # Try to add the same director again
        success = tournament_service.add_director(
            campionato_id=campionato.id, user_id=director.id, assigned_by_id=admin.id
        )

        assert success is False

    def test_remove_director(self, db_session):
        """Test removing co-director from campionato."""
        # Create directors
        main_director = User(
            username="main_director",
            email="main@test.com",
            role=UserRole.DIRECTOR.value,
        )
        co_director = User(
            username="co_director", email="co@test.com", role=UserRole.DIRECTOR.value
        )
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        db_session.add_all([main_director, co_director, admin])
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Remove Director Test",
            creator_user_id=main_director.id,
            campionato_type="Amalfi",
        )

        # Add co-director
        tournament_service.add_director(
            campionato_id=campionato.id, user_id=co_director.id, assigned_by_id=admin.id
        )

        # Remove co-director
        success = tournament_service.remove_director(
            campionato_id=campionato.id, user_id=co_director.id
        )

        assert success is True

        # Check assignment was removed
        assignment = (
            db_session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == campionato.id,
                DirectorAssignment.user_id == co_director.id,
            )
            .first()
        )
        assert assignment is None

    def test_remove_director_not_found(self, db_session):
        """Test removing director who is not assigned."""
        # Create directors
        main_director = User(
            username="main_director",
            email="main@test.com",
            role=UserRole.DIRECTOR.value,
        )
        other_director = User(
            username="other_director",
            email="other@test.com",
            role=UserRole.DIRECTOR.value,
        )
        db_session.add_all([main_director, other_director])
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Remove Non-Existent Director Test",
            creator_user_id=main_director.id,
            campionato_type="Amalfi",
        )

        # Try to remove director who was never added
        success = tournament_service.remove_director(
            campionato_id=campionato.id, user_id=other_director.id
        )

        assert success is False
