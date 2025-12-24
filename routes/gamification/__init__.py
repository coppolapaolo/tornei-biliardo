"""
Gamification Routes - Dashboard and API Endpoints

Public routes:
- /gamification/dashboard - User's gamification dashboard with XP, level, achievements
- /gamification/leaderboards - XP, level, and streak leaderboards
- /gamification/achievements - Achievement showcase

User routes:
- /gamification/quests - Active and completed quests
- /gamification/streaks - Streak tracking

Admin routes:
- /gamification/admin/quests - Quest management (future)

All routes respect user authentication and permissions.
"""

from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
from flask_babel import gettext as _

from utils import admin_required
from models.base import db
from models.gamification.level_service import LevelService
from models.gamification.achievement_service import AchievementService
from models.gamification.streak_service import StreakService
from models.gamification.quest_service import QuestService
from models.gamification.models import (
    UserLevel, Achievement, UserAchievement, StreakTracker,
    AchievementCategory, AchievementDifficulty, StreakType,
    LeaderboardType, Quest, QuestStatus, XPTransactionType
)

# Create blueprint
gamification_bp = Blueprint("gamification", __name__, url_prefix="/gamification")


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

    return render_template(
        "gamification/dashboard.html",
        progress=progress,
        stats=stats,
        recent_achievements=recent_achievements,
        streaks=streaks,
        active_quests=active_quests,
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

    return render_template(
        "gamification/achievements.html",
        achievements_by_category=achievements_by_category,
        summary=summary,
        categories=AchievementCategory,
        difficulties=AchievementDifficulty,
        page_title=_("I Tuoi Achievement")
    )


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
    leaderboard_type = request.args.get("type", "xp")
    limit = min(int(request.args.get("limit", 20)), 100)

    # Get XP leaderboard (all-time)
    xp_leaderboard = UserLevel.query.order_by(
        UserLevel.total_xp.desc()
    ).limit(limit).all()

    # Get level leaderboard
    level_leaderboard = UserLevel.query.order_by(
        UserLevel.current_level.desc(),
        UserLevel.total_xp.desc()
    ).limit(limit).all()

    # Get streak leaderboard (weekly activity streaks)
    streak_leaderboard = StreakTracker.query.filter_by(
        streak_type=StreakType.WEEKLY_ACTIVITY
    ).order_by(
        StreakTracker.current_streak.desc()
    ).limit(limit).all()

    return render_template(
        "gamification/leaderboards.html",
        xp_leaderboard=xp_leaderboard,
        level_leaderboard=level_leaderboard,
        streak_leaderboard=streak_leaderboard,
        active_tab=leaderboard_type,
        page_title=_("Classifiche")
    )


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
    achievements = AchievementService.get_user_achievements(
        current_user.id,
        unlocked_only=request.args.get("unlocked_only", "false").lower() == "true"
    )
    return jsonify(achievements)


@gamification_bp.route("/api/streaks")
@login_required
def api_streaks():
    """API endpoint for user's streaks."""
    streaks = StreakService.get_all_streaks(current_user.id)
    return jsonify(streaks)


@gamification_bp.route("/api/quests")
@login_required
def api_quests():
    """API endpoint for active quests with user progress."""
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


# ============================================
# Admin Routes - Gamification Management
# ============================================

@gamification_bp.route("/admin")
@admin_required
def admin_dashboard():
    """
    Gamification admin dashboard - overview of system status.

    Displays:
    - Total XP distributed
    - Active users by level
    - Quest participation stats
    - Achievement unlock rates
    """
    from models import User
    from sqlalchemy import func

    # Get level distribution
    level_stats = db.session.query(
        UserLevel.current_level,
        func.count(UserLevel.user_id).label("count")
    ).group_by(UserLevel.current_level).order_by(UserLevel.current_level).all()

    # Get total XP distributed
    total_xp = db.session.query(func.sum(UserLevel.total_xp)).scalar() or 0

    # Get quest stats
    active_quests = Quest.query.filter_by(status=QuestStatus.ACTIVE).count()

    # Get achievement stats
    total_achievements = Achievement.query.count()
    total_unlocks = UserAchievement.query.filter(
        UserAchievement.unlocked_at.isnot(None)
    ).count()

    # Get top XP users
    top_users = UserLevel.query.order_by(
        UserLevel.total_xp.desc()
    ).limit(10).all()

    return render_template(
        "gamification/admin/dashboard.html",
        level_stats=level_stats,
        total_xp=total_xp,
        active_quests=active_quests,
        total_achievements=total_achievements,
        total_unlocks=total_unlocks,
        top_users=top_users,
        page_title=_("Admin Gamification")
    )


# --------------------------------------------
# Quest Management
# --------------------------------------------

@gamification_bp.route("/admin/quests")
@admin_required
def admin_quests():
    """List all quests for management."""
    quests = Quest.query.order_by(Quest.start_date.desc()).all()
    return render_template(
        "gamification/admin/quests.html",
        quests=quests,
        quest_statuses=QuestStatus,
        page_title=_("Gestione Quest")
    )


@gamification_bp.route("/admin/quests/create", methods=["GET", "POST"])
@admin_required
def admin_create_quest():
    """Create a new quest."""
    from models.gamification.models import QuestType
    from datetime import datetime, timedelta

    if request.method == "POST":
        try:
            # Parse form data
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            quest_type = request.form.get("quest_type", "weekly")
            requirement_type = request.form.get("requirement_type", "matches_played")
            requirement_target = int(request.form.get("requirement_target", 10))
            xp_reward = int(request.form.get("xp_reward", 100))

            # Parse dates
            start_date_str = request.form.get("start_date")
            end_date_str = request.form.get("end_date")

            if not name:
                flash(_("Il nome della quest è obbligatorio"), "error")
                return redirect(url_for("gamification.admin_create_quest"))

            start_date = datetime.fromisoformat(start_date_str) if start_date_str else datetime.utcnow()

            if end_date_str:
                end_date = datetime.fromisoformat(end_date_str)
            else:
                # Default duration based on type
                if quest_type == "weekly":
                    end_date = start_date + timedelta(days=7)
                else:
                    end_date = start_date + timedelta(days=30)

            # Determine initial status
            now = datetime.utcnow()
            if start_date <= now < end_date:
                status = QuestStatus.ACTIVE
            elif start_date > now:
                status = QuestStatus.UPCOMING
            else:
                status = QuestStatus.EXPIRED

            # Create quest
            quest = Quest(
                name=name,
                description=description,
                quest_type=QuestType[quest_type.upper()],
                status=status,
                start_date=start_date,
                end_date=end_date,
                requirements={"type": requirement_type, "target": requirement_target},
                xp_reward=xp_reward
            )
            db.session.add(quest)
            db.session.commit()

            flash(_("Quest creata con successo"), "success")
            return redirect(url_for("gamification.admin_quests"))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore nella creazione: {str(e)}", "error")
            return redirect(url_for("gamification.admin_create_quest"))

    # GET - show form
    return render_template(
        "gamification/admin/quest_form.html",
        quest=None,
        page_title=_("Crea Nuova Quest")
    )


@gamification_bp.route("/admin/quests/<int:quest_id>/activate", methods=["POST"])
@admin_required
def admin_activate_quest(quest_id: int):
    """Activate a quest (set status to ACTIVE)."""
    quest = db.session.get(Quest, quest_id)
    if not quest:
        flash(_("Quest non trovata"), "error")
        return redirect(url_for("gamification.admin_quests"))

    try:
        quest.status = QuestStatus.ACTIVE
        db.session.commit()
        flash(_("Quest attivata"), "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_quests"))


