"""Dashboard, statistics, availability, and admin views for individual matches."""

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
import logging

from flask_babel import gettext as _
from flask_login import current_user

from models.individual_match.services import IndividualMatchService
from models.user.permissions import RoleRequirement
from utils import admin_required

from . import individual_match_bp

logger = logging.getLogger(__name__)


@individual_match_bp.route("/")
@RoleRequirement.player_or_director_required
def dashboard():
    """Individual match dashboard for current user."""
    try:
        user_data = IndividualMatchService.get_user_dashboard_data(current_user.id)
        return render_template("individual_match/dashboard.html", **user_data)
    except Exception as e:
        logger.error("Error loading dashboard: %s", e, exc_info=True)
        flash(_("Errore interno del server"), "danger")
        return redirect(url_for("dashboard.dashboard"))


@individual_match_bp.route("/statistics")
@RoleRequirement.player_or_director_required
def user_statistics():
    """View user's individual match statistics."""
    try:
        stats = IndividualMatchService.get_user_statistics(current_user.id)

        if request.is_json:
            return jsonify({"success": True, "statistics": stats})
        else:
            return render_template("individual_match/statistics.html", statistics=stats)

    except Exception as e:
        error_msg = f"Error loading statistics: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.dashboard"))


@individual_match_bp.route("/availability", methods=["GET", "POST"])
@RoleRequirement.player_or_director_required
def manage_availability():
    """Manage player availability for match proposals."""
    from models.location.models import BilliardHall

    verified_venues = (
        BilliardHall.query.filter_by(is_active=True, verified=True)
        .order_by(BilliardHall.name)
        .all()
    )

    if request.method == "GET":
        availability_data = IndividualMatchService.get_user_availability(
            current_user.id
        )
        return render_template(
            "individual_match/availability.html",
            verified_venues=verified_venues,
            **availability_data,
        )

    try:
        data = request.get_json() if request.is_json else request.form

        availability_data = data.get("availability", [])
        if not isinstance(availability_data, list):
            raise ValueError("Availability data must be a list")

        IndividualMatchService.update_user_availability(
            user_id=current_user.id, availability_data=availability_data
        )

        if request.is_json:
            return jsonify(
                {"success": True, "message": "Availability updated successfully"}
            )
        else:
            flash(_("Disponibilità aggiornata con successo!"), "success")
            return redirect(url_for("individual_match.manage_availability"))

    except ValueError as e:
        error_msg = f"Error updating availability: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return render_template(
                "individual_match/availability.html",
                verified_venues=verified_venues,
            )


@individual_match_bp.route(
    "/availability/<int:availability_id>/remove", methods=["POST"]
)
@RoleRequirement.player_or_director_required
def remove_availability(availability_id):
    """Remove one of the current user's availability records."""
    try:
        IndividualMatchService.remove_user_availability(
            availability_id, current_user.id
        )
        if request.is_json:
            return jsonify({"success": True})
        flash(_("Disponibilità rimossa."), "success")
    except ValueError as e:
        if request.is_json:
            return jsonify({"success": False, "error": str(e)}), 400
        flash(str(e), "danger")
    return redirect(url_for("individual_match.manage_availability"))


# Admin routes
@individual_match_bp.route("/admin/overview")
@admin_required
def admin_overview():
    """Admin overview of all individual matches."""
    try:
        overview_data = IndividualMatchService.get_admin_overview()
        return render_template("individual_match/admin_overview.html", **overview_data)
    except Exception as e:
        logger.error("Error loading admin overview: %s", e, exc_info=True)
        flash(_("Errore interno del server"), "danger")
        return redirect(url_for("dashboard.dashboard"))


# Error handlers
@individual_match_bp.errorhandler(404)
def individual_match_not_found(error):
    """Handle 404 errors in individual match blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Resource not found"}), 404
    else:
        flash(_("Risorsa non trovata."), "danger")
        return redirect(url_for("individual_match.dashboard"))


@individual_match_bp.errorhandler(403)
def individual_match_access_denied(error):
    """Handle 403 errors in individual match blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Access denied"}), 403
    else:
        flash(_("Accesso negato."), "danger")
        return redirect(url_for("individual_match.dashboard"))
