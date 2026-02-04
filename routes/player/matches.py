# routes/player/matches.py
"""Match operations and rack management routes."""

from flask import request, jsonify
from flask_login import login_required, current_user

from models import db, Match
from models.match.services import MatchService
from models.competition.services import GaraService
from utils import match_player_required, trio_player_required

from . import player_bp


# ============ TRIO MATCH RACK OPERATIONS ============


@player_bp.route("/match/<int:match_id>/trio/add_rack", methods=["POST"])
@login_required
@trio_player_required
def add_trio_rack(match_id):
    """Add rack to trio match (player endpoint)"""
    try:
        winner_id = int(request.form["winner_id"])

        # Get the trio match
        match = db.session.get(Match, match_id)
        if not match or not match.trio_match:
            return jsonify({"error": "Trio match non trovato"}), 404

        trio_id = match.trio_match.id

        # Use the service layer (same as admin)
        result = GaraService.add_trio_rack(trio_id, winner_id)
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante aggiunta rack: {str(e)}"}), 500


@player_bp.route("/match/<int:match_id>/trio/remove_rack", methods=["POST"])
@login_required
@trio_player_required
def remove_trio_rack(match_id):
    """Remove last rack from trio match (player endpoint - undo)"""
    try:
        # Get the trio match
        match = db.session.get(Match, match_id)
        if not match or not match.trio_match:
            return jsonify({"error": "Trio match non trovato"}), 404

        trio_id = match.trio_match.id

        # Use the service layer
        result = GaraService.remove_trio_rack(trio_id, current_user.id)
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante rimozione rack: {str(e)}"}), 500


@player_bp.route("/match/<int:match_id>/trio/confirm", methods=["POST"])
@login_required
@trio_player_required
def confirm_trio_result(match_id):
    """Confirm trio match result (player endpoint).

    Player confirmation requires all 3 players to confirm.
    Returns confirmation count and completion status.
    """
    try:
        # Get the trio match
        match = db.session.get(Match, match_id)
        if not match or not match.trio_match:
            return jsonify({"error": "Trio match non trovato"}), 404

        trio_id = match.trio_match.id

        # Use player-specific confirmation (requires all 3 to confirm)
        result = GaraService.confirm_trio_result_by_player(trio_id, current_user.id)
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante conferma risultato: {str(e)}"}), 500


@player_bp.route("/match/<int:match_id>/trio/forfeit", methods=["POST"])
@login_required
@trio_player_required
def forfeit_trio(match_id):
    """Handle player forfeit in trio match"""
    try:
        # Get the trio match
        match = db.session.get(Match, match_id)
        if not match or not match.trio_match:
            return jsonify({"error": "Trio match non trovato"}), 404

        trio_id = match.trio_match.id

        # Get forfeiting player from request
        forfeiting_player_id = request.form.get("player_id", type=int)
        if not forfeiting_player_id:
            # Default to current user if not specified
            forfeiting_player_id = current_user.id

        # Use the service layer
        result = GaraService.forfeit_trio(trio_id, forfeiting_player_id, current_user.id)
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante registrazione forfait: {str(e)}"}), 500


# ============ SIMPLIFIED UX - Match (Tournament) Rack Management ============


@player_bp.route("/match/<int:match_id>/racks/add", methods=["POST"])
@login_required
@match_player_required
def add_rack_simplified(match_id):
    """Add rack for player (new simplified UX for tournament matches)"""
    winner_id = request.form.get("winner_id", type=int)

    if not winner_id:
        return jsonify({"error": "Winner ID is required"}), 400

    try:
        rack = MatchService.add_rack_for_player(
            match_id=match_id, user_id=current_user.id, winner_id=winner_id
        )

        # Get updated match
        match = db.session.get(Match, match_id)

        # Emit event AFTER transaction committed (for real-time updates)
        from routes.sse import emit_match_event

        emit_match_event(
            match_id,
            "rack_added",
            {
                "match_id": match_id,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "winner_id": winner_id,
                "rack_number": rack.rack_number,
            },
        )

        return jsonify(
            {
                "success": True,
                "rack_id": rack.id,
                "rack_number": rack.rack_number,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "is_ready_for_validation": match.is_ready_for_validation(),
            }
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore: {str(e)}"}), 500


@player_bp.route("/match/<int:match_id>/racks/remove", methods=["POST"])
@login_required
@match_player_required
def remove_rack_simplified(match_id):
    """Remove last rack for player (new simplified UX for tournament matches)"""
    player_id = request.form.get("player_id", type=int)

    if not player_id:
        return jsonify({"error": "Player ID is required"}), 400

    try:
        MatchService.remove_rack_for_player(
            match_id=match_id, user_id=current_user.id, player_id=player_id
        )

        # Get updated match
        match = db.session.get(Match, match_id)

        # Emit event AFTER transaction committed (for real-time updates)
        from routes.sse import emit_match_event

        emit_match_event(
            match_id,
            "rack_removed",
            {
                "match_id": match_id,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "player_id": player_id,
            },
        )

        return jsonify(
            {
                "success": True,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "is_ready_for_validation": match.is_ready_for_validation(),
            }
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore: {str(e)}"}), 500


@player_bp.route("/match/<int:match_id>/confirm", methods=["POST"])
@login_required
@match_player_required
def confirm_match_result(match_id):
    """Confirm match result (new simplified UX for tournament matches)"""
    try:
        match = MatchService.confirm_match_result(
            match_id=match_id, user_id=current_user.id
        )

        # Emit event AFTER transaction committed (for real-time updates)
        from routes.sse import emit_match_event

        emit_match_event(
            match_id,
            "result_confirmed",
            {
                "match_id": match_id,
                "player1_confirmed": match.player1_confirmed,
                "player2_confirmed": match.player2_confirmed,
                "confirmed_by": current_user.id,
                "status": match.status,
            },
        )

        return jsonify(
            {
                "success": True,
                "player1_confirmed": match.player1_confirmed,
                "player2_confirmed": match.player2_confirmed,
                "status": match.status,
                "completed": (match.player1_confirmed and match.player2_confirmed),
            }
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore: {str(e)}"}), 500


@player_bp.route("/match/<int:match_id>/reject", methods=["POST"])
@login_required
@match_player_required
def reject_match_result(match_id):
    """Reject match result - removes last rack (new simplified UX)"""
    try:
        match = MatchService.reject_match_result(
            match_id=match_id, user_id=current_user.id
        )

        # Emit event AFTER transaction committed (for real-time updates)
        from routes.sse import emit_match_event

        emit_match_event(
            match_id,
            "rack_removed",
            {
                "match_id": match_id,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "rejected_by": current_user.id,
            },
        )

        return jsonify(
            {
                "success": True,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "player1_confirmed": match.player1_confirmed,
                "player2_confirmed": match.player2_confirmed,
                "is_ready_for_validation": match.is_ready_for_validation(),
            }
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore: {str(e)}"}), 500


@player_bp.route("/match/<int:match_id>/forfeit", methods=["POST"])
@login_required
@match_player_required
def forfeit_match(match_id):
    """Forfeit match - current user loses automatically"""
    try:
        match = MatchService.forfeit_match(match_id=match_id, user_id=current_user.id)

        # Emit event AFTER transaction committed (for real-time updates)
        from routes.sse import emit_match_event

        emit_match_event(
            match_id,
            "forfeit",
            {
                "match_id": match_id,
                "forfeit_by": current_user.id,
                "winner_id": match.winner_id,
                "status": match.status,
            },
        )

        return jsonify(
            {
                "success": True,
                "status": match.status,
                "winner_id": match.winner_id,
                "message": f"Forfait dichiarato. {match.winner.username} vince per forfait.",
            }
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore: {str(e)}"}), 500
