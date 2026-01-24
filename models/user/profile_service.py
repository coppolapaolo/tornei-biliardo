# models/user/profile_service.py
"""UserProfileService - User CRUD and authentication management.

This service extracts user profile management responsibilities from UserService
following Task 1.3 decomposition patterns.
"""

from typing import Optional, List, Dict, Any
from sqlalchemy import func
from models.base import db
from models.user.models import User
from models.user.role_enum import UserRole
from models.transaction.manager import transactional, read_only
from models.user.tokens import UserToken
from models.shared.email_service import EmailService
from flask import request  # For base_url


class UserProfileService:
    """Service for user profile management and authentication.

    **Responsibilities:**
    - User CRUD operations (create, read, update, delete)
    - User authentication and password management
    - User lookup and retrieval operations
    - Profile data management and validation

    **Transaction Management:**
    - Uses @transactional(domain="user") for state changes
    - Uses @read_only for query operations
    - Ensures atomicity of profile operations

    **Integration:**
    - Core foundation service for other user domain services
    - Provides authentication primitives for authorization
    - Supports user profile management workflows
    """

    @staticmethod
    @transactional(domain="user")
    def create_user(
        username: str,
        email: str,
        password: str,
        role: str = "player",
        phone: Optional[str] = None,
        send_verification_email: bool = True,
    ) -> User:
        """Create new user with validation and proper transaction management.

        Args:
            username: Unique username for community identification
            email: User's email address (encrypted storage)
            password: Plain text password (will be hashed using User.set_password())
            role: User role in the community (admin, director, player)
            phone: Optional phone number (encrypted storage)

        Returns:
            User: Newly created user instance with hashed password

        Raises:
            ValueError: If validation fails, user already exists, or admin
                constraint violated

        Business Rules:
            - Only one active admin allowed in the system
            - Username must be unique (case-insensitive)
            - Email must be unique across all users
            - Password must be at least 6 characters
        """
        # Business constraint: single active administrator in the system
        if role == UserRole.ADMIN.value:
            exists_active_admin = (
                User.query.filter_by(role=UserRole.ADMIN.value)
                .filter(User.deleted_at.is_(None))
                .count()
            )
            if exists_active_admin > 0:
                raise ValueError("Esiste già un amministratore attivo.")

        # Validate role
        if role not in ["admin", "director", "player"]:
            raise ValueError(
                f"Invalid role: {role}. Must be one of: admin, director, player"
            )

        # Validate required fields
        if not username or not username.strip():
            raise ValueError("Username is required")

        if not email or not email.strip():
            raise ValueError("Email is required")

        if not password or len(password.strip()) < 6:
            raise ValueError("Password must be at least 6 characters")

        # Check for existing username (case insensitive)
        existing_user = User.query.filter(
            func.lower(User.username) == func.lower(username.strip())
        ).first()
        if existing_user:
            raise ValueError(f"Username '{username}' already exists")

        # Check for existing email (encrypted field requires manual iteration)
        # Note: This is necessary due to EncryptedString field encryption
        email_normalized = email.strip().lower()
        users = User.query.all()
        for user in users:
            if user.email and user.email.lower() == email_normalized:
                raise ValueError(f"Email '{email}' already exists")

        # Create new user
        user = User(
            username=username.strip(),
            email=email.strip(),
            role=role,
            phone=phone.strip() if phone else None,
        )
        user.set_password(password)

        user.set_password(password)
        
        # New users are not verified by default (except admin for bootstrapping if needed, but let's keep consistent)
        user.is_verified = False

        db.session.add(user)
        db.session.flush()  # Need ID for token
        
        if send_verification_email:
            # Create verification token (saved in same transaction)
            token = UserToken.create_token(user.id, "verification")
            
            # Store data for post-commit email sending
            # The caller should call send_pending_verification_email() after this returns
            user._pending_verification_email = {
                'token': token,
                'base_url': request.host_url.rstrip("/")
            }

        return user

    @staticmethod
    def send_pending_verification_email(user: User) -> bool:
        """Send verification email for a user that was just created.
        
        This method should be called AFTER the transaction that created the user
        has been committed, to avoid holding database locks during email sending.
        
        Args:
            user: User instance with _pending_verification_email attribute set
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        pending_data = getattr(user, '_pending_verification_email', None)
        if not pending_data:
            return False
            
        try:
            EmailService.send_verification_email(
                user, 
                pending_data['token'], 
                pending_data['base_url']
            )
            # Clean up the temporary attribute
            delattr(user, '_pending_verification_email')
            return True
        except Exception:
            # Don't block if email fails, but log it
            return False

    @staticmethod
    @transactional(domain="user")
    def update_user(user_id: int, **kwargs) -> User:
        """Update user profile with validation and business rule enforcement.

        Args:
            user_id: ID of user to update
            **kwargs: Fields to update (username, email, phone)

        Returns:
            User: Updated user instance

        Raises:
            ValueError: If user not found, admin modification attempted, or
                validation fails

        Business Rules:
            - Admin users cannot be modified
            - Username uniqueness must be maintained
            - Only allowed fields can be updated
        """
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        # Prevent modification of admin users
        if user.role == UserRole.ADMIN.value:
            raise ValueError("Cannot modify administrator user")

        # Validate username uniqueness if being updated
        if "username" in kwargs:
            new_username = kwargs["username"].strip()
            existing_user = User.query.filter(
                User.username == new_username, User.id != user_id
            ).first()
            if existing_user:
                raise ValueError(f"Username '{new_username}' already exists")

        # Update allowed fields
        allowed_fields = ["username", "email", "phone"]
        for field, value in kwargs.items():
            if field in allowed_fields and hasattr(user, field):
                if isinstance(value, str):
                    setattr(user, field, value.strip() if value else None)
                else:
                    setattr(user, field, value)

        return user

    @staticmethod
    @transactional(domain="user")
    def change_password(user_id: int, old_password: str, new_password: str) -> bool:
        """Change user password with validation and security checks.

        Args:
            user_id: ID of user changing password
            old_password: Current password for verification
            new_password: New password to set

        Returns:
            bool: True if password changed successfully, False if old password incorrect

        Raises:
            ValueError: If user not found, admin modification attempted, or new
                password invalid

        Security Rules:
            - Admin passwords cannot be changed through this method
            - Old password must be verified before change
            - New password must meet minimum length requirement
        """
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        # Prevent admin password changes
        if user.role == UserRole.ADMIN.value:
            raise ValueError("Cannot change password for administrator user")

        # Validate old password
        if not user.check_password(old_password):
            return False

        # Validate new password
        if not new_password or len(new_password.strip()) < 6:
            raise ValueError("New password must be at least 6 characters")

        user.set_password(new_password)
        return True

    @staticmethod
    @transactional(domain="user")
    def soft_delete_user(user_id: int) -> None:
        """Soft delete user using SoftDeleteMixin functionality.

        Args:
            user_id: ID of user to soft delete

        Raises:
            ValueError: If user not found or admin deletion attempted

        Business Rules:
            - Admin users cannot be deleted
            - Uses soft delete to maintain audit trail
            - User data remains in database but marked as deleted
        """
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        # Prevent admin deletion
        if user.role == UserRole.ADMIN.value:
            raise ValueError("Cannot delete administrator user")

        user.soft_delete()

    @staticmethod
    @read_only(domain="user")
    def authenticate_user(username: str, password: str) -> Optional[User]:
        """Authenticate user credentials for login.

        Args:
            username: Username for authentication (case-insensitive)
            password: Plain text password to verify

        Returns:
            Optional[User]: User instance if authentication successful, None otherwise

        Security:
            - Uses secure password hashing verification
            - Case-insensitive username lookup
            - Returns None for invalid credentials (no detailed error info)
        """
        if not username or not password:
            return None

        user = User.query.filter(
            func.lower(User.username) == func.lower(username.strip())
        ).first()
        if user and user.check_password(password):
            return user
        return None

    @staticmethod
    @read_only(domain="user")
    def get_user_by_username(username: str) -> Optional[User]:
        """Get user by username with case-insensitive lookup.

        Args:
            username: Username to search for

        Returns:
            Optional[User]: User instance if found, None otherwise

        Search Behavior:
            - Case-insensitive matching (converts to lowercase)
            - Strips whitespace from input
            - Returns None for empty/None username
        """
        if not username:
            return None
        return User.query.filter(
            func.lower(User.username) == func.lower(username.strip())
        ).first()

    @staticmethod
    @read_only(domain="user")
    def get_user_by_email(email: str) -> Optional[User]:
        """Get user by email with encrypted field handling.

        Args:
            email: Email address to search for

        Returns:
            Optional[User]: User instance if found, None otherwise

        Implementation Notes:
            - Handles encrypted email fields by loading all users in memory
            - Case-insensitive matching (converts to lowercase)
            - Strips whitespace from input
            - Less efficient than username lookup due to encryption
            - Returns None for empty/None email
        """
        if not email:
            return None
        # For encrypted fields, we need to retrieve all users and filter in Python
        email_normalized = email.strip().lower()
        users = User.query.all()
        for user in users:
            if user.email and user.email.lower() == email_normalized:
                return user
        return None

    @staticmethod
    @read_only(domain="user")
    def get_all_users() -> List[User]:
        """Get all active users (excluding soft-deleted users).

        Returns:
            List[User]: List of all non-deleted users

        Soft Delete Handling:
            - Filters out users with deleted_at timestamp
            - Only returns currently active users
            - Maintains audit trail by keeping deleted users in database
            - Used for user listings and administrative views
        """
        return User.query.filter(User.deleted_at.is_(None)).all()

    @staticmethod
    @read_only(domain="user")
    def get_users_by_role(role: str) -> List[User]:
        """Get all active users by role.

        Args:
            role: User role to filter by ('admin', 'director', 'player')

        Returns:
            List[User]: List of active users with the specified role

        Role Filtering:
            - Filters by exact role match
            - Excludes soft-deleted users
            - Common roles: 'admin', 'director', 'player'
            - Used for role-based user management and statistics
        """
        return User.query.filter_by(role=role).filter(User.deleted_at.is_(None)).all()

    @staticmethod
    @read_only(domain="user")
    def get_user_detail_data(user_id: int) -> Dict[str, Any]:
        """Get comprehensive user data for profile display and analytics.

        Args:
            user_id: ID of user to retrieve data for

        Returns:
            Dict[str, Any]: Dictionary containing user, inscriptions, matches,
                and classifications

        Raises:
            ValueError: If user not found

        Data Structure:
            - user: User instance
            - inscriptions: Tournament registrations ordered by date
            - matches: User's matches ordered by recency
            - classifications: Tournament rankings ordered by date
        """
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        # Import models needed for complex queries
        from models.competition.models import Gara, Inscription
        from models.match.models import Match
        from models.classification.models import Classification
        from models.campionato.models import Campionato

        # User's tournament inscriptions (chronologically ordered)
        inscriptions = (
            Inscription.query.filter_by(user_id=user_id)
            .join(Gara)
            .join(Campionato)
            .order_by(Campionato.created_at.desc(), Gara.number.desc())
            .all()
        )

        # User's completed matches (chronologically ordered)
        matches = (
            Match.query.filter(
                db.or_(Match.player1_id == user_id, Match.player2_id == user_id)
            )
            .join(Gara)
            .join(Campionato)
            .order_by(
                Campionato.created_at.desc(),
                Gara.number.desc(),
                Match.round_number.desc(),
            )
            .all()
        )

        # User's tournament classifications (chronologically ordered)
        classifications = (
            Classification.query.filter_by(user_id=user_id)
            .join(Campionato)
            .order_by(Campionato.created_at.desc())
            .all()
        )

        return {
            "user": user,
            "inscriptions": inscriptions,
            "matches": matches,
            "classifications": classifications,
        }

    @staticmethod
    @transactional(domain="user")
    def request_verification_email(user: User) -> bool:
        """Request a new verification email for an existing user.

        Args:
            user: User instance to send verification email to

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if user.is_verified:
            return False
            
        try:
            token = UserToken.create_token(user.id, "verification")
            # request.host_url requires Flask request context, usually available in service call from route
            EmailService.send_verification_email(user, token, request.host_url.rstrip("/"))
            return True
        except Exception:
            # Helper to log exception would be good here
            return False

    @staticmethod
    @transactional(domain="user")
    def verify_email(token_str: str) -> bool:
        """Verify user email using token.

        Args:
            token_str: Verification token string

        Returns:
            bool: True if verified successfully, False otherwise
        """
        token = UserToken.query.filter_by(token=token_str, token_type="verification").first()
        if not token or not token.is_valid():
            return False

        user = db.session.get(User, token.user_id)
        if not user:
            return False

        user.is_verified = True
        token.mark_as_used()
        return True

    @staticmethod
    @transactional(domain="user")
    def request_password_reset(email: str) -> bool:
        """Request password reset for user.

        Args:
            email: User email

        Returns:
            bool: True if request processed (even if user not found, for security), False on error
        """
        user = UserProfileService.get_user_by_email(email)
        if not user:
            return True  # Return True to prevent user enumeration

        try:
            token = UserToken.create_token(user.id, "password_reset")
            EmailService.send_password_reset_email(user, token, request.host_url.rstrip("/"))
        except Exception:
            return False
            
        return True

    @staticmethod
    @transactional(domain="user")
    def reset_password_with_token(token_str: str, new_password: str) -> bool:
        """Reset password using token.

        Args:
            token_str: Reset token string
            new_password: New password

        Returns:
            bool: True if success, False otherwise
        """
        token = UserToken.query.filter_by(token=token_str, token_type="password_reset").first()
        if not token or not token.is_valid():
            return False

        user = db.session.get(User, token.user_id)
        if not user:
            return False

        if len(new_password.strip()) < 6:
            raise ValueError("Password must be at least 6 characters")

        user.set_password(new_password)
        token.mark_as_used()
        
        # Invalidate other sessions/tokens if needed (optional)
        
        return True

