"""Multi-set match operations (start set, add/remove rack within sets)."""

from flask import (
    request,
    jsonify,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models import Match, db
from models.status_enum import MatchStatus
from utils import match_manager_required
from routes.sse import emit_gara_event
from utils.card_partita import (
    annuncia_punteggio,
    rifiuto_del_dominio,
    rifiuto_punteggio_card,
)
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
        # Dalla card del direttore (2026-09-13): stesse guardie degli stepper.
        rifiuto = rifiuto_punteggio_card(match)
        if rifiuto is not None:
            return rifiuto

        # Start next set
        new_set = MatchService.start_next_set(match_id)
        annuncia_punteggio(match, current_user.id, set_number=new_set.set_number)

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
                    current_set.status == MatchStatus.CLOSED_UNILATERALLY.value
                    if current_set
                    else False
                ),
                "match_completed": (
                    match.status == MatchStatus.CLOSED_UNILATERALLY.value
                ),
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


@match_bp.route("/<int:match_id>/set/punteggio", methods=["POST"])
@login_required
@match_manager_required
def set_punteggio(match_id):
    """I triangoli del set in corso dagli stepper della card: risponde in JSON.

    La card della partita a set mostra in alto i set vinti, in sola lettura, e
    sotto gli stepper del set che si gioca. Stesse guardie di
    `punteggio_partita` (chiusa o turno bloccato 409, oltre la distanza del set
    400); il set si chiude alla sua distanza e la partita ai set.
    """
    from models.match.services import MatchService

    match = get_or_ajax_404(Match, match_id, "Match")
    if not match.is_multi_set:
        errore = _("Questa non è una partita a set.")
        return jsonify({"success": False, "error": str(errore)}), 400
    try:
        player1_racks = int(request.form["player1_racks"])
        player2_racks = int(request.form["player2_racks"])
    except (KeyError, ValueError):
        return (
            jsonify({"success": False, "error": str(_("Punteggio non valido."))}),
            400,
        )
    rifiuto = rifiuto_punteggio_card(
        match, _("La partita è chiusa: si cambia dal segnapunti.")
    )
    if rifiuto is not None:
        return rifiuto

    try:
        corrente = MatchService.set_current_set_racks(
            match_id, player1_racks, player2_racks
        )
    except ValueError as ve:
        return rifiuto_del_dominio(ve)

    match = db.session.get(Match, match_id)
    assert match is not None
    finita = MatchStatus.is_finished(match.status)
    if finita and match.gara_id:
        from models.competition.round_service import RoundService

        RoundService.update_round_progression(match.gara_id)
    annuncia_punteggio(match, current_user.id, set_number=corrente.set_number)
    return jsonify(
        {
            "success": True,
            "match_id": match_id,
            "punti": [corrente.player1_racks, corrente.player2_racks],
            "set_vinti": [match.player1_score, match.player2_score],
            "set_chiuso": corrente.status != MatchStatus.PLAYING.value,
            "finished": finita,
            "at_distance": False,
        }
    )
