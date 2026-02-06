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
from models.kpi import track_match_played, track_result_submit
from routes.sse import emit_gara_event
from utils.route_helpers import handle_service_action

# Match management blueprint
match_bp = Blueprint("match", __name__)


@match_bp.route("/<int:match_id>")
@login_required
def match_detail(match_id):
    """
    Vista unificata per dettaglio match.
    Si adatta automaticamente in base ai permessi dell'utente:
    - Admin/Director con permessi → Vista gestionale completa
    - Player iscritto → Vista personale semplificata
    """
    from flask_login import current_user

    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)

    # Determina permessi (pattern da gara_detail)
    user_can_manage = False
    user_is_player = False

    # Track if user was player in match (for view access, even if forfeited)
    is_player_in_match = False

    if current_user.is_authenticated:
        # Check se può gestire la gara di questo match
        user_can_manage = current_user.can_manage_competition(match.gara_id)

        # Check se è player nel match (trio has 3 players, normal match has 2)
        if match.is_trio and match.trio_match:
            trio = match.trio_match
            is_player_in_match = current_user.id in [
                trio.player1_id, trio.player2_id, trio.player3_id
            ]
        else:
            is_player_in_match = current_user.id in [match.player1_id, match.player2_id]

        # Se è player nel match, verifica che non abbia dato forfait per i controlli
        if is_player_in_match:
            from models.competition.withdraw_policy_service import WithdrawPolicyService
            has_forfeit = WithdrawPolicyService.is_player_forfeit(
                gara_id=match.gara_id,
                user_id=current_user.id
            )
            # user_is_player = True solo se non ha dato forfait (per i controlli UI)
            user_is_player = not has_forfeit
        else:
            user_is_player = False

    # Pre-load forfait status to avoid N+1 queries in template
    player1_is_forfeit = False
    player2_is_forfeit = False
    if match.player1:
        from models.competition.withdraw_policy_service import WithdrawPolicyService
        player1_is_forfeit = WithdrawPolicyService.is_player_forfeit(
            gara_id=match.gara_id,
            user_id=match.player1_id
        )
    if match.player2:
        player2_is_forfeit = WithdrawPolicyService.is_player_forfeit(
            gara_id=match.gara_id,
            user_id=match.player2_id
        )

    # Verifica accesso: deve essere gestore O player nel match (anche se forfait per sola lettura)
    if not (user_can_manage or is_player_in_match):
        abort(403)

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
        user_can_manage=user_can_manage,
        user_is_player=user_is_player,
        available_challenges=available_challenges,
        player_challenge_progress=player_challenge_progress,
        player1_is_forfeit=player1_is_forfeit,
        player2_is_forfeit=player2_is_forfeit,
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

        # Emit SSE event for gara detail page polling
        match = db.session.get(Match, match_id)
        if match and match.gara_id:
            emit_gara_event(match.gara_id, "match_updated", {
                "match_id": match_id,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "winner_id": winner_id,
            })

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

    def action():
        player1_score = int(request.form["player1_score"])
        player2_score = int(request.form["player2_score"])

        RackService.set_match_result_direct(match_id, player1_score, player2_score)

        from models.match.models import Match
        from models.competition.services import GaraService

        match = Match.query.get(match_id)
        if match and match.gara_id:
            GaraService.update_round_progression(match.gara_id)

    return handle_service_action(
        action=action,
        redirect_url=url_for("admin.match.match_detail", match_id=match_id),
        success_message="Risultato impostato con successo!",
        error_prefix=None,
    )


