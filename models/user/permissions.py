"""
Permission checking system for role-based access control

This module provides comprehensive permission checking functionality
for the campionato billiards application with granular control over
user actions based on roles and relationships.

Author: Refactoring Phase 1 - Task 1.3
Created: 2025-01-31
"""

from functools import wraps
from flask import abort
from flask_login import current_user


class PermissionChecker:
    """
    Centralized permission checking system for role-based access control.

    This class provides static methods to check various permissions
    throughout the application, supporting Admin, Director, and Player roles
    with context-aware permissions based on relationships and ownership.
    """

    @staticmethod
    def can_manage_campionato(user, campionato_id: int) -> bool:
        """
        Check if user can manage a specific campionato.

        Args:
            user: User instance or None
            campionato_id: ID of the campionato to check

        Returns:
            bool: True if user can manage the campionato
        """
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            return False

        # Admin can manage all campionati
        if user.is_admin:
            return True

        # Director can manage assigned campionati
        if user.is_director:
            try:
                from .models import DirectorAssignment
                from models.base import db

                assignment = (
                    db.session.query(DirectorAssignment)
                    .filter(
                        DirectorAssignment.entity_type == 'campionato',
                        DirectorAssignment.entity_id == campionato_id,
                        DirectorAssignment.user_id == user.id
                    )
                    .first()
                )
                return assignment is not None
            except Exception:
                # If we're outside application context or other issues, return False
                return False

        return False

    @staticmethod
    def can_manage_competition(user, competition_id: int) -> bool:
        """
        Check if user can manage a specific competition (gara).

        Args:
            user: User instance or None
            competition_id: ID of the competition to check

        Returns:
            bool: True if user can manage the competition
        """
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            return False

        # Admin can manage all competitions
        if user.is_admin:
            return True

        # Director can manage competitions in their campionati OR standalone gare they manage
        if user.is_director:
            try:
                # Import here to avoid circular imports during transition
                from models import Gara, db

                competition = db.session.get(Gara, competition_id)
                if competition:
                    # For gare in campionati
                    if competition.campionato_id:
                        return PermissionChecker.can_manage_campionato(
                            user, competition.campionato_id
                        )
                    # For standalone gare
                    else:
                        # Director principale
                        if hasattr(competition, 'director_id') and competition.director_id == user.id:
                            return True
                        # Co-direttore via DirectorAssignment
                        from .models import DirectorAssignment
                        is_co_director = (
                            db.session.query(DirectorAssignment)
                            .filter(
                                DirectorAssignment.entity_type == 'gara',
                                DirectorAssignment.entity_id == competition_id,
                                DirectorAssignment.user_id == user.id
                            )
                            .first() is not None
                        )
                        return is_co_director
            except Exception:
                # If we're outside application context or other issues, return False
                return False

        return False

    @staticmethod
    def can_view_admin_panel(user) -> bool:
        """
        Check if user can access admin panel.

        Args:
            user: User instance or None

        Returns:
            bool: True if user can access admin panel
        """
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            return False
        return user.is_admin

    @staticmethod
    def can_manage_users(user) -> bool:
        """
        Check if user can manage other users.

        Args:
            user: User instance or None

        Returns:
            bool: True if user can manage users
        """
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            return False
        return user.is_admin

    @staticmethod
    def can_inscribe_to_competition(user, competition_id: int) -> bool:
        """
        Check if user can inscribe to a competition.

        Args:
            user: User instance or None
            competition_id: ID of the competition

        Returns:
            bool: True if user can inscribe
        """
        if not user or not user.is_authenticated:
            return False

        # Admin cannot inscribe (administrative role only)
        if user.is_admin:
            return False

        # Players can always inscribe
        if user.is_player:
            return True

        # Directors cannot inscribe to competitions they manage
        if user.is_director:
            return not PermissionChecker.can_manage_competition(user, competition_id)

        return False

    @staticmethod
    def can_view_competition_management(user, competition_id: int) -> bool:
        """
        Check if user can view competition management interface.

        Args:
            user: User instance or None
            competition_id: ID of the competition

        Returns:
            bool: True if user can view management interface
        """
        return PermissionChecker.can_manage_competition(user, competition_id)

    @staticmethod
    def can_insert_match_results(user, match_id: int) -> bool:
        """
        Check if user can insert results for a match.

        Args:
            user: User instance or None
            match_id: ID of the match

        Returns:
            bool: True if user can insert results
        """
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            return False

        try:
            # Import here to avoid circular imports
            from models import Match, db

            match = db.session.get(Match, match_id)
            if not match:
                return False

            # Admin can insert any results
            if user.is_admin:
                return True

            # Director can insert results for matches in their competitions
            if user.is_director:
                return PermissionChecker.can_manage_competition(user, match.gara_id)

            # Players can insert results for their own matches
            if user.is_player:
                return match.player1_id == user.id or match.player2_id == user.id

        except Exception:
            # If we're outside application context or other issues, return False
            return False

        return False

    @staticmethod
    def can_create_campionato(user) -> bool:
        """
        Check if user can create new campionati.

        Args:
            user: User instance or None

        Returns:
            bool: True if user can create campionati
        """
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            return False
        return user.is_admin or user.is_director

    @staticmethod
    def can_delete_campionato(user, campionato_id: int) -> bool:
        """
        Check if user can delete a campionato.

        Args:
            user: User instance or None
            campionato_id: ID of the campionato

        Returns:
            bool: True if user can delete campionato
        """
        if not user or not user.is_authenticated:
            return False

        # Only admin can delete campionati
        # (Directors can manage but not delete)
        return user.is_admin

    @staticmethod
    def can_modify_campionato(user, campionato_id: int) -> bool:
        """
        Check if user can modify campionato settings.

        Args:
            user: User instance or None
            campionato_id: ID of the campionato

        Returns:
            bool: True if user can modify campionato
        """
        return PermissionChecker.can_manage_campionato(user, campionato_id)

    @staticmethod
    def can_assign_directors(user) -> bool:
        """
        Check if user can assign directors to campionati.

        Args:
            user: User instance or None

        Returns:
            bool: True if user can assign directors
        """
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            return False
        return user.is_admin

    @staticmethod
    def can_promote_user(user) -> bool:
        """
        Check if user can promote other users to director.

        Args:
            user: User instance or None

        Returns:
            bool: True if user can promote users
        """
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            return False
        return user.is_admin

    @staticmethod
    def can_process_director_requests(user) -> bool:
        """
        Check if user can process director promotion requests.

        Args:
            user: User instance or None

        Returns:
            bool: True if user can process requests
        """
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            return False
        return user.is_admin

    @staticmethod
    def can_reset_database(user) -> bool:
        """
        Check if user can reset the database.

        Args:
            user: User instance or None

        Returns:
            bool: True if user can reset database
        """
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            return False
        return user.is_admin

    @staticmethod
    def get_campionato_management_level(user, campionato_id: int) -> str:
        """
        Get the level of management permission for a campionato.

        Args:
            user: User instance or None
            campionato_id: ID of the campionato

        Returns:
            str: Permission level ('none', 'view', 'manage', 'full')
        """
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            return "none"

        if user.is_admin:
            return "full"  # Can do everything including delete

        try:
            if user.is_director and PermissionChecker.can_manage_campionato(
                user, campionato_id
            ):
                return "manage"  # Can manage but not delete
        except Exception:
            # If there's an error checking management, default to view
            pass

        return "view"  # Can only view

    @staticmethod
    def filter_campionatos_by_permission(user, campionati, permission_level="view"):
        """
        Filter campionati based on user permissions.

        Args:
            user: User instance or None
            campionati: List of campionato objects
            permission_level: Required permission level

        Returns:
            list: Filtered campionati
        """
        if (
            not user
            or not hasattr(user, "is_authenticated")
            or not user.is_authenticated
        ):
            return [] if permission_level != "view" else campionati

        if user.is_admin:
            return campionati  # Admin sees everything

        if permission_level == "view":
            return campionati  # Everyone can view all campionati

        if permission_level == "manage" and user.is_director:
            # Directors see only their assigned campionati
            try:
                from .models import DirectorAssignment
                from models.base import db

                managed_ids = [
                    da.entity_id for da in 
                    db.session.query(DirectorAssignment)
                    .filter(
                        DirectorAssignment.entity_type == 'campionato',
                        DirectorAssignment.user_id == user.id
                    )
                    .all()
                ]
                return [t for t in campionati if t.id in managed_ids]
            except Exception:
                # If there's an error with the query, return empty list
                return []

        return []

    @staticmethod
    def can_access_route(user, route_name: str, **kwargs) -> bool:
        """
        Check if user can access a specific route.

        Args:
            user: User instance or None
            route_name: Name of the route to check
            **kwargs: Additional parameters (campionato_id, competition_id, etc.)

        Returns:
            bool: True if user can access the route
        """
        if not user or not user.is_authenticated:
            return route_name in ["auth.login", "auth.register", "main.index"]

        # Route-specific permission mapping
        route_permissions = {
            # Admin-only routes
            "admin.dashboard": lambda u, **kw: u.is_admin,
            "admin.users_list": lambda u, **kw: u.is_admin,
            "admin.reset_database": lambda u, **kw: u.is_admin,
            "admin.director_requests": lambda u, **kw: u.is_admin,
            # Campionato management routes
            "admin.campionato_detail": (
                lambda u, **kw: (
                    lambda tid: tid is not None
                    and PermissionChecker.can_manage_campionato(u, tid)
                )(kw.get("campionato_id"))
            ),
            "admin.create_campionato": (
                lambda u, **kw: PermissionChecker.can_create_campionato(u)
            ),
            "admin.edit_campionato": (
                lambda u, **kw: (
                    lambda tid: tid is not None
                    and PermissionChecker.can_modify_campionato(u, tid)
                )(kw.get("campionato_id"))
            ),
            "admin.delete_campionato": (
                lambda u, **kw: (
                    lambda tid: tid is not None
                    and PermissionChecker.can_delete_campionato(u, tid)
                )(kw.get("campionato_id"))
            ),
            # Competition management routes
            "admin.gara_detail": (
                lambda u, **kw: (
                    lambda cid: cid is not None
                    and PermissionChecker.can_manage_competition(u, cid)
                )(kw.get("gara_id"))
            ),
            "admin.create_gara": (
                lambda u, **kw: (
                    lambda tid: tid is not None
                    and PermissionChecker.can_manage_campionato(u, tid)
                )(kw.get("campionato_id"))
            ),
            "admin.edit_gara": (
                lambda u, **kw: (
                    lambda cid: cid is not None
                    and PermissionChecker.can_manage_competition(u, cid)
                )(kw.get("gara_id"))
            ),
            # Player routes (all authenticated users)
            "player.dashboard": lambda u, **kw: True,
            "player.profile": lambda u, **kw: True,
            "player.delete_account": lambda u, **kw: True,
        }

        permission_check = route_permissions.get(route_name)
        if permission_check:
            return permission_check(user, **kwargs)

        # Default: allow access if not explicitly restricted
        return True


