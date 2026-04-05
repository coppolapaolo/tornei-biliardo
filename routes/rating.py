"""
Module: routes/rating.py
Purpose: Rating domain HTTP routes for player categories and handicap system
Requirements: Rating and handicap system for fair play and skill-based matching
"""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from models.rating.services import RatingService, CategoryService, HandicapService
from models.rating.models import (
    RatingSystem,
    CategoryLevel,
)
from utils import admin_required, director_required
from utils.route_helpers import handle_ajax_service_action, safe_json_error

# Blueprint initialization
rating_bp = Blueprint("rating", __name__)


@rating_bp.route("/")
@login_required
def rating_dashboard():
    """Player rating and category dashboard."""
    try:
        user_data = RatingService.get_user_rating_profile(current_user.id)
        return render_template("rating/dashboard.html", **user_data)
    except Exception as e:
        flash(f"Error loading rating dashboard: {str(e)}", "danger")
        return redirect(url_for("dashboard.dashboard"))


@rating_bp.route("/category")
@login_required
def view_category():
    """View current player category and history."""
    try:
        category_data = CategoryService.get_user_category_info(current_user.id)
        return render_template("rating/category.html", **category_data)
    except Exception as e:
        flash(f"Error loading category information: {str(e)}", "danger")
        return redirect(url_for("rating.rating_dashboard"))


@rating_bp.route("/ratings")
@login_required
def view_ratings():
    """View all player ratings in different systems."""
    try:
        ratings_data = RatingService.get_user_all_ratings(current_user.id)
        return render_template("rating/ratings.html", **ratings_data)
    except Exception as e:
        flash(f"Error loading ratings: {str(e)}", "danger")
        return redirect(url_for("rating.rating_dashboard"))


@rating_bp.route("/ratings/update", methods=["POST"])
@login_required
def update_rating():
    """Update player rating (self-reported, requires verification)."""
    data = request.get_json() if request.is_json else request.form

    def action():
        rating = RatingService.update_user_rating(
            user_id=current_user.id,
            rating_system=RatingSystem(data["rating_system"]),
            rating_value=int(data["rating_value"]),
            external_id=data.get("external_id"),
            confidence=float(data.get("confidence", 0.5)),
        )
        return {"rating_id": rating.id, "verified": rating.verified}

    return handle_ajax_service_action(
        action=action,
        redirect_url=url_for("rating.view_ratings"),
        success_message="Rating updated successfully. Verification pending.",
        error_prefix=None,
    )


@rating_bp.route("/handicap/calculator")
@login_required
def handicap_calculator():
    """Handicap calculator for match planning."""
    try:
        return render_template("rating/handicap_calculator.html")
    except Exception as e:
        flash(f"Error loading handicap calculator: {str(e)}", "danger")
        return redirect(url_for("rating.rating_dashboard"))


@rating_bp.route("/handicap/calculate", methods=["POST"])
@login_required
def calculate_handicap():
    """Calculate handicap between two players."""
    try:
        data = request.get_json() if request.is_json else request.form

        handicap_info = HandicapService.calculate_handicap(
            player1_id=int(data["player1_id"]),
            player2_id=int(data["player2_id"]),
            rule_id=data.get("rule_id", type=int),
        )

        if request.is_json:
            return jsonify({"success": True, "handicap": handicap_info})
        else:
            return render_template(
                "rating/handicap_result.html", handicap=handicap_info
            )

    except ValueError as e:
        error_msg = f"Error calculating handicap: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("rating.handicap_calculator"))


# Director routes
@rating_bp.route("/manage")
@director_required
def manage_ratings():
    """Manage player ratings and categories (directors only)."""
    try:
        management_data = RatingService.get_management_overview()
        return render_template("rating/manage.html", **management_data)
    except Exception as e:
        flash(f"Error loading management interface: {str(e)}", "danger")
        return redirect(url_for("dashboard.dashboard"))


@rating_bp.route("/category/assign", methods=["POST"])
@director_required
def assign_category():
    """Assign category to player (directors only)."""
    data = request.get_json() if request.is_json else request.form

    def action():
        category = CategoryService.assign_category(
            user_id=int(data["user_id"]),
            category=CategoryLevel(data["category"]),
            assigned_by_id=current_user.id,
            reason=data.get("reason"),
        )
        return {"category_id": category.id}

    return handle_ajax_service_action(
        action=action,
        redirect_url=url_for("rating.manage_ratings"),
        success_message="Category assigned successfully!",
        error_prefix=None,
    )


