"""Match detail, table assignment, and time management routes."""

from flask import (
    render_template,
    request,
    jsonify,
    abort,
)
from flask_login import login_required

from models import (
    Match,
    Rack,
    db,
)
from utils import match_manager_required
from models.match.services import MatchService
from models.status_enum import GaraStatus, MatchStatus
from models.matchmaking.configuration import MatchmakingStrategy
from routes.sse import emit_gara_event
from utils.route_helpers import safe_json_error

from . import match_bp


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

    match = db.get_or_404(Match, match_id)

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
                trio.player1_id,
                trio.player2_id,
                trio.player3_id,
            ]
        else:
            is_player_in_match = current_user.id in [match.player1_id, match.player2_id]

        # Se è player nel match, verifica che non abbia dato forfait per i controlli
        if is_player_in_match:
            from models.competition.withdraw_policy_service import WithdrawPolicyService

            has_forfeit = WithdrawPolicyService.is_player_forfeit(
                gara_id=match.gara_id, user_id=current_user.id
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
            gara_id=match.gara_id, user_id=match.player1_id
        )
    if match.player2:
        player2_is_forfeit = WithdrawPolicyService.is_player_forfeit(
            gara_id=match.gara_id, user_id=match.player2_id
        )

    # Accesso: gestore O player nel match (anche forfait: sola lettura consentita)
    if not (user_can_manage or is_player_in_match):
        abort(403)

    racks = Rack.query.filter_by(match_id=match_id).order_by(Rack.rack_number).all()

    # Get available challenges for this match if it's a Random gara
    available_challenges = []
    player_challenge_progress = {}
    if (
        match.gara
        and match.gara.matchmaking_strategy == MatchmakingStrategy.RANDOM.value
        and match.gara.status in [GaraStatus.PLAYING.value, GaraStatus.COMPLETED.value]
    ):

        from models.competition.gara_challenge_service import GaraChallengeService

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

    match_can_modify = True
    if match.gara_id:
        from models.competition.round_manager import AdvancedRoundManager

        match_can_modify, _modify_reason = AdvancedRoundManager.can_modify_match(
            match.id
        )

    # "L'azionabile va prima" (UI_CONVENTIONS): a punteggio definitivo - rack
    # massimi raggiunti, o match gia' chiuso - la prossima azione probabile e'
    # uscire dal match (torna alla gara / alla dashboard), quindi su mobile il
    # pulsante di ritorno sale in cima alla pagina.
    # Nei match multi-set player*_score conta i set, non i rack: li si considera
    # definitivi solo a match chiuso (is_at_distance ragiona sui rack).
    score_is_final = MatchStatus.is_finished(match.status) or (
        not match.is_multi_set and match.is_at_distance
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
        match_can_modify=match_can_modify,
        score_is_final=score_is_final,
    )


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
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Dati mancanti"}), 400

        start_time = data.get("start_time")
        end_time = data.get("end_time")

        if not start_time and not end_time:
            return (
                jsonify({"success": False, "error": "Specificare almeno un orario"}),
                400,
            )

        MatchService.update_times(
            match_id=match_id, start_time_str=start_time, end_time_str=end_time
        )

        return jsonify({"success": True, "message": "Orari aggiornati con successo"})

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "updating match times")


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

        # Call service layer (has @transactional, commits automatically)
        success, message, swapped_match_id = TableAssignmentService.reassign_table(
            match_id, new_table
        )

        if success:

            # Emit SSE events for polling updates
            match = db.session.get(Match, match_id)
            if match:
                event_type = "table_assigned" if new_table else "table_removed"

                # Emit to gara scope (for gara_detail page)
                if match.gara_id:
                    emit_gara_event(
                        match.gara_id,
                        "match_updated",
                        {
                            "match_id": match_id,
                            "table_assignment": match.table_assignment,
                            "status": match.status,
                            "event": event_type,
                        },
                    )

                # Emit to match scope (for match_detail page)
                from routes.sse import emit_match_event, emit_user_event

                emit_match_event(
                    match_id,
                    event_type,
                    {
                        "match_id": match_id,
                        "table_assignment": match.table_assignment,
                        "status": match.status,
                    },
                )

                # Emit to user scope (for player dashboard)
                for player_id in [match.player1_id, match.player2_id]:
                    if player_id:
                        emit_user_event(
                            player_id,
                            "match_table_changed",
                            {
                                "match_id": match_id,
                                "table_assignment": match.table_assignment,
                                "event": event_type,
                            },
                        )

                # If there was a swap, also emit for the swapped match
                if swapped_match_id:
                    swapped_match = db.session.get(Match, swapped_match_id)
                    if swapped_match:
                        if swapped_match.gara_id:
                            emit_gara_event(
                                swapped_match.gara_id,
                                "match_updated",
                                {
                                    "match_id": swapped_match_id,
                                    "table_assignment": swapped_match.table_assignment,
                                    "status": swapped_match.status,
                                    "event": "table_swapped",
                                },
                            )
                        emit_match_event(
                            swapped_match_id,
                            "table_swapped",
                            {
                                "match_id": swapped_match_id,
                                "table_assignment": swapped_match.table_assignment,
                                "status": swapped_match.status,
                            },
                        )
                        # Emit to users of swapped match
                        for player_id in [
                            swapped_match.player1_id,
                            swapped_match.player2_id,
                        ]:
                            if player_id:
                                emit_user_event(
                                    player_id,
                                    "match_table_changed",
                                    {
                                        "match_id": swapped_match_id,
                                        "table_assignment": (
                                            swapped_match.table_assignment
                                        ),
                                        "event": "table_swapped",
                                    },
                                )

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
        return safe_json_error(e, f"assigning table to match {match_id}")
