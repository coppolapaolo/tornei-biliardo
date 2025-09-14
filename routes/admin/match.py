# routes/admin/match.py
"""Match and rack management blueprint for admin interface."""

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
from flask_login import login_required

from models import (
    Match,
    Rack,
    db,
)
from utils import (
    match_manager_required,
    rack_manager_required,
)
from models.match.services import RackService

# Match management blueprint
match_bp = Blueprint("match", __name__)


@match_bp.route("/<int:match_id>")
@login_required
@match_manager_required
def match_detail(match_id):
    """Dettaglio partita per admin"""
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)
    racks = Rack.query.filter_by(match_id=match_id).order_by(Rack.rack_number).all()

    # Get available challenges for this match if it's a Random gara
    available_challenges = []
    player_challenge_progress = {}
    if (
        match.gara
        and match.gara.matchmaking_strategy == "random"
        and match.gara.status in ["playing", "completed"]
    ):

        from models.challenge import GaraChallengeService

        # Get challenges available for current round
        available_challenges = GaraChallengeService.get_available_challenges_for_round(
            match.gara.id, match.gara.current_round
        )

        # Get progress for both players
        if match.player1:
            player_challenge_progress[match.player1.id] = (
                GaraChallengeService.get_user_gara_challenge_progress(
                    match.gara.id, match.player1.id
                )
            )
        if match.player2:
            player_challenge_progress[match.player2.id] = (
                GaraChallengeService.get_user_gara_challenge_progress(
                    match.gara.id, match.player2.id
                )
            )

    return render_template(
        "match_detail.html",
        match=match,
        racks=racks,
        available_challenges=available_challenges,
        player_challenge_progress=player_challenge_progress,
    )


@match_bp.route("/<int:match_id>/add_rack", methods=["POST"])
@login_required
@match_manager_required
def add_rack_result(match_id):
    """Aggiungi risultato rack (admin)"""
    winner_id = int(request.form["winner_id"])

    # Usa il service layer invece del direct database access
    try:
        result = RackService.add_rack_with_score_update(
            match_id=match_id,
            winner_id=winner_id,
            reported_by_id=1,  # Admin user ID
            validated_by_admin=True,  # Admin validation immediate
        )
        return jsonify(result)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante aggiunta rack: {str(e)}"}), 500


@match_bp.route("/<int:match_id>/set_result", methods=["POST"])
@login_required
@match_manager_required
def set_match_result_direct(match_id):
    """Imposta risultato completo di una partita (admin)"""
    try:
        player1_score = int(request.form["player1_score"])
        player2_score = int(request.form["player2_score"])

        # Usa il service layer invece del direct database access
        RackService.set_match_result_direct(match_id, player1_score, player2_score)

        # Dopo aver impostato il risultato, controlla se ci sono turni da aggiornare
        from models.match.models import Match
        from models.competition.services import GaraService

        match = Match.query.get(match_id)
        if match and match.gara_id:
            GaraService.update_round_progression(match.gara_id)

        flash("Risultato impostato con successo!")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))

    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))
    except Exception as e:
        flash(f"Errore durante l'impostazione del risultato: {str(e)}", "error")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))


@match_bp.route("/<int:match_id>/reset", methods=["POST"])
@login_required
@match_manager_required
def reset_match(match_id):
    """Reset completo di una partita (admin)"""
    try:
        # Usa il service layer invece del direct database access
        RackService.reset_match_complete(match_id)

        # Dopo aver resettato il match, controlla se ci sono turni da aggiornare
        from models.match.models import Match
        from models.competition.services import GaraService

        match = Match.query.get(match_id)
        if match and match.gara_id:
            GaraService.update_round_progression(match.gara_id)

        flash("Partita resettata con successo!")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))

    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))
    except Exception as e:
        flash(f"Errore durante il reset: {str(e)}", "error")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))


# ============ GESTIONE RACK ADMIN ============


