# routes/gamification/admin.py
"""Admin gamification management routes: quests, achievements, XP, streaks."""

from flask import render_template, jsonify, request, flash, redirect, url_for
from flask_login import current_user
from flask_babel import gettext as _

from utils import admin_required
from models.base import db, utc_now
from models.gamification.level_service import LevelService
from models.gamification.models import (
    UserLevel, Achievement, UserAchievement, StreakTracker,
    AchievementCategory, AchievementDifficulty, StreakType,
    Quest, QuestStatus, XPTransactionType
)

from . import gamification_bp


# ============================================
# Admin Dashboard
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

            start_date = datetime.fromisoformat(start_date_str) if start_date_str else utc_now()

            if end_date_str:
                end_date = datetime.fromisoformat(end_date_str)
            else:
                # Default duration based on type
                if quest_type == "weekly":
                    end_date = start_date + timedelta(days=7)
                else:
                    end_date = start_date + timedelta(days=30)

            # Determine initial status
            now = utc_now()
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
    users = User.query.filter(User.deleted_at.is_(None)).order_by(User.username).all()

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
        User.deleted_at.is_(None)
    ).limit(10).all()

    return jsonify([
        {"id": u.id, "username": u.username}
        for u in users
    ])
