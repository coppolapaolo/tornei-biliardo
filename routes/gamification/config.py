# routes/gamification/config.py
"""Admin gamification configuration routes: XP rates, levels, streaks."""

from flask import render_template, request, flash, redirect, url_for
from flask_login import current_user
from flask_babel import gettext as _

from utils import admin_required
from utils.route_helpers import handle_service_action
from models.gamification.config_service import GamificationConfigService

from . import gamification_bp


# ============================================
# Gamification Configuration Dashboard
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
    key = request.form.get("key", "").strip()
    try:
        value = int(request.form.get("value", 0))
    except ValueError:
        flash(_("Valore XP non valido"), "error")
        return redirect(url_for("gamification.admin_xp_config"))

    return handle_service_action(
        action=lambda: GamificationConfigService.update_config(
            key=key, value=value, updated_by_id=current_user.id
        ),
        redirect_url=url_for("gamification.admin_xp_config"),
        success_message=f"XP rate '{key}' aggiornato a {value}",
    )


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
    key = request.form.get("key", "").strip()
    try:
        value = int(request.form.get("value", 0))
    except ValueError:
        flash(_("Valore non valido"), "error")
        return redirect(url_for("gamification.admin_level_curve_config"))

    if value < 1:
        flash(_("Il valore deve essere almeno 1"), "error")
        return redirect(url_for("gamification.admin_level_curve_config"))

    return handle_service_action(
        action=lambda: GamificationConfigService.update_config(
            key=key, value=value, updated_by_id=current_user.id
        ),
        redirect_url=url_for("gamification.admin_level_curve_config"),
        success_message=f"Parametro '{key}' aggiornato a {value}",
    )


@gamification_bp.route("/admin/config/levels/unlock/add", methods=["POST"])
@admin_required
def admin_add_level_unlock():
    """Add a new level unlock."""
    try:
        level = int(request.form.get("level", 0))
    except ValueError:
        flash(_("Valore livello non valido"), "error")
        return redirect(url_for("gamification.admin_level_curve_config"))

    feature_code = request.form.get("feature_code", "").strip().lower().replace(" ", "_")
    feature_name = request.form.get("feature_name", "").strip()
    description = request.form.get("description", "").strip()

    return handle_service_action(
        action=lambda: GamificationConfigService.add_level_unlock(
            level=level,
            feature_code=feature_code,
            feature_name=feature_name,
            description=description,
        ),
        redirect_url=url_for("gamification.admin_level_curve_config"),
        success_message=f"Level unlock per livello {level} aggiunto",
    )


@gamification_bp.route("/admin/config/levels/unlock/<int:unlock_id>/edit", methods=["POST"])
@admin_required
def admin_edit_level_unlock(unlock_id: int):
    """Edit an existing level unlock."""
    feature_name = request.form.get("feature_name", "").strip()
    description = request.form.get("description", "").strip()
    is_active = request.form.get("is_active") == "on"

    return handle_service_action(
        action=lambda: GamificationConfigService.update_level_unlock(
            unlock_id=unlock_id,
            feature_name=feature_name,
            description=description,
            is_active=is_active,
        ),
        redirect_url=url_for("gamification.admin_level_curve_config"),
        success_message="Level unlock modificato",
    )


@gamification_bp.route("/admin/config/levels/unlock/<int:unlock_id>/delete", methods=["POST"])
@admin_required
def admin_delete_level_unlock(unlock_id: int):
    """Delete a level unlock."""
    return handle_service_action(
        action=lambda: GamificationConfigService.delete_level_unlock(unlock_id),
        redirect_url=url_for("gamification.admin_level_curve_config"),
        success_message="Level unlock eliminato",
    )


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
    key = request.form.get("key", "").strip()
    try:
        value = int(request.form.get("value", 0))
    except ValueError:
        flash(_("Valore non valido"), "error")
        return redirect(url_for("gamification.admin_streak_config"))

    return handle_service_action(
        action=lambda: GamificationConfigService.update_config(
            key=key, value=value, updated_by_id=current_user.id
        ),
        redirect_url=url_for("gamification.admin_streak_config"),
        success_message="Configurazione streak aggiornata",
    )


@gamification_bp.route("/admin/config/streaks/milestone/add", methods=["POST"])
@admin_required
def admin_add_streak_milestone():
    """Add a new streak milestone."""
    try:
        weeks = int(request.form.get("weeks", 0))
        freeze_tokens = int(request.form.get("freeze_tokens", 1))
        xp_bonus_multiplier = int(request.form.get("xp_bonus_multiplier", 1))
    except ValueError:
        flash(_("Valore non valido"), "error")
        return redirect(url_for("gamification.admin_streak_config"))

    is_recurring = request.form.get("is_recurring") == "on"

    return handle_service_action(
        action=lambda: GamificationConfigService.add_streak_milestone(
            weeks=weeks,
            freeze_tokens=freeze_tokens,
            xp_bonus_multiplier=xp_bonus_multiplier,
            is_recurring=is_recurring,
        ),
        redirect_url=url_for("gamification.admin_streak_config"),
        success_message=f"Milestone {weeks} settimane aggiunto",
    )


@gamification_bp.route("/admin/config/streaks/milestone/<int:milestone_id>/edit", methods=["POST"])
@admin_required
def admin_edit_streak_milestone(milestone_id: int):
    """Edit an existing streak milestone."""
    try:
        freeze_tokens = int(request.form.get("freeze_tokens", 1))
        xp_bonus_multiplier = int(request.form.get("xp_bonus_multiplier", 1))
    except ValueError:
        flash(_("Valore non valido"), "error")
        return redirect(url_for("gamification.admin_streak_config"))

    is_recurring = request.form.get("is_recurring") == "on"
    is_active = request.form.get("is_active") == "on"

    return handle_service_action(
        action=lambda: GamificationConfigService.update_streak_milestone(
            milestone_id=milestone_id,
            freeze_tokens=freeze_tokens,
            xp_bonus_multiplier=xp_bonus_multiplier,
            is_recurring=is_recurring,
            is_active=is_active,
        ),
        redirect_url=url_for("gamification.admin_streak_config"),
        success_message="Milestone modificato",
    )


@gamification_bp.route("/admin/config/streaks/milestone/<int:milestone_id>/delete", methods=["POST"])
@admin_required
def admin_delete_streak_milestone(milestone_id: int):
    """Delete a streak milestone."""
    return handle_service_action(
        action=lambda: GamificationConfigService.delete_streak_milestone(milestone_id),
        redirect_url=url_for("gamification.admin_streak_config"),
        success_message="Milestone eliminato",
    )
