# routes/player/__init__.py
"""Player routes package.

This package contains all player-related routes decomposed into logical modules:
- profile: User profile, privacy settings, account management
- competitions: Gara inscriptions, history
- matches: Match operations, rack management
- notifications: Notifications, venue manager requests
- challenges: Challenge system integration
"""

from flask import Blueprint

player_bp = Blueprint("player", __name__)

# Import all route modules to register their routes with the blueprint.
# Servono per l'effetto collaterale (registrano le route sul blueprint),
# non per il nome che legano: F401 qui e' atteso.
from . import (  # noqa: F401,E402
    profile,
    privacy,
    account,
    exports,
    competitions,
    matches,
    notifications,
    challenges,
    geo,
    playoff,
)

__all__ = ["player_bp"]
