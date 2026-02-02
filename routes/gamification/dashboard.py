# routes/gamification/dashboard.py
"""User-facing gamification routes: dashboard, achievements, quests, streaks, leaderboards."""

from flask import render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
from flask_babel import gettext as _

from models.gamification.level_service import LevelService
from models.gamification.achievement_service import AchievementService
from models.gamification.streak_service import StreakService
from models.gamification.quest_service import QuestService
from models.gamification.unlock_progress_service import UnlockProgressService
from models.gamification.models import (
    UserLevel, Achievement, UserAchievement, StreakTracker,
    AchievementCategory, AchievementDifficulty, StreakType,
    Quest, QuestStatus
)
from models.kpi import track_achievement_view, track_leaderboard_view
from utils import admin_required

from . import gamification_bp


# ============================================
# Test & Dashboard Routes
# ============================================


@gamification_bp.route("/test")
def test_gamification():
    """Test page for gamification mascot integration - no login required."""
    return render_template("test_gamification.html")


@gamification_bp.route("/dashboard")
@login_required
def dashboard():
    """
    Gamification dashboard showing user's complete gamification profile.

    Displays:
    - Current level and XP progress bar
    - Total XP earned and next unlock
    - Recent achievements (last 5 unlocked)
    - Current streaks
    - Active quests with progress

    Note: Admin users are redirected to the admin dashboard since they
    don't participate in gamification.
    """
    # Admin users don't participate in gamification - redirect to admin dashboard
    if current_user.is_admin:
        flash(_("Gli amministratori non partecipano alla gamification."), "info")
        return redirect(url_for("gamification.admin_dashboard"))

    # Get user's level progress
    progress = LevelService.get_level_progress(current_user.id)

    # Get detailed stats
    stats = LevelService.get_user_level_stats(current_user.id)

    # Get recent achievements (last 5 unlocked)
    all_unlocked = AchievementService.get_user_achievements(
        current_user.id,
        unlocked_only=True
    )
    # Sort by unlock date and take last 5
    recent_achievements = sorted(
        all_unlocked,
        key=lambda x: x.get("unlocked_at") or "",
        reverse=True
    )[:5]

    # Get current streaks
    streaks = StreakService.get_all_streaks(current_user.id)

    # Get active quests with user's progress
    active_quests = QuestService.get_user_quests(current_user.id, active_only=True)

    # Get locked features progress for "what's next" section
    locked_features = UnlockProgressService.get_locked_features_progress(current_user.id)

    return render_template(
        "gamification/dashboard.html",
        progress=progress,
        stats=stats,
        recent_achievements=recent_achievements,
        streaks=streaks,
        active_quests=active_quests,
        locked_features=locked_features,
        page_title=_("Dashboard Gamification")
    )


# ============================================
# User API Endpoints
# ============================================


@gamification_bp.route("/api/level-progress")
@login_required
def api_level_progress():
    """
    API endpoint for real-time level progress updates.
    """
    if current_user.is_admin:
        return jsonify({"error": "Admin users do not participate in gamification"}), 403

    progress = LevelService.get_level_progress(current_user.id)
    return jsonify(progress)


@gamification_bp.route("/api/user-stats")
@login_required
def api_user_stats():
    """
    API endpoint for detailed user statistics.
    """
    if current_user.is_admin:
        return jsonify({"error": "Admin users do not participate in gamification"}), 403

    stats = LevelService.get_user_level_stats(current_user.id)
    return jsonify(stats)


# ============================================
# Achievement Routes
# ============================================


@gamification_bp.route("/achievements")
@login_required
def achievements():
    """
    Achievement showcase displaying all achievements by category.

    Displays:
    - Unlocked achievements with unlock date
    - Locked achievements with progress (for progressive)
    - Hidden achievements (shown as ???)
    - Achievement categories and rarity
    """
    # Admin users don't participate in gamification
    if current_user.is_admin:
        flash(_("Gli amministratori non partecipano alla gamification."), "info")
        return redirect(url_for("gamification.admin_achievements"))

    # Get all user achievements grouped by category
    user_achievements = AchievementService.get_user_achievements(
        current_user.id,
        unlocked_only=False
    )

    # Get achievement stats (total, unlocked, by category)
    summary = AchievementService.get_achievement_stats(current_user.id)

    # Group by category for display
    achievements_by_category = {}
    for ua in user_achievements:
        achievement = ua.get("achievement")
        category = achievement.category.value if achievement else "other"
        if category not in achievements_by_category:
            achievements_by_category[category] = []
        achievements_by_category[category].append(ua)

    track_achievement_view()  # KPI tracking
    return render_template(
        "gamification/achievements.html",
        achievements_by_category=achievements_by_category,
        summary=summary,
        categories=AchievementCategory,
        difficulties=AchievementDifficulty,
        page_title=_("I Tuoi Achievement")
    )


# ============================================
# Leaderboard Routes
# ============================================


