"""Dashboard, statistics, availability, and admin views for individual matches."""

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
from flask_login import current_user

from models.individual_match.services import IndividualMatchService
from models.user.permissions import RoleRequirement
from utils import admin_required

from . import individual_match_bp


@individual_match_bp.route("/")
@RoleRequirement.player_or_director_required
def dashboard():
    """Individual match dashboard for current user."""
    try:
        user_data = IndividualMatchService.get_user_dashboard_data(current_user.id)
        return render_template("individual_match/dashboard.html", **user_data)
    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}", "danger")
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


# Availability and player-discovery routes live in availability.py
# (consolidated onto AvailabilityService — see ADR-032).


# Admin routes
@individual_match_bp.route("/admin/overview")
@admin_required
def admin_overview():
    """Admin overview of all individual matches."""
    try:
        overview_data = IndividualMatchService.get_admin_overview()
        return render_template("individual_match/admin_overview.html", **overview_data)
    except Exception as e:
        flash(f"Error loading admin overview: {str(e)}", "danger")
        return redirect(url_for("dashboard.dashboard"))


# Error handlers
@individual_match_bp.errorhandler(404)
def individual_match_not_found(error):
    """Handle 404 errors in individual match blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Resource not found"}), 404
    else:
        flash("Resource not found.", "danger")
        return redirect(url_for("individual_match.dashboard"))


@individual_match_bp.errorhandler(403)
def individual_match_access_denied(error):
    """Handle 403 errors in individual match blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Access denied"}), 403
    else:
        flash("Access denied.", "danger")
        return redirect(url_for("individual_match.dashboard"))
