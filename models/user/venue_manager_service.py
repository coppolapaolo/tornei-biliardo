# models/user/venue_manager_service.py
"""VenueManagerService - Venue management request workflow.

This service extracts venue management responsibilities from UserService
following Task 1.3 decomposition patterns.
"""

from typing import Optional, List
from models.base import db
from models.user.models import User, VenueManagerRequest, VenueManagement
from models.user.role_enum import UserRole
from models.transaction.manager import transactional, read_only


class VenueManagerService:
    """Service for venue management request workflow.

    **Responsibilities:**
    - Venue manager request creation and processing
    - Venue assignment and management
    - Permission validation for venue operations
    - Venue management workflow coordination

    **Transaction Management:**
    - Uses @transactional(domain="user") for state changes
    - Uses @read_only(domain="user") for query operations
    - Ensures atomicity of venue management operations

    **Integration:**
    - Coordinates with location domain for venue data
    - Supports venue-based permissions and access control
    - Manages venue manager assignments and requests
    """

    @staticmethod
    @transactional(domain="user")
    def create_venue_manager_request(
        user_id: int, venue_id: int, notes: str
    ) -> VenueManagerRequest:
        """Create new venue manager request with validation.

        Args:
            user_id: ID of user requesting venue management
            venue_id: ID of venue to manage (BilliardHall)
            notes: Written justification for management request

        Returns:
            VenueManagerRequest: Newly created request in pending status

        Raises:
            ValueError: If user/venue not found, pending request exists, or motivation invalid

        Business Rules:
            - One pending request per user-venue pair
            - Venue must exist in system
            - Notes are required and cannot be empty
        """
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        # Import BilliardHall model for venue validation
        from models.location.models import BilliardHall

        venue = db.session.get(BilliardHall, venue_id)
        if not venue:
            raise ValueError("Venue not found")

        # Check for existing pending request
        existing_request = VenueManagerRequest.query.filter_by(
            user_id=user_id, venue_id=venue_id, status="pending"
        ).first()
        if existing_request:
            raise ValueError("Pending request already exists for this venue")

        # Validate notes
        if not notes or not notes.strip():
            raise ValueError("Notes are required")

        # Create new request
        request = VenueManagerRequest(
            user_id=user_id,
            venue_id=venue_id,
            notes=notes.strip(),
            status="pending",
        )

        db.session.add(request)
        return request

    @staticmethod
    @transactional(domain="user")
    def process_venue_manager_request(
        request_id: int, admin_user: User, approve: bool, notes: Optional[str] = None
    ) -> VenueManagerRequest:
        """Process venue manager request with approval or rejection.

        Args:
            request_id: ID of venue manager request to process
            admin_user: Admin user processing the request
            approve: True to approve, False to reject
            notes: Optional processing notes from admin

        Returns:
            VenueManagerRequest: Updated request with new status

        Raises:
            ValueError: If admin invalid, request not found, or request not pending

        Authorization:
            - Only admin users can process venue manager requests
            - Request must be in pending status
            - Approval creates VenueManagement relationship
        """
        # Validate admin user
        if admin_user.role != UserRole.ADMIN.value:
            raise ValueError("Only administrators can process venue manager requests")

        request = db.session.get(VenueManagerRequest, request_id)
        if not request:
            raise ValueError("Request not found")

        if request.status != "pending":
            raise ValueError("Request is not pending")

        # Process the request with appropriate status and venue assignment
        if approve:
            request.status = "approved"
            request.processed_by_id = admin_user.id
            request.notes = notes

            # Create venue management relationship upon approval
            venue_management = VenueManagement(
                user_id=request.user_id, venue_id=request.venue_id
            )
            db.session.add(venue_management)
        else:
            request.status = "rejected"
            request.processed_by_id = admin_user.id
            request.notes = notes

        return request

    @staticmethod
    @read_only(domain="user")
    def get_pending_venue_manager_requests() -> List[VenueManagerRequest]:
        """Get all pending venue manager requests for admin review.

        Returns:
            List[VenueManagerRequest]: List of requests awaiting admin processing

        Usage:
            - Used by admin interface to show pending requests
            - Filters to only pending status requests
            - Ordered by request creation date
        """
        return VenueManagerRequest.query.filter_by(status="pending").all()

    @staticmethod
    @read_only(domain="user")
    def get_venue_manager_requests_by_user(user_id: int) -> List[VenueManagerRequest]:
        """Get all venue manager requests for a specific user.

        Args:
            user_id: ID of user to get requests for

        Returns:
            List[VenueManagerRequest]: List of all requests by the user (all statuses)

        Usage:
            - Shows user's complete request history
            - Includes pending, approved, and rejected requests
            - Useful for user profile and request status tracking
        """
        return VenueManagerRequest.query.filter_by(user_id=user_id).all()

    @staticmethod
    @read_only(domain="user")
    def get_venue_manager_requests_by_venue(venue_id: int) -> List[VenueManagerRequest]:
        """Get all venue manager requests for a specific venue.

        Args:
            venue_id: ID of venue to get requests for

        Returns:
            List[VenueManagerRequest]: List of all requests for the venue (all statuses)

        Usage:
            - Shows venue's complete request history
            - Includes requests from all users for this venue
            - Useful for venue-specific management analytics
        """
        return VenueManagerRequest.query.filter_by(venue_id=venue_id).all()

    @staticmethod
    @read_only(domain="user")
    def is_venue_manager(user_id: int, venue_id: Optional[int] = None) -> bool:
        """Check if user is a venue manager for specific or any venue.

        Args:
            user_id: ID of user to check
            venue_id: Optional specific venue ID to check

        Returns:
            bool: True if user manages the venue(s), False otherwise

        Usage:
            - is_venue_manager(user_id, venue_id) checks specific venue
            - is_venue_manager(user_id) checks if user manages any venue
        """
        if venue_id:
            return (
                VenueManagement.query.filter_by(
                    user_id=user_id, venue_id=venue_id
                ).first()
                is not None
            )
        else:
            return VenueManagement.query.filter_by(user_id=user_id).first() is not None

    @staticmethod
    @read_only(domain="user")
    def get_managed_venues(user_id: int) -> List:
        """Get all venues managed by a user.

        Args:
            user_id: ID of user to get managed venues for

        Returns:
            List[BilliardHall]: List of venues managed by the user

        Query Details:
            - Joins VenueManagement with BilliardHall
            - Returns full BilliardHall objects
            - Shows all venues where user has management privileges
        """
        from models.location.models import BilliardHall  # Import for join query

        managed_venues = (
            db.session.query(BilliardHall)
            .join(VenueManagement, VenueManagement.venue_id == BilliardHall.id)
            .filter(VenueManagement.user_id == user_id)
            .all()
        )

        return managed_venues

    @staticmethod
    @transactional(domain="user")
    def remove_venue_manager(user_id: int, venue_id: int, admin_user: User) -> bool:
        """Remove venue manager assignment with authorization checks.

        Args:
            user_id: ID of user to remove from venue management
            venue_id: ID of venue to remove management from
            admin_user: Admin user performing the removal

        Returns:
            bool: True if removal successful

        Raises:
            ValueError: If admin invalid or management assignment not found

        Authorization:
            - Only admin users can remove venue managers
            - Management assignment must exist
            - Permanently removes management privileges for the venue
        """
        # Validate admin user
        if admin_user.role != UserRole.ADMIN.value:
            raise ValueError("Only administrators can remove venue managers")

        venue_management = VenueManagement.query.filter_by(
            user_id=user_id, venue_id=venue_id
        ).first()

        if not venue_management:
            raise ValueError("Venue management assignment not found")

        db.session.delete(venue_management)
        return True