@match_bp.route("/<int:match_id>/validate", methods=["POST"])
@login_required
@match_manager_required
def validate_match(match_id):
    """Valida risultato match e completa la partita (admin/director).

    Questa azione:
    - Imposta validated_by_admin = True
    - Completa il match (status = completed)
    - Libera il tavolo e lo assegna alla prima partita in attesa

    Note: Se winner_id non è impostato ma la distanza è raggiunta,
    determina automaticamente il vincitore in base al punteggio.
    Per match con pareggio (es. "Esattamente N"), accetta winner_id dalla request.
    """
    try:
        match = db.session.get(Match, match_id)
        if not match:
            return jsonify({"success": False, "error": "Match non trovato"}), 404

        # Verifica che il match non sia già completato
        from models.status_enum import MatchStatus
        if match.status in [MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value]:
            return jsonify({
                "success": False,
                "error": "Il match è già stato completato"
            }), 400

        # Se winner_id non è impostato, verifica se la distanza è raggiunta
        # e determina il vincitore in base al punteggio
        if not match.winner_id:
            # Verifica se il match ha raggiunto la distanza
            if not match.is_ready_for_validation():
                return jsonify({
                    "success": False,
                    "error": "Il match non ha ancora raggiunto la distanza"
                }), 400

            # Determina il vincitore in base al punteggio
            if match.player1_score > match.player2_score:
                match.winner_id = match.player1_id
            elif match.player2_score > match.player1_score:
                match.winner_id = match.player2_id
            # else: Pareggio - winner_id rimane NULL (consentito)

        # Verifica che il match non sia già completato (check duplicato rimosso)
        if match.status == MatchStatus.COMPLETED.value:
            return jsonify({
                "success": False,
                "error": "Il match è già stato completato"
            }), 400

        # Imposta validazione admin
        match.validated_by_admin = True

        # Completa il match
        from models.match.services import MatchService
        MatchService.to_completed(match_id)

        # Riassegna il tavolo alle partite in attesa
        old_table = match.table_assignment
        if old_table:
            from models.match.table_assignment_service import TableAssignmentService
            # IMPORTANTE: Rimuovi il tavolo dal match originale per evitare
            # che SQLAlchemy lo ripristini al commit
            match.table_assignment = None

            # Trova e assegna il tavolo al primo match in attesa
            waiting_match = TableAssignmentService.release_and_reassign_table(match_id)

            # Se c'è un match in attesa, transizionalo a PLAYING
            if waiting_match and waiting_match.status != "playing":
                try:
                    MatchService.to_playing(waiting_match.id)
                except Exception:
                    pass  # Table assignment è comunque stato fatto

        # Aggiorna progressione round
        from models.competition.services import GaraService
        gara_id = match.gara_id  # Store before commit
        if gara_id:
            GaraService.update_round_progression(gara_id)

        db.session.commit()

        # Emit SSE event for gara detail page polling
        if gara_id:
            emit_gara_event(gara_id, "match_completed", {
                "match_id": match_id,
                "winner_id": match.winner_id,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
            })

        track_match_played()  # KPI tracking
        flash("Risultato validato e partita completata!")
        return jsonify({
            "success": True,
            "message": "Risultato validato con successo",
            "match_completed": True
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": f"Errore durante la validazione: {str(e)}"
        }), 500


@match_bp.route("/<int:match_id>/reset", methods=["POST"])
@login_required
@match_manager_required
def reset_match(match_id):
    """Reset completo di una partita con validazione avanzata.

    Features:
    - Validazione round locking (blocca se round successivi esistono)
    - Ricalcolo automatico classifiche per turni affetti
    - Aggiornamento round progression (può decrementare current_round)
    - Gestione intelligente stato match basata su table_assignment
    - Conformità Use Case 8 specification

    Implementazione:
        Delega completamente ad AdvancedRoundManager per garantire
        consistenza con business rules e integrità dati.
    """
    from models.competition.round_manager import AdvancedRoundManager

    try:
        # Usa reset avanzato con validazione completa
        success, message = AdvancedRoundManager.reset_match_with_validation(match_id)

        if success:
            flash("Partita resettata con successo!")
        else:
            flash(message, "error")

        return redirect(url_for("admin.match.match_detail", match_id=match_id))

    except Exception as e:
        flash(f"Errore durante il reset: {str(e)}", "error")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))


@match_bp.route("/<int:match_id>/update-times", methods=["POST"])
@login_required
@match_manager_required
def update_match_times(match_id):
    """Update match start and end times (admin/director).

    Request JSON:
        {
            "start_time": "14:30",  // HH:MM format, optional
            "end_time": "16:45"     // HH:MM format, optional
        }

    Response JSON:
        Success: {"success": true, "message": "Orari aggiornati"}
        Error: {"success": false, "error": "..."}
    """
    from models.match.services import MatchService

    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Dati mancanti"}), 400

        start_time = data.get("start_time")
        end_time = data.get("end_time")

        if not start_time and not end_time:
            return jsonify({
                "success": False,
                "error": "Specificare almeno un orario"
            }), 400

        MatchService.update_times(
            match_id=match_id,
            start_time_str=start_time,
            end_time_str=end_time
        )

        return jsonify({
            "success": True,
            "message": "Orari aggiornati con successo"
        })

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Errore durante l'aggiornamento: {str(e)}"
        }), 500


