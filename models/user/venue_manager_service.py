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
            ValueError: If user/venue not found, pending request exists, or
                motivation invalid

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
        # Ensures only one pending request per user-venue pair at a time
        existing_request = VenueManagerRequest.query.filter_by(
            user_id=user_id, venue_id=venue_id, status="pending"
        ).first()
        if existing_request:
            raise ValueError("Pending request already exists for this venue")

        # Validate notes
        if not notes or not notes.strip():
            raise ValueError("Notes are required")

        # Check if venue already has a manager (contested request)
        from models.user.models import VenueManagement
        current_manager = VenueManagement.query.filter_by(venue_id=venue_id).first()
        is_contested = current_manager is not None

        # Create new request
        request = VenueManagerRequest(
            user_id=user_id,
            venue_id=venue_id,
            notes=notes.strip(),
            status="pending",
            is_contested=is_contested,
        )

        db.session.add(request)

        # Create notifications for all admin users
        from models.notification.models import Notification, NotificationType, NotificationStatus, NotificationPriority
        from models.user.role_enum import UserRole

        admin_users = User.query.filter_by(role=UserRole.ADMIN.value).all()
        notification_priority = NotificationPriority.HIGH if is_contested else NotificationPriority.NORMAL

        # Different message for contested requests
        if is_contested:
            message = f"ATTENZIONE: L'utente {user.username} ha richiesto di gestire la venue {venue.name} (la venue ha già un gestore)"
        else:
            message = f"L'utente {user.username} ha richiesto di gestire la venue {venue.name}"

        for admin in admin_users:
            notification = Notification(
                user_id=admin.id,
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                title=f"Richiesta Gestore Sala - {venue.name}",
                message=message,
                status=NotificationStatus.PENDING,
                priority=notification_priority,
            )
            db.session.add(notification)

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
            # This grants the user management privileges for the venue
            venue_management = VenueManagement(
                user_id=request.user_id,
                venue_id=request.venue_id,
                assigned_by_id=admin_user.id
            )
            db.session.add(venue_management)

            # Send notification to user about approval
            from models.notification.services import NotificationService
            from models.notification.models import NotificationType, NotificationPriority

            message = f"La tua richiesta per gestire '{request.venue.name}' è stata approvata! Ora puoi gestire questa sala."
            if notes:
                message += f" Nota dell'admin: {notes}"

            NotificationService.create_notification(
                user_id=request.user_id,
                notification_type=NotificationType.ACCOUNT_UPDATE,
                title=f"Richiesta Gestore '{request.venue.name}' Approvata",
                message=message,
                priority=NotificationPriority.HIGH,
            )
        else:
            request.status = "rejected"
            request.processed_by_id = admin_user.id
            request.notes = notes

            # Send notification to user about rejection
            from models.notification.services import NotificationService
            from models.notification.models import NotificationType, NotificationPriority

            message = f"La tua richiesta per gestire '{request.venue.name}' è stata rifiutata."
            if notes:
                message += f" Motivo: {notes}"
            message += " Per maggiori informazioni, contatta l'amministratore."

            NotificationService.create_notification(
                user_id=request.user_id,
                notification_type=NotificationType.ACCOUNT_UPDATE,
                title=f"Richiesta Gestore '{request.venue.name}' Rifiutata",
                message=message,
                priority=NotificationPriority.NORMAL,
            )

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

    @staticmethod
    @transactional(domain="user")
    def assign_venue_manager(
        user_id: int, venue_id: int, assigned_by: User
    ) -> VenueManagement:
        """Assign a user as manager of a venue.

        Args:
            user_id: ID of user to assign as manager
            venue_id: ID of venue to assign
            assigned_by: Admin user making the assignment

        Returns:
            VenueManagement: Created assignment

        Raises:
            ValueError: If user/venue not found or venue already has manager
            PermissionError: If assigned_by is not admin
        """
        if assigned_by.role != UserRole.ADMIN.value:
            raise ValueError("Only administrators can assign venue managers")

        # Import User model for user validation
        from models.user.models import User

        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        # Import BilliardHall model for venue validation
        from models.location.models import BilliardHall

        venue = db.session.get(BilliardHall, venue_id)
        if not venue:
            raise ValueError("Venue not found")

        # Check if venue already has an active manager
        existing_assignment = VenueManagement.query.filter_by(
            venue_id=venue_id
        ).first()
        if existing_assignment:
            raise ValueError("Venue already has a manager")

        # Create assignment
        assignment = VenueManagement(
            user_id=user_id, venue_id=venue_id, assigned_by_id=assigned_by.id
        )
        db.session.add(assignment)

        return assignment

    @staticmethod
    @transactional(domain="user")
    def revoke_venue_manager(assignment_id: int, revoked_by: User) -> VenueManagement:
        """Revoke venue manager assignment.

        Args:
            assignment_id: ID of assignment to revoke
            revoked_by: Admin user revoking the assignment

        Returns:
            VenueManagement: Revoked assignment

        Raises:
            ValueError: If assignment not found
            PermissionError: If revoked_by is not admin
        """
        if revoked_by.role != UserRole.ADMIN.value:
            raise ValueError("Only administrators can revoke venue manager assignments")

        assignment = db.session.get(VenueManagement, assignment_id)
        if not assignment:
            raise ValueError("Venue management assignment not found")

        # Soft delete the assignment by setting a revoked_by field if it exists,
        # or delete it completely
        db.session.delete(assignment)

        # Send notification to user
        from models.notification.services import NotificationService
        from models.notification.models import NotificationType, NotificationPriority

        NotificationService.create_notification(
            user_id=assignment.user_id,
            notification_type=NotificationType.ACCOUNT_UPDATE,
            title="Revoca Gestione Sala",
            message="La tua gestione della sala è stata revocata dall'amministratore.",
            priority=NotificationPriority.NORMAL,
        )

        return assignment

    @staticmethod
    @read_only(domain="user")
    def get_venue_assignments(venue_id: int) -> List[VenueManagement]:
        """Get all assignments for a venue (including inactive ones).

        Args:
            venue_id: ID of venue

        Returns:
            List of VenueManagement assignments for the venue
        """
        return VenueManagement.query.filter_by(venue_id=venue_id).all()

    @staticmethod
    @read_only(domain="user")
    def get_venue_manager(venue_id: int) -> Optional:
        """Get current manager of a venue.

        Args:
            venue_id: ID of venue to get manager for

        Returns:
            User: Current venue manager or None if no manager assigned
        """
        from models.user.models import User

        assignment = VenueManagement.query.filter_by(venue_id=venue_id).first()
        return assignment.user if assignment else None
