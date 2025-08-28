"""
Module: routes/challenge.py
Purpose: Challenge domain HTTP routes and API endpoints
Requirements: Challenge system for individual skill testing with RESTful interface
"""

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
    current_app,
)
from flask_login import login_required, current_user

from models import (
    db,
    Challenge,
    ChallengeAttempt,
)
from utils import (
    director_required,
    challenge_player_required,
    challenge_attempt_player_required,
)
from models.challenge.services import ChallengeService
from sqlalchemy import desc

# Blueprint initialization
challenge_bp = Blueprint("challenge", __name__)


@challenge_bp.route("/")
@login_required
def challenge_catalog():
    """Display challenge catalog for current user."""
    try:
        user_challenges = ChallengeService.get_user_challenges(current_user.id)
        return render_template("challenge/catalog.html", **user_challenges)
    except Exception as e:
        flash(f"Error loading challenges: {str(e)}", "danger")
        return redirect(url_for("dashboard.index"))


@challenge_bp.route("/create", methods=["GET", "POST"])
@director_required
def create_challenge():
    """Create new challenge (directors only)."""
    if request.method == "GET":
        return render_template("challenge/create.html")

    try:
        data = request.get_json() if request.is_json else request.form

        challenge = ChallengeService.create_challenge(
            name=data["name"],
            description=data["description"],
            min_score=int(data.get("min_score", 0)),
            max_score=int(data.get("max_score", 100)),
            pass_fail_only=data.get("pass_fail_only", "false").lower() == "true",
            image_path=data.get("image_path"),
            created_by_id=current_user.id,
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "challenge_id": challenge.id,
                    "message": "Challenge created successfully",
                }
            )
        else:
            flash("Challenge created successfully!", "success")
            return redirect(
                url_for("challenge.challenge_detail", challenge_id=challenge.id)
            )

    except ValueError as e:
        error_msg = f"Error creating challenge: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return render_template("challenge/create.html")


@challenge_bp.route("/<int:challenge_id>")
@login_required
@challenge_player_required
def challenge_detail(challenge_id):
    """Dettaglio sfida"""
    challenge = db.session.get(Challenge, challenge_id)
    if challenge is None:
        abort(404)

    return render_template("player/challenge_detail.html", challenge=challenge)


@challenge_bp.route("/<int:challenge_id>/attempt", methods=["POST"])
@login_required
def start_attempt(challenge_id):
    """Start a new challenge attempt."""
    try:
        data = request.get_json() if request.is_json else request.form

        attempt = ChallengeService.start_challenge_attempt(
            user_id=current_user.id,
            challenge_id=challenge_id,
            prova_id=int(data["prova_id"]) if data.get("prova_id") else None,
            round_number=int(data["round_number"])
            if data.get("round_number")
            else None,
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "attempt_id": attempt.id,
                    "message": "Challenge attempt started",
                }
            )
        else:
            flash("Challenge attempt started!", "success")
            return redirect(url_for("challenge.attempt_detail", attempt_id=attempt.id))

    except ValueError as e:
        error_msg = f"Error starting attempt: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(
                url_for("challenge.challenge_detail", challenge_id=challenge_id)
            )


@challenge_bp.route("/attempt/<int:attempt_id>")
@login_required
@challenge_attempt_player_required
def attempt_detail(attempt_id):
    """Dettaglio tentativo di sfida"""
    attempt = db.session.get(ChallengeAttempt, attempt_id)
    if attempt is None:
        abort(404)

    return render_template("player/challenge_attempt_detail.html", attempt=attempt)


@challenge_bp.route("/attempt/<int:attempt_id>/complete", methods=["POST"])
@login_required
def complete_attempt(attempt_id):
    """Complete a challenge attempt with results."""
    try:
        attempt = ChallengeAttempt.query.get_or_404(attempt_id)

        # Verify user owns this attempt
        if attempt.user_id != current_user.id:
            return jsonify({"success": False, "error": "Access denied"}), 403

        data = request.get_json() if request.is_json else request.form

        completed_attempt = ChallengeService.complete_challenge_attempt(
            attempt_id=attempt_id,
            score=data.get("score", type=int),
            passed=data.get("passed", type=bool),
            notes=data.get("notes"),
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "final_score": completed_attempt.score,
                    "passed": completed_attempt.passed,
                    "message": "Challenge completed successfully",
                }
            )
        else:
            flash("Challenge completed successfully!", "success")
            return redirect(
                url_for(
                    "challenge.challenge_detail",
                    challenge_id=completed_attempt.challenge_id,
                )
            )

    except ValueError as e:
        error_msg = f"Error completing attempt: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("challenge.attempt_detail", attempt_id=attempt_id))


