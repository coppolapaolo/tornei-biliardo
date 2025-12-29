# routes/admin/competition/challenges.py
"""Challenge management routes for Random tournaments."""

import os
import uuid
from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from models import (
    db,
    Gara,
)
from models.status_enum import GaraStatus
from utils import gara_manager_required, admin_required

from . import competition_bp


# ────────────────────────────────────────────────────────────────────────────────
# CHALLENGE MANAGEMENT (Random Tournaments only)
# ────────────────────────────────────────────────────────────────────────────────


@competition_bp.route("/<int:gara_id>/challenges")
@login_required
@gara_manager_required
def get_gara_challenges(gara_id):
    """Get active challenges for a gara (AJAX endpoint)."""
    from models.challenge import GaraChallengeService

    gara = db.session.get(Gara, gara_id)
    if not gara:
        return jsonify({"success": False, "error": "Gara non trovata"}), 404

    # Solo per gare Random
    if gara.matchmaking_strategy != "random":
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Challenge disponibili solo per tornei Random",
                }
            ),
            400,
        )

    try:
        gara_challenges = GaraChallengeService.get_gara_challenges(gara_id)
        challenges_data = []

        for gara_challenge in gara_challenges:
            challenges_data.append(
                {
                    "id": gara_challenge.id,
                    "challenge_id": gara_challenge.challenge_id,
                    "challenge_name": gara_challenge.challenge.get_display_name(),
                    "challenge_description": gara_challenge.challenge.description,
                    "challenge_image_filename": gara_challenge.challenge.image_filename,
                    "round_number": gara_challenge.round_number,
                    "max_attempts": gara_challenge.max_attempts,
                    "is_active": gara_challenge.is_active,
                }
            )

        return jsonify({"success": True, "challenges": challenges_data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@competition_bp.route("/<int:gara_id>/add_challenge", methods=["POST"])
@login_required
@gara_manager_required
def add_challenge_to_gara(gara_id):
    """Add a challenge to a gara (AJAX endpoint)."""
    from models.challenge import GaraChallengeService

    gara = db.session.get(Gara, gara_id)
    if not gara:
        return jsonify({"success": False, "error": "Gara non trovata"}), 404

    # Solo per gare Random
    if gara.matchmaking_strategy != "random":
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Challenge disponibili solo per tornei Random",
                }
            ),
            400,
        )

    # Solo se la gara non è ancora iniziata (SETUP o INSCRIPTION)
    if gara.status not in [GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value]:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Non è possibile aggiungere challenge dopo "
                    "l'inizio della gara",
                }
            ),
            400,
        )

    try:
        # Validazione input
        challenge_id_str = request.form.get("challenge_id", "").strip()
        if not challenge_id_str:
            return (
                jsonify({"success": False, "error": "Devi selezionare una challenge"}),
                400,
            )

        challenge_id = int(challenge_id_str)
        round_number = int(request.form["round_number"])
        max_attempts = int(request.form["max_attempts"])

        gara_challenge = GaraChallengeService.add_challenge_to_gara(
            gara_id=gara_id,
            challenge_id=challenge_id,
            round_number=round_number,
            max_attempts=max_attempts,
            added_by_id=current_user.id,
        )

        return jsonify(
            {
                "success": True,
                "message": "Challenge aggiunta con successo",
                "gara_challenge_id": gara_challenge.id,
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Errore durante l'aggiunta della challenge: {str(e)}",
                }
            ),
            500,
        )


@competition_bp.route("/<int:gara_id>/remove_challenge", methods=["POST"])
@login_required
@gara_manager_required
def remove_challenge_from_gara(gara_id):
    """Remove a challenge from a gara (AJAX endpoint)."""
    from models.challenge import GaraChallengeService, GaraChallenge

    gara = db.session.get(Gara, gara_id)
    if not gara:
        return jsonify({"success": False, "error": "Gara non trovata"}), 404

    # Solo per gare Random
    if gara.matchmaking_strategy != "random":
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Challenge disponibili solo per tornei Random",
                }
            ),
            400,
        )

    try:
        data = request.get_json()
        gara_challenge_id = data.get("gara_challenge_id")

        if not gara_challenge_id:
            return (
                jsonify({"success": False, "error": "ID gara challenge mancante"}),
                400,
            )

        # Verifica che la gara challenge appartenga alla gara corrente
        gara_challenge = GaraChallenge.query.get(gara_challenge_id)
        if not gara_challenge or gara_challenge.gara_id != gara_id:
            return jsonify({"success": False, "error": "Challenge non trovata"}), 404

        # Rimuovi la challenge (o disattivala se ci sono già tentativi)
        success = GaraChallengeService.remove_challenge_from_gara(
            gara_id, gara_challenge.challenge_id, gara_challenge.round_number
        )

        if success:
            return jsonify(
                {"success": True, "message": "Challenge rimossa con successo"}
            )
        else:
            return jsonify({"success": False, "error": "Challenge non trovata"}), 404

    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Errore durante la rimozione della challenge: {str(e)}",
                }
            ),
            500,
        )


