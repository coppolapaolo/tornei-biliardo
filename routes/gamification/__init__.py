"""
Gamification Routes - Dashboard and API Endpoints

Public routes:
- /gamification/dashboard - User's gamification dashboard with XP, level, achievements
- /gamification/leaderboards - Leaderboards (future)
- /gamification/achievements - Achievement showcase (future)

Admin routes:
- /gamification/admin/quests/create - Create weekly/monthly quests (future)

All routes respect user authentication and permissions.
"""

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from flask_babel import gettext as _

from models.gamification.level_service import LevelService

# Create blueprint
gamification_bp = Blueprint("gamification", __name__, url_prefix="/gamification")


@gamification_bp.route("/dashboard")
@login_required
def dashboard():
    """
    Gamification dashboard showing user's XP, level, and progress.
    
    Displays:
    - Current level and XP progress bar
    - Total XP earned
    - Next feature unlock
    - XP breakdown by source (future)
    - Recent level ups (future)
    - Achievement showcase (future)
    - Current streaks (future)
    """
    # Get user's level progress
    progress = LevelService.get_level_progress(current_user.id)
    
    # Get detailed stats
    stats = LevelService.get_user_level_stats(current_user.id)
    
    return render_template(
        "gamification/dashboard.html",
        progress=progress,
        stats=stats,
        page_title=_("Dashboard Gamification")
    )


@gamification_bp.route("/api/level-progress")
@login_required
def api_level_progress():
    """
    API endpoint for real-time level progress updates.
    
    Returns JSON with current level, XP, and progress percentage.
    Used by AJAX to update UI after XP gain.
    
    Response:
    {
        "current_level": 8,
        "current_xp": 450,
        "total_xp": 3500,
        "xp_for_next_level": 600,
        "progress_percentage": 75.0,
        "next_unlock": {
            "level": 10,
            "feature": "tournament_creation",
            "description": "Puoi creare tornei standalone"
        }
    }
    """
    progress = LevelService.get_level_progress(current_user.id)
    return jsonify(progress)


@gamification_bp.route("/api/user-stats")
@login_required
def api_user_stats():
    """
    API endpoint for detailed user statistics.
    
    Returns JSON with XP breakdown by source and recent transactions.
    
    Response:
    {
        "current_level": 8,
        "total_xp": 3500,
        "highest_level_reached": 8,
        "xp_by_type": {
            "match_win": 1200,
            "match_loss": 400,
            "tournament_inscription": 250,
            "tournament_completion": 1000,
            "tournament_win": 500
        },
        "recent_transactions": [
            {
                "type": "match_win",
                "xp_amount": 50,
                "reason": "Won match 456",
                "created_at": "2025-12-23T10:30:00"
            },
            ...
        ]
    }
    """
    stats = LevelService.get_user_level_stats(current_user.id)
    return jsonify(stats)


# Future routes (placeholders)

@gamification_bp.route("/achievements")
@login_required
def achievements():
    """
    Achievement showcase (FASE 2).
    
    Displays:
    - Unlocked achievements with progress
    - Locked achievements (with requirements)
    - Achievement categories
    - Rarity badges
    """
    return render_template(
        "gamification/achievements.html",
        page_title=_("I Tuoi Achievement")
    )


@gamification_bp.route("/leaderboards")
def leaderboards():
    """
    Leaderboards (FASE 4).
    
    Public route - no login required for viewing.
    
    Displays:
    - XP leaderboards (all-time, weekly, monthly)
    - Level leaderboards
    - Streak leaderboards
    - Win rate leaderboards
    """
    return render_template(
        "gamification/leaderboards.html",
        page_title=_("Classifiche")
    )


@gamification_bp.route("/quests")
@login_required
def quests():
    """
    Quest system (FASE 5).
    
    Displays:
    - Active quests with progress
    - Completed quests
    - Upcoming quests
    """
    return render_template(
        "gamification/quests.html",
        page_title=_("Quest Settimanali/Mensili")
    )
