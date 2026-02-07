"""
Module: models/user/role_decorators.py
Purpose: Role-based route protection decorators
"""

from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user, login_required

from .permissions import PermissionChecker


class RoleRequirement:
    """
    Decorator helper classes for role-based route protection.

    Provides decorators that can be applied to Flask routes to enforce
    role requirements and permissions.
    """

    @staticmethod
    def admin_required(f):
        """Decorator for admin-only functions."""

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin:
                abort(403)
            return f(*args, **kwargs)

        return decorated_function

    @staticmethod
    def director_required(f):
        """Decorator for director-only functions."""

        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.is_director and not current_user.is_admin:
                flash(
                    "Accesso negato. Funzione riservata ai direttori di torneo.",
                    "warning",
                )
                return redirect(url_for("dashboard.dashboard"))
            return f(*args, **kwargs)

        return decorated_function

    @staticmethod
    def director_or_admin_required(f):
        """Decorator for director/admin functions."""

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not (
                current_user.is_admin or current_user.is_director
            ):
                abort(403)
            return f(*args, **kwargs)

        return decorated_function

    @staticmethod
    def player_or_director_required(f):
        """
        Decorator for player/director functions (excludes admin and guest).

        Useful for functions like competition inscription where admin
        shouldn't participate as a player.
        """

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if (
                not current_user.is_authenticated
                or not (current_user.is_player or current_user.is_director)
                or current_user.is_admin
            ):
                abort(403)
            return f(*args, **kwargs)

        return decorated_function

    @staticmethod
    def authenticated_required(f):
        """Decorator for authenticated user functions."""

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            return f(*args, **kwargs)

        return decorated_function

    @staticmethod
    def campionato_manager_required(campionato_id_getter):
        """Decorator for campionato management functions."""

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
        """Decorator for competition management functions."""

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
        """Decorator for match result management functions."""

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
        """Generic decorator for custom permission checks."""

        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                if not permission_check(current_user, **kwargs):
                    abort(403)
                return f(*args, **kwargs)

            return decorated_function

        return decorator