@gamification_bp.route("/admin/quests/<int:quest_id>/expire", methods=["POST"])
@admin_required
def admin_expire_quest(quest_id: int):
    """Expire a quest (set status to EXPIRED)."""
    quest = db.session.get(Quest, quest_id)
    if not quest:
        flash(_("Quest non trovata"), "error")
        return redirect(url_for("gamification.admin_quests"))

    try:
        quest.status = QuestStatus.EXPIRED
        db.session.commit()
        flash(_("Quest scaduta"), "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_quests"))


@gamification_bp.route("/admin/quests/<int:quest_id>/delete", methods=["POST"])
@admin_required
def admin_delete_quest(quest_id: int):
    """Delete a quest (only if no participants)."""
    quest = db.session.get(Quest, quest_id)
    if not quest:
        flash(_("Quest non trovata"), "error")
        return redirect(url_for("gamification.admin_quests"))

    if quest.participant_count > 0:
        flash(_("Non è possibile eliminare una quest con partecipanti"), "error")
        return redirect(url_for("gamification.admin_quests"))

    try:
        db.session.delete(quest)
        db.session.commit()
        flash(_("Quest eliminata"), "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_quests"))


# --------------------------------------------
# Achievement Management
# --------------------------------------------

@gamification_bp.route("/admin/achievements")
@admin_required
def admin_achievements():
    """List all achievements with unlock statistics."""
    from sqlalchemy import func

    # Get all achievements with unlock counts
    achievements = Achievement.query.all()

    # Get unlock counts per achievement
    unlock_stats = dict(
        db.session.query(
            UserAchievement.achievement_id,
            func.count(UserAchievement.id).label("count")
        ).filter(
            UserAchievement.unlocked_at.isnot(None)
        ).group_by(UserAchievement.achievement_id).all()
    )

    # Combine data
    achievement_data = []
    for achievement in achievements:
        achievement_data.append({
            "achievement": achievement,
            "unlock_count": unlock_stats.get(achievement.id, 0)
        })

    return render_template(
        "gamification/admin/achievements.html",
        achievements=achievement_data,
        categories=AchievementCategory,
        difficulties=AchievementDifficulty,
        page_title=_("Gestione Achievement")
    )


