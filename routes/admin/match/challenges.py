"""Challenge attempt recording routes for Random tournament matches."""

from flask import (
    request,
    jsonify,
)
from flask_login import login_required

from utils import match_manager_required
from utils.route_helpers import safe_json_error

from . import match_bp


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

        from models.competition.gara_challenge_service import GaraChallengeService
        from models.competition.gara_challenge import GaraChallenge

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
        return safe_json_error(e, "recording challenge attempt")


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
                            "error": (
                                "Specificare punteggio o risultato "
                                "pass/fail per tutti i tentativi"
                            ),
                        }
                    ),
                    400,
                )

        from models.competition.gara_challenge_service import GaraChallengeService

        # Record all attempts
        recorded_attempts = GaraChallengeService.record_multiple_attempts(
            attempts_data=attempts_data,
            round_when_attempted=attempts_data[0].get("round_when_attempted"),
        )

        return jsonify(
            {
                "success": True,
                "message": (
                    f"{len(recorded_attempts)} tentativo/i " "registrato/i con successo"
                ),
                "recorded_count": len(recorded_attempts),
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "recording challenge attempts")