class RoleRequirement:
    """
    Decorator helper classes for role-based route protection.

    Provides decorators that can be applied to Flask routes to enforce
    role requirements and permissions.
    """

    @staticmethod
    def admin_required(f):
        """
        Decorator for admin-only functions.

        Args:
            f: Function to decorate

        Returns:
            function: Decorated function with admin check
        """

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin:
                abort(403)
            return f(*args, **kwargs)

        return decorated_function

    @staticmethod
    def director_required(f):
        """
        Decorator for director-only functions.

        Args:
            f: Function to decorate

        Returns:
            function: Decorated function with director check
        """

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or (not current_user.is_director and not current_user.is_admin):
                abort(403)
            return f(*args, **kwargs)

        return decorated_function

    @staticmethod
    def director_or_admin_required(f):
        """
        Decorator for director/admin functions.

        Args:
            f: Function to decorate

        Returns:
            function: Decorated function with director/admin check
        """

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not (
                current_user.is_admin or current_user.is_director
            ):
                abort(403)
            return f(*args, **kwargs)

        return decorated_function

    @staticmethod
    def authenticated_required(f):
        """
        Decorator for authenticated user functions.

        Args:
            f: Function to decorate

        Returns:
            function: Decorated function with authentication check
        """

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            return f(*args, **kwargs)

        return decorated_function

    @staticmethod
    def campionato_manager_required(campionato_id_getter):
        """
        Decorator for campionato management functions.

        Args:
            campionato_id_getter: Function or lambda to get campionato_id from kwargs

        Returns:
            function: Decorator function
        """

        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                campionato_id = (
                    campionato_id_getter(**kwargs)
                    if callable(campionato_id_getter)
                    else campionato_id_getter
                )
                if (
                    campionato_id is None
                    or not isinstance(campionato_id, int)
                    or not PermissionChecker.can_manage_campionato(
                        current_user, campionato_id
                    )
                ):
                    abort(403)
                return f(*args, **kwargs)

            return decorated_function

        return decorator

    @staticmethod
    def competition_manager_required(competition_id_getter):
        """
        Decorator for competition management functions.

        Args:
            competition_id_getter: Function or lambda to get competition_id from kwargs

        Returns:
            function: Decorator function
        """

        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                competition_id = (
                    competition_id_getter(**kwargs)
                    if callable(competition_id_getter)
                    else competition_id_getter
                )
                if (
                    competition_id is None
                    or not isinstance(competition_id, int)
                    or not PermissionChecker.can_manage_competition(
                        current_user, competition_id
                    )
                ):
                    abort(403)
                return f(*args, **kwargs)

            return decorated_function

        return decorator

    @staticmethod
    def match_result_manager_required(match_id_getter):
        """
        Decorator for match result management functions.

        Args:
            match_id_getter: Function or lambda to get match_id from kwargs

        Returns:
            function: Decorator function
        """

        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                match_id = (
                    match_id_getter(**kwargs)
                    if callable(match_id_getter)
                    else match_id_getter
                )
                if (
                    match_id is None
                    or not isinstance(match_id, int)
                    or not PermissionChecker.can_insert_match_results(
                        current_user, match_id
                    )
                ):
                    abort(403)
                return f(*args, **kwargs)

            return decorated_function

        return decorator

    @staticmethod
    def permission_required(permission_check):
        """
        Generic decorator for custom permission checks.

        Args:
            permission_check: Function that takes current_user and kwargs, returns bool

        Returns:
            function: Decorator function
        """

        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                if not permission_check(current_user, **kwargs):
                    abort(403)
                return f(*args, **kwargs)

            return decorated_function

        return decorator