@gamification_bp.route("/admin/achievements/create", methods=["GET", "POST"])
@admin_required
def admin_create_achievement():
    """Create a new achievement."""
    import json

    if request.method == "POST":
        try:
            slug = request.form.get("slug", "").strip().lower().replace(" ", "_")
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            category = request.form.get("category", "match")
            difficulty = request.form.get("difficulty", "common")
            icon_path = request.form.get("icon_path", "").strip() or None
            xp_reward = int(request.form.get("xp_reward", 50))
            is_hidden = request.form.get("is_hidden") == "on"
            is_progressive = request.form.get("is_progressive") == "on"
            requirement_type = request.form.get("requirement_type", "match_wins")
            requirement_value = int(request.form.get("requirement_value", 1))

            if not slug or not name:
                flash(_("Slug e nome sono obbligatori"), "error")
                return redirect(url_for("gamification.admin_create_achievement"))

            # Check unique slug
            if Achievement.query.filter_by(slug=slug).first():
                flash(_("Un achievement con questo slug esiste già"), "error")
                return redirect(url_for("gamification.admin_create_achievement"))

            # Build requirements JSON
            requirements = json.dumps({"type": requirement_type, "count": requirement_value})

            achievement = Achievement(
                slug=slug,
                name=name,
                description=description,
                category=AchievementCategory[category.upper()],
                difficulty=AchievementDifficulty[difficulty.upper()],
                icon_path=icon_path,
                xp_reward=xp_reward,
                is_hidden=is_hidden,
                is_progressive=is_progressive,
                requirements=requirements
            )
            db.session.add(achievement)
            db.session.commit()

            flash(_("Achievement creato con successo"), "success")
            return redirect(url_for("gamification.admin_achievements"))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore nella creazione: {str(e)}", "error")
            return redirect(url_for("gamification.admin_create_achievement"))

    return render_template(
        "gamification/admin/achievement_form.html",
        achievement=None,
        categories=AchievementCategory,
        difficulties=AchievementDifficulty,
        page_title=_("Crea Nuovo Achievement")
    )


