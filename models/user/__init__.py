"""
User domain models and services

This module contains all user-related models, services, and functionality
following Domain-Driven Design principles.

Domain: User Management
- User authentication and profiles
- Role-based permissions (Admin, Director, Player)
- Tournament director assignments
- Director promotion requests

Author: Refactoring Phase 1
Created: 2025-08-01
Updated: Task 1.4 - Added comprehensive services
"""

from .models import User, TournamentDirector, DirectorRequest
from .permissions import PermissionChecker, RoleRequirement
from .services import UserService, DirectorRequestService, UserStatsService

# Export all public classes and functions
__all__ = [
    # Models
    "User",
    "TournamentDirector",
    "DirectorRequest",
    # Permissions
    "PermissionChecker",
    "RoleRequirement",
    # Services
    "UserService",
    "DirectorRequestService",
    "UserStatsService",
]

# Domain version and metadata
__version__ = "1.0.0"
__domain__ = "User Management"
__phase__ = "Phase 1 - Task 1.4 Complete"


def get_user_models():
    """
    Get all user domain models.

    Returns:
        dict: Dictionary mapping model names to model classes
    """
    return {
        "User": User,
        "TournamentDirector": TournamentDirector,
        "DirectorRequest": DirectorRequest,
    }


def get_user_services():
    """
    Get all user domain services.

    Returns:
        dict: Dictionary mapping service names to service classes
    """
    return {
        "UserService": UserService,
        "DirectorRequestService": DirectorRequestService,
        "UserStatsService": UserStatsService,
    }


def check_domain_health():
    """
    Check if user domain is properly configured.

    Returns:
        dict: Health status and information
    """
    try:
        # Test model imports
        models = get_user_models()
        services = get_user_services()

        # Test basic functionality
        user_count = User.query.count() if hasattr(User, "query") else 0

        return {
            "status": "healthy",
            "models_count": len(models),
            "services_count": len(services),
            "total_users": user_count,
            "version": __version__,
            "phase": __phase__,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "version": __version__,
            "phase": __phase__,
        }