@match_bp.route("/rack/<int:rack_id>/remove", methods=["POST"])
@login_required
@rack_manager_required
def remove_rack_admin(rack_id):
    """Rimuovi un rack (admin)"""
    try:
        # Prima ottieni le info del match per il round update
        from models.competition.services import GaraService

        rack = Rack.query.get(rack_id)
        gara_id = None
        if rack and rack.match and rack.match.gara_id:
            gara_id = rack.match.gara_id

        # Usa il service layer invece del direct database access
        result = RackService.remove_rack_admin(rack_id)

        # Dopo aver rimosso il rack, controlla se ci sono turni da aggiornare
        if gara_id:
            GaraService.update_round_progression(gara_id)

        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante la rimozione: {str(e)}"}), 500


@match_bp.route("/rack/<int:rack_id>/validate", methods=["POST"])
@login_required
@rack_manager_required
def validate_rack_admin(rack_id):
    """Valida un rack (admin)"""
    try:
        # Usa il service layer invece del direct database access
        RackService.validate_rack_admin(rack_id)

        return jsonify(
            {"success": True, "message": "Rack validato dall'amministratore"}
        )

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante la validazione: {str(e)}"}), 500


# ────────────────────────────────────────────────────────────────────────────────
# CHALLENGE ATTEMPTS RECORDING
# ────────────────────────────────────────────────────────────────────────────────


@match_bp.route("/record_challenge_attempt", methods=["POST"])
@login_required
@match_manager_required
def record_challenge_attempt():
    """Record a single challenge attempt during match (AJAX endpoint)."""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ["gara_challenge_id", "user_id"]
        for field in required_fields:
            if field not in data:
                return (
                    jsonify({"success": False, "error": f"Campo {field} mancante"}),
                    400,
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

        from models.challenge import GaraChallengeService, GaraChallenge

        # Verify gara challenge exists and user has permissions
        gara_challenge = GaraChallenge.query.get(data["gara_challenge_id"])
        if not gara_challenge:
            return jsonify({"success": False, "error": "Challenge non trovata"}), 404

        # Verify it's a Random tournament
        if gara_challenge.gara.matchmaking_strategy != "random":
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Challenge disponibili solo per tornei Random",
                    }
                ),
                400,
            )

        # Record the attempt
        attempt = GaraChallengeService.record_challenge_attempt(
            gara_challenge_id=data["gara_challenge_id"],
            user_id=data["user_id"],
            score=data.get("score"),
            passed=data.get("passed"),
            notes=data.get("notes"),
            round_when_attempted=data.get("round_when_attempted"),
        )

        return jsonify(
            {
                "success": True,
                "message": "Tentativo registrato con successo",
                "attempt_id": attempt.id,
                "score": attempt.score,
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Errore durante la registrazione: {str(e)}",
                }
            ),
            500,
        )


@match_bp.route("/record_challenge_attempts", methods=["POST"])
@login_required
@match_manager_required
def record_challenge_attempts():
    """Record multiple challenge attempts at once (AJAX endpoint)."""
    try:
        data = request.get_json()

        if "attempts" not in data or not data["attempts"]:
            return (
                jsonify(
                    {"success": False, "error": "Lista tentativi mancante o vuota"}
                ),
                400,
            )

        attempts_data = data["attempts"]

        # Validate all attempts before processing
        for attempt_data in attempts_data:
            required_fields = ["gara_challenge_id", "user_id"]
            for field in required_fields:
                if field not in attempt_data:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": f"Campo {field} mancante in un tentativo",
                            }
                        ),
                        400,
                    )

            if "score" not in attempt_data and "passed" not in attempt_data:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Specificare punteggio o risultato pass/fail per tutti i tentativi",
                        }
                    ),
                    400,
                )

        from models.challenge import GaraChallengeService

        # Record all attempts
        recorded_attempts = GaraChallengeService.record_multiple_attempts(
            attempts_data=attempts_data,
            round_when_attempted=attempts_data[0].get("round_when_attempted"),
        )

        return jsonify(
            {
                "success": True,
                "message": f"{len(recorded_attempts)} tentativo/i registrato/i con successo",
                "recorded_count": len(recorded_attempts),
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Errore durante la registrazione: {str(e)}",
                }
            ),
            500,
        )