@gamification_bp.route("/admin/achievements/<int:achievement_id>/toggle_hidden", methods=["POST"])
@admin_required
def admin_toggle_achievement_hidden(achievement_id: int):
    """Toggle hidden status of an achievement."""
    achievement = db.session.get(Achievement, achievement_id)
    if not achievement:
        flash(_("Achievement non trovato"), "error")
        return redirect(url_for("gamification.admin_achievements"))

    try:
        achievement.is_hidden = not achievement.is_hidden
        db.session.commit()
        status = "nascosto" if achievement.is_hidden else "visibile"
        flash(f"Achievement ora {status}", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_achievements"))


# --------------------------------------------
# XP & Level Management
# --------------------------------------------

@gamification_bp.route("/admin/xp")
@admin_required
def admin_xp_management():
    """XP management dashboard - grant XP, view transactions."""
    from models import User
    from models.gamification.models import XPTransaction

    # Get recent transactions
    recent_transactions = XPTransaction.query.order_by(
        XPTransaction.created_at.desc()
    ).limit(50).all()

    # Get users for dropdown
    users = User.query.filter_by(is_deleted=False).order_by(User.username).all()

    return render_template(
        "gamification/admin/xp_management.html",
        recent_transactions=recent_transactions,
        users=users,
        xp_types=XPTransactionType,
        page_title=_("Gestione XP")
    )


@gamification_bp.route("/admin/xp/grant", methods=["POST"])
@admin_required
def admin_grant_xp():
    """Grant XP to a user (admin tool)."""
    from models.gamification.models import XPTransactionType

    try:
        user_id = int(request.form.get("user_id", 0))
        xp_amount = int(request.form.get("xp_amount", 0))
        reason = request.form.get("reason", "Admin grant").strip()

        if user_id <= 0:
            flash(_("Seleziona un utente valido"), "error")
            return redirect(url_for("gamification.admin_xp_management"))

        if xp_amount <= 0:
            flash(_("L'importo XP deve essere positivo"), "error")
            return redirect(url_for("gamification.admin_xp_management"))

        # Award XP using the service
        user_level, new_level = LevelService.award_xp(
            user_id=user_id,
            xp_amount=xp_amount,
            transaction_type=XPTransactionType.ADMIN_GRANT,
            reason=f"[ADMIN] {reason}",
            related_entities={"admin_id": current_user.id}
        )

        if new_level:
            flash(f"Concessi {xp_amount} XP all'utente. Nuovo livello: {new_level}!", "success")
        else:
            flash(f"Concessi {xp_amount} XP all'utente.", "success")

    except Exception as e:
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_xp_management"))


@gamification_bp.route("/admin/xp/reset/<int:user_id>", methods=["POST"])
@admin_required
def admin_reset_user_level(user_id: int):
    """Reset a user's level and XP (admin tool)."""
    user_level = UserLevel.query.filter_by(user_id=user_id).first()

    if not user_level:
        flash(_("Utente non ha dati di livello"), "error")
        return redirect(url_for("gamification.admin_xp_management"))

    try:
        # Reset to level 1, 0 XP
        user_level.current_level = 1
        user_level.current_xp = 0
        # Keep total_xp for historical record
        db.session.commit()

        flash(_("Livello utente resettato a 1"), "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_xp_management"))


# --------------------------------------------
# Streak Management
# --------------------------------------------

