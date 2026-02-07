# models/user/permission_service.py
"""UserPermissionService - User roles and director requests management.

This service extracts user permission management responsibilities from UserService
following Task 1.3 decomposition patterns.
"""

from typing import Optional, List, Dict
from models.base import db, utc_now
from models.user.models import User, DirectorRequest
from models.user.role_enum import UserRole
from models.status_enum import DirectorRequestStatus
from models.transaction.manager import transactional, read_only


class UserPermissionService:
    """Service for user permissions and director request management.

    **Responsibilities:**
    - Director request workflow (create, process, approve/reject)
    - User role validation and checks
    - Permission-based operations
    - Role-based access control

    **Transaction Management:**
    - Uses @transactional(domain="user") for state changes
    - Uses @read_only(domain="user") for query operations
    - Ensures atomicity of permission operations

    **Integration:**
    - Coordinates with UserProfileService for user data
    - Manages director promotion workflow
    - Supports role-based authorization
    """

    @staticmethod
    @transactional(domain="user")
    def create_director_request(
        user_id: int, notes: Optional[str] = None
    ) -> DirectorRequest:
        """Create new director request with validation and business rule enforcement.

        Args:
            user_id: ID of user requesting director promotion
            notes: Optional justification or notes from user

        Returns:
            DirectorRequest: Newly created request in pending status

        Raises:
            ValueError: If user not found, already director/admin, or has pending request

        Business Rules:
            - Directors and admins cannot request promotion
            - Only one pending request allowed per user
            - No justification required
        """
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        # Check if user is already a director or admin
        if user.role in [UserRole.DIRECTOR.value, UserRole.ADMIN.value]:
            raise ValueError("User is already director or admin")

        # Check if user has the "Aspirante Direttore" achievement prerequisite
        from models.gamification.achievement_service import AchievementService

        if not AchievementService.has_achievement(user_id, "aspiring_director"):
            raise ValueError(
                "Devi sbloccare l'achievement 'Aspirante Direttore' per richiedere questo ruolo. "
                "Partecipa ad almeno 10 gare o completa un campionato intero."
            )

        # Check for existing pending request
        existing_request = DirectorRequest.query.filter_by(
            user_id=user_id, status=DirectorRequestStatus.PENDING.value
        ).first()
        if existing_request:
            raise ValueError("User already has a pending director request")

        # Create new request
        director_request = DirectorRequest(
            user_id=user_id, notes=notes, status=DirectorRequestStatus.PENDING.value
        )

        db.session.add(director_request)
        db.session.flush()  # Ensure ID is available for event

        # Emit event for notification system
        from models.events.user_events import DirectorRequestCreatedEvent
        from models.events.base import EventBus

        admin_users = User.query.filter_by(role=UserRole.ADMIN.value).all()
        admin_user_ids = [admin.id for admin in admin_users]

        event = DirectorRequestCreatedEvent(
            request_id=director_request.id,
            user_id=user_id,
            username=user.username,
            admin_user_ids=admin_user_ids,
        )
        EventBus.publish(event)

        return director_request

    @staticmethod
    @transactional(domain="user")
    def process_director_request(
        request_id: int, admin_user: User, approve: bool, notes: Optional[str] = None
    ) -> DirectorRequest:
        """Process director request with approval or rejection.

        Args:
            request_id: ID of director request to process
            admin_user: Admin user processing the request
            approve: True to approve, False to reject
            notes: Optional processing notes from admin

        Returns:
            DirectorRequest: Updated request with new status

        Raises:
            ValueError: If admin invalid, request not found, or request not pending

        Authorization:
            - Only admin users can process director requests
            - Request must be in pending status
            - Approval automatically promotes user to director role
        """
        # Validate admin user
        if admin_user.role != UserRole.ADMIN.value:
            raise ValueError("Only administrators can process director requests")

        director_request = db.session.get(DirectorRequest, request_id)
        if not director_request:
            raise ValueError("Director request not found")

        if director_request.status != DirectorRequestStatus.PENDING.value:
            raise ValueError("Director request is not pending")

        # Process the request with appropriate status and actions
        if approve:
            director_request.status = DirectorRequestStatus.APPROVED.value
            director_request.processed_by_id = admin_user.id
            director_request.processed_at = utc_now()
            director_request.notes = notes

            # Automatically promote user to director role upon approval
            user = db.session.get(User, director_request.user_id)
            if user:
                user.role = UserRole.DIRECTOR.value
        else:
            director_request.status = DirectorRequestStatus.REJECTED.value
            director_request.processed_by_id = admin_user.id
            director_request.processed_at = utc_now()
            director_request.notes = notes

        # Emit event for notification system
        db.session.flush()  # Ensure changes are persisted before event

        from models.events.user_events import DirectorRequestProcessedEvent
        from models.events.base import EventBus

        user = db.session.get(User, director_request.user_id)
        if user:
            event = DirectorRequestProcessedEvent(
                request_id=director_request.id,
                user_id=user.id,
                username=user.username,
                status=DirectorRequestStatus.APPROVED.value if approve else DirectorRequestStatus.REJECTED.value,
                processed_by_id=admin_user.id,
                notes=notes
            )
            EventBus.publish(event)

        return director_request

    @staticmethod
    @read_only(domain="user")
    def get_pending_director_requests() -> List[DirectorRequest]:
        """Get all pending director requests for admin review.

        Returns:
            List[DirectorRequest]: List of director requests awaiting admin processing

        Usage:
            - Used by admin interface to show pending requests
            - Filtered to only 'pending' status requests
            - Ordered by request creation date (implicit database order)
        """
        return DirectorRequest.query.filter_by(
            status=DirectorRequestStatus.PENDING.value
        ).all()

    @staticmethod
    @read_only(domain="user")
    def get_director_requests_by_user(user_id: int) -> List[DirectorRequest]:
        """Get all director requests for a specific user.

        Args:
            user_id: ID of user to get requests for

        Returns:
            List[DirectorRequest]: List of all requests by the user (all statuses)

        Usage:
            - Shows user's complete request history
            - Includes pending, approved, and rejected requests
            - Useful for user profile and request status tracking
        """
        return DirectorRequest.query.filter_by(user_id=user_id).all()

    @staticmethod
    @read_only(domain="user")
    def can_create_director_request(user_id: int) -> bool:
        """Check if user is eligible to create a new director request.

        Args:
            user_id: ID of user to check eligibility for

        Returns:
            bool: True if user can create director request, False otherwise

        Business Logic:
            - Returns False if user not found
            - Returns False if user is already director or admin
            - Returns False if user doesn't have 'Aspirante Direttore' achievement
            - Returns False if user has pending request
            - Returns True only if user is regular player with achievement and no pending request
        """
        user = db.session.get(User, user_id)
        if not user:
            return False

        # Users with elevated roles cannot request further promotion
        if user.role in [UserRole.DIRECTOR.value, UserRole.ADMIN.value]:
            return False

        # Check if user has the required achievement
        from models.gamification.achievement_service import AchievementService

        if not AchievementService.has_achievement(user_id, "aspiring_director"):
            return False

        # Users with pending requests cannot submit additional requests
        existing_request = DirectorRequest.query.filter_by(
            user_id=user_id, status=DirectorRequestStatus.PENDING.value
        ).first()
        if existing_request:
            return False

        return True

    @staticmethod
    @read_only(domain="user")
    def is_director_or_admin(user_id: int) -> bool:
        """Check if user has director or admin privileges.

        Args:
            user_id: ID of user to check

        Returns:
            bool: True if user is director or admin, False otherwise

        Permission Levels:
            - Returns True for both DIRECTOR and ADMIN roles
            - Returns False for PLAYER role or non-existent users
            - Used for authorization checks in tournament management
        """
        user = db.session.get(User, user_id)
        if not user:
            return False

        return user.role in [UserRole.DIRECTOR.value, UserRole.ADMIN.value]

    @staticmethod
    @read_only(domain="user")
    def is_admin(user_id: int) -> bool:
        """Check if user has admin privileges.

        Args:
            user_id: ID of user to check

        Returns:
            bool: True if user is admin, False otherwise

        Admin Privileges:
            - Only ADMIN role returns True
            - Directors and players return False
            - Used for highest-level authorization checks
            - Required for user management and system configuration
        """
        user = db.session.get(User, user_id)
        if not user:
            return False

        return user.role == UserRole.ADMIN.value

    @staticmethod
    @read_only(domain="user")
    def get_user_permissions(user_id: int) -> Dict[str, bool]:
        """Get comprehensive user permissions based on role and status.

        Args:
            user_id: ID of user to get permissions for

        Returns:
            Dict[str, bool]: Dictionary of permission flags

        Permission Structure:
            - can_create_competitions: Director/Admin can create tournaments
            - can_manage_users: Admin can manage user accounts
            - can_view_admin_panel: Admin can access admin interface
            - can_approve_director_requests: Admin can process director requests
            - can_create_director_request: Player can request director promotion
            - is_director: User has director role
            - is_admin: User has admin role
        """
        user = db.session.get(User, user_id)
        if not user:
            return {}

        permissions = {
            "can_create_competitions": user.role
            in [UserRole.DIRECTOR.value, UserRole.ADMIN.value],
            "can_manage_users": user.role == UserRole.ADMIN.value,
            "can_view_admin_panel": user.role == UserRole.ADMIN.value,
            "can_approve_director_requests": user.role == UserRole.ADMIN.value,
            "can_create_director_request": (
                UserPermissionService.can_create_director_request(user_id)
            ),
            "is_director": user.role == UserRole.DIRECTOR.value,
            "is_admin": user.role == UserRole.ADMIN.value,
        }

        return permissions

    @staticmethod
    @transactional(domain="user")
    def promote_to_director(user_id: int, promoted_by_id: int) -> bool:
        """Promote user to director role with authorization checks.

        Args:
            user_id: ID of user to promote
            promoted_by_id: ID of admin user performing promotion

        Returns:
            bool: True if promotion successful

        Raises:
            ValueError: If users not found, authorization fails, or promotion invalid

        Authorization:
            - Only admin users can promote to director
            - Cannot promote existing directors
            - Cannot promote admin users
            - Direct promotion bypasses formal request process
        """
        # Validate admin user
        admin_user = db.session.get(User, promoted_by_id)
        if not admin_user or admin_user.role != UserRole.ADMIN.value:
            raise ValueError("Only administrators can promote users")

        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        if user.role == UserRole.DIRECTOR.value:
            raise ValueError("User is already a director")

        if user.role == UserRole.ADMIN.value:
            raise ValueError("Cannot promote admin user")

        user.role = UserRole.DIRECTOR.value

        # Direct promotion without formal request process
        # Maintains backward compatibility with existing User model
        return True

    @staticmethod
    @transactional(domain="user")
    def demote_director_to_player(user_id: int, demoted_by_id: int) -> bool:
        """Demote director to player role with authorization checks.

        Args:
            user_id: ID of director to demote
            demoted_by_id: ID of admin user performing demotion

        Returns:
            bool: True if demotion successful

        Raises:
            ValueError: If users not found, authorization fails, or user not director

        Authorization:
            - Only admin users can demote directors
            - User must have director role to be demoted
            - Removes tournament creation and management privileges
        """
        # Validate admin user
        admin_user = db.session.get(User, demoted_by_id)
        if not admin_user or admin_user.role != UserRole.ADMIN.value:
            raise ValueError("Only administrators can demote users")

        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        if user.role != UserRole.DIRECTOR.value:
            raise ValueError("User is not a director")

        user.role = UserRole.PLAYER.value
        return True

    @staticmethod
    @transactional(domain="user")
    def request_director_promotion(
        user_id: int, notes: Optional[str] = None
    ) -> DirectorRequest:
        """Request director promotion (convenience alias).

        This is an alias for create_director_request() to provide alternative naming.
        See create_director_request() for complete documentation.

        Args:
            user_id: ID of user requesting promotion
            notes: Optional justification or notes from user

        Returns:
            DirectorRequest: Newly created request
        """
        return UserPermissionService.create_director_request(user_id, notes)

    @staticmethod
    @read_only(domain="user")
    def get_director_requests(status: Optional[str] = None) -> List[DirectorRequest]:
        """Get director requests with optional status filtering.

        Args:
            status: Optional status filter (pending, approved, rejected)

        Returns:
            List[DirectorRequest]: List of director requests matching criteria

        Usage:
            - get_director_requests() returns all requests
            - get_director_requests('pending') returns only pending requests
            - get_director_requests('approved') returns only approved requests
        """
        if status:
            return DirectorRequest.query.filter_by(status=status).all()
        return DirectorRequest.query.all()

    @staticmethod
    @read_only(domain="user")
    def can_view_admin_panel(user_id: int) -> bool:
        """Check if user has admin panel access permissions.

        Args:
            user_id: ID of user to check

        Returns:
            bool: True if user can view admin panel, False otherwise

        Authorization:
            - Only admin users can view admin panel
            - Directors and players do not have admin panel access
        """
        return UserPermissionService.is_admin(user_id)