@gamification_bp.route("/leaderboards")
def leaderboards():
    """
    Leaderboards - public route, no login required.

    Displays:
    - XP leaderboard (all-time top 20)
    - Level leaderboard (highest levels)
    - Streak leaderboard (longest current streaks)
    """
    # Get leaderboard type from query param (default: xp)
    leaderboard_type_str = request.args.get("type", "xp")
    limit = min(int(request.args.get("limit", 20)), 100)

    from models.gamification.leaderboard_service import LeaderboardService
    from models.gamification.models import LeaderboardType

    # Map string type to enum
    type_map = {
        "xp": LeaderboardType.XP_ALL_TIME,
        "level": LeaderboardType.LEVEL_HIGHEST,
        "streak": LeaderboardType.STREAK_CURRENT,
        "elo": LeaderboardType.ELO_RATING
    }
    
    # Get all leaderboards for the view to allow switching without reload (or just active one)
    # Ideally for HTMX we'd fetch only one. For now fetch all 3 major ones.
    
    xp_leaderboard = LeaderboardService.get_leaderboard(LeaderboardType.XP_ALL_TIME, limit)
    level_leaderboard = LeaderboardService.get_leaderboard(LeaderboardType.LEVEL_HIGHEST, limit)
    streak_leaderboard = LeaderboardService.get_leaderboard(LeaderboardType.STREAK_CURRENT, limit)
    
    from models.gamification.ui_helpers import GamificationUIHelper
    elo_leaderboard = []
    if GamificationUIHelper.can_view_ratings(current_user):
        elo_leaderboard = LeaderboardService.get_leaderboard(LeaderboardType.ELO_RATING, limit)

    track_leaderboard_view()  # KPI tracking
    
    # Check if we should render partial (for tabs)
    if request.headers.get("HX-Request"):
        template_name = f"gamification/partials/leaderboard_{leaderboard_type_str}.html"
        # Since we don't have partials yet, stick to full render or create logic later
        pass

    return render_template(
        "gamification/leaderboards.html",
        xp_leaderboard=xp_leaderboard,
        level_leaderboard=level_leaderboard,
        streak_leaderboard=streak_leaderboard,
        elo_leaderboard=elo_leaderboard,
        active_tab=leaderboard_type_str,
        page_title=_("Classifiche")
    )


# ============================================
# Quest Routes
# ============================================


@gamification_bp.route("/quests")
@login_required
def quests():
    """
    Quest system showing user's quest progress.

    Displays:
    - Active quests with progress bars
    - Completed quests history
    - Upcoming quests preview
    """
    # Admin users don't participate in gamification
    if current_user.is_admin:
        flash(_("Gli amministratori non partecipano alla gamification."), "info")
        return redirect(url_for("gamification.admin_quests"))

    # Get active quests with user's progress
    active_quests = QuestService.get_user_quests(current_user.id, active_only=True)

    # Get user's completed quests
    all_quests = QuestService.get_user_quests(current_user.id, include_completed=True)
    completed_quests = [q for q in all_quests if q.get("is_completed")]

    # Get upcoming quests (status = UPCOMING)
    upcoming_quests = Quest.query.filter_by(status=QuestStatus.UPCOMING).all()

    return render_template(
        "gamification/quests.html",
        active_quests=active_quests,
        completed_quests=completed_quests,
        upcoming_quests=upcoming_quests,
        page_title=_("Quest Settimanali/Mensili")
    )


# ============================================
# Streak Routes
# ============================================


@gamification_bp.route("/streaks")
@login_required
def streaks():
    """
    Detailed streak view for user.

    Displays:
    - All streak types with current/longest values
    - Freeze availability
    - Milestone progress
    """
    # Admin users don't participate in gamification
    if current_user.is_admin:
        flash(_("Gli amministratori non partecipano alla gamification."), "info")
        return redirect(url_for("gamification.admin_streaks"))

    # Get all user streaks
    user_streaks = StreakService.get_all_streaks(current_user.id)

    # Milestones are included in each streak info
    # Get the primary activity streak for milestone display
    primary_streak = user_streaks.get("weekly_activity", {})

    return render_template(
        "gamification/streaks.html",
        streaks=user_streaks,
        primary_streak=primary_streak,
        streak_types=StreakType,
        page_title=_("Le Tue Streak")
    )


# ============================================
# API Endpoints
# ============================================


@gamification_bp.route("/api/achievements")
@login_required
def api_achievements():
    """API endpoint for user's achievements."""
    if current_user.is_admin:
        return jsonify([]), 403

    achievements = AchievementService.get_user_achievements(
        current_user.id,
        unlocked_only=request.args.get("unlocked_only", "false").lower() == "true"
    )
    return jsonify(achievements)


@gamification_bp.route("/api/streaks")
@login_required
def api_streaks():
    """API endpoint for user's streaks."""
    if current_user.is_admin:
        return jsonify({}), 403

    streaks = StreakService.get_all_streaks(current_user.id)
    return jsonify(streaks)


@gamification_bp.route("/api/quests")
@login_required
def api_quests():
    """API endpoint for active quests with user progress."""
    if current_user.is_admin:
        return jsonify([]), 403

    quests = QuestService.get_user_quests(current_user.id, active_only=True)
    # Convert to serializable format
    result = []
    for q in quests:
        quest = q.get("quest")
        result.append({
            "id": quest.id if quest else None,
            "name": quest.name if quest else None,
            "description": quest.description if quest else None,
            "is_participating": q.get("is_participating"),
            "is_completed": q.get("is_completed"),
            "progress_percentage": q.get("progress_percentage")
        })
    return jsonify(result)
