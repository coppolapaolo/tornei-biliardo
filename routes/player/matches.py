# routes/player/matches.py
"""Match operations and rack management routes."""

from flask import request, jsonify
from flask_babel import _
from flask_login import login_required, current_user

from models import db, Match
from models.match.services import MatchService
from models.competition.trio_service import TrioMatchService
from models.exceptions import http_status_for_exception
from utils import match_player_required, trio_player_required
from utils.route_helpers import safe_json_error

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

        # Come nel segnapunti a due (`add_rack_for_player`): il permesso si
        # guarda **su questa gara**, non sul ruolo globale.
        from models.user.permissions import PermissionChecker

        dirige_la_gara = bool(
            match.gara_id
            and PermissionChecker.can_manage_competition(current_user, match.gara_id)
        )

        # Use the service layer (same as admin)
        result = TrioMatchService.add_trio_rack(
            trio_id,
            winner_id,
            added_by_id=current_user.id,
            authoritative=dirige_la_gara,
        )
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "player add rack")


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
        result = TrioMatchService.remove_trio_rack(trio_id, current_user.id)
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "player remove rack")


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
        result = TrioMatchService.confirm_trio_result_by_player(
            trio_id, current_user.id
        )
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "player confirm result")


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

        # IDOR fix: un giocatore può forfeitare SOLO se stesso. La route player
        # è per l'auto-forfeit; il forfeit per conto di altri ha la sua route
        # admin (routes/admin/competition/matches.py). Se la form indica un
        # player_id diverso da current_user → 403, altrimenti si forfeita sé.
        requested_player_id = request.form.get("player_id", type=int)
        if requested_player_id and requested_player_id != current_user.id:
            return (
                jsonify({"error": _("Puoi ritirare solo te stesso da questo trio")}),
                403,
            )
        forfeiting_player_id = current_user.id

        # Use the service layer
        result = TrioMatchService.forfeit_trio(
            trio_id, forfeiting_player_id, current_user.id
        )
        return jsonify(result)

    except ValueError as ve:
        # Un turno superato e' un conflitto, 409: il resto resta 400.
        return jsonify({"error": str(ve)}), http_status_for_exception(ve)
    except Exception as e:
        return safe_json_error(e, "player forfeit")


# ============ SIMPLIFIED UX - Match (Tournament) Rack Management ============


