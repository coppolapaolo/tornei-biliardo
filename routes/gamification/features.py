"""
Admin routes for Feature Config management.

Allows admins to view and edit feature gating rules through a web UI.
"""

from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_babel import gettext as _

from utils import admin_required
from utils.route_helpers import handle_service_action, get_or_ajax_404
from models.base import db
from models.gamification.feature_models import FeatureConfig
from models.gamification.feature_config_service import FeatureConfigService
from models.user.models import User
from . import gamification_bp


@gamification_bp.route("/admin/features")
@admin_required
def admin_features():
    """List all feature configurations."""
    features = FeatureConfig.query.order_by(FeatureConfig.code).all()
    return render_template(
        "gamification/admin/features.html",
        features=features,
        page_title=_("Gestione Feature Gating"),
    )


@gamification_bp.route("/admin/features/<code>")
@admin_required
def admin_feature_detail(code: str):
    """View/edit feature configuration."""
    feature = db.session.get(FeatureConfig, code)
    if not feature:
        flash(_("Feature non trovata"), "danger")
        return redirect(url_for("gamification.admin_features"))

    # Available metrics for dropdown
    available_metrics = [
        {"name": "total_matches", "label": _("Match totali giocati")},
        {"name": "scores_inserted", "label": _("Match con punteggio inserito")},
        {"name": "tournaments_played", "label": _("Gare/tornei giocati")},
        {"name": "tournaments_organized", "label": _("Gare organizzate")},
        {"name": "matches_in_location", "label": _("Match in una sala")},
        {"name": "distinct_opponents", "label": _("Avversari diversi")},
        {"name": "challenges_completed", "label": _("Drill completati")},
        {"name": "gare_with_drill_played", "label": _("Gare con drill giocate")},
        {"name": "tournament_drills_completed", "label": _("Drill completati in gara")},
    ]

    # Condition types
    condition_types = [
        {"value": "LEVEL", "label": _("Livello")},
        {"value": "METRIC", "label": _("Metrica")},
        {"value": "ROLE", "label": _("Ruolo")},
        {"value": "ACHIEVEMENT", "label": _("Achievement")},
    ]

    # Operators
    operators = [
        {"value": "gte", "label": ">="},
        {"value": "gt", "label": ">"},
        {"value": "lte", "label": "<="},
        {"value": "lt", "label": "<"},
        {"value": "eq", "label": "="},
    ]

    # Roles
    roles = [
        {"value": "ADMIN", "label": _("Admin")},
        {"value": "DIRECTOR", "label": _("Director")},
        {"value": "VENUE_MANAGER", "label": _("Gestore Sala")},
        {"value": "EXAMINER", "label": _("Esaminatore")},
    ]

    return render_template(
        "gamification/admin/feature_detail.html",
        feature=feature,
        available_metrics=available_metrics,
        condition_types=condition_types,
        operators=operators,
        roles=roles,
        page_title=f"Feature: {feature.name}",
    )


@gamification_bp.route("/admin/features/<code>/update", methods=["POST"])
@admin_required
def admin_update_feature(code: str):
    """Update feature rules."""
    import json

    rules_json = request.form.get("rules", "[]")
    try:
        rules = json.loads(rules_json)
    except json.JSONDecodeError:
        flash(_("Formato regole non valido"), "danger")
        return redirect(url_for("gamification.admin_feature_detail", code=code))

    is_active = request.form.get("is_active") == "on"
    name = request.form.get("name", "")
    description = request.form.get("description", "")

    return handle_service_action(
        action=lambda: FeatureConfigService.update_feature(
            code=code,
            rules=rules,
            is_active=is_active,
            name=name,
            description=description,
        ),
        redirect_url=url_for("gamification.admin_feature_detail", code=code),
        success_message=_("Feature aggiornata con successo"),
    )


@gamification_bp.route("/admin/features/<code>/preview")
@admin_required
def admin_feature_preview(code: str):
    """Preview how many users can access this feature.

    Returns JSON with stats about eligible users.
    """
    get_or_ajax_404(FeatureConfig, code, "Feature")  # 404 se non esiste

    # Get all active users
    users = User.query.filter(User.deleted_at.is_(None)).all()
    eligible = [u for u in users if u.can_access(code)]

    return jsonify(
        {
            "total_users": len(users),
            "eligible_users": len(eligible),
            "percentage": round(len(eligible) / len(users) * 100, 1) if users else 0,
            "eligible_usernames": [u.username for u in eligible[:20]],  # First 20
        }
    )


@gamification_bp.route("/admin/features/create", methods=["GET", "POST"])
@admin_required
def admin_create_feature():
    """Create a new feature configuration."""
    if request.method == "GET":
        return render_template(
            "gamification/admin/feature_create.html", page_title=_("Nuova Feature")
        )

    code = request.form.get("code", "").strip().lower().replace(" ", "_")
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "")
    is_active = request.form.get("is_active") == "on"

    return handle_service_action(
        action=lambda: FeatureConfigService.create_feature(
            code=code,
            name=name,
            description=description,
            is_active=is_active,
        ),
        redirect_url=url_for("gamification.admin_features"),
        success_message=_("Feature creata con successo"),
    )
