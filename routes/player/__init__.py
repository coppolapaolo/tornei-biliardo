# routes/player/__init__.py
"""Player routes package.

This package contains all player-related routes decomposed into logical modules:
- profile: User profile, privacy settings, account management
- competitions: Gara inscriptions, history
- matches: Match operations, rack management
- proposals: Individual match proposals, availability system
- notifications: Notifications, venue manager requests
- challenges: Challenge system integration
"""
from flask import Blueprint

player_bp = Blueprint("player", __name__)

# Import all route modules to register their routes with the blueprint
from . import (
    profile,
    competitions,
    matches,
    proposals,
    notifications,
    challenges,
    geo,
)

__all__ = ["player_bp"]