@match_bp.route("/<int:match_id>/assign-table", methods=["POST"])
@login_required
@match_manager_required
def assign_table(match_id):
    """Assegna o cambia tavolo per un match con swap automatico.

    Request JSON:
        {
            "table_name": "1" | "A" | "Sala Rossa" | null
        }

    Response JSON:
        Success: {
            "success": true,
            "message": "Tavolo assegnato: ...",
            "swapped_match_id": 123 (optional)
        }
        Error: {
            "success": false,
            "message": "Errore: ..."
        }

    Business Rules:
        - Validazione round locking automatica
        - Swap automatico se tavolo occupato nello stesso round
        - Rimozione tavolo se table_name=null
    """
    import logging
    logger = logging.getLogger(__name__)

    from models import db
    from models.match.table_assignment_service import TableAssignmentService

    try:
        data = request.get_json()
        if not data:
            logger.error(f"No JSON data received for match {match_id}")
            return jsonify({"success": False, "message": "Dati mancanti"}), 400

        new_table = data.get("table_name")
        logger.info(
            f"Route assign_table called: match_id={match_id}, new_table={new_table}"
        )

        # Call service layer (has @transactional)
        success, message, swapped_match_id = TableAssignmentService.reassign_table(
            match_id, new_table
        )

        # CRITICAL: Explicit commit required for Flask routes
        # The @transactional decorator in reassign_table() creates a savepoint
        # within the Flask request's session, but doesn't commit the parent
        # transaction. Flask-SQLAlchemy requires explicit commit at route level.
        if success:
            db.session.commit()
            logger.info("Changes committed to database")

            # Emit SSE events for polling updates
            match = db.session.get(Match, match_id)
            if match:
                event_type = "table_assigned" if new_table else "table_removed"

                # Emit to gara scope (for gara_detail page)
                if match.gara_id:
                    emit_gara_event(match.gara_id, "match_updated", {
                        "match_id": match_id,
                        "table_assignment": match.table_assignment,
                        "status": match.status,
                        "event": event_type,
                    })

                # Emit to match scope (for match_detail page)
                from routes.sse import emit_match_event, emit_user_event
                emit_match_event(match_id, event_type, {
                    "match_id": match_id,
                    "table_assignment": match.table_assignment,
                    "status": match.status,
                })

                # Emit to user scope (for player dashboard)
                for player_id in [match.player1_id, match.player2_id]:
                    if player_id:
                        emit_user_event(player_id, "match_table_changed", {
                            "match_id": match_id,
                            "table_assignment": match.table_assignment,
                            "event": event_type,
                        })

                # If there was a swap, also emit for the swapped match
                if swapped_match_id:
                    swapped_match = db.session.get(Match, swapped_match_id)
                    if swapped_match:
                        if swapped_match.gara_id:
                            emit_gara_event(swapped_match.gara_id, "match_updated", {
                                "match_id": swapped_match_id,
                                "table_assignment": swapped_match.table_assignment,
                                "status": swapped_match.status,
                                "event": "table_swapped",
                            })
                        emit_match_event(swapped_match_id, "table_swapped", {
                            "match_id": swapped_match_id,
                            "table_assignment": swapped_match.table_assignment,
                            "status": swapped_match.status,
                        })
                        # Emit to users of swapped match
                        for player_id in [swapped_match.player1_id, swapped_match.player2_id]:
                            if player_id:
                                emit_user_event(player_id, "match_table_changed", {
                                    "match_id": swapped_match_id,
                                    "table_assignment": swapped_match.table_assignment,
                                    "event": "table_swapped",
                                })

        logger.info(
            f"Service returned: success={success}, message='{message}', "
            f"swapped_match_id={swapped_match_id}"
        )

        response = {"success": success, "message": message}

        if swapped_match_id:
            response["swapped_match_id"] = swapped_match_id

        status_code = 200 if success else 400
        logger.info(f"Returning response: {response} with status {status_code}")
        return jsonify(response), status_code

    except Exception as e:
        logger.error(
            f"Exception in assign_table for match {match_id}: {str(e)}", exc_info=True
        )
        db.session.rollback()  # Rollback on error
        return (
            jsonify({"success": False, "message": f"Errore: {str(e)}"}),
            500,
        )


