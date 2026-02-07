"""
Module: models/user/permission_helpers.py
Purpose: Template helpers and utility functions for permission checking
"""

from flask_login import current_user

from .permissions import PermissionChecker


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
        "managed_campionatos_count": (
            len(user.get_managed_campionatos())
            if hasattr(user, "get_managed_campionatos")
            else 0
        ),
    }