@rating_bp.route("/ratings/<int:rating_id>/verify", methods=["POST"])
@director_required
def verify_rating(rating_id):
    """Verify a player's rating (directors only)."""
    data = request.get_json() if request.is_json else request.form

    def action():
        rating = RatingService.verify_rating(
            rating_id=rating_id,
            verified_by_id=current_user.id,
            verified=data.get("verified", "true").lower() == "true",
        )
        return {"verified": rating.verified}

    return handle_ajax_service_action(
        action=action,
        redirect_url=url_for("rating.manage_ratings"),
        success_message="Rating verification updated!",
        error_prefix=None,
    )


# Admin routes
@rating_bp.route("/admin/rules")
@admin_required
def manage_handicap_rules():
    """Manage handicap rules (admin only)."""
    try:
        rules_data = HandicapService.get_all_rules()
        return render_template("rating/admin_rules.html", **rules_data)
    except Exception as e:
        flash(f"Error loading handicap rules: {str(e)}", "danger")
        return redirect(url_for("dashboard.dashboard"))


@rating_bp.route("/admin/rules/create", methods=["POST"])
@admin_required
def create_handicap_rule():
    """Create new handicap rule (admin only)."""
    import json

    data = request.get_json() if request.is_json else request.form

    def action():
        # Handle category_rules - convert from string if needed
        category_rules = data.get("category_rules")
        if category_rules is not None:
            if isinstance(category_rules, str):
                try:
                    category_rules = json.loads(category_rules)
                except (json.JSONDecodeError, ValueError):
                    category_rules = []
            elif not isinstance(category_rules, list):
                category_rules = []
        else:
            category_rules = None

        # Handle rating_rules - convert from string if needed
        rating_rules = data.get("rating_rules")
        if rating_rules is not None:
            if isinstance(rating_rules, str):
                try:
                    rating_rules = json.loads(rating_rules)
                except (json.JSONDecodeError, ValueError):
                    rating_rules = []
            elif not isinstance(rating_rules, list):
                rating_rules = []
        else:
            rating_rules = None

        rule = HandicapService.create_handicap_rule(
            name=data["name"],
            description=data.get("description"),
            applies_to_campionatos=data.get("applies_to_campionatos", "true").lower()
            == "true",
            applies_to_individual_matches=data.get(
                "applies_to_individual_matches", "true"
            ).lower()
            == "true",
            category_rules=category_rules,
            rating_rules=rating_rules,
        )
        return {"rule_id": rule.id}

    return handle_ajax_service_action(
        action=action,
        redirect_url=url_for("rating.manage_handicap_rules"),
        success_message="Handicap rule created successfully!",
        error_prefix=None,
    )


@rating_bp.route("/admin/statistics")
@admin_required
def rating_statistics():
    """View rating system statistics (admin only)."""
    try:
        stats = RatingService.get_system_statistics()

        if request.is_json:
            return jsonify({"success": True, "statistics": stats})
        else:
            return render_template("rating/admin_statistics.html", statistics=stats)

    except Exception as e:
        if request.is_json:
            return safe_json_error(e, "loading statistics")
        else:
            flash("Error loading statistics", "danger")
            return redirect(url_for("dashboard.dashboard"))


@rating_bp.route("/leaderboard")
def public_leaderboard():
    """Public leaderboard showing top players by category."""
    try:
        leaderboard_data = RatingService.get_public_leaderboard()
        return render_template("rating/leaderboard.html", **leaderboard_data)
    except Exception as e:
        flash(f"Error loading leaderboard: {str(e)}", "danger")
        return redirect(url_for("main.index"))


# API endpoints for integration
@rating_bp.route("/api/user/<int:user_id>/category")
@login_required
def get_user_category_api(user_id):
    """API endpoint to get user's current category."""
    try:
        category = CategoryService.get_user_current_category(user_id)

        if category:
            return jsonify(
                {
                    "success": True,
                    "category": {
                        "level": category.category.value,
                        "assigned_at": category.assigned_at.isoformat(),
                        "is_active": category.is_active,
                    },
                }
            )
        else:
            return jsonify({"success": True, "category": None})

    except Exception as e:
        return safe_json_error(e, "fetching user category")


@rating_bp.route("/api/handicap/<int:player1_id>/<int:player2_id>")
@login_required
def get_handicap_api(player1_id, player2_id):
    """API endpoint to get handicap between two players."""
    try:
        handicap = HandicapService.calculate_handicap(player1_id, player2_id)
        return jsonify({"success": True, "handicap": handicap})
    except Exception as e:
        return safe_json_error(e, "calculating handicap")


# Error handlers
@rating_bp.errorhandler(404)
def rating_not_found(error):
    """Handle 404 errors in rating blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Resource not found"}), 404
    else:
        flash("Resource not found.", "danger")
        return redirect(url_for("rating.rating_dashboard"))


@rating_bp.errorhandler(403)
def rating_access_denied(error):
    """Handle 403 errors in rating blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Access denied"}), 403
    else:
        flash("Access denied.", "danger")
        return redirect(url_for("rating.rating_dashboard"))
