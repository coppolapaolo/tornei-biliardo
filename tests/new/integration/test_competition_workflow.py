"""Integration tests for competition management workflows."""

import pytest
from datetime import date, timedelta

from models import User, Campionato, Gara
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole
from models.campionato.services import TournamentService
from models.competition.services import GaraService


@pytest.mark.integration
class TestCampionatoWorkflow:
    """Test campionato management workflow."""

    def test_complete_campionato_creation_workflow(self, client, db_session):
        """Test complete campionato creation workflow."""
        # Create director
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        # Login as director
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # Create campionato
        response = client.post(
            "/admin/campionato/create",
            data={
                "name": "Test Tournament",
                "campionato_type": "Amalfi",
                "without_x": "on",
                "final_playoffs": "on",
                "challenge_mode": "",  # Not checked
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Check campionato was created
        campionato = Campionato.query.filter_by(name="Test Tournament").first()
        assert campionato is not None
        assert campionato.campionato_type == "Amalfi"
        assert campionato.without_x is True
        assert campionato.final_playoffs is True
        assert campionato.challenge_mode is False
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

    def test_campionato_detail_access_workflow(self, client, db_session):
        """Test campionato detail access workflow."""
        # Create director and campionato
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Detail Test Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )

        # Add some gare
        _ = GaraService.create_gara(  # gara1 not used
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

        # Login as director
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # Access campionato detail
        response = client.get(f"/admin/campionato/{campionato.id}")
        assert response.status_code == 200
        assert b"Detail Test Tournament" in response.data
        assert b"First Competition" in response.data

    def test_campionato_edit_workflow(self, client, db_session):
        """Test campionato edit workflow."""
        # Create director and campionato
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
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

        # Login as director
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # GET edit form
        response = client.get(f"/admin/campionato/{campionato.id}/edit")
        assert response.status_code == 200
        assert b"Original Name" in response.data

        # POST edit
        response = client.post(
            f"/admin/campionato/{campionato.id}/edit",
            data={
                "name": "Updated Name",
                "campionato_type": "Round Robin",
                "without_x": "on",
                "final_playoffs": "on",
                "challenge_mode": "on",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Check campionato was updated
        db_session.refresh(campionato)
        assert campionato.name == "Updated Name"
        assert campionato.campionato_type == "Round Robin"
        assert campionato.without_x is True
        assert campionato.final_playoffs is True
        assert campionato.challenge_mode is True

    def test_campionato_delete_workflow(self, client, db_session):
        """Test campionato delete workflow."""
        # Create admin and campionato
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        admin.set_password("admin123")
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add_all([admin, director])
        db_session.commit()

        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Tournament to Delete",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )
        campionato_id = campionato.id

        # Login as admin (only admin can delete)
        client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        # Delete campionato
        response = client.post(
            f"/admin/campionato/{campionato_id}/delete", follow_redirects=True
        )
        assert response.status_code == 200

        # Check campionato was deleted
        deleted_campionato = db_session.get(Campionato, campionato_id)
        assert deleted_campionato is None

    def test_campionato_toggle_active_workflow(self, client, db_session):
        """Test campionato toggle active workflow."""
        # Create director and campionato
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
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

        # Login as director
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # Toggle to inactive
        response = client.post(
            f"/admin/campionato/{campionato.id}/toggle_active", follow_redirects=True
        )
        assert response.status_code == 200

        db_session.refresh(campionato)
        assert campionato.is_active is False

        # Toggle back to active
        response = client.post(
            f"/admin/campionato/{campionato.id}/toggle_active", follow_redirects=True
        )
        assert response.status_code == 200

        db_session.refresh(campionato)
        assert campionato.is_active is True

    def test_co_director_management_workflow(self, client, db_session):
        """Test co-director management workflow."""
        # Create users
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        admin.set_password("admin123")
        main_director = User(
            username="main_director",
            email="main@test.com",
            role=UserRole.DIRECTOR.value,
        )
        co_director = User(
            username="co_director", email="co@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add_all([admin, main_director, co_director])
        db_session.commit()

        # Create campionato with main director
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Multi-Director Tournament",
            creator_user_id=main_director.id,
            campionato_type="Amalfi",
        )

        # Login as admin
        client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        # Add co-director
        response = client.post(
            f"/admin/campionato/{campionato.id}/add_director",
            data={"user_id": str(co_director.id)},
            follow_redirects=True,
        )

        assert response.status_code == 200

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

        # Remove co-director
        response = client.post(
            f"/admin/campionato/{campionato.id}/remove_director",
            data={"user_id": str(co_director.id)},
            follow_redirects=True,
        )

        assert response.status_code == 200

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


@pytest.mark.integration
class TestGaraWorkflow:
    """Test gara (standalone competition) management workflow."""

    def test_standalone_gara_creation_workflow(self, client, db_session):
        """Test standalone gara creation workflow."""
        # Create director
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        # Login as director
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # GET creation form
        response = client.get("/director/create_standalone")
        assert response.status_code == 200

        # POST creation
        tomorrow = date.today() + timedelta(days=1)
        response = client.post(
            "/director/create_standalone",
            data={
                "name": "Standalone Test Competition",
                "date": tomorrow.strftime("%Y-%m-%d"),
                "location": "Test Location",
                "description": "Test standalone competition",
                "rounds_count": "3",
                "min_participants": "4",
                "max_participants": "16",
                "entry_fee": "15.0",
                "discipline": "palla 9",
                "distance": "7",
                "exact_number": "",  # Not checked, so best_of=True
                "withdraw_policy": "exclude",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Check gara was created
        gara = Gara.query.filter_by(name="Standalone Test Competition").first()
        assert gara is not None
        assert gara.campionato_id is None  # Standalone
        assert gara.date == tomorrow
        assert gara.location == "Test Location"
        assert gara.director_id == director.id
        assert gara.discipline == "palla 9"
        assert gara.distance == 7
        assert gara.best_of is True

    def test_gara_detail_access_workflow(self, client, db_session):
        """Test gara detail access workflow."""
        # Create director and gara
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Detail Test Competition",
            date=tomorrow,
            location="Test Location",
            description="Test gara for detail access",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            best_of=True,
            director_id=director.id,
        )

        # Login as director
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # Access gara detail
        response = client.get(f"/admin/gara/{gara.id}")
        assert response.status_code == 200
        assert b"Detail Test Competition" in response.data

    def test_gara_edit_workflow(self, client, db_session):
        """Test gara edit workflow."""
        # Create director and gara
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Original Gara Name",
            date=tomorrow,
            location="Original Location",
            description="Original description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            best_of=True,
            director_id=director.id,
        )

        # Login as director
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # GET edit form
        response = client.get(f"/admin/gara/{gara.id}/edit")
        assert response.status_code == 200
        assert b"Original Gara Name" in response.data

        # POST edit
        next_week = date.today() + timedelta(days=7)
        response = client.post(
            f"/admin/gara/{gara.id}/edit",
            data={
                "name": "Updated Gara Name",
                "date": next_week.strftime("%Y-%m-%d"),
                "location": "Updated Location",
                "description": "Updated description",
                "rounds_count": "4",
                "min_participants": "6",
                "max_participants": "20",
                "entry_fee": "20.0",
                "discipline": "palla 8",
                "distance": "5",
                "exact_number": "on",  # Checked, so best_of=False
                "withdraw_policy": "include",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Check gara was updated
        db_session.refresh(gara)
        assert gara.name == "Updated Gara Name"
        assert gara.date == next_week
        assert gara.location == "Updated Location"
        assert gara.description == "Updated description"
        assert gara.rounds_count == 4
        assert gara.min_participants == 6
        assert gara.max_participants == 20
        assert gara.entry_fee == 20.0
        assert gara.discipline == "palla 8"
        assert gara.distance == 5
        assert gara.best_of is False

    def test_gara_delete_workflow(self, client, db_session):
        """Test gara delete workflow."""
        # Create director and gara
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Gara to Delete",
            date=tomorrow,
            location="Test Location",
            description="Test gara for deletion",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            best_of=True,
            director_id=director.id,
        )
        gara_id = gara.id

        # Login as director
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # Delete gara
        response = client.post(f"/admin/gara/{gara_id}/delete", follow_redirects=True)
        assert response.status_code == 200

        # Check gara was deleted
        deleted_gara = db_session.get(Gara, gara_id)
        assert deleted_gara is None

    def test_co_director_access_workflow(self, client, db_session):
        """Test co-director access to standalone gara."""
        # Create directors
        main_director = User(
            username="main_director",
            email="main@test.com",
            role=UserRole.DIRECTOR.value,
        )
        main_director.set_password("main123")
        co_director = User(
            username="co_director", email="co@test.com", role=UserRole.DIRECTOR.value
        )
        co_director.set_password("co123")
        db_session.add_all([main_director, co_director])
        db_session.commit()

        # Create gara with main director
        tomorrow = date.today() + timedelta(days=1)
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Co-Director Test Competition",
            date=tomorrow,
            location="Test Location",
            description="Test co-director access",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            best_of=True,
            director_id=main_director.id,
        )

        # Add co-director assignment
        assignment = DirectorAssignment(
            user_id=co_director.id,
            entity_type="gara",
            entity_id=gara.id,
            assigned_by_id=main_director.id,
        )
        db_session.add(assignment)
        db_session.commit()

        # Login as co-director
        client.post(
            "/auth/login", data={"username": "co_director", "password": "co123"}
        )

        # Should be able to access gara detail
        response = client.get(f"/admin/gara/{gara.id}")
        assert response.status_code == 200
        assert b"Co-Director Test Competition" in response.data

        # Should be able to edit gara
        response = client.get(f"/admin/gara/{gara.id}/edit")
        assert response.status_code == 200


@pytest.mark.integration
class TestDashboardWorkflow:
    """Test dashboard workflow for different user types."""

    def test_admin_dashboard_workflow(self, client, db_session):
        """Test admin dashboard workflow."""
        # Create admin and some test data
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        admin.set_password("admin123")
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add_all([admin, director])
        db_session.commit()

        # Create test campionato and gara
        tournament_service = TournamentService()
        _ = tournament_service.create_campionato_with_director(
            name="Test Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )  # not used in this test

        tomorrow = date.today() + timedelta(days=1)
        _ = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Test Competition",
            date=tomorrow,
            location="Test Location",
            description="Test gara",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            best_of=True,
            director_id=director.id,
        )

        # Login as admin
        client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        # Access admin dashboard
        response = client.get("/admin/dashboard")
        assert response.status_code == 200

        # Should show both campionato and gara
        assert b"Test Tournament" in response.data
        assert b"Test Competition" in response.data

        # Should have admin capabilities
        assert b"Crea Campionato" in response.data or b"Create" in response.data

    def test_director_dashboard_workflow(self, client, db_session):
        """Test director dashboard workflow."""
        # Create directors
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
        other_director = User(
            username="other_director",
            email="other@test.com",
            role=UserRole.DIRECTOR.value,
        )
        db_session.add_all([director, other_director])
        db_session.commit()

        # Create managed and non-managed competitions
        tournament_service = TournamentService()
        _ = tournament_service.create_campionato_with_director(
            name="Managed Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )  # managed_campionato not used

        _ = tournament_service.create_campionato_with_director(
            name="Other Tournament",
            creator_user_id=other_director.id,
            campionato_type="Amalfi",
        )  # other_campionato not used

        # Login as director
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # Access director dashboard (should redirect to unified dashboard)
        response = client.get("/dashboard")
        assert response.status_code == 200

        # Should show both managed and non-managed competitions
        assert b"Managed Tournament" in response.data
        assert b"Other Tournament" in response.data

        # Should have director capabilities
        assert b"Crea Campionato" in response.data or b"Create" in response.data

    def test_player_dashboard_workflow(self, client, db_session):
        """Test player dashboard workflow."""
        # Create player and director
        player = User(
            username="player", email="player@test.com", role=UserRole.PLAYER.value
        )
        player.set_password("player123")
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        db_session.add_all([player, director])
        db_session.commit()

        # Create competitions
        tournament_service = TournamentService()
        _ = tournament_service.create_campionato_with_director(
            name="Test Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )  # not used in this test

        tomorrow = date.today() + timedelta(days=1)
        _ = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Test Competition",
            date=tomorrow,
            location="Test Location",
            description="Test gara",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            best_of=True,
            director_id=director.id,
        )

        # Login as player
        client.post("/auth/login", data={"username": "player", "password": "player123"})

        # Access player dashboard
        response = client.get("/dashboard")
        assert response.status_code == 200

        # Should show competitions for viewing
        assert b"Test Tournament" in response.data
        assert b"Test Competition" in response.data

        # Should NOT have creation capabilities
        # (Check that admin/director buttons are not present)
        # This might be implementation-specific