@player_bp.route("/match/<int:match_id>/racks/add", methods=["POST"])
@login_required
@match_player_required
def add_rack_simplified(match_id):
    """Add rack for player (new simplified UX for tournament matches)"""
    winner_id = request.form.get("winner_id", type=int)

    if not winner_id:
        return jsonify({"error": "Winner ID is required"}), 400

    # Chi dirige la gara e ci gioca resta su questo segnapunti — è quello
    # comodo da usare al tavolo, e il flusso player è la scelta giusta dopo
    # l'issue #66. Ma il suo punteggio non ha bisogno della firma di nessuno:
    # è già quello ufficiale. Il permesso si guarda **su questa gara**, non
    # sul ruolo globale, che è esattamente la distinzione persa in #66.
    from models.user.permissions import PermissionChecker

    match_prima = db.session.get(Match, match_id)
    dirige_la_gara = bool(
        match_prima
        and match_prima.gara_id
        and PermissionChecker.can_manage_competition(current_user, match_prima.gara_id)
    )

    try:
        rack = MatchService.add_rack_for_player(
            match_id=match_id,
            user_id=current_user.id,
            winner_id=winner_id,
            authoritative=dirige_la_gara,
        )

        # Get updated match
        match = db.session.get(Match, match_id)

        # Emit event AFTER transaction committed (for real-time updates)
        from routes.sse import emit_match_event, emit_gara_event

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

        # Also emit to gara scope for directors watching gara_detail
        if match.gara_id:
            emit_gara_event(
                match.gara_id,
                "match_updated",
                {
                    "match_id": match_id,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
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
        return safe_json_error(e, "player match operation")


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
        from routes.sse import emit_match_event, emit_gara_event

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

        # Also emit to gara scope for directors watching gara_detail
        if match.gara_id:
            emit_gara_event(
                match.gara_id,
                "match_updated",
                {
                    "match_id": match_id,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
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
        return safe_json_error(e, "player match operation")


# ============ ADR-056 - Acchito e runout (Match di gara) ============


def _lettera(stato: dict) -> str:
    """La sigla sul trattino: ``B`` se aveva aperto lui, ``R`` se ha risposto.

    Resta in inglese di proposito: nel regolamento FIBiS non esiste un termine
    italiano per run-out o break and run, e «serie» è già occupato — indica il
    **gruppo** di bilie assegnato («la propria serie»). Vedi ADR-056.
    """
    if not stato.get("is_run_out"):
        return ""
    return "B" if stato.get("is_break_and_run") else "R"


@player_bp.route("/match/<int:match_id>/lag", methods=["POST"])
@login_required
@match_player_required
def register_lag(match_id):
    """Esito dell'acchito: chi ha vinto, e chi esegue il tiro di apertura.

    Due campi e non uno: chi vince l'acchito **sceglie chi** apre, e può
    scegliere l'avversario («Regole generali pool» 1.2). Dedurre il secondo
    dal primo sarebbe riscrivere il regolamento.
    """
    lag_winner_id = request.form.get("lag_winner_id", type=int)
    first_break_player_id = request.form.get("first_break_player_id", type=int)

    if not lag_winner_id or not first_break_player_id:
        return jsonify({"error": _("Scegli uno dei due giocatori.")}), 400

    try:
        MatchService.register_lag(
            match_id=match_id,
            lag_winner_id=lag_winner_id,
            first_break_player_id=first_break_player_id,
        )
        return jsonify({"success": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return safe_json_error(e, "player match lag")


@player_bp.route("/match/<int:match_id>/racks/<int:rack_id>/runout", methods=["POST"])
@login_required
@match_player_required
def toggle_run_out(match_id, rack_id):
    """Marca (o smarca) un triangolo come chiuso in una visita.

    È il trattino di progresso, non un pulsante: il runout è un evento raro su
    una superficie fatta per un gesto frequente, e un bersaglio permanente
    sbaglierebbe in un verso o nell'altro (ADR-056).
    """
    try:
        stato = MatchService.toggle_run_out(match_id=match_id, rack_id=rack_id)
        return jsonify({"success": True, "letter": _lettera(stato), **stato})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return safe_json_error(e, "player match runout")


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
        from routes.sse import emit_match_event, emit_gara_event

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

        # Also emit to gara scope for directors watching gara_detail
        if match.gara_id:
            is_completed = match.player1_confirmed and match.player2_confirmed
            event_type = "match_completed" if is_completed else "match_updated"
            emit_gara_event(
                match.gara_id,
                event_type,
                {
                    "match_id": match_id,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
                    "winner_id": match.winner_id,
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
        return safe_json_error(e, "player match operation")


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
        from routes.sse import emit_match_event, emit_gara_event

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

        # Also emit to gara scope for directors watching gara_detail
        if match.gara_id:
            emit_gara_event(
                match.gara_id,
                "match_updated",
                {
                    "match_id": match_id,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
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
        return safe_json_error(e, "player match operation")


@player_bp.route("/match/<int:match_id>/forfeit", methods=["POST"])
@login_required
@match_player_required
def forfeit_match(match_id):
    """Forfeit match - current user loses automatically"""
    try:
        match = MatchService.forfeit_match(match_id=match_id, user_id=current_user.id)

        # Emit event AFTER transaction committed (for real-time updates)
        from routes.sse import emit_match_event, emit_gara_event

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

        # Also emit to gara scope for directors watching gara_detail
        if match.gara_id:
            emit_gara_event(
                match.gara_id,
                "match_completed",
                {
                    "match_id": match_id,
                    "winner_id": match.winner_id,
                    "forfeit": True,
                },
            )

        return jsonify(
            {
                "success": True,
                "status": match.status,
                "winner_id": match.winner_id,
                "message": (
                    f"Forfait dichiarato. {match.winner.username} "
                    f"vince per forfait."
                ),
            }
        )

    except ValueError as e:
        # Un turno superato e' un conflitto, 409: il resto resta 400.
        return jsonify({"error": str(e)}), http_status_for_exception(e)
    except Exception as e:
        return safe_json_error(e, "player match operation")