# ============ GESTIONE RACK ADMIN ============


@match_bp.route("/rack/<int:rack_id>/remove", methods=["POST"])
@login_required
@rack_manager_required
def remove_rack_admin(rack_id):
    """Rimuovi un rack (admin)"""
    try:
        # Prima ottieni le info del match per il round update e SSE
        from models.competition.services import GaraService

        rack = Rack.query.get(rack_id)
        gara_id = None
        match_id = None
        if rack and rack.match:
            match_id = rack.match_id
            if rack.match.gara_id:
                gara_id = rack.match.gara_id

        # Usa il service layer invece del direct database access
        result = RackService.remove_rack_admin(rack_id)

        # Dopo aver rimosso il rack, controlla se ci sono turni da aggiornare
        if gara_id:
            GaraService.update_round_progression(gara_id)

            # Emit SSE event for gara detail page polling
            match = db.session.get(Match, match_id)
            if match:
                emit_gara_event(gara_id, "match_updated", {
                    "match_id": match_id,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
                })

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


# ────────────────────────────────────────────────────────────────────────────────
# MULTI-SET MATCH OPERATIONS
# ────────────────────────────────────────────────────────────────────────────────


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
        match = db.session.get(Match, match_id)
        if not match:
            return jsonify({"success": False, "error": "Match non trovato"}), 404

        if not match.is_multi_set:
            return jsonify({
                "success": False,
                "error": "Match non è multi-set"
            }), 400

        # Start next set
        new_set = MatchService.start_next_set(match_id)

        return jsonify({
            "success": True,
            "set_number": new_set.set_number,
            "message": f"Set {new_set.set_number} iniziato"
        })

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Errore durante l'avvio del set: {str(e)}"
        }), 500


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

        match = db.session.get(Match, match_id)
        if not match:
            return jsonify({"success": False, "error": "Match non trovato"}), 404

        if not match.is_multi_set:
            return jsonify({
                "success": False,
                "error": "Match non è multi-set"
            }), 400

        # Add rack to current set
        rack = MatchService.add_rack_to_current_set(match_id, winner_id)

        # Get updated set state
        current_set = match.get_current_set()
        set_score = f"{current_set.player1_racks}-{current_set.player2_racks}" if current_set else "0-0"

        # Emit SSE event for gara detail page polling
        if match.gara_id:
            emit_gara_event(match.gara_id, "match_updated", {
                "match_id": match_id,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "set_score": set_score,
            })

        return jsonify({
            "success": True,
            "rack_number": rack.rack_number,
            "set_score": set_score,
            "set_completed": current_set.status == "completed" if current_set else False,
            "match_completed": match.status == "completed"
        })

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Errore durante l'aggiunta del rack: {str(e)}"
        }), 500


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
        match = db.session.get(Match, match_id)
        if not match:
            return jsonify({"success": False, "error": "Match non trovato"}), 404

        if not match.is_multi_set:
            return jsonify({
                "success": False,
                "error": "Match non è multi-set"
            }), 400

        # Remove last rack from current set
        MatchService.remove_rack_from_current_set(match_id)

        # Get updated set state
        current_set = match.get_current_set()
        set_score = f"{current_set.player1_racks}-{current_set.player2_racks}" if current_set else "0-0"

        # Emit SSE event for gara detail page polling
        if match.gara_id:
            emit_gara_event(match.gara_id, "match_updated", {
                "match_id": match_id,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "set_score": set_score,
            })

        return jsonify({
            "success": True,
            "set_score": set_score
        })

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Errore durante la rimozione del rack: {str(e)}"
        }), 500


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
                            "error": (
                                "Specificare punteggio o risultato "
                                "pass/fail per tutti i tentativi"
                            ),
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
                "message": (
                    f"{len(recorded_attempts)} tentativo/i "
                    "registrato/i con successo"
                ),
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
