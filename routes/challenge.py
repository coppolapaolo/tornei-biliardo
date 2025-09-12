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
import os
import uuid
from werkzeug.utils import secure_filename
from flask_login import login_required, current_user
from PIL import Image

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

# Blueprint initialization
challenge_bp = Blueprint("challenge", __name__)

# Helper functions
def allowed_file(filename):
    """Check if file extension is allowed."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_challenge_image(image_file):
    """Save uploaded challenge image with resizing and optimization for mobile landscape viewing."""
    if not image_file or not allowed_file(image_file.filename):
        return None
    
    # Generate unique filename (always use .jpg for optimized output)
    filename = f"{uuid.uuid4().hex}.jpg"
    
    # Create upload directory if it doesn't exist
    if current_app.static_folder is None:
        raise ValueError("Static folder not configured")
    upload_dir = os.path.join(current_app.static_folder, 'uploads', 'challenges')
    os.makedirs(upload_dir, exist_ok=True)
    
    # Process and save image with optimization
    filepath = os.path.join(upload_dir, filename)
    
    try:
        # Open image with PIL
        with Image.open(image_file) as img:
            # Convert to RGB if necessary (handles PNG with alpha, etc.)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Calculate resize dimensions for mobile landscape (max 800x600)
            max_width, max_height = 800, 600
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            # Save with optimization for web
            img.save(
                filepath, 
                'JPEG', 
                quality=85,  # Good quality but smaller file size
                optimize=True,  # Enable optimization
                progressive=True  # Progressive JPEG for better loading
            )
        
        return filename
        
    except Exception as e:
        # If image processing fails, remove any partial file and return None
        if os.path.exists(filepath):
            os.remove(filepath)
        current_app.logger.error(f"Failed to process challenge image: {str(e)}")
        return None


def delete_challenge_image(image_filename):
    """Delete challenge image file from disk."""
    if not image_filename:
        return
    
    if current_app.static_folder is None:
        return
        
    filepath = os.path.join(current_app.static_folder, 'uploads', 'challenges', image_filename)
    
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            current_app.logger.info(f"Deleted challenge image: {image_filename}")
    except Exception as e:
        current_app.logger.error(f"Failed to delete challenge image {image_filename}: {str(e)}")


@challenge_bp.route("/")
@login_required
def challenge_catalog():
    """Display challenge catalog for current user."""
    try:
        catalog_data = ChallengeService.get_catalog_data(current_user.id)
        return render_template("challenge/catalog.html", **catalog_data)
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
        if request.is_json:
            data = request.get_json()
            image_filename = None
        else:
            data = request.form
            # Handle image upload
            image_file = request.files.get('image')
            image_filename = save_challenge_image(image_file) if image_file else None

        challenge = ChallengeService.create_challenge(
            name=data.get("name") if data.get("name") else None,
            description=data["description"],
            min_score=int(data.get("min_score", 0)),
            max_score=int(data.get("max_score", 100)),
            pass_fail_only=data.get("pass_fail_only", "false").lower() == "true",
            image_path=image_filename,
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


@challenge_bp.route("/<int:challenge_id>/edit", methods=["GET", "POST"])
@director_required
def edit_challenge(challenge_id):
    """Edit existing challenge (directors and admins only)."""
    challenge = db.session.get(Challenge, challenge_id)
    if challenge is None:
        abort(404)
    
    # Check if user can edit (admin can edit all, directors can edit their own)
    can_edit = (
        current_user.is_admin or 
        (current_user.is_director and challenge.created_by_id == current_user.id)
    )
    if not can_edit:
        abort(403)
    
    if request.method == "GET":
        return render_template("challenge/edit.html", challenge=challenge)

    try:
        if request.is_json:
            data = request.get_json()
            image_filename = data.get("image_path")
        else:
            data = request.form
            # Handle image upload
            image_file = request.files.get('image')
            image_filename = save_challenge_image(image_file) if image_file else None
            # If no new image uploaded, keep existing image
            if image_filename is None:
                image_filename = challenge.image_filename
            else:
                # New image uploaded, delete old image if it exists
                if challenge.image_filename and challenge.image_filename != image_filename:
                    delete_challenge_image(challenge.image_filename)

        updated_challenge = ChallengeService.update_challenge(
            challenge_id=challenge_id,
            name=data.get("name") if data.get("name") else None,
            description=data.get("description"),
            image_path=image_filename,
            is_active=data.get("is_active", "false").lower() == "true"
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "challenge_id": updated_challenge.id,
                    "message": "Challenge updated successfully",
                }
            )
        else:
            flash("Challenge updated successfully!", "success")
            return redirect(url_for("challenge.challenge_detail", challenge_id=challenge_id))

    except ValueError as e:
        error_msg = f"Error updating challenge: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return render_template("challenge/edit.html", challenge=challenge)


@challenge_bp.route("/<int:challenge_id>/delete", methods=["POST"])
@director_required
def delete_challenge(challenge_id):
    """Delete challenge (soft delete - mark as inactive)."""
    challenge = db.session.get(Challenge, challenge_id)
    if challenge is None:
        abort(404)
    
    # Check if user can delete (admin can delete all, directors can delete their own)
    can_delete = (
        current_user.is_admin or 
        (current_user.is_director and challenge.created_by_id == current_user.id)
    )
    if not can_delete:
        abort(403)

    try:
        # Delete associated image file before deleting the challenge
        if challenge.image_filename:
            delete_challenge_image(challenge.image_filename)
        
        ChallengeService.delete_challenge(challenge_id)
        
        message = "Challenge deleted successfully"
        if request.is_json:
            return jsonify({"success": True, "message": message})
        else:
            flash(message, "success")
            return redirect(url_for("challenge.challenge_catalog"))

    except Exception as e:
        error_msg = f"Error deleting challenge: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("challenge.challenge_catalog"))


@challenge_bp.route("/<int:challenge_id>")
@login_required
@challenge_player_required
def challenge_detail(challenge_id):
    """Dettaglio sfida"""
    challenge = db.session.get(Challenge, challenge_id)
    if challenge is None:
        abort(404)

    # Always return the full page template (no more modal)
    return render_template("player/challenge_detail.html", challenge=challenge)


@challenge_bp.route("/<int:challenge_id>/attempt", methods=["GET", "POST"])
@login_required
def start_attempt(challenge_id):
    """Start a new challenge attempt."""
    challenge = db.session.get(Challenge, challenge_id)
    if challenge is None:
        abort(404)
    
    if not challenge.is_active:
        flash("Questa challenge non è più attiva.", "warning")
        return redirect(url_for("challenge.challenge_catalog"))

    if request.method == "GET":
        return render_template("challenge/start_attempt.html", challenge=challenge)

    try:
        data = request.get_json() if request.is_json else request.form

        attempt = ChallengeService.start_challenge_attempt(
            user_id=current_user.id,
            challenge_id=challenge_id,
            gara_id=int(data["gara_id"]) if data.get("gara_id") else None,
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
                {"success": True, "is_favorite": is_favorited, "message": message}
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
    "/x-replacement/<int:gara_id>/<int:round_number>", methods=["POST"]
)
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
        if attempt.user_id != current_user.id or not attempt.gara_id:
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
            return redirect(url_for("admin.gara_detail", gara_id=attempt.gara_id))

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
