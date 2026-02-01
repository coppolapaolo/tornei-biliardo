# routes/gamification/__init__.py
"""
Gamification Routes - Dashboard and API Endpoints

This package contains all gamification-related routes decomposed into logical modules:
- dashboard: User-facing routes (dashboard, achievements, quests, streaks, leaderboards)
- admin: Admin management routes (quests, achievements, XP, streaks)
- config: Admin configuration routes (XP rates, levels, streak milestones)

Public routes:
- /gamification/dashboard - User's gamification dashboard with XP, level, achievements
- /gamification/leaderboards - XP, level, and streak leaderboards
- /gamification/achievements - Achievement showcase

User routes:
- /gamification/quests - Active and completed quests
- /gamification/streaks - Streak tracking

Admin routes:
- /gamification/admin - Admin dashboard
- /gamification/admin/quests - Quest management
- /gamification/admin/achievements - Achievement management
- /gamification/admin/xp - XP management
- /gamification/admin/streaks - Streak management
- /gamification/admin/config - Gamification configuration

All routes respect user authentication and permissions.
"""

from flask import Blueprint

# Create blueprint
gamification_bp = Blueprint("gamification", __name__, url_prefix="/gamification")

# Import all route modules to register their routes with the blueprint
from . import (
    dashboard,
    admin,
    config,
    features,
)

__all__ = ["gamification_bp"]