@gamification_bp.route("/admin/streaks")
@admin_required
def admin_streaks():
    """View streak statistics and manage freezes."""
    from sqlalchemy import func

    # Get streak distribution
    streak_stats = db.session.query(
        StreakTracker.streak_type,
        func.avg(StreakTracker.current_streak).label("avg_streak"),
        func.max(StreakTracker.current_streak).label("max_streak"),
        func.sum(StreakTracker.freeze_count).label("total_freezes")
    ).group_by(StreakTracker.streak_type).all()

    # Get top streakers
    top_streakers = StreakTracker.query.filter_by(
        streak_type=StreakType.WEEKLY_ACTIVITY
    ).order_by(
        StreakTracker.current_streak.desc()
    ).limit(20).all()

    return render_template(
        "gamification/admin/streaks.html",
        streak_stats=streak_stats,
        top_streakers=top_streakers,
        streak_types=StreakType,
        page_title=_("Gestione Streak")
    )


@gamification_bp.route("/admin/streaks/grant_freeze", methods=["POST"])
@admin_required
def admin_grant_freeze():
    """Grant a freeze token to a user."""
    try:
        user_id = int(request.form.get("user_id", 0))
        streak_type_str = request.form.get("streak_type", "WEEKLY_ACTIVITY")
        freeze_count = int(request.form.get("freeze_count", 1))

        if user_id <= 0:
            flash(_("Seleziona un utente valido"), "error")
            return redirect(url_for("gamification.admin_streaks"))

        streak_type = StreakType[streak_type_str]

        # Get or create streak tracker
        tracker = StreakTracker.query.filter_by(
            user_id=user_id,
            streak_type=streak_type
        ).first()

        if not tracker:
            tracker = StreakTracker(
                user_id=user_id,
                streak_type=streak_type
            )
            db.session.add(tracker)

        tracker.freeze_count += freeze_count
        tracker.total_freeze_earned += freeze_count
        db.session.commit()

        flash(f"Concessi {freeze_count} freeze all'utente.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_streaks"))


# --------------------------------------------
# Admin API Endpoints
# --------------------------------------------

@gamification_bp.route("/admin/api/user_search")
@admin_required
def admin_api_user_search():
    """Search users by username for admin dropdowns."""
    from models import User

    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify([])

    users = User.query.filter(
        User.username.ilike(f"%{query}%"),  # type: ignore[union-attr]
        User.is_deleted == False  # noqa: E712
    ).limit(10).all()

    return jsonify([
        {"id": u.id, "username": u.username}
        for u in users
    ])


# ============================================
# Gamification Configuration Routes (Task 6.4)
# ============================================

@gamification_bp.route("/admin/config")
@admin_required
def admin_config_dashboard():
    """
    Gamification configuration dashboard - overview of all configurable settings.

    Shows categories:
    - XP Rates: XP amounts for different activities
    - Level Curve: Level progression parameters
    - Level Unlocks: Feature unlocks at specific levels
    - Streak Milestones: Streak reward configuration
    """
    from models.gamification.config_models import (
        GamificationConfig, LevelUnlock, StreakMilestone
    )

    # Get config grouped by category
    xp_rates = GamificationConfig.query.filter_by(category="xp_rates").all()
    level_params = GamificationConfig.query.filter_by(category="level_curve").all()
    streak_config = GamificationConfig.query.filter_by(category="streak").all()

    # Get level unlocks
    level_unlocks = LevelUnlock.query.order_by(LevelUnlock.level).all()

    # Get streak milestones
    streak_milestones = StreakMilestone.query.order_by(StreakMilestone.weeks).all()

    return render_template(
        "gamification/admin/config_dashboard.html",
        xp_rates=xp_rates,
        level_params=level_params,
        streak_config=streak_config,
        level_unlocks=level_unlocks,
        streak_milestones=streak_milestones,
        page_title=_("Configurazione Gamification")
    )


# --------------------------------------------
# XP Rates Configuration
# --------------------------------------------

@gamification_bp.route("/admin/config/xp")
@admin_required
def admin_xp_config():
    """Configure XP rates for each transaction type."""
    from models.gamification.config_models import GamificationConfig

    configs = GamificationConfig.query.filter_by(category="xp_rates").all()

    return render_template(
        "gamification/admin/xp_config.html",
        configs=configs,
        page_title=_("Configurazione XP")
    )


