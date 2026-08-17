# routes/gamification/admin.py
"""Admin gamification management routes: quests, achievements, XP, streaks."""

from flask import render_template, jsonify, request, flash, redirect, url_for
from flask_login import current_user
from flask_babel import gettext as _

from utils import admin_required
from utils.route_helpers import handle_service_action
from models.base import db, utc_now
from models.gamification.level_service import LevelService
from models.gamification.quest_service import QuestService
from models.gamification.achievement_metrics import AchievementMetrics
from models.gamification.achievement_service import AchievementService
from models.gamification.streak_service import StreakService
from models.gamification.models import (
    UserLevel,
    Achievement,
    UserAchievement,
    StreakTracker,
    AchievementCategory,
    AchievementDifficulty,
    StreakType,
    Quest,
    QuestStatus,
    XPTransactionType,
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
    from sqlalchemy import func

    # Get level distribution
    level_stats = (
        db.session.query(
            UserLevel.current_level, func.count(UserLevel.user_id).label("count")
        )
        .group_by(UserLevel.current_level)
        .order_by(UserLevel.current_level)
        .all()
    )

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
    top_users = UserLevel.query.order_by(UserLevel.total_xp.desc()).limit(10).all()

    return render_template(
        "gamification/admin/dashboard.html",
        level_stats=level_stats,
        total_xp=total_xp,
        active_quests=active_quests,
        total_achievements=total_achievements,
        total_unlocks=total_unlocks,
        top_users=top_users,
        page_title=_("Admin Gamification"),
    )


# --------------------------------------------
# Quest Management
# --------------------------------------------


@gamification_bp.route("/admin/quests")
@admin_required
def admin_quests():
    """List all quests for management."""
    page = request.args.get("page", 1, type=int)
    pagination = Quest.query.order_by(Quest.start_date.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template(
        "gamification/admin/quests.html",
        quests=pagination.items,
        pagination=pagination,
        quest_statuses=QuestStatus,
        page_title=_("Gestione Quest"),
    )


@gamification_bp.route("/admin/quests/create", methods=["GET", "POST"])
@admin_required
def admin_create_quest():
    """Create a new quest."""
    from models.gamification.models import QuestType
    from datetime import timedelta

    from utils.local_time import parse_local_datetime

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        quest_type = request.form.get("quest_type", "weekly")
        requirement_type = request.form.get("requirement_type", "matches_played")

        if not name:
            flash(_("Il nome della quest è obbligatorio"), "error")
            return redirect(url_for("gamification.admin_create_quest"))

        # int()/QuestType[...] sollevano ValueError/KeyError su input invalido:
        # senza guardia il parsing esplode in 500 PRIMA di
        # handle_service_action.
        try:
            requirement_target = int(request.form.get("requirement_target", 10))
            xp_reward = int(request.form.get("xp_reward", 100))
            quest_type_enum = QuestType[quest_type.upper()]
        except (ValueError, KeyError):
            flash(_("Dati del form non validi"), "error")
            return redirect(url_for("gamification.admin_create_quest"))

        # I due campi sono `<input type="datetime-local">`: arrivano in ora
        # italiana, mentre `Quest.is_active` li confronta con `utc_now()`. Letti
        # grezzi, una quest aperta "dalle 21:00" restava chiusa fino alle 23:00
        # — e scadeva due ore dopo il previsto, senza che nulla lo segnalasse.
        #
        # Campo vuoto e campo illeggibile non sono la stessa cosa: il primo
        # significa "usa il default", il secondo che qualcosa è andato storto.
        # `parse_local_datetime` risponde `None` a entrambi, quindi la
        # distinzione va fatta qui — altrimenti una data manomessa (o mandata
        # da un browser che non rispetta il formato) creerebbe in silenzio una
        # quest che parte adesso e dura sette giorni, senza che nessuno lo
        # sappia.
        raw_start = (request.form.get("start_date") or "").strip()
        raw_end = (request.form.get("end_date") or "").strip()

        start_date = parse_local_datetime(raw_start) if raw_start else utc_now()
        end_date = parse_local_datetime(raw_end) if raw_end else None
        if (raw_start and start_date is None) or (raw_end and end_date is None):
            flash(_("Date del form non valide"), "error")
            return redirect(url_for("gamification.admin_create_quest"))

        if end_date is None:
            span = timedelta(days=7 if quest_type == "weekly" else 30)
            end_date = start_date + span

        return handle_service_action(
            action=lambda: QuestService.create_quest(
                name=name,
                description=description,
                quest_type=quest_type_enum,
                start_date=start_date,
                end_date=end_date,
                requirements={"type": requirement_type, "target": requirement_target},
                xp_reward=xp_reward,
            ),
            redirect_url=url_for("gamification.admin_quests"),
            success_message=_("Quest creata con successo"),
        )

    # GET - show form
    return render_template(
        "gamification/admin/quest_form.html",
        quest=None,
        page_title=_("Crea Nuova Quest"),
    )


@gamification_bp.route("/admin/quests/<int:quest_id>/activate", methods=["POST"])
@admin_required
def admin_activate_quest(quest_id: int):
    """Activate a quest (set status to ACTIVE)."""
    return handle_service_action(
        action=lambda: QuestService.activate_quest(quest_id),
        redirect_url=url_for("gamification.admin_quests"),
        success_message=_("Quest attivata"),
    )


@gamification_bp.route("/admin/quests/<int:quest_id>/expire", methods=["POST"])
@admin_required
def admin_expire_quest(quest_id: int):
    """Expire a quest (set status to EXPIRED)."""
    return handle_service_action(
        action=lambda: QuestService.expire_quest(quest_id),
        redirect_url=url_for("gamification.admin_quests"),
        success_message=_("Quest scaduta"),
    )


@gamification_bp.route("/admin/quests/<int:quest_id>/delete", methods=["POST"])
@admin_required
def admin_delete_quest(quest_id: int):
    """Delete a quest (only if no participants)."""
    return handle_service_action(
        action=lambda: QuestService.delete_quest(quest_id),
        redirect_url=url_for("gamification.admin_quests"),
        success_message=_("Quest eliminata"),
    )


# --------------------------------------------
# Achievement Management
# --------------------------------------------


@gamification_bp.route("/admin/achievements")
@admin_required
def admin_achievements():
    """List all achievements with unlock statistics."""
    from sqlalchemy import func

    page = request.args.get("page", 1, type=int)

    # Paginate achievements
    pagination = Achievement.query.paginate(page=page, per_page=20, error_out=False)

    # Get unlock counts per achievement
    unlock_stats = dict(
        db.session.query(
            UserAchievement.achievement_id,
            func.count(UserAchievement.id).label("count"),
        )
        .filter(UserAchievement.unlocked_at.isnot(None))
        .group_by(UserAchievement.achievement_id)
        .all()
    )

    # Combine data
    achievement_data = []
    for achievement in pagination.items:
        achievement_data.append(
            {
                "achievement": achievement,
                "unlock_count": unlock_stats.get(achievement.id, 0),
            }
        )

    return render_template(
        "gamification/admin/achievements.html",
        achievements=achievement_data,
        pagination=pagination,
        categories=AchievementCategory,
        difficulties=AchievementDifficulty,
        page_title=_("Gestione Achievement"),
    )


@gamification_bp.route("/admin/achievements/create", methods=["GET", "POST"])
@admin_required
def admin_create_achievement():
    """Create a new achievement."""
    if request.method == "POST":
        slug = request.form.get("slug", "").strip().lower().replace(" ", "_")
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "match")
        difficulty = request.form.get("difficulty", "common")
        icon_path = request.form.get("icon_path", "").strip() or None
        is_hidden = request.form.get("is_hidden") == "on"
        is_progressive = request.form.get("is_progressive") == "on"
        requirement_type = request.form.get("requirement_type", "match_wins")
        try:
            xp_reward = int(request.form.get("xp_reward", 50))
            requirement_value = int(request.form.get("requirement_value", 1))
        except ValueError:
            flash(_("Dati del form non validi"), "error")
            return redirect(url_for("gamification.admin_create_achievement"))

        return handle_service_action(
            action=lambda: AchievementService.create_achievement(
                slug=slug,
                name=name,
                description=description,
                category=category,
                difficulty=difficulty,
                icon_path=icon_path,
                xp_reward=xp_reward,
                is_hidden=is_hidden,
                is_progressive=is_progressive,
                requirement_type=requirement_type,
                requirement_value=requirement_value,
            ),
            redirect_url=url_for("gamification.admin_achievements"),
            success_message=_("Achievement creato con successo"),
        )

    return render_template(
        "gamification/admin/achievement_form.html",
        achievement=None,
        categories=AchievementCategory,
        difficulties=AchievementDifficulty,
        requirement_types=sorted(AchievementMetrics.COUNTABLE_TYPES),
        requirement_type_labels=_requirement_type_labels(),
        page_title=_("Crea Nuovo Achievement"),
    )


def _requirement_type_labels() -> dict[str, str]:
    """Etichette leggibili per i requirement type conteggiabili.

    La mappa e' *solo* per la resa: l'elenco autorevole e'
    `AchievementMetrics.COUNTABLE_TYPES`, e il template ripiega sul nome grezzo
    per un tipo senza etichetta. Cosi' aggiungere un resolver lo rende subito
    creabile da interfaccia — al peggio con un nome brutto, mai invisibile.
    """
    return {
        "match_wins": _("Vittorie partita"),
        "tournament_participation": _("Partecipazioni a gara"),
        "tournament_wins": _("Vittorie di gara"),
        "tournament_podium": _("Podi di gara"),
        "unique_opponents": _("Avversari diversi affrontati"),
        "match_proposals_created": _("Proposte di partita create"),
        "match_proposals_accepted": _("Proposte di partita accettate"),
        "win_streak": _("Serie di vittorie consecutive"),
        "strategies_tried": _("Formule di gara provate"),
        "challenges_completed": _("Drill completati"),
        "perfect_challenges": _("Drill eseguiti alla perfezione"),
    }


@gamification_bp.route(
    "/admin/achievements/<int:achievement_id>/toggle_hidden", methods=["POST"]
)
@admin_required
def admin_toggle_achievement_hidden(achievement_id: int):
    """Toggle hidden status of an achievement."""
    return handle_service_action(
        action=lambda: AchievementService.toggle_hidden(achievement_id),
        redirect_url=url_for("gamification.admin_achievements"),
        success_message=_("Stato achievement aggiornato"),
    )


# --------------------------------------------
# XP & Level Management
# --------------------------------------------


@gamification_bp.route("/admin/xp")
@admin_required
def admin_xp_management():
    """XP management dashboard - grant XP, view transactions."""
    from models import User
    from models.gamification.models import XPTransaction

    page = request.args.get("page", 1, type=int)

    # Paginate recent transactions
    pagination = XPTransaction.query.order_by(XPTransaction.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    # Get users for dropdown
    users = User.query.filter(User.deleted_at.is_(None)).order_by(User.username).all()

    return render_template(
        "gamification/admin/xp_management.html",
        recent_transactions=pagination.items,
        pagination=pagination,
        users=users,
        xp_types=XPTransactionType,
        page_title=_("Gestione XP"),
    )


@gamification_bp.route("/admin/xp/grant", methods=["POST"])
@admin_required
def admin_grant_xp():
    """Grant XP to a user (admin tool)."""
    from models.gamification.models import XPTransactionType

    try:
        user_id = int(request.form.get("user_id", 0))
        xp_amount = int(request.form.get("xp_amount", 0))
    except ValueError:
        flash(_("Dati del form non validi"), "error")
        return redirect(url_for("gamification.admin_xp_management"))
    reason = request.form.get("reason", "Admin grant").strip()

    if user_id <= 0:
        flash(_("Seleziona un utente valido"), "error")
        return redirect(url_for("gamification.admin_xp_management"))

    if xp_amount <= 0:
        flash(_("L'importo XP deve essere positivo"), "error")
        return redirect(url_for("gamification.admin_xp_management"))

    return handle_service_action(
        action=lambda: LevelService.award_xp(
            user_id=user_id,
            xp_amount=xp_amount,
            transaction_type=XPTransactionType.ADMIN_GRANT,
            reason=f"[ADMIN] {reason}",
            related_entities={"admin_id": current_user.id},
        ),
        redirect_url=url_for("gamification.admin_xp_management"),
        success_message=_("Concessi %(n)s XP all'utente.", n=xp_amount),
    )


@gamification_bp.route("/admin/xp/reset/<int:user_id>", methods=["POST"])
@admin_required
def admin_reset_user_level(user_id: int):
    """Reset a user's level and XP (admin tool)."""
    return handle_service_action(
        action=lambda: LevelService.reset_user_level(user_id),
        redirect_url=url_for("gamification.admin_xp_management"),
        success_message=_("Livello utente resettato a 1"),
    )


# --------------------------------------------
# Streak Management
# --------------------------------------------


@gamification_bp.route("/admin/streaks")
@admin_required
def admin_streaks():
    """View streak statistics and manage freezes."""
    from sqlalchemy import func

    # Get streak distribution
    streak_stats = (
        db.session.query(
            StreakTracker.streak_type,
            func.avg(StreakTracker.current_streak).label("avg_streak"),
            func.max(StreakTracker.current_streak).label("max_streak"),
            func.sum(StreakTracker.freeze_count).label("total_freezes"),
        )
        .group_by(StreakTracker.streak_type)
        .all()
    )

    # Get top streakers
    top_streakers = (
        StreakTracker.query.filter_by(streak_type=StreakType.WEEKLY_ACTIVITY)
        .order_by(StreakTracker.current_streak.desc())
        .limit(20)
        .all()
    )

    return render_template(
        "gamification/admin/streaks.html",
        streak_stats=streak_stats,
        top_streakers=top_streakers,
        streak_types=StreakType,
        page_title=_("Gestione Streak"),
    )


@gamification_bp.route("/admin/streaks/grant_freeze", methods=["POST"])
@admin_required
def admin_grant_freeze():
    """Grant a freeze token to a user."""
    try:
        user_id = int(request.form.get("user_id", 0))
        freeze_count = int(request.form.get("freeze_count", 1))
        streak_type = StreakType[request.form.get("streak_type", "WEEKLY_ACTIVITY")]
    except (ValueError, KeyError):
        flash(_("Dati del form non validi"), "error")
        return redirect(url_for("gamification.admin_streaks"))

    if user_id <= 0:
        flash(_("Seleziona un utente valido"), "error")
        return redirect(url_for("gamification.admin_streaks"))

    return handle_service_action(
        action=lambda: StreakService.admin_grant_freeze(
            user_id=user_id,
            streak_type=streak_type,
            freeze_count=freeze_count,
        ),
        redirect_url=url_for("gamification.admin_streaks"),
        success_message=_("Concessi %(n)s freeze all'utente.", n=freeze_count),
    )


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

    users = (
        User.query.filter(
            User.username.ilike(f"%{query}%"),  # type: ignore[union-attr]
            User.deleted_at.is_(None),
        )
        .limit(10)
        .all()
    )

    return jsonify([{"id": u.id, "username": u.username} for u in users])
