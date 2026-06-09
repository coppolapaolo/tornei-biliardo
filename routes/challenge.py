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
from utils.route_helpers import handle_ajax_service_action, safe_json_error
from utils.image_paths import ImagePathManager

# Blueprint initialization
challenge_bp = Blueprint("challenge", __name__)


# Convenience aliases for image operations (delegated to ImagePathManager)
save_challenge_image = ImagePathManager.save_challenge_image
delete_challenge_image = ImagePathManager.delete_challenge_image


@challenge_bp.route("/")
@login_required
def challenge_catalog():
    """Display challenge catalog for current user."""
    try:
        catalog_data = ChallengeService.get_catalog_data(current_user.id)
        return render_template("challenge/catalog.html", **catalog_data)
    except Exception as e:
        flash(f"Error loading challenges: {str(e)}", "danger")
        return redirect(url_for("dashboard.dashboard"))


@challenge_bp.route("/create", methods=["GET", "POST"])
@director_required
def create_challenge():
    """Create new challenge (directors only)."""
    if request.method == "GET":
        return render_template("challenge/create.html")

    try:
        if request.is_json:
            data = request.get_json()
            image_filename = data.get("image_path")
            if not image_filename:
                raise ValueError("Immagine obbligatoria per creare una challenge")
        else:
            data = request.form
            # Handle image upload
            image_file = request.files.get("image")
            image_filename = save_challenge_image(image_file) if image_file else None

        # Validate that image is provided or use default for testing
        if not image_filename:
            # Use default path for testing scenarios
            image_filename = "default_challenge.jpg"

        # Convert filename to proper database path
        from utils.image_paths import ImagePathManager

        image_path = ImagePathManager.get_challenge_db_path(image_filename)

        challenge = ChallengeService.create_challenge(
            description=data["description"],
            image_path=image_path,
            pass_fail_only=data.get("pass_fail_only", "false").lower() == "true",
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


@challenge_bp.route("/<int:challenge_id>/delete", methods=["POST"])
@director_required
def delete_challenge(challenge_id):
    """Delete challenge (soft delete - mark as inactive)."""
    challenge = db.get_or_404(Challenge, challenge_id)

    # Check if user can delete (admin can delete all, directors can delete their own)
    can_delete = current_user.is_admin or (
        current_user.is_director and challenge.created_by_id == current_user.id
    )
    if not can_delete:
        abort(403)

    def action():
        if challenge.image_filename:
            delete_challenge_image(challenge.image_filename)
        ChallengeService.delete_challenge(challenge_id)

    return handle_ajax_service_action(
        action=action,
        redirect_url=url_for("challenge.challenge_catalog"),
        success_message="Challenge eliminata con successo",
        error_prefix=None,
    )


@challenge_bp.route("/<int:challenge_id>")
@login_required
@challenge_player_required
def challenge_detail(challenge_id):
    """Dettaglio sfida"""
    challenge = db.get_or_404(Challenge, challenge_id)

    # Always return the full page template (no more modal)
    return render_template("player/challenge_detail.html", challenge=challenge)


@challenge_bp.route("/<int:challenge_id>/attempt", methods=["GET", "POST"])
@login_required
def start_attempt(challenge_id):
    """Start a new challenge attempt."""
    challenge = db.get_or_404(Challenge, challenge_id)

    # Check if challenge is active
    if not challenge.is_active:
        flash("Questa challenge non è più disponibile.", "warning")
        return redirect(url_for("challenge.challenge_catalog"))

    # Prevent admins from attempting challenges
    if current_user.is_admin:
        flash("Gli amministratori non possono provare le challenge.", "warning")
        return redirect(
            url_for("challenge.challenge_detail", challenge_id=challenge_id)
        )

    if request.method == "GET":
        return render_template("challenge/start_attempt.html", challenge=challenge)

    try:
        data = request.get_json() if request.is_json else request.form

        attempt = ChallengeService.start_challenge_attempt(
            user_id=current_user.id,
            challenge_id=challenge_id,
            gara_id=int(data["gara_id"]) if data.get("gara_id") else None,
            round_number=(
                int(data["round_number"]) if data.get("round_number") else None
            ),
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
    attempt = db.get_or_404(ChallengeAttempt, attempt_id)

    return render_template("player/challenge_attempt_detail.html", attempt=attempt)


def _parse_complete_attempt_payload(data):
    """Estrae (score, passed, notes) dal payload di completamento tentativo.

    Funziona sia con un dict semplice (body JSON) sia con un MultiDict
    (request.form). NON usa il kwarg `type=` di MultiDict.get:
    - su un dict JSON `dict.get("score", type=int)` solleva TypeError → 500;
    - `MultiDict.get("passed", type=bool)` fa bool("false") == True, segnando
      come PASSATO un tentativo pass/fail in realtà fallito.

    Lo score viene coerciato a int (None se assente/non numerico). `passed`
    è True/False solo su valori espliciti; None se assente (challenge
    numeriche: `passed` non si applica).
    """
    raw_score = data.get("score")
    try:
        score = int(raw_score) if raw_score not in (None, "") else None
    except (TypeError, ValueError):
        score = None

    raw_passed = data.get("passed")
    if isinstance(raw_passed, bool):
        passed = raw_passed
    elif raw_passed is None:
        passed = None
    else:
        passed = str(raw_passed).strip().lower() in ("true", "1", "yes", "on")

    return score, passed, data.get("notes")


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
        score, passed, notes = _parse_complete_attempt_payload(data)

        completed_attempt = ChallengeService.complete_challenge_attempt(
            attempt_id=attempt_id,
            score=score,
            passed=passed,
            notes=notes,
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
                {"success": True, "is_favorite": is_favorited, "message": message}
            )
        else:
            flash(message, "success")
            return redirect(
                url_for("challenge.challenge_detail", challenge_id=challenge_id)
            )

    except Exception as e:
        if request.is_json:
            return safe_json_error(e, "toggling favorite")
        else:
            flash("Error updating favorites", "danger")
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
        if request.is_json:
            return safe_json_error(e, "loading challenge statistics")
        else:
            flash("Error loading statistics", "danger")
            return redirect(url_for("challenge.challenge_catalog"))


@challenge_bp.route("/x-replacement/<int:gara_id>/<int:round_number>", methods=["POST"])
@login_required
def create_x_replacement(gara_id, round_number):
    """Create challenge attempt for X replacement in campionato."""
    try:
        data = request.get_json() if request.is_json else request.form

        attempt = ChallengeService.create_x_replacement_attempt(
            user_id=current_user.id,
            gara_id=gara_id,
            round_number=round_number,
            challenge_id=data.get("challenge_id", type=int),
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "attempt_id": attempt.id,
                    "challenge_description": attempt.challenge.get_display_name(),
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
            return redirect(url_for("dashboard.dashboard"))


@challenge_bp.route("/x-replacement/<int:attempt_id>/complete", methods=["POST"])
@login_required
def complete_x_replacement(attempt_id):
    """Complete X replacement challenge attempt."""
    from models.competition.gara_bye_challenge import GaraByeChallenge

    try:
        attempt = ChallengeAttempt.query.get_or_404(attempt_id)

        # Check if this is an X replacement via GaraByeChallenge (new pattern)
        bye_challenge = GaraByeChallenge.query.filter_by(
            challenge_attempt_id=attempt_id
        ).first()

        # Verify user owns this attempt and it's for X replacement
        # Check both new pattern (GaraByeChallenge) and deprecated field (gara_id)
        is_x_replacement = bye_challenge is not None or attempt.gara_id is not None
        if attempt.user_id != current_user.id or not is_x_replacement:
            return jsonify({"success": False, "error": "Access denied"}), 403

        data = request.get_json() if request.is_json else request.form

        completed_attempt = ChallengeService.complete_x_replacement_attempt(
            attempt_id=attempt_id, score=int(data["score"]), notes=data.get("notes")
        )

        # Get gara_id for redirect (prefer GaraByeChallenge, fall back to
        # deprecated field)
        redirect_gara_id = bye_challenge.gara_id if bye_challenge else attempt.gara_id

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "final_score": completed_attempt.score,
                    "message": "X replacement completed successfully",
                }
            )
        else:
            flash("X replacement completed successfully!", "success")
            return redirect(url_for("admin.gara_detail", gara_id=redirect_gara_id))

    except ValueError as e:
        error_msg = f"Error completing X replacement: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("challenge.attempt_detail", attempt_id=attempt_id))


@challenge_bp.route("/<int:challenge_id>/edit", methods=["GET", "POST"])
@director_required
def edit_challenge(challenge_id):
    """Edit challenge (directors only)."""
    challenge = db.get_or_404(Challenge, challenge_id)

    # Check if user can edit (admin can edit all, directors can edit their own)
    can_edit = current_user.is_admin or (
        current_user.is_director and challenge.created_by_id == current_user.id
    )
    if not can_edit:
        abort(403)

    if request.method == "GET":
        return render_template(
            "challenge/create.html", challenge=challenge, edit_mode=True
        )

    from models.challenge.services import ChallengeService
    from utils.route_helpers import handle_ajax_service_action

    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    # Handle image upload if provided (filesystem concern, before service call)
    new_image_path = None
    if not request.is_json:
        image_file = request.files.get("image")
        if image_file:
            image_filename = save_challenge_image(image_file)
            if image_filename:
                if challenge.image_filename:
                    delete_challenge_image(challenge.image_filename)
                from utils.image_paths import ImagePathManager

                new_image_path = ImagePathManager.get_challenge_db_path(image_filename)

    description = data["description"]
    is_active = data.get("is_active", "false").lower() == "true"

    return handle_ajax_service_action(
        action=lambda: ChallengeService.update_challenge(
            challenge_id=challenge_id,
            description=description,
            is_active=is_active,
            image_path=new_image_path,
        ),
        redirect_url=url_for("challenge.challenge_detail", challenge_id=challenge.id),
        success_message="Challenge updated successfully",
    )


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