@gamification_bp.route("/admin/config/xp/update", methods=["POST"])
@admin_required
def admin_update_xp_config():
    """Update an XP rate configuration."""
    from models.gamification.config_models import GamificationConfig
    from models.gamification.config_service import GamificationConfigService

    try:
        key = request.form.get("key", "").strip()
        value = int(request.form.get("value", 0))

        if not key:
            flash(_("Chiave configurazione mancante"), "error")
            return redirect(url_for("gamification.admin_xp_config"))

        if value < 0:
            flash(_("Il valore XP non può essere negativo"), "error")
            return redirect(url_for("gamification.admin_xp_config"))

        config = db.session.get(GamificationConfig, key)
        if not config:
            flash(_("Configurazione non trovata"), "error")
            return redirect(url_for("gamification.admin_xp_config"))

        config.value = value
        config.updated_by_id = current_user.id
        db.session.commit()

        # Invalidate cache
        GamificationConfigService.invalidate_cache()

        flash(f"XP rate '{key}' aggiornato a {value}", "success")

    except ValueError:
        flash(_("Valore XP non valido"), "error")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_xp_config"))


# --------------------------------------------
# Level Curve Configuration
# --------------------------------------------

@gamification_bp.route("/admin/config/levels")
@admin_required
def admin_level_curve_config():
    """Configure level curve parameters and level unlocks."""
    from models.gamification.config_models import GamificationConfig, LevelUnlock

    # Level curve params
    level_params = GamificationConfig.query.filter_by(category="level_curve").all()

    # Level unlocks
    level_unlocks = LevelUnlock.query.order_by(LevelUnlock.level).all()

    return render_template(
        "gamification/admin/level_config.html",
        level_params=level_params,
        level_unlocks=level_unlocks,
        page_title=_("Configurazione Livelli")
    )


@gamification_bp.route("/admin/config/levels/update_curve", methods=["POST"])
@admin_required
def admin_update_level_curve():
    """Update level curve parameters."""
    from models.gamification.config_models import GamificationConfig
    from models.gamification.config_service import GamificationConfigService

    try:
        key = request.form.get("key", "").strip()
        value = int(request.form.get("value", 0))

        if not key:
            flash(_("Parametro mancante"), "error")
            return redirect(url_for("gamification.admin_level_curve_config"))

        if value < 1:
            flash(_("Il valore deve essere almeno 1"), "error")
            return redirect(url_for("gamification.admin_level_curve_config"))

        config = db.session.get(GamificationConfig, key)
        if not config:
            flash(_("Configurazione non trovata"), "error")
            return redirect(url_for("gamification.admin_level_curve_config"))

        config.value = value
        config.updated_by_id = current_user.id
        db.session.commit()

        GamificationConfigService.invalidate_cache()
        flash(f"Parametro '{key}' aggiornato a {value}", "success")

    except ValueError:
        flash(_("Valore non valido"), "error")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_level_curve_config"))


@gamification_bp.route("/admin/config/levels/unlock/add", methods=["POST"])
@admin_required
def admin_add_level_unlock():
    """Add a new level unlock."""
    from models.gamification.config_models import LevelUnlock
    from models.gamification.config_service import GamificationConfigService

    try:
        level = int(request.form.get("level", 0))
        feature_code = request.form.get("feature_code", "").strip().lower().replace(" ", "_")
        feature_name = request.form.get("feature_name", "").strip()
        description = request.form.get("description", "").strip()

        if level < 1:
            flash(_("Il livello deve essere almeno 1"), "error")
            return redirect(url_for("gamification.admin_level_curve_config"))

        if not feature_code or not feature_name:
            flash(_("Codice e nome feature sono obbligatori"), "error")
            return redirect(url_for("gamification.admin_level_curve_config"))

        # Check if level already has an unlock
        existing = LevelUnlock.query.filter_by(level=level).first()
        if existing:
            flash(f"Il livello {level} ha già un unlock definito", "error")
            return redirect(url_for("gamification.admin_level_curve_config"))

        unlock = LevelUnlock(
            level=level,
            feature_code=feature_code,
            feature_name=feature_name,
            description=description,
            is_active=True
        )
        db.session.add(unlock)
        db.session.commit()

        GamificationConfigService.invalidate_cache()
        flash(f"Level unlock per livello {level} aggiunto", "success")

    except ValueError:
        flash(_("Valore livello non valido"), "error")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_level_curve_config"))