# Utility functions for permission checking in templates
def user_can(permission: str, **kwargs) -> bool:
    """
    Template helper function for permission checking.

    Args:
        permission: Permission name to check
        **kwargs: Additional parameters for permission check

    Returns:
        bool: True if current user has permission
    """
    if not current_user.is_authenticated:
        return False

    permission_map = {
        "manage_campionatos": lambda **kw: current_user.is_admin
        or current_user.is_director,
        "manage_users": lambda **kw: PermissionChecker.can_manage_users(current_user),
        "view_admin_panel": lambda **kw: PermissionChecker.can_view_admin_panel(
            current_user
        ),
        "create_campionato": lambda **kw: PermissionChecker.can_create_campionato(
            current_user
        ),
        "manage_campionato": lambda **kw: (
            lambda tid: tid is not None
            and PermissionChecker.can_manage_campionato(current_user, tid)
        )(kw.get("campionato_id")),
        "manage_competition": lambda **kw: (
            lambda cid: cid is not None
            and PermissionChecker.can_manage_competition(current_user, cid)
        )(kw.get("competition_id")),
        "inscribe_to_competition": (
            lambda **kw: (
                lambda cid: cid is not None
                and PermissionChecker.can_inscribe_to_competition(current_user, cid)
            )(kw.get("competition_id"))
        ),
        "insert_match_results": lambda **kw: (
            lambda mid: mid is not None
            and PermissionChecker.can_insert_match_results(current_user, mid)
        )(kw.get("match_id")),
    }

    check_func = permission_map.get(permission)
    if check_func:
        return check_func(**kwargs)

    return False


def get_user_permissions_summary(user) -> dict:
    """
    Get a summary of user permissions for debugging/display.

    Args:
        user: User instance

    Returns:
        dict: Summary of permissions
    """
    if not user or not user.is_authenticated:
        return {"authenticated": False}

    return {
        "authenticated": True,
        "role": user.role,
        "can_view_admin_panel": PermissionChecker.can_view_admin_panel(user),
        "can_manage_users": PermissionChecker.can_manage_users(user),
        "can_create_campionato": PermissionChecker.can_create_campionato(user),
        "can_assign_directors": PermissionChecker.can_assign_directors(user),
        "can_promote_users": PermissionChecker.can_promote_user(user),
        "can_reset_database": PermissionChecker.can_reset_database(user),
        "managed_campionatos_count": len(user.get_managed_campionatos())
        if hasattr(user, "get_managed_campionatos")
        else 0,
    }


# Export public interface
__all__ = [
    "PermissionChecker",
    "RoleRequirement",
    "user_can",
    "get_user_permissions_summary",
]
