# routes/gamification/config.py
"""Admin gamification configuration routes: XP rates, levels, streaks."""

from flask import render_template, request, flash, redirect, url_for
from flask_login import current_user
from flask_babel import gettext as _

from utils import admin_required
from models.base import db

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
        flash("Level unlock modificato", "success")

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
        flash("Configurazione streak aggiornata", "success")

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
