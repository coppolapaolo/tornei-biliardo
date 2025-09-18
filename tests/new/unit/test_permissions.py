"""Unit tests for permission system."""

import pytest
import uuid

from models import User
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole
from models.user.permissions import PermissionChecker
from models.campionato.services import TournamentService
from models.competition.services import GaraService


@pytest.mark.unit
class TestPermissionChecker:
    """Test PermissionChecker functionality."""

    def test_admin_permissions(self, db_session):
        """Test admin has all permissions."""
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("admin123")
        db_session.add(admin)
        db_session.commit()

        # Admin should be able to manage any campionato
        assert PermissionChecker.can_manage_campionato(admin, 1) is True
        assert PermissionChecker.can_manage_campionato(admin, 999) is True

        # Admin should be able to manage any competition
        assert PermissionChecker.can_manage_competition(admin, 1) is True
        assert PermissionChecker.can_manage_competition(admin, 999) is True

        # Admin should have admin panel access
        assert PermissionChecker.can_view_admin_panel(admin) is True
        assert PermissionChecker.can_manage_users(admin) is True
        assert PermissionChecker.can_create_campionato(admin) is True
        assert PermissionChecker.can_assign_directors(admin) is True
        assert PermissionChecker.can_promote_user(admin) is True
        assert PermissionChecker.can_reset_database(admin) is True

    def test_director_permissions(self, db_session):
        """Test director permissions."""
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        # Director should be able to create campionato
        assert PermissionChecker.can_create_campionato(director) is True

        # Director should not have admin-only permissions
        assert PermissionChecker.can_view_admin_panel(director) is False
        assert PermissionChecker.can_manage_users(director) is False
        assert PermissionChecker.can_assign_directors(director) is False
        assert PermissionChecker.can_promote_user(director) is False
        assert PermissionChecker.can_reset_database(director) is False

    def test_player_permissions(self, db_session):
        """Test player permissions."""
        unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add(player)
        db_session.commit()

        # Player should not have management permissions
        assert PermissionChecker.can_create_campionato(player) is False
        assert PermissionChecker.can_view_admin_panel(player) is False
        assert PermissionChecker.can_manage_users(player) is False
        assert PermissionChecker.can_assign_directors(player) is False
        assert PermissionChecker.can_promote_user(player) is False
        assert PermissionChecker.can_reset_database(player) is False

    def test_unauthenticated_user_permissions(self, db_session):
        """Test permissions for unauthenticated user."""
        # Test with None user
        assert PermissionChecker.can_manage_campionato(None, 1) is False
        assert PermissionChecker.can_manage_competition(None, 1) is False
        assert PermissionChecker.can_view_admin_panel(None) is False
        assert PermissionChecker.can_manage_users(None) is False
        assert PermissionChecker.can_create_campionato(None) is False

    def test_campionato_management_permissions(self, db_session):
        """Test campionato management permissions."""
        # Create users
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        director1 = User(
            username=f"director1_{unique_id}",
            email=f"director1_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director1.set_password("testpass123")
        director2 = User(
            username=f"director2_{unique_id}",
            email=f"director2_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director2.set_password("testpass123")
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add_all([admin, director1, director2, player])
        db_session.commit()

        # Create campionato using service
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Test Tournament",
            creator_user_id=director1.id,
            campionato_type="Amalfi",
        )

        # Admin should be able to manage any campionato
        assert PermissionChecker.can_manage_campionato(admin, campionato.id) is True

        # Director1 (creator) should be able to manage
        assert PermissionChecker.can_manage_campionato(director1, campionato.id) is True

        # Director2 (not assigned) should not be able to manage
        assert (
            PermissionChecker.can_manage_campionato(director2, campionato.id) is False
        )

        # Player should not be able to manage
        assert PermissionChecker.can_manage_campionato(player, campionato.id) is False

        # Add director2 as co-director
        tournament_service.add_director(campionato.id, director2.id, admin.id)

        # Now director2 should be able to manage
        assert PermissionChecker.can_manage_campionato(director2, campionato.id) is True

    def test_competition_management_permissions(self, db_session):
        """Test competition (gara) management permissions."""
        # Create users
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        director1 = User(
            username=f"director1_{unique_id}",
            email=f"director1_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director1.set_password("testpass123")
        director2 = User(
            username=f"director2_{unique_id}",
            email=f"director2_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director2.set_password("testpass123")
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add_all([admin, director1, director2, player])
        db_session.commit()

        # Create standalone gara
        from datetime import date, timedelta

        gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
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
            director_id=director1.id,
        )

        # Admin should be able to manage any competition
        assert PermissionChecker.can_manage_competition(admin, gara.id) is True

        # Director1 (creator) should be able to manage
        assert PermissionChecker.can_manage_competition(director1, gara.id) is True

        # Director2 (not assigned) should not be able to manage
        assert PermissionChecker.can_manage_competition(director2, gara.id) is False

        # Player should not be able to manage
        assert PermissionChecker.can_manage_competition(player, gara.id) is False

        # Add director2 as co-director
        assignment = DirectorAssignment(
            user_id=director2.id,
            entity_type="gara",
            entity_id=gara.id,
            assigned_by_id=director1.id,
        )
        db_session.add(assignment)
        db_session.commit()

        # Now director2 should be able to manage
        assert PermissionChecker.can_manage_competition(director2, gara.id) is True

    def test_competition_in_campionato_permissions(self, db_session):
        """Test permissions for competitions within campionati."""
        # Create users
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        director1 = User(
            username=f"director1_{unique_id}",
            email=f"director1_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director1.set_password("testpass123")
        director2 = User(
            username=f"director2_{unique_id}",
            email=f"director2_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director2.set_password("testpass123")
        db_session.add_all([admin, director1, director2])
        db_session.commit()

        # Create campionato
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Test Tournament",
            creator_user_id=director1.id,
            campionato_type="Amalfi",
        )

        # Create gara within campionato
        from datetime import date, timedelta

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

        # Admin should be able to manage
        assert PermissionChecker.can_manage_competition(admin, gara.id) is True

        # Director1 (campionato manager) should be able to manage
        assert PermissionChecker.can_manage_competition(director1, gara.id) is True

        # Director2 (not campionato manager) should not be able to manage
        assert PermissionChecker.can_manage_competition(director2, gara.id) is False

    def test_inscription_permissions(self, db_session):
        """Test inscription permissions."""
        # Create users
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add_all([admin, director, player])
        db_session.commit()

        # Create gara
        from datetime import date, timedelta

        gara = GaraService.create_gara(
            campionato_id=None,
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
            director_id=director.id,
        )

        # Admin should not be able to inscribe (administrative role)
        assert PermissionChecker.can_inscribe_to_competition(admin, gara.id) is False

        # Director managing the competition should not be able to inscribe
        assert PermissionChecker.can_inscribe_to_competition(director, gara.id) is False

        # Player should be able to inscribe
        assert PermissionChecker.can_inscribe_to_competition(player, gara.id) is True

    def test_delete_campionato_permissions(self, db_session):
        """Test campionato deletion permissions."""
        # Create users
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add_all([admin, director, player])
        db_session.commit()

        # Create campionato
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Test Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )

        # Only admin should be able to delete campionato
        assert PermissionChecker.can_delete_campionato(admin, campionato.id) is True
        assert PermissionChecker.can_delete_campionato(director, campionato.id) is False
        assert PermissionChecker.can_delete_campionato(player, campionato.id) is False

    def test_management_level_permissions(self, db_session):
        """Test management level permissions."""
        # Create users
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add_all([admin, director, player])
        db_session.commit()

        # Create campionato
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Test Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )

        # Test management levels
        assert (
            PermissionChecker.get_campionato_management_level(admin, campionato.id)
            == "full"
        )
        assert (
            PermissionChecker.get_campionato_management_level(director, campionato.id)
            == "manage"
        )
        assert (
            PermissionChecker.get_campionato_management_level(player, campionato.id)
            == "view"
        )

    def test_filter_campionatos_by_permission(self, db_session):
        """Test filtering campionatos by permission."""
        # Create users
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        director1 = User(
            username=f"director1_{unique_id}",
            email=f"director1_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director1.set_password("testpass123")
        director2 = User(
            username=f"director2_{unique_id}",
            email=f"director2_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director2.set_password("testpass123")
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add_all([admin, director1, director2, player])
        db_session.commit()

        # Create campionati
        tournament_service = TournamentService()
        campionato1 = tournament_service.create_campionato_with_director(
            name="Tournament 1", creator_user_id=director1.id, campionato_type="Amalfi"
        )
        campionato2 = tournament_service.create_campionato_with_director(
            name="Tournament 2", creator_user_id=director2.id, campionato_type="Amalfi"
        )

        all_campionati = [campionato1, campionato2]

        # Admin should see all for manage permission
        admin_filtered = PermissionChecker.filter_campionatos_by_permission(
            admin, all_campionati, "manage"
        )
        assert len(admin_filtered) == 2

        # Director1 should see only their managed campionato
        director1_filtered = PermissionChecker.filter_campionatos_by_permission(
            director1, all_campionati, "manage"
        )
        assert len(director1_filtered) == 1
        assert director1_filtered[0].id == campionato1.id

        # Player should see none for manage permission
        player_filtered = PermissionChecker.filter_campionatos_by_permission(
            player, all_campionati, "manage"
        )
        assert len(player_filtered) == 0

        # Everyone should see all for view permission
        player_view = PermissionChecker.filter_campionatos_by_permission(
            player, all_campionati, "view"
        )
        assert len(player_view) == 2

    def test_route_access_permissions(self, db_session):
        """Test route access permissions."""
        # Create users
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        db_session.add_all([admin, director, player])
        db_session.commit()

        # Test admin routes
        assert PermissionChecker.can_access_route(admin, "admin.dashboard") is True
        assert PermissionChecker.can_access_route(director, "admin.dashboard") is False
        assert PermissionChecker.can_access_route(player, "admin.dashboard") is False

        # Test user management routes
        assert PermissionChecker.can_access_route(admin, "admin.users_list") is True
        assert PermissionChecker.can_access_route(director, "admin.users_list") is False
        assert PermissionChecker.can_access_route(player, "admin.users_list") is False

        # Test campionato creation
        assert (
            PermissionChecker.can_access_route(admin, "admin.create_campionato") is True
        )
        assert (
            PermissionChecker.can_access_route(director, "admin.create_campionato")
            is True
        )
        assert (
            PermissionChecker.can_access_route(player, "admin.create_campionato")
            is False
        )

        # Test player routes (available to all authenticated users)
        assert PermissionChecker.can_access_route(admin, "player.dashboard") is True
        assert PermissionChecker.can_access_route(director, "player.dashboard") is True
        assert PermissionChecker.can_access_route(player, "player.dashboard") is True
