"""
Models package initialization - Phase 1 Completed

This module provides domain-driven model organization while maintaining
backward compatibility with existing code.

Phase 1 Status:
- ✅ Base infrastructure complete
- ✅ User domain extracted and modularized
- ⚠️ Other domains in legacy_models.py (Phase 2 target)

Author: Refactoring Phase 1
Updated: 2025-08-04 (Fixed import duplication issue)
"""

# Import database instance and utilities from base module
from .base import (
    db,
    get_or_create,
    bulk_create,
    safe_commit,
    init_db,
    reset_db,
)

# PHASE 1 COMPLETE: User domain imported from modular structure
from .user.models import User, TournamentDirector, DirectorRequest

# PHASE 1: Import remaining models from legacy_models.py
# These will be modularized in Phase 2
from .legacy_models import (
    Tournament,
    Prova,
    Inscription,
    Match,
    Rack,
    MatchResult,
    Classification,
    Playoff,
    PlayerEncounter,
    RoundClassification,
    TrioMatch,
)

# Export all available models for backward compatibility
__all__ = [
    # Database and utilities
    "db",
    "get_or_create",
    "bulk_create",
    "safe_commit",
    "init_db",
    "reset_db",
    # User domain models (Phase 1)
    "User",
    "TournamentDirector",
    "DirectorRequest",
    # Legacy models (Phase 2 target)
    "Tournament",
    "Prova",
    "Inscription",
    "Match",
    "Rack",
    "MatchResult",
    "Classification",
    "Playoff",
    "PlayerEncounter",
    "RoundClassification",
    "TrioMatch",
]

# Phase tracking
__version__ = "1.2.1-phase1-cleanup"
__phase__ = "Phase 1: User Domain Complete, Legacy Cleanup"


def get_current_models():
    """
    Get list of all currently available models.

    Returns:
        dict: Dictionary of model names and their classes
    """
    models = {}
    for name in __all__:
        if name not in [
            "db",
            "get_or_create",
            "bulk_create",
            "safe_commit",
            "init_db",
            "reset_db",
        ]:
            try:
                models[name] = globals()[name]
            except KeyError:
                models[name] = None
    return models


def verify_user_domain():
    """
    Verify that user domain is properly integrated.

    Returns:
        dict: Integration status
    """
    try:
        from .user.models import User as UserDomain
        from .user import check_domain_health

        # Test that our modular User is being used
        current_user = globals().get("User")
        is_modular = current_user is UserDomain

        domain_health = check_domain_health()

        return {
            "status": "success",
            "user_domain_active": is_modular,
            "domain_health": domain_health,
            "available_models": len(__all__),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "available_models": len(__all__),
        }


def verify_backward_compatibility():
    """
    Verify that backward compatibility is maintained.

    Returns:
        tuple: (success, missing_models)
    """
    expected_models = [
        "User",
        "TournamentDirector",
        "DirectorRequest",
        "Tournament",
        "Prova",
        "Inscription",
        "Match",
        "Rack",
        "MatchResult",
        "Classification",
        "Playoff",
    ]

    missing = []
    for model_name in expected_models:
        if model_name not in globals():
            missing.append(model_name)

    return len(missing) == 0, missing


# Debug information (development only)
if __name__ == "__main__":
    print(f"Models package {__version__}")
    print(f"Current phase: {__phase__}")
    print(f"Available models: {list(get_current_models().keys())}")

    # Test user domain integration
    user_status = verify_user_domain()
    print(f"User domain status: {user_status}")

    # Test backward compatibility
    success, missing = verify_backward_compatibility()
    if success:
        print("✅ Backward compatibility verified")
    else:
        print(f"⚠️ Missing models: {missing}")
