"""
TDD Tests for VenueManagerService Decomposition (Task 1.3)

VenueManagerService focuses on venue management operations:
- create_venue_manager_request() - Create venue manager requests
- process_venue_manager_request() - Approve/reject requests
- get_pending_venue_manager_requests() - Query pending requests
- get_venue_manager_requests_by_user() - Query user requests
- get_venue_manager_requests_by_venue() - Query venue requests
- is_venue_manager() - Check venue management status
- get_managed_venues() - Get venues managed by user
- remove_venue_manager() - Remove venue manager assignment

Strategy: Align TDD tests with actual VenueManagerService implementation
"""

import pytest

from models import db
from models.user.models import User, VenueManagement
from models.user.role_enum import UserRole
from models.user.venue_manager_service import VenueManagerService
from models.location.models import BilliardHall


class TestVenueManagerServiceTDD:
    """TDD tests for VenueManagerService venue management operations."""

    @pytest.fixture
    def test_venue(self, app, db_session):
        """Create test billiard hall for venue management tests."""
        with app.app_context():
            venue = BilliardHall(
                name="Test Billiard Hall",
                address="123 Test Street",
                city="Test City",
                postal_code="12345",
            )
            db.session.add(venue)
            db.session.commit()

            yield venue

            # Note: Cleanup handled by test isolation
            db.session.commit()

    @pytest.fixture
    def test_user(self, app, db_session):
        """Create test user for venue management requests."""
        with app.app_context():
            user = User(
                username="venue_user",
                email="venue@example.com",
                role=UserRole.PLAYER.value,
            )
            user.set_password("secure123")
            db.session.add(user)
            db.session.commit()

            yield user

            # Note: Cleanup handled by test isolation
            db.session.commit()

    @pytest.fixture
    def test_admin(self, app, db_session):
        """Create test admin user for venue management tests."""
        with app.app_context():
            # Create a test admin user
            admin = User(
                username="test_venue_admin",
                email="test_venue_admin@example.com",
                role=UserRole.ADMIN.value,
            )
            admin.set_password("secure123")
            db.session.add(admin)
            db.session.commit()

            yield admin

            # Note: No cleanup - let test isolation handle it via db rollback

    def test_create_venue_manager_request_functionality(
        self, app, test_user, test_venue
    ):
        """
        Test VenueManagerService.create_venue_manager_request() basic functionality.
        """
        with app.app_context():
            # Test successful request creation
            request = VenueManagerService.create_venue_manager_request(
                user_id=test_user.id,
                venue_id=test_venue.id,
                notes="I want to manage this venue for community events",
            )

            assert request is not None
            assert request.user_id == test_user.id
            assert request.venue_id == test_venue.id
            assert request.notes == "I want to manage this venue for community events"
            assert request.status == "pending"

    def test_create_venue_manager_request_user_not_found(self, app, test_venue):
        """Test VenueManagerService.create_venue_manager_request() with invalid user."""
        with app.app_context():
            with pytest.raises(ValueError, match="User not found"):
                VenueManagerService.create_venue_manager_request(
                    user_id=99999, venue_id=test_venue.id, notes="Test motivation"
                )

    def test_create_venue_manager_request_venue_not_found(self, app, test_user):
        """
        Test VenueManagerService.create_venue_manager_request() with invalid venue.
        """
        with app.app_context():
            with pytest.raises(ValueError, match="Venue not found"):
                VenueManagerService.create_venue_manager_request(
                    user_id=test_user.id, venue_id=99999, notes="Test motivation"
                )

    def test_create_venue_manager_request_duplicate_pending(
        self, app, test_user, test_venue
    ):
        """Test VenueManagerService.create_venue_manager_request() prevents duplicate
        pending requests.
        """
        with app.app_context():
            # Create first request
            VenueManagerService.create_venue_manager_request(
                user_id=test_user.id, venue_id=test_venue.id, notes="First request"
            )

            # Attempt to create duplicate request
            with pytest.raises(
                ValueError, match="Pending request already exists for this venue"
            ):
                VenueManagerService.create_venue_manager_request(
                    user_id=test_user.id,
                    venue_id=test_venue.id,
                    notes="Duplicate request",
                )

    def test_create_venue_manager_request_empty_motivation(
        self, app, test_user, test_venue
    ):
        """
        Test VenueManagerService.create_venue_manager_request() validates motivation.
        """
        with app.app_context():
            # Test empty motivation
            with pytest.raises(ValueError, match="Notes are required"):
                VenueManagerService.create_venue_manager_request(
                    user_id=test_user.id, venue_id=test_venue.id, notes=""
                )

            # Test whitespace-only motivation
            with pytest.raises(ValueError, match="Notes are required"):
                VenueManagerService.create_venue_manager_request(
                    user_id=test_user.id, venue_id=test_venue.id, notes="   "
                )

    def test_process_venue_manager_request_approve(
        self, app, test_user, test_venue, test_admin
    ):
        """Test VenueManagerService.process_venue_manager_request() approval
        functionality.
        """
        with app.app_context():
            # Create request
            request = VenueManagerService.create_venue_manager_request(
                user_id=test_user.id,
                venue_id=test_venue.id,
                notes="I want to manage this venue",
            )

            # Process request - approve
            processed_request = VenueManagerService.process_venue_manager_request(
                request_id=request.id,
                admin_user=test_admin,
                approve=True,
                notes="Approved for community leadership",
            )

            assert processed_request.status == "approved"
            assert processed_request.processed_by_id == test_admin.id
            assert processed_request.notes == "Approved for community leadership"

            # Check that VenueManagement relationship was created
            venue_management = VenueManagement.query.filter_by(
                user_id=test_user.id, venue_id=test_venue.id
            ).first()
            assert venue_management is not None

    def test_process_venue_manager_request_reject(
        self, app, test_user, test_venue, test_admin
    ):
        """Test VenueManagerService.process_venue_manager_request() rejection
        functionality.
        """
        with app.app_context():
            # Create request
            request = VenueManagerService.create_venue_manager_request(
                user_id=test_user.id,
                venue_id=test_venue.id,
                notes="I want to manage this venue",
            )

            # Process request - reject
            processed_request = VenueManagerService.process_venue_manager_request(
                request_id=request.id,
                admin_user=test_admin,
                approve=False,
                notes="Insufficient experience",
            )

            assert processed_request.status == "rejected"
            assert processed_request.processed_by_id == test_admin.id
            assert processed_request.notes == "Insufficient experience"

            # Check that NO VenueManagement relationship was created
            venue_management = VenueManagement.query.filter_by(
                user_id=test_user.id, venue_id=test_venue.id
            ).first()
            assert venue_management is None

    def test_process_venue_manager_request_non_admin(self, app, test_user, test_venue):
        """
        Test VenueManagerService.process_venue_manager_request() requires admin user.
        """
        with app.app_context():
            # Create request
            request = VenueManagerService.create_venue_manager_request(
                user_id=test_user.id,
                venue_id=test_venue.id,
                notes="I want to manage this venue",
            )

            # Create non-admin user
            director = User(
                username="director_user",
                email="director@example.com",
                role=UserRole.DIRECTOR.value,
            )
            director.set_password("secure123")
            db.session.add(director)
            db.session.commit()

            # Attempt to process with non-admin
            with pytest.raises(
                ValueError,
                match="Only administrators can process venue manager requests",
            ):
                VenueManagerService.process_venue_manager_request(
                    request_id=request.id, admin_user=director, approve=True
                )

            # Note: Cleanup handled by test isolation

    def test_process_venue_manager_request_not_found(self, app, test_admin):
        """Test VenueManagerService.process_venue_manager_request() with invalid
        request.
        """
        with app.app_context():
            with pytest.raises(ValueError, match="Request not found"):
                VenueManagerService.process_venue_manager_request(
                    request_id=99999, admin_user=test_admin, approve=True
                )

    def test_process_venue_manager_request_not_pending(
        self, app, test_user, test_venue, test_admin
    ):
        """Test VenueManagerService.process_venue_manager_request() requires pending
        status.
        """
        with app.app_context():
            # Create and process request
            request = VenueManagerService.create_venue_manager_request(
                user_id=test_user.id,
                venue_id=test_venue.id,
                notes="I want to manage this venue",
            )

            VenueManagerService.process_venue_manager_request(
                request_id=request.id, admin_user=test_admin, approve=True
            )

            # Attempt to process again
            with pytest.raises(ValueError, match="Request is not pending"):
                VenueManagerService.process_venue_manager_request(
                    request_id=request.id, admin_user=test_admin, approve=False
                )

    def test_get_pending_venue_manager_requests(
        self, app, test_user, test_venue, test_admin
    ):
        """
        Test VenueManagerService.get_pending_venue_manager_requests() functionality.
        """
        with app.app_context():
            # Initially no pending requests
            pending = VenueManagerService.get_pending_venue_manager_requests()
            initial_count = len(pending)

            # Create pending request
            VenueManagerService.create_venue_manager_request(
                user_id=test_user.id,
                venue_id=test_venue.id,
                notes="I want to manage this venue",
            )

            # Check pending requests
            pending = VenueManagerService.get_pending_venue_manager_requests()
            assert len(pending) == initial_count + 1
            assert pending[-1].status == "pending"

    def test_get_venue_manager_requests_by_user(
        self, app, test_user, test_venue, test_admin
    ):
        """
        Test VenueManagerService.get_venue_manager_requests_by_user() functionality.
        """
        with app.app_context():
            # Initially no requests for user
            user_requests = VenueManagerService.get_venue_manager_requests_by_user(
                test_user.id
            )
            assert len(user_requests) == 0

            # Create request
            VenueManagerService.create_venue_manager_request(
                user_id=test_user.id,
                venue_id=test_venue.id,
                notes="I want to manage this venue",
            )

            # Check user requests
            user_requests = VenueManagerService.get_venue_manager_requests_by_user(
                test_user.id
            )
            assert len(user_requests) == 1
            assert user_requests[0].user_id == test_user.id

    def test_get_venue_manager_requests_by_venue(self, app, test_user, test_venue):
        """
        Test VenueManagerService.get_venue_manager_requests_by_venue() functionality.
        """
        with app.app_context():
            # Initially no requests for venue
            venue_requests = VenueManagerService.get_venue_manager_requests_by_venue(
                test_venue.id
            )
            assert len(venue_requests) == 0

            # Create request
            VenueManagerService.create_venue_manager_request(
                user_id=test_user.id,
                venue_id=test_venue.id,
                notes="I want to manage this venue",
            )

            # Check venue requests
            venue_requests = VenueManagerService.get_venue_manager_requests_by_venue(
                test_venue.id
            )
            assert len(venue_requests) == 1
            assert venue_requests[0].venue_id == test_venue.id

    def test_is_venue_manager_specific_venue(
        self, app, test_user, test_venue, test_admin
    ):
        """Test VenueManagerService.is_venue_manager() for specific venue."""
        with app.app_context():
            # Initially not a venue manager
            assert (
                VenueManagerService.is_venue_manager(test_user.id, test_venue.id)
                is False
            )

            # Create and approve request
            request = VenueManagerService.create_venue_manager_request(
                user_id=test_user.id,
                venue_id=test_venue.id,
                notes="I want to manage this venue",
            )

            VenueManagerService.process_venue_manager_request(
                request_id=request.id, admin_user=test_admin, approve=True
            )

            # Now should be venue manager
            assert (
                VenueManagerService.is_venue_manager(test_user.id, test_venue.id)
                is True
            )

    def test_is_venue_manager_any_venue(self, app, test_user, test_venue, test_admin):
        """Test VenueManagerService.is_venue_manager() for any venue."""
        with app.app_context():
            # Initially not a venue manager
            assert VenueManagerService.is_venue_manager(test_user.id) is False

            # Create and approve request
            request = VenueManagerService.create_venue_manager_request(
                user_id=test_user.id,
                venue_id=test_venue.id,
                notes="I want to manage this venue",
            )

            VenueManagerService.process_venue_manager_request(
                request_id=request.id, admin_user=test_admin, approve=True
            )

            # Now should be venue manager
            assert VenueManagerService.is_venue_manager(test_user.id) is True

    def test_get_managed_venues(self, app, test_user, test_venue, test_admin):
        """Test VenueManagerService.get_managed_venues() functionality."""
        with app.app_context():
            # Initially no managed venues
            managed_venues = VenueManagerService.get_managed_venues(test_user.id)
            assert len(managed_venues) == 0

            # Create and approve request
            request = VenueManagerService.create_venue_manager_request(
                user_id=test_user.id,
                venue_id=test_venue.id,
                notes="I want to manage this venue",
            )

            VenueManagerService.process_venue_manager_request(
                request_id=request.id, admin_user=test_admin, approve=True
            )

            # Check managed venues
            managed_venues = VenueManagerService.get_managed_venues(test_user.id)
            assert len(managed_venues) == 1
            assert managed_venues[0].id == test_venue.id

    def test_remove_venue_manager(self, app, test_user, test_venue, test_admin):
        """Test VenueManagerService.remove_venue_manager() functionality."""
        with app.app_context():
            # Create and approve request
            request = VenueManagerService.create_venue_manager_request(
                user_id=test_user.id,
                venue_id=test_venue.id,
                notes="I want to manage this venue",
            )

            VenueManagerService.process_venue_manager_request(
                request_id=request.id, admin_user=test_admin, approve=True
            )

            # Verify management assignment exists
            assert (
                VenueManagerService.is_venue_manager(test_user.id, test_venue.id)
                is True
            )

            # Remove venue manager
            result = VenueManagerService.remove_venue_manager(
                user_id=test_user.id, venue_id=test_venue.id, admin_user=test_admin
            )

            assert result is True
            assert (
                VenueManagerService.is_venue_manager(test_user.id, test_venue.id)
                is False
            )

    def test_remove_venue_manager_non_admin(self, app, test_user, test_venue):
        """Test VenueManagerService.remove_venue_manager() requires admin user."""
        with app.app_context():
            # Create non-admin user
            director = User(
                username="director_user",
                email="director@example.com",
                role=UserRole.DIRECTOR.value,
            )
            director.set_password("secure123")
            db.session.add(director)
            db.session.commit()

            # Attempt to remove with non-admin
            with pytest.raises(
                ValueError, match="Only administrators can remove venue managers"
            ):
                VenueManagerService.remove_venue_manager(
                    user_id=test_user.id, venue_id=test_venue.id, admin_user=director
                )

            # Note: Cleanup handled by test isolation

    def test_remove_venue_manager_not_found(
        self, app, test_user, test_venue, test_admin
    ):
        """
        Test VenueManagerService.remove_venue_manager() with non-existent assignment.
        """
        with app.app_context():
            with pytest.raises(
                ValueError, match="Venue management assignment not found"
            ):
                VenueManagerService.remove_venue_manager(
                    user_id=test_user.id, venue_id=test_venue.id, admin_user=test_admin
                )
