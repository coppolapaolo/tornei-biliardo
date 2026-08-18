# routes/player/challenges.py
"""Challenge system routes for players."""

from flask import render_template, request, jsonify
from flask_babel import _
from flask_login import login_required, current_user
from werkzeug.exceptions import abort

from models import db, Inscription
from utils.route_helpers import safe_json_error

from . import player_bp

# ====================================================================
# CHALLENGE SYSTEM ROUTES
# ====================================================================


@player_bp.route("/challenge/<int:gara_challenge_id>")
@login_required
def challenge_detail(gara_challenge_id):
    """Show challenge detail page for players"""
    from models.competition.gara_challenge import GaraChallenge

    gara_challenge = db.session.get(GaraChallenge, gara_challenge_id)
    if not gara_challenge:
        abort(404, "Challenge non trovata")

    # Verify user has access to this challenge's gara
    if gara_challenge.gara.campionato:
        # For campionato gara, user should be registered to access challenges
        inscription = Inscription.query.filter_by(
            user_id=current_user.id, gara_id=gara_challenge.gara_id
        ).first()
        if not inscription:
            abort(403, "Non hai accesso a questa challenge")

    # Get user progress for this challenge's gara
    from models.competition.gara_challenge_service import GaraChallengeService

    progress = GaraChallengeService.get_user_gara_challenge_progress(
        gara_challenge.gara_id, current_user.id
    )

    # `gara_challenge` dentro il progresso è il **modello**, non un dizionario:
    # `c.get("gara_challenge", {}).get("id")` sollevava AttributeError su ogni
    # gara che avesse almeno una challenge — cioè su ogni pagina che si potesse
    # davvero aprire (500). Con la lista vuota il generatore non iterava e
    # l'errore non compariva mai in sviluppo.
    challenge_data = next(
        (
            c
            for c in (progress or {}).get("challenges", [])
            if c["gara_challenge"].id == gara_challenge_id
        ),
        None,
    )

    return render_template(
        "player/gara_challenge_detail.html",
        gara_challenge=gara_challenge,
        challenge_data=challenge_data,
        user_progress=progress,
    )


@player_bp.route("/challenge/<int:gara_challenge_id>/attempt", methods=["POST"])
@login_required
def record_challenge_attempt(gara_challenge_id):
    """Record a challenge attempt by the player"""
    from models.competition.gara_challenge import GaraChallenge
    from models.competition.gara_challenge_service import GaraChallengeService

    try:
        data = request.get_json() if request.is_json else request.form.to_dict()

        # Get gara challenge and verify access
        gara_challenge = db.session.get(GaraChallenge, gara_challenge_id)
        if not gara_challenge:
            return jsonify({"success": False, "error": "Challenge non trovata"}), 404

        # Verify user has access to this challenge's gara.
        # Authz fix: l'iscrizione è per-gara (Inscription.gara_id) e vale sia
        # per gare di campionato sia standalone. Prima il controllo era
        # annidato in `if gara.campionato`, saltando del tutto l'autorizzazione
        # per le gare standalone (campionato_id=None): qualunque utente loggato
        # poteva registrare tentativi con score arbitrario.
        inscription = Inscription.query.filter_by(
            user_id=current_user.id, gara_id=gara_challenge.gara_id
        ).first()
        if not inscription:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": _("Non hai accesso a questo esercizio"),
                    }
                ),
                403,
            )

        # Validate that we have either score or passed
        if "score" not in data and "passed" not in data:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Specificare punteggio o risultato pass/fail",
                    }
                ),
                400,
            )

        # Record the attempt
        score = data.get("score")
        passed = data.get("passed")

        # Convert types
        if score is not None:
            score = int(score)
        if passed is not None:
            passed = bool(passed) if isinstance(passed, bool) else passed == "true"

        attempt = GaraChallengeService.record_challenge_attempt(
            gara_challenge_id=gara_challenge_id,
            user_id=current_user.id,
            score=score,
            passed=passed,
            notes=data.get("notes"),
        )

        return jsonify(
            {
                "success": True,
                "message": "Tentativo registrato con successo",
                "attempt_id": attempt.id,
                "score": attempt.score,
                "passed": attempt.passed,
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "recording player challenge attempt")