@challenge_bp.route("/<int:challenge_id>/favorite", methods=["POST"])
@login_required
def toggle_favorite(challenge_id):
    """Toggle challenge as favorite."""
    try:
        is_favorited = ChallengeService.toggle_favorite(current_user.id, challenge_id)

        action = "added to" if is_favorited else "removed from"
        message = f"Challenge {action} favorites"

        if request.is_json:
            return jsonify(
                {"success": True, "is_favorited": is_favorited, "message": message}
            )
        else:
            flash(message, "success")
            return redirect(
                url_for("challenge.challenge_detail", challenge_id=challenge_id)
            )

    except Exception as e:
        error_msg = f"Error updating favorites: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(
                url_for("challenge.challenge_detail", challenge_id=challenge_id)
            )


@challenge_bp.route("/<int:challenge_id>/statistics")
@director_required
def challenge_statistics(challenge_id):
    """View challenge statistics (directors only)."""
    try:
        challenge = Challenge.query.get_or_404(challenge_id)
        statistics = challenge.get_statistics()

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "challenge": {
                        "id": challenge.id,
                        "name": challenge.name,
                        "description": challenge.description,
                    },
                    "statistics": statistics,
                }
            )
        else:
            return render_template(
                "challenge/statistics.html", challenge=challenge, statistics=statistics
            )

    except Exception as e:
        error_msg = f"Error loading statistics: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("challenge.challenge_catalog"))


@challenge_bp.route(
    "/x-replacement/<int:prova_id>/<int:round_number>", methods=["POST"]
)
@login_required
def create_x_replacement(prova_id, round_number):
    """Create challenge attempt for X replacement in tournament."""
    try:
        data = request.get_json() if request.is_json else request.form

        attempt = ChallengeService.create_x_replacement_attempt(
            user_id=current_user.id,
            prova_id=prova_id,
            round_number=round_number,
            challenge_id=data.get("challenge_id", type=int),
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "attempt_id": attempt.id,
                    "challenge_name": attempt.challenge.name,
                    "message": "X replacement challenge created",
                }
            )
        else:
            flash("X replacement challenge created!", "success")
            return redirect(url_for("challenge.attempt_detail", attempt_id=attempt.id))

    except ValueError as e:
        error_msg = f"Error creating X replacement: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("dashboard.index"))


@challenge_bp.route("/x-replacement/<int:attempt_id>/complete", methods=["POST"])
@login_required
def complete_x_replacement(attempt_id):
    """Complete X replacement challenge attempt."""
    try:
        attempt = ChallengeAttempt.query.get_or_404(attempt_id)

        # Verify user owns this attempt and it's for X replacement
        if attempt.user_id != current_user.id or not attempt.prova_id:
            return jsonify({"success": False, "error": "Access denied"}), 403

        data = request.get_json() if request.is_json else request.form

        completed_attempt = ChallengeService.complete_x_replacement_attempt(
            attempt_id=attempt_id, score=int(data["score"]), notes=data.get("notes")
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "final_score": completed_attempt.score,
                    "rack_difference_equivalent": completed_attempt.get_rack_difference_equivalent(),
                    "message": "X replacement completed successfully",
                }
            )
        else:
            flash("X replacement completed successfully!", "success")
            return redirect(url_for("admin.prova_detail", prova_id=attempt.prova_id))

    except ValueError as e:
        error_msg = f"Error completing X replacement: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("challenge.attempt_detail", attempt_id=attempt_id))


# Error handlers
@challenge_bp.errorhandler(404)
def challenge_not_found(error):
    """Handle 404 errors in challenge blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Challenge not found"}), 404
    else:
        flash("Challenge not found.", "danger")
        return redirect(url_for("challenge.challenge_catalog"))


@challenge_bp.errorhandler(403)
def challenge_access_denied(error):
    """Handle 403 errors in challenge blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Access denied"}), 403
    else:
        flash("Access denied.", "danger")
        return redirect(url_for("challenge.challenge_catalog"))
