"""Unit tests for guest access to gara details and card button visibility."""

import pytest
import uuid
from datetime import date, timedelta

from models import User, Gara
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus
from models.competition.services import GaraService
from models.dashboard.services import DashboardService


@pytest.mark.unit
class TestGuestGaraAccess:
    """Test guest access to gara details and card visibility."""

    @pytest.fixture
    def admin_user(self, db_session) -> User:
        """Create admin user for test."""
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("admin123")
        db_session.add(admin)
        db_session.commit()
        return admin

    @pytest.fixture
    def player_user(self, db_session) -> User:
        """Create player user for test."""
        unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        db_session.add(player)
        db_session.commit()
        return player

    @pytest.fixture
    def gara_with_open_inscriptions(self, db_session, admin_user) -> Gara:
        """Create a gara with open inscriptions."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=1,
            name="Test Random Gara",
            date=tomorrow,
            location="Test Location",
            description="Test gara with random strategy",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=admin_user.id,
        )

        # Set status to inscription to simulate open inscriptions
        gara.status = GaraStatus.INSCRIPTION.value
        db_session.commit()
        return gara

    def test_player_can_view_details_in_dashboard(
        self, db_session, player_user, gara_with_open_inscriptions
    ):
        """Test that player can view details in dashboard unified items."""
        # Get dashboard data for player using correct method
        vm = DashboardService.for_player(user_id=player_user.id)

        # Find the gara in unified items
        gara_item = None
        for item in vm.unified_items:
            if item.type == "gara" and item.entity.id == gara_with_open_inscriptions.id:
                gara_item = item
                break

        # Assert gara is found and can_view_details is True
        assert gara_item is not None, "Gara should be found in unified items"
        assert (
            gara_item.can_view_details is True
        ), "Player should be able to view gara details"

    def test_guest_cannot_view_details_in_current_logic(
        self, db_session, gara_with_open_inscriptions
    ):
        """Test current behavior: guest sees gara in public list but button logic needs to be checked."""
        # Simulate what happens in main.py for guest (index route)

        # This is how guest sees standalone garas (from main.py lines 38-44)
        standalone_garas = (
            Gara.query.filter_by(campionato_id=None)
            .filter(Gara.status != GaraStatus.SETUP.value)  # Hide setup garas
            .order_by(Gara.date.desc())
            .all()
        )

        # Find our gara
        found_gara = None
        for gara in standalone_garas:
            if gara.id == gara_with_open_inscriptions.id:
                found_gara = gara
                break

        # Guest can see the gara since inscriptions are open (status = INSCRIPTION, not SETUP)
        assert found_gara is not None, "Guest should see gara with inscriptions open"
        assert found_gara.status == GaraStatus.INSCRIPTION.value

        # But now we need to test if guest can access details
        # This will depend on route/template logic we'll implement

    def test_guest_should_view_details_when_inscriptions_open(
        self, db_session, gara_with_open_inscriptions
    ):
        """Test desired behavior: guest should view details when inscriptions are open (THIS SHOULD PASS after we implement)."""
        # This test represents the desired behavior
        # We'll implement a for_guest method in DashboardService

        # Get dashboard data for guest using method we'll implement
        vm = DashboardService.for_guest()

        # Find the gara in unified items
        gara_item = None
        for item in vm.unified_items:
            if item.type == "gara" and item.entity.id == gara_with_open_inscriptions.id:
                gara_item = item
                break

        # DESIRED behavior: guest can view details when inscriptions are open
        assert (
            gara_item is not None
        ), "Gara should be visible to guests when inscriptions are open"
        assert (
            gara_item.can_view_details is True
        ), "Guest should be able to view details when inscriptions are open"

    def test_guest_cannot_view_details_when_inscriptions_closed(
        self, db_session, admin_user
    ):
        """Test that guest cannot view details when inscriptions are closed."""
        tomorrow = date.today() + timedelta(days=1)

        # Create gara with closed inscriptions (SETUP status)
        closed_gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=2,
            name="Test Closed Gara",
            date=tomorrow,
            location="Test Location",
            description="Test gara with closed inscriptions",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=15.0,
            discipline="palla 8",
            distance=5,
            is_race_to=True,
            director_id=admin_user.id,
        )

        # Ensure status is SETUP (inscriptions not open)
        assert closed_gara.status == GaraStatus.SETUP.value

        # Test guest access using same logic as main.py

        standalone_garas = (
            Gara.query.filter_by(campionato_id=None)
            .filter(Gara.status != GaraStatus.SETUP.value)  # Hide setup garas
            .order_by(Gara.date.desc())
            .all()
        )

        # Find the closed gara
        found_gara = None
        for gara in standalone_garas:
            if gara.id == closed_gara.id:
                found_gara = gara
                break

        # Guest should NOT see gara with SETUP status (inscriptions closed)
        assert (
            found_gara is None
        ), "Guest should not see gara with closed inscriptions (SETUP status)"

    def test_gara_status_inscription_detection(
        self, db_session, gara_with_open_inscriptions
    ):
        """Test that we can properly detect when inscriptions are open."""
        # This is a helper test to ensure our status detection works
        assert gara_with_open_inscriptions.status == GaraStatus.INSCRIPTION.value

        # Check if gara has method to check if inscriptions are open
        # This might need to be implemented if not exists
        if hasattr(gara_with_open_inscriptions, "is_inscription_open"):
            assert gara_with_open_inscriptions.is_inscription_open() is True
        else:
            # Alternative: check status directly
            assert gara_with_open_inscriptions.status == GaraStatus.INSCRIPTION.value