@gamification_bp.route("/admin/config/levels/unlock/<int:unlock_id>/edit", methods=["POST"])
@admin_required
def admin_edit_level_unlock(unlock_id: int):
    """Edit an existing level unlock."""
    from models.gamification.config_models import LevelUnlock
    from models.gamification.config_service import GamificationConfigService

    unlock = db.session.get(LevelUnlock, unlock_id)
    if not unlock:
        flash(_("Level unlock non trovato"), "error")
        return redirect(url_for("gamification.admin_level_curve_config"))

    try:
        feature_name = request.form.get("feature_name", "").strip()
        description = request.form.get("description", "").strip()
        is_active = request.form.get("is_active") == "on"

        if not feature_name:
            flash(_("Il nome feature è obbligatorio"), "error")
            return redirect(url_for("gamification.admin_level_curve_config"))

        unlock.feature_name = feature_name
        unlock.description = description
        unlock.is_active = is_active
        db.session.commit()

        GamificationConfigService.invalidate_cache()
        flash(f"Level unlock modificato", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_level_curve_config"))


@gamification_bp.route("/admin/config/levels/unlock/<int:unlock_id>/delete", methods=["POST"])
@admin_required
def admin_delete_level_unlock(unlock_id: int):
    """Delete a level unlock."""
    from models.gamification.config_models import LevelUnlock
    from models.gamification.config_service import GamificationConfigService

    unlock = db.session.get(LevelUnlock, unlock_id)
    if not unlock:
        flash(_("Level unlock non trovato"), "error")
        return redirect(url_for("gamification.admin_level_curve_config"))

    try:
        level = unlock.level
        db.session.delete(unlock)
        db.session.commit()

        GamificationConfigService.invalidate_cache()
        flash(f"Level unlock per livello {level} eliminato", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_level_curve_config"))


# --------------------------------------------
# Streak Milestones Configuration
# --------------------------------------------

@gamification_bp.route("/admin/config/streaks")
@admin_required
def admin_streak_config():
    """Configure streak milestones and freeze settings."""
    from models.gamification.config_models import GamificationConfig, StreakMilestone

    # Max freeze config
    streak_config = GamificationConfig.query.filter_by(category="streak").all()

    # Streak milestones
    milestones = StreakMilestone.query.order_by(StreakMilestone.weeks).all()

    return render_template(
        "gamification/admin/streak_config.html",
        streak_config=streak_config,
        milestones=milestones,
        page_title=_("Configurazione Streak")
    )


@gamification_bp.route("/admin/config/streaks/update", methods=["POST"])
@admin_required
def admin_update_streak_config():
    """Update streak configuration."""
    from models.gamification.config_models import GamificationConfig
    from models.gamification.config_service import GamificationConfigService

    try:
        key = request.form.get("key", "").strip()
        value = int(request.form.get("value", 0))

        if not key:
            flash(_("Parametro mancante"), "error")
            return redirect(url_for("gamification.admin_streak_config"))

        if value < 0:
            flash(_("Il valore non può essere negativo"), "error")
            return redirect(url_for("gamification.admin_streak_config"))

        config = db.session.get(GamificationConfig, key)
        if not config:
            flash(_("Configurazione non trovata"), "error")
            return redirect(url_for("gamification.admin_streak_config"))

        config.value = value
        config.updated_by_id = current_user.id
        db.session.commit()

        GamificationConfigService.invalidate_cache()
        flash(f"Configurazione streak aggiornata", "success")

    except ValueError:
        flash(_("Valore non valido"), "error")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_streak_config"))


@gamification_bp.route("/admin/config/streaks/milestone/add", methods=["POST"])
@admin_required
def admin_add_streak_milestone():
    """Add a new streak milestone."""
    from models.gamification.config_models import StreakMilestone
    from models.gamification.config_service import GamificationConfigService

    try:
        weeks = int(request.form.get("weeks", 0))
        freeze_tokens = int(request.form.get("freeze_tokens", 1))
        xp_bonus_multiplier = int(request.form.get("xp_bonus_multiplier", 1))
        is_recurring = request.form.get("is_recurring") == "on"

        if weeks < 1:
            flash(_("Le settimane devono essere almeno 1"), "error")
            return redirect(url_for("gamification.admin_streak_config"))

        if freeze_tokens < 0:
            flash(_("I freeze token non possono essere negativi"), "error")
            return redirect(url_for("gamification.admin_streak_config"))

        # Check if weeks milestone already exists
        existing = StreakMilestone.query.filter_by(weeks=weeks).first()
        if existing:
            flash(f"Milestone per {weeks} settimane già esistente", "error")
            return redirect(url_for("gamification.admin_streak_config"))

        milestone = StreakMilestone(
            weeks=weeks,
            freeze_tokens=freeze_tokens,
            xp_bonus_multiplier=xp_bonus_multiplier,
            is_recurring=is_recurring,
            is_active=True
        )
        db.session.add(milestone)
        db.session.commit()

        GamificationConfigService.invalidate_cache()
        flash(f"Milestone {weeks} settimane aggiunto", "success")

    except ValueError:
        flash(_("Valore non valido"), "error")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_streak_config"))


@gamification_bp.route("/admin/config/streaks/milestone/<int:milestone_id>/edit", methods=["POST"])
@admin_required
def admin_edit_streak_milestone(milestone_id: int):
    """Edit an existing streak milestone."""
    from models.gamification.config_models import StreakMilestone
    from models.gamification.config_service import GamificationConfigService

    milestone = db.session.get(StreakMilestone, milestone_id)
    if not milestone:
        flash(_("Milestone non trovato"), "error")
        return redirect(url_for("gamification.admin_streak_config"))

    try:
        freeze_tokens = int(request.form.get("freeze_tokens", 1))
        xp_bonus_multiplier = int(request.form.get("xp_bonus_multiplier", 1))
        is_recurring = request.form.get("is_recurring") == "on"
        is_active = request.form.get("is_active") == "on"

        if freeze_tokens < 0:
            flash(_("I freeze token non possono essere negativi"), "error")
            return redirect(url_for("gamification.admin_streak_config"))

        milestone.freeze_tokens = freeze_tokens
        milestone.xp_bonus_multiplier = xp_bonus_multiplier
        milestone.is_recurring = is_recurring
        milestone.is_active = is_active
        db.session.commit()

        GamificationConfigService.invalidate_cache()
        flash(f"Milestone {milestone.weeks} settimane modificato", "success")

    except ValueError:
        flash(_("Valore non valido"), "error")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_streak_config"))


@gamification_bp.route("/admin/config/streaks/milestone/<int:milestone_id>/delete", methods=["POST"])
@admin_required
def admin_delete_streak_milestone(milestone_id: int):
    """Delete a streak milestone."""
    from models.gamification.config_models import StreakMilestone
    from models.gamification.config_service import GamificationConfigService

    milestone = db.session.get(StreakMilestone, milestone_id)
    if not milestone:
        flash(_("Milestone non trovato"), "error")
        return redirect(url_for("gamification.admin_streak_config"))

    try:
        weeks = milestone.weeks
        db.session.delete(milestone)
        db.session.commit()

        GamificationConfigService.invalidate_cache()
        flash(f"Milestone {weeks} settimane eliminato", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("gamification.admin_streak_config"))
