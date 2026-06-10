# routes/player/privacy.py
"""Privacy settings and hide/show routes for player profiles."""

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from flask_babel import _

from utils import player_only

from . import player_bp

# ============ PRIVACY SETTINGS ============


@player_bp.route("/privacy-settings", methods=["GET", "POST"])
@login_required
@player_only
def privacy_settings():
    """Gestione impostazioni privacy del profilo."""
    from models.user.privacy_service import PrivacyService

    if request.method == "POST":
        PrivacyService.update_privacy_settings(
            user_id=current_user.id,
            show_email="show_email" in request.form,
            show_phone="show_phone" in request.form,
            show_statistics="show_statistics" in request.form,
            show_recent_matches="show_recent_matches" in request.form,
            show_classifications="show_classifications" in request.form,
            show_challenge_stats="show_challenge_stats" in request.form,
        )
        flash(_("Impostazioni privacy aggiornate con successo."), "success")
        return redirect(url_for("player.privacy_settings"))

    settings = PrivacyService.get_privacy_settings(current_user.id)
    return render_template("player/privacy_settings.html", settings=settings)


# ========== Hide/Show AJAX Routes ==========


@player_bp.route("/hide/match/<int:match_id>", methods=["POST"])
@login_required
@player_only
def hide_match(match_id):
    """Hide a match from public profile (AJAX)."""
    from models.user.privacy_service import PrivacyService

    try:
        PrivacyService.hide_match(current_user.id, match_id)
        return jsonify({"success": True, "message": _("Match nascosto")})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@player_bp.route("/show/match/<int:match_id>", methods=["POST"])
@login_required
@player_only
def show_match(match_id):
    """Show a previously hidden match (AJAX)."""
    from models.user.privacy_service import PrivacyService

    if PrivacyService.show_match(current_user.id, match_id):
        return jsonify({"success": True, "message": _("Match visibile")})
    return jsonify({"success": False, "error": _("Match non era nascosto")}), 400


@player_bp.route("/hide/inscription/<int:inscription_id>", methods=["POST"])
@login_required
@player_only
def hide_inscription(inscription_id):
    """Hide an inscription from public profile (AJAX)."""
    from models.user.privacy_service import PrivacyService

    try:
        PrivacyService.hide_inscription(current_user.id, inscription_id)
        return jsonify({"success": True, "message": _("Gara nascosta")})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@player_bp.route("/show/inscription/<int:inscription_id>", methods=["POST"])
@login_required
@player_only
def show_inscription(inscription_id):
    """Show a previously hidden inscription (AJAX)."""
    from models.user.privacy_service import PrivacyService

    if PrivacyService.show_inscription(current_user.id, inscription_id):
        return jsonify({"success": True, "message": _("Gara visibile")})
    return jsonify({"success": False, "error": _("Gara non era nascosta")}), 400


@player_bp.route("/hide/campionato/<int:campionato_id>", methods=["POST"])
@login_required
@player_only
def hide_campionato(campionato_id):
    """Hide a campionato from public profile (AJAX)."""
    from models.user.privacy_service import PrivacyService

    try:
        PrivacyService.hide_campionato(current_user.id, campionato_id)
        return jsonify({"success": True, "message": _("Campionato nascosto")})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@player_bp.route("/show/campionato/<int:campionato_id>", methods=["POST"])
@login_required
@player_only
def show_campionato(campionato_id):
    """Show a previously hidden campionato (AJAX)."""
    from models.user.privacy_service import PrivacyService

    if PrivacyService.show_campionato(current_user.id, campionato_id):
        return jsonify({"success": True, "message": _("Campionato visibile")})
    return jsonify({"success": False, "error": _("Campionato non era nascosto")}), 400
