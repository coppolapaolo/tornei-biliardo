"""Unit tests for dashboard functionality."""

import pytest
import uuid
from datetime import date, timedelta

from models import User
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole
from models.dashboard.services import DashboardService
from models.campionato.services import TournamentService
from models.competition.services import GaraService


@pytest.mark.unit
class TestDashboardService:
    """Test DashboardService functionality."""

    def test_admin_dashboard_data(self, db_session):
        """Test admin dashboard data."""
        unique_id = str(uuid.uuid4())[:8]
        # Create admin user
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("admin123")
        db_session.add(admin)
        db_session.commit()

        # Create test data
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        tournament_service = TournamentService()
        _ = tournament_service.create_campionato_with_director(
            name="Test Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )  # campionato not used

        # Create standalone gara
        _ = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Standalone Competition",
            date=date.today() + timedelta(days=7),
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=director.id,
        )  # gara not used

        # Get admin dashboard data
        dashboard_data = DashboardService.for_admin()

        # Verify structure
        assert hasattr(dashboard_data, "unified_items")
        assert hasattr(dashboard_data, "caps")

        # Verify capabilities
        caps = dashboard_data.caps
        assert caps.can_create_campionato is True
        assert caps.can_create_standalone is True
        # Note: Admin capabilities don't include can_manage_users and
        # can_view_admin_panel in CapabilityVM
        # These are implicit for admins

        # Verify unified items include both campionato and gara
        unified_items = dashboard_data.unified_items
        assert unified_items is not None
        assert len(unified_items) == 2

        # Check items are properly typed
        campionato_item = next(
            (item for item in unified_items if item.type == "campionato"), None
        )
        gara_item = next((item for item in unified_items if item.type == "gara"), None)

        assert campionato_item is not None
        assert gara_item is not None
        assert campionato_item.can_manage is True
        assert gara_item.can_manage is True

    def test_director_dashboard_data(self, db_session):
        """Test director dashboard data."""
        unique_id = str(uuid.uuid4())[:8]
        # Create director user
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        # Create campionato managed by director
        tournament_service = TournamentService()
        managed_campionato = tournament_service.create_campionato_with_director(
            name="Managed Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )

        # Create campionato NOT managed by director
        other_director = User(
            username=f"other_{unique_id}",
            email=f"other_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        other_director.set_password("other123")
        db_session.add(other_director)
        db_session.commit()

        other_campionato = tournament_service.create_campionato_with_director(
            name="Other Tournament",
            creator_user_id=other_director.id,
            campionato_type="Amalfi",
        )

        # Create standalone gara managed by director
        managed_gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Managed Competition",
            date=date.today() + timedelta(days=7),
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=director.id,
        )

        # Create standalone gara NOT managed by director
        other_gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Other Competition",
            date=date.today() + timedelta(days=14),
            location="Other Location",
            description="Other description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=20.0,
            discipline="palla 8",
            distance=5,
            is_race_to=True,
            director_id=other_director.id,
        )

        # Get director dashboard data
        dashboard_data = DashboardService.for_director(director.id)

        # Verify capabilities
        caps = dashboard_data.caps
        assert caps.can_create_campionato is True
        assert caps.can_create_standalone is True
        # Note: Director capabilities don't include can_manage_users and
        # can_view_admin_panel in CapabilityVM

        # Verify unified items include managed items and viewable others
        unified_items = dashboard_data.unified_items
        assert unified_items is not None
        assert len(unified_items) == 4  # All items visible for view

        # Check managed items have manage permissions
        managed_campionato_item = next(
            (
                item
                for item in unified_items
                if item.type == "campionato" and item.id == managed_campionato.id
            ),
            None,
        )
        managed_gara_item = next(
            (
                item
                for item in unified_items
                if item.type == "gara" and item.id == managed_gara.id
            ),
            None,
        )

        assert managed_campionato_item.can_manage is True
        assert managed_gara_item.can_manage is True

        # Check non-managed items don't have manage permissions
        other_campionato_item = next(
            (
                item
                for item in unified_items
                if item.type == "campionato" and item.id == other_campionato.id
            ),
            None,
        )
        other_gara_item = next(
            (
                item
                for item in unified_items
                if item.type == "gara" and item.id == other_gara.id
            ),
            None,
        )

        assert other_campionato_item.can_manage is False
        assert other_gara_item.can_manage is False

    def test_player_dashboard_data(self, db_session):
        """Test player dashboard data."""
        unique_id = str(uuid.uuid4())[:8]
        # Create player user
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        db_session.add(player)
        db_session.commit()

        # Create director and competitions
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        tournament_service = TournamentService()
        _ = tournament_service.create_campionato_with_director(
            name="Test Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )

        _ = GaraService.create_gara(
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
            is_race_to=True,
            director_id=director.id,
        )

        # Get player dashboard data
        dashboard_data = DashboardService.for_player(player.id)

        # Verify capabilities
        caps = dashboard_data.caps
        assert caps.can_create_campionato is False
        assert caps.can_create_standalone is False
        # Note: Player capabilities don't include can_manage_users and
        # can_view_admin_panel in CapabilityVM

        # Verify unified items are view-only
        unified_items = dashboard_data.unified_items
        assert unified_items is not None
        assert len(unified_items) == 2

        for item in unified_items:
            assert item.can_manage is False
            assert item.can_view_details is True  # Players can view but not manage

    def test_unified_dashboard_sorting(self, db_session):
        """Test unified dashboard sorting by date."""
        unique_id = str(uuid.uuid4())[:8]
        # Create director
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        # Create competitions with different dates
        today = date.today()

        # Campionato with gara in 5 days
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Tournament", creator_user_id=director.id, campionato_type="Amalfi"
        )

        _ = GaraService.create_gara(
            campionato_id=campionato.id,
            number=1,
            name="Tournament Competition",
            date=today + timedelta(days=5),
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
        )

        # Standalone gara in 3 days (should come first)
        _ = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Early Competition",
            date=today + timedelta(days=3),
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=20.0,
            discipline="palla 8",
            distance=5,
            is_race_to=True,
            director_id=director.id,
        )

        # Standalone gara in 10 days (should come last)
        _ = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Late Competition",
            date=today + timedelta(days=10),
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=25.0,
            discipline="palla 10",
            distance=9,
            is_race_to=True,
            director_id=director.id,
        )

        # Get dashboard data
        dashboard_data = DashboardService.for_director(director.id)
        unified_items = dashboard_data.unified_items

        # Should be sorted by next prova date
        assert unified_items is not None
        assert len(unified_items) == 3
        assert unified_items[0].name == "Early Competition"  # 3 days
        assert unified_items[1].name == "Tournament"  # 5 days (campionato)
        assert unified_items[2].name == "Late Competition"  # 10 days

    def test_unified_dashboard_item_creation(self, db_session):
        """Test UnifiedDashboardItem creation."""
        unique_id = str(uuid.uuid4())[:8]
        # Create director and competitions
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        # Create campionato
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Test Tournament",
            creator_user_id=director.id,
            campionato_type="Amalfi",
        )

        # Create gara within campionato
        gara = GaraService.create_gara(
            campionato_id=campionato.id,
            number=1,
            name="Tournament Competition",
            date=date.today() + timedelta(days=7),
            location="Test Location",
            description="Test description",
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
        )

        # Get dashboard data to test item creation
        dashboard_data = DashboardService.for_director(director.id)

        # Find the campionato item in the dashboard
        campionato_item = None
        for item in dashboard_data.unified_items:
            if item.type == "campionato" and item.id == campionato.id:
                campionato_item = item
                break

        assert (
            campionato_item is not None
        ), "Campionato item should be found in dashboard"

        assert campionato_item.type == "campionato"
        assert campionato_item.id == campionato.id
        assert campionato_item.name == "Test Tournament"
        assert campionato_item.entity == campionato
        assert campionato_item.next_prova_date == gara.date
        assert campionato_item.can_manage is True
        assert campionato_item.can_view_details is True

        # Test sort key generation
        expected_sort_key = (
            gara.date.strftime("%Y-%m-%d") + "_campionato_" + str(campionato.id)
        )
        assert campionato_item.sort_key == expected_sort_key

    def test_co_director_permissions_in_dashboard(self, db_session):
        """Test co-director permissions in dashboard."""
        unique_id = str(uuid.uuid4())[:8]
        # Create directors
        main_director = User(
            username=f"main_director_{unique_id}",
            email=f"main_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        main_director.set_password("main123")
        co_director = User(
            username=f"co_director_{unique_id}",
            email=f"co_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        co_director.set_password("co123")
        db_session.add_all([main_director, co_director])
        db_session.commit()

        # Create campionato with main director
        tournament_service = TournamentService()
        campionato = tournament_service.create_campionato_with_director(
            name="Test Tournament",
            creator_user_id=main_director.id,
            campionato_type="Amalfi",
        )

        # Add co-director
        tournament_service.add_director(campionato.id, co_director.id, main_director.id)

        # Create standalone gara with main director
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
            is_race_to=True,
            director_id=main_director.id,
        )

        # Add co-director to standalone gara
        assignment = DirectorAssignment(
            user_id=co_director.id,
            entity_type="gara",
            entity_id=gara.id,
            assigned_by_id=main_director.id,
        )
        db_session.add(assignment)
        db_session.commit()

        # Get co-director dashboard data
        dashboard_data = DashboardService.for_director(co_director.id)
        unified_items = dashboard_data.unified_items

        # Co-director should be able to manage both
        campionato_item = next(
            (item for item in unified_items if item.type == "campionato"), None
        )
        gara_item = next((item for item in unified_items if item.type == "gara"), None)

        assert campionato_item is not None
        assert gara_item is not None
        assert campionato_item.can_manage is True
        assert gara_item.can_manage is True

    def test_dashboard_with_no_competitions(self, db_session):
        """Test dashboard with no competitions."""
        unique_id = str(uuid.uuid4())[:8]
        # Create users
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("admin123")
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        db_session.add_all([admin, director, player])
        db_session.commit()

        # Get dashboard data for each user type
        admin_data = DashboardService.for_admin()
        director_data = DashboardService.for_director(director.id)
        player_data = DashboardService.for_player(player.id)

        # All should have empty unified_items but proper capabilities
        assert admin_data.unified_items is not None
        assert len(admin_data.unified_items) == 0
        assert director_data.unified_items is not None
        assert len(director_data.unified_items) == 0
        assert player_data.unified_items is not None
        assert len(player_data.unified_items) == 0

        assert admin_data.caps.can_create_campionato is True
        assert director_data.caps.can_create_campionato is True
        assert player_data.caps.can_create_campionato is False