@competition_bp.route("/<int:gara_id>/challenges/available")
@login_required
@gara_manager_required
def get_available_challenges_for_gara(gara_id):
    """Get available challenges for selection, excluding those already added
    to the gara (AJAX endpoint)."""
    from models.challenge import Challenge
    from models.challenge.gara_challenge_service import GaraChallengeService

    try:
        # Get all active challenges
        all_challenges = (
            Challenge.query.filter_by(is_active=True)
            .order_by(Challenge.description)
            .all()
        )

        # Get challenge IDs already assigned to this gara
        assigned_challenges = GaraChallengeService.get_gara_challenges(gara_id)
        assigned_challenge_ids = {gc.challenge_id for gc in assigned_challenges}

        # Filter out challenges already assigned to this gara
        available_challenges = [
            c for c in all_challenges if c.id not in assigned_challenge_ids
        ]

        challenges_data = []
        for challenge in available_challenges:
            # Assicura che il percorso dell'immagine sia corretto
            image_filename = None
            if challenge.image_path:
                if challenge.image_path.startswith("uploads/"):
                    image_filename = challenge.image_path.split("/")[-1]
                else:
                    image_filename = challenge.image_path

            challenges_data.append(
                {
                    "id": challenge.id,
                    "name": challenge.get_display_name(),
                    "description": challenge.description,
                    "pass_fail_only": challenge.pass_fail_only,
                    "image_filename": image_filename,
                }
            )

        return jsonify({"success": True, "challenges": challenges_data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@competition_bp.route("/challenges/available")
@login_required
@admin_required
def get_available_challenges():
    """Get all available challenges for selection (AJAX endpoint)."""
    from models.challenge import Challenge

    try:
        challenges = (
            Challenge.query.filter_by(is_active=True)
            .order_by(Challenge.description)
            .all()
        )

        challenges_data = []
        for challenge in challenges:
            # Assicura che il percorso dell'immagine sia corretto
            image_filename = None
            if challenge.image_path:
                if challenge.image_path.startswith("uploads/"):
                    image_filename = challenge.image_path.split("/")[-1]
                else:
                    image_filename = challenge.image_path

            challenges_data.append(
                {
                    "id": challenge.id,
                    "name": challenge.get_display_name(),
                    "description": challenge.description,
                    "pass_fail_only": challenge.pass_fail_only,
                    "image_filename": image_filename,
                }
            )

        return jsonify({"success": True, "challenges": challenges_data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@competition_bp.route("/challenges/create", methods=["POST"])
@login_required
@admin_required
def create_new_challenge():
    """Create a new challenge (AJAX endpoint)."""
    from models.challenge import ChallengeService

    try:
        description = request.form["description"].strip()
        pass_fail_only = request.form.get("pass_fail_only", "false").lower() == "true"

        if not description:
            return (
                jsonify({"success": False, "error": "La descrizione è obbligatoria"}),
                400,
            )

        # Handle image upload (required)
        if "image" not in request.files or not request.files["image"].filename:
            return (
                jsonify({"success": False, "error": "L'immagine è obbligatoria"}),
                400,
            )

        file = request.files["image"]
        if not file or not file.filename:
            return (
                jsonify({"success": False, "error": "L'immagine è obbligatoria"}),
                400,
            )

        # Check file size (max 5MB)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > 5 * 1024 * 1024:  # 5MB
            return (
                jsonify(
                    {"success": False, "error": "Immagine troppo grande (max 5MB)"}
                ),
                400,
            )

        filename = secure_filename(file.filename)
        if not filename:
            return (
                jsonify({"success": False, "error": "Nome file non valido"}),
                400,
            )

        # Check file extension
        allowed_extensions = {"png", "jpg", "jpeg", "gif", "webp"}
        file_extension = filename.rsplit(".", 1)[1].lower() if "." in filename else None

        if not file_extension or file_extension not in allowed_extensions:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Formato file non supportato. "
                        "Usa JPG, PNG, GIF o WebP",
                    }
                ),
                400,
            )

        # Generate unique filename
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"

        # Use centralized image path management
        from utils.image_paths import ImagePathManager

        # Ensure uploads directory exists
        ImagePathManager.ensure_challenge_upload_dir()

        # Get upload directory and save file
        uploads_dir = ImagePathManager.get_challenge_upload_dir()
        file_path = os.path.join(uploads_dir, unique_filename)
        file.save(file_path)

        # Get database path using centralized utility
        image_path = ImagePathManager.get_challenge_db_path(unique_filename)

        # Create the challenge
        challenge = ChallengeService.create_challenge(
            description=description,
            pass_fail_only=pass_fail_only,
            image_path=image_path,
            created_by_id=current_user.id,
        )

        return jsonify(
            {
                "success": True,
                "message": "Challenge creata con successo",
                "challenge_id": challenge.id,
                "challenge_name": challenge.get_display_name(),
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Errore durante la creazione della challenge: {str(e)}",
                }
            ),
            500,
        )


@competition_bp.route("/<int:gara_id>/challenge_classification")
@login_required
@gara_manager_required
def get_gara_challenge_classification(gara_id):
    """Get challenge classification for a gara."""
    from models.challenge import GaraChallengeService

    gara = db.session.get(Gara, gara_id)
    if not gara:
        abort(404)

    # Solo per gare Random
    if gara.matchmaking_strategy != "random":
        flash("Classifica challenge disponibile solo per tornei Random", "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Verifica se ci sono challenge attive
    if not GaraChallengeService.has_active_challenges(gara_id):
        flash("Nessuna challenge attiva per questa gara", "info")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Aggiorna e ottieni la classificazione
    classification = GaraChallengeService.update_gara_classification(gara_id)
    challenge_stats = GaraChallengeService.get_challenge_statistics(gara_id)
    gara_challenges = GaraChallengeService.get_gara_challenges(gara_id)

    return render_template(
        "admin/gara_challenge_classification.html",
        gara=gara,
        classification=classification,
        challenge_stats=challenge_stats,
        gara_challenges=gara_challenges,
    )
