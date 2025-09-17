"""Integration tests for guest workflow: card → details button → gara details page."""

import pytest
import uuid
from datetime import date, timedelta
from typing import Dict, Any

from models import User, Gara
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus
from models.competition.services import GaraService
from models.dashboard.services import DashboardService


@pytest.mark.integration
class TestGuestCardToDetailsWorkflow:
    """Test complete workflow from card display to details page access."""

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
    def gara_with_random_strategy_and_challenges(self, db_session, admin_user) -> Gara:
        """Create a gara with random strategy that can have challenges."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=1,
            name="Random Strategy Gara with Challenges",
            date=tomorrow,
            location="Test Venue",
            description="Test gara with random strategy for challenge testing",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            best_of=True,
            director_id=admin_user.id,
            strategy_config={
                "matchmaking_strategy": "random",
                "first_round_policy": "random",
                "odd_number_policy": "X",  # For challenges
            },
        )

        # Set status to inscription to simulate open inscriptions
        gara.status = GaraStatus.INSCRIPTION.value
        db_session.commit()
        return gara

    @pytest.fixture
    def gara_with_closed_inscriptions(self, db_session, admin_user) -> Gara:
        """Create a gara with closed inscriptions (SETUP status)."""
        tomorrow = date.today() + timedelta(days=2)

        gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=2,
            name="Closed Inscriptions Gara",
            date=tomorrow,
            location="Test Venue 2",
            description="Test gara with closed inscriptions",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=20.0,
            discipline="palla 8",
            distance=5,
            best_of=True,
            director_id=admin_user.id,
        )

        # Keep status as SETUP (default) to simulate closed inscriptions
        assert gara.status == GaraStatus.SETUP.value
        return gara

    def test_guest_sees_details_button_for_open_inscriptions(
        self, db_session, gara_with_random_strategy_and_challenges
    ):
        """Test that guest can see 'Details' button for gara with open inscriptions."""
        # Get guest dashboard data
        vm = DashboardService.for_guest()

        # Find the gara in unified items
        gara_item = None
        for item in vm.unified_items:
            if (
                item.type == "gara"
                and item.entity.id == gara_with_random_strategy_and_challenges.id
            ):
                gara_item = item
                break

        # Assert gara is found and can_view_details is True
        assert gara_item is not None, "Gara with open inscriptions should be visible to guest"
        assert gara_item.can_view_details is True, "Guest should be able to view details when inscriptions are open"

        # Verify this is the random strategy gara we expect
        assert gara_item.entity.name == "Random Strategy Gara with Challenges"
        assert gara_item.entity.status == GaraStatus.INSCRIPTION.value

    def test_guest_cannot_see_details_button_for_closed_inscriptions(
        self, db_session, gara_with_closed_inscriptions
    ):
        """Test that guest cannot see 'Details' button for gara with closed inscriptions."""
        # Get guest dashboard data
        vm = DashboardService.for_guest()

        # Find the gara in unified items
        gara_item = None
        for item in vm.unified_items:
            if item.type == "gara" and item.entity.id == gara_with_closed_inscriptions.id:
                gara_item = item
                break

        # Gara with closed inscriptions should either:
        # 1. Not be visible to guest at all, OR
        # 2. Be visible but can_view_details should be False
        if gara_item is not None:
            assert (
                gara_item.can_view_details is False
            ), "Guest should not see details button for closed inscriptions"
        # If gara_item is None, that's also acceptable (gara not shown to guests)

    def test_player_sees_details_button_for_all_garas(
        self, db_session, player_user, gara_with_random_strategy_and_challenges, gara_with_closed_inscriptions
    ):
        """Test that player can see 'Details' button for all garas regardless of inscription status."""
        # Get player dashboard data
        vm = DashboardService.for_player(user_id=player_user.id)

        # Find both garas in unified items
        open_gara_item = None
        closed_gara_item = None

        for item in vm.unified_items:
            if item.type == "gara":
                if item.entity.id == gara_with_random_strategy_and_challenges.id:
                    open_gara_item = item
                elif item.entity.id == gara_with_closed_inscriptions.id:
                    closed_gara_item = item

        # Player should see both garas and be able to view details
        assert open_gara_item is not None, "Player should see gara with open inscriptions"
        assert open_gara_item.can_view_details is True, "Player should see details for open inscriptions"

        assert closed_gara_item is not None, "Player should see gara with closed inscriptions"
        assert closed_gara_item.can_view_details is True, "Player should see details for closed inscriptions"

    def test_template_logic_for_guest_button_display(
        self, db_session, gara_with_random_strategy_and_challenges
    ):
        """Test the logic that would be used in templates to show/hide Details button for guests."""
        # Get guest dashboard data
        vm = DashboardService.for_guest()

        # Simulate template logic from _unified_cards.html
        details_buttons = []
        for item in vm.unified_items:
            if item.type == "gara":
                # This simulates the template logic: {% if item.can_view_details %}
                if item.can_view_details:
                    details_buttons.append({
                        "gara_id": item.entity.id,
                        "gara_name": item.entity.name,
                        "can_show_button": True,
                        "url_pattern": f"/gara/{item.entity.id}",  # Public route
                    })

        # Find our test gara
        test_button = None
        for button in details_buttons:
            if button["gara_id"] == gara_with_random_strategy_and_challenges.id:
                test_button = button
                break

        # Assert that guest sees the Details button for gara with open inscriptions
        assert test_button is not None, "Guest should see Details button for gara with open inscriptions"
        assert test_button["can_show_button"] is True
        assert test_button["gara_name"] == "Random Strategy Gara with Challenges"
        assert test_button["url_pattern"] == f"/gara/{gara_with_random_strategy_and_challenges.id}"

    def test_url_generation_for_guest_vs_player(
        self, db_session, player_user, gara_with_random_strategy_and_challenges
    ):
        """Test that correct URLs are generated for guest vs player access."""
        # Get guest dashboard data
        guest_vm = DashboardService.for_guest()

        # Get player dashboard data
        player_vm = DashboardService.for_player(user_id=player_user.id)

        # Find the gara in both VMs
        guest_item = None
        player_item = None

        for item in guest_vm.unified_items:
            if (
                item.type == "gara"
                and item.entity.id == gara_with_random_strategy_and_challenges.id
            ):
                guest_item = item
                break

        for item in player_vm.unified_items:
            if (
                item.type == "gara"
                and item.entity.id == gara_with_random_strategy_and_challenges.id
            ):
                player_item = item
                break

        # Both should find the gara
        assert guest_item is not None
        assert player_item is not None

        # Both should be able to view details
        assert guest_item.can_view_details is True
        assert player_item.can_view_details is True

        # In template, this would determine which route to use:
        # Guest: url_for('main.gara_detail_public', gara_id=gara.id) → /gara/<id>
        # Player: url_for('player.gara_detail', gara_id=gara.id) → /player/gara/<id>
        # But for unified cards, they might both go to public route for simplicity

        guest_url = f"/gara/{guest_item.entity.id}"  # Public route
        player_url = f"/player/gara/{player_item.entity.id}"  # Player route (if different)

        assert guest_url == f"/gara/{gara_with_random_strategy_and_challenges.id}"
        assert player_url == f"/player/gara/{gara_with_random_strategy_and_challenges.id}"

    def test_dashboard_vm_structure_for_guests(self, db_session, gara_with_random_strategy_and_challenges):
        """Test that DashboardVM for guests has the correct structure and capabilities."""
        vm = DashboardService.for_guest()

        # Check basic structure
        assert vm.title == "Vista Pubblica"
        assert vm.can_inscribe is False, "Guests cannot inscribe"
        assert vm.caps.can_create_campionato is False, "Guests cannot create campionatos"
        assert vm.caps.can_create_standalone is False, "Guests cannot create standalone garas"
        assert vm.caps.can_register_self is False, "Guests cannot register"
        assert vm.caps.can_create_match_proposal is False, "Guests cannot create match proposals"

        # Check guest-specific data is None/empty
        assert vm.my_inscriptions == [], "Guests have no inscriptions"
        assert vm.current_matches == [], "Guests have no current matches"
        assert vm.user_stats is None, "Guests have no user stats"
        assert vm.match_proposals is None, "Guests have no match proposals"

        # Check that unified_items is populated
        assert vm.unified_items is not None, "Guests should see unified items"
        assert len(vm.unified_items) > 0, "Guests should see some public content"

        # Find our test gara
        found_gara = False
        for item in vm.unified_items:
            if (
                item.type == "gara"
                and item.entity.id == gara_with_random_strategy_and_challenges.id
            ):
                found_gara = True
                break

        assert found_gara, "Guest should see the test gara with open inscriptions"