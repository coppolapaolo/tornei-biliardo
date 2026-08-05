"""Multi-set match operations (start set, add/remove rack within sets)."""

from flask import (
    request,
    jsonify,
)
from flask_login import login_required

from models import Match
from utils import match_manager_required
from routes.sse import emit_gara_event
from utils.route_helpers import get_or_ajax_404, safe_json_error

from . import match_bp


@match_bp.route("/<int:match_id>/start-next-set", methods=["POST"])
@login_required
@match_manager_required
def start_next_set(match_id):
    """Start the next set in a multi-set match.

    Creates a new Set record and transitions it to 'playing' status.
    If no sets exist yet, creates the first set.

    Response JSON:
        Success: {"success": true, "set_number": 2, "message": "Set 2 iniziato"}
        Error: {"success": false, "error": "..."}
    """
    from models.match.services import MatchService

    try:
        match = get_or_ajax_404(Match, match_id, "Match")

        if not match.is_multi_set:
            return jsonify({"success": False, "error": "Match non è multi-set"}), 400

        # Start next set
        new_set = MatchService.start_next_set(match_id)

        return jsonify(
            {
                "success": True,
                "set_number": new_set.set_number,
                "message": f"Set {new_set.set_number} iniziato",
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "starting set")


@match_bp.route("/<int:match_id>/set/add_rack", methods=["POST"])
@login_required
@match_manager_required
def add_set_rack(match_id):
    """Add a rack to the current set in a multi-set match.

    Request form:
        winner_id: int - ID of player who won the rack

    Response JSON:
        Success: {"success": true, "rack_number": 3, "set_score": "2-1"}
        Error: {"success": false, "error": "..."}
    """
    from models.match.services import MatchService

    try:
        winner_id = int(request.form["winner_id"])

        match = get_or_ajax_404(Match, match_id, "Match")

        if not match.is_multi_set:
            return jsonify({"success": False, "error": "Match non è multi-set"}), 400

        # Add rack to current set
        rack = MatchService.add_rack_to_current_set(match_id, winner_id)

        # Get updated set state
        current_set = match.get_current_set()
        set_score = (
            f"{current_set.player1_racks}-{current_set.player2_racks}"
            if current_set
            else "0-0"
        )

        # Emit SSE event for gara detail page polling
        if match.gara_id:
            emit_gara_event(
                match.gara_id,
                "match_updated",
                {
                    "match_id": match_id,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
                    "set_score": set_score,
                },
            )

        return jsonify(
            {
                "success": True,
                "rack_number": rack.rack_number,
                "set_score": set_score,
                "set_completed": (
                    current_set.status == "completed" if current_set else False
                ),
                "match_completed": match.status == "completed",
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "adding rack to set")


@match_bp.route("/<int:match_id>/set/remove_rack", methods=["POST"])
@login_required
@match_manager_required
def remove_set_rack(match_id):
    """Remove the last rack from the current set in a multi-set match.

    Request form:
        player_id: int - ID of player whose rack to remove (unused, removes last)

    Response JSON:
        Success: {"success": true, "set_score": "1-1"}
        Error: {"success": false, "error": "..."}
    """
    from models.match.services import MatchService

    try:
        match = get_or_ajax_404(Match, match_id, "Match")

        if not match.is_multi_set:
            return jsonify({"success": False, "error": "Match non è multi-set"}), 400

        # Remove last rack from current set
        MatchService.remove_rack_from_current_set(match_id)

        # Get updated set state
        current_set = match.get_current_set()
        set_score = (
            f"{current_set.player1_racks}-{current_set.player2_racks}"
            if current_set
            else "0-0"
        )

        # Emit SSE event for gara detail page polling
        if match.gara_id:
            emit_gara_event(
                match.gara_id,
                "match_updated",
                {
                    "match_id": match_id,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
                    "set_score": set_score,
                },
            )

        return jsonify({"success": True, "set_score": set_score})

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "removing rack from set")
