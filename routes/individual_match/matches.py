"""Match scoring and lifecycle routes for individual matches."""

from flask import (
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
from flask_login import current_user
from datetime import datetime

from models import IndividualMatch
from models.individual_match.services import IndividualMatchService
from models.user.permissions import RoleRequirement

from . import individual_match_bp


@individual_match_bp.route("/matches")
@RoleRequirement.player_or_director_required
def match_list():
    """List individual matches for current user."""
    try:
        matches = IndividualMatchService.get_user_matches(current_user.id)
        from flask import render_template

        return render_template("individual_match/matches.html", matches=matches)
    except Exception as e:
        flash(f"Error loading matches: {str(e)}", "danger")
        return redirect(url_for("individual_match.dashboard"))


@individual_match_bp.route("/matches/<int:match_id>")
@RoleRequirement.player_or_director_required
def match_detail(match_id):
    """View individual match details and submit results."""
    try:
        match = IndividualMatch.query.get_or_404(match_id)

        # Verify user is part of this match
        if current_user.id not in (match.player1_id, match.player2_id):
            flash("Access denied to this match.", "danger")
            return redirect(url_for("individual_match.match_list"))

        from flask import render_template

        return render_template("individual_match/match_detail.html", match=match)

    except Exception as e:
        flash(f"Error loading match: {str(e)}", "danger")
        return redirect(url_for("individual_match.match_list"))


@individual_match_bp.route("/matches/<int:match_id>/start", methods=["POST"])
@RoleRequirement.player_or_director_required
def start_match(match_id):
    """Start an individual match."""
    try:
        IndividualMatchService.start_match(match_id, current_user.id)

        # Emit SSE event for real-time sync
        from routes.sse import emit_individual_match_event

        emit_individual_match_event(
            match_id, "match_started", {"started_by": current_user.id}
        )

        if request.is_json:
            return jsonify({"success": True, "message": "Match started successfully"})
        else:
            flash("Match started successfully!", "success")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Error starting match: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/racks/add", methods=["POST"])
@RoleRequirement.player_or_director_required
def add_rack(match_id):
    """Add a rack for a player (new simplified UX)."""
    try:
        data = request.get_json() if request.is_json else request.form

        # data.get + guard: data["winner_id"] mancante era KeyError → 500.
        if data.get("winner_id") is None:
            raise ValueError("Campo winner_id mancante")
        winner_id = int(data["winner_id"])

        rack = IndividualMatchService.add_rack_for_player(
            match_id=match_id,
            user_id=current_user.id,
            winner_id=winner_id,
        )

        # Emit SSE event for real-time sync
        from routes.sse import emit_individual_match_event
        from models.base import db

        match = IndividualMatch.query.get(match_id)
        db.session.refresh(match)  # Force fresh state after @transactional commit
        emit_individual_match_event(
            match_id,
            "rack_updated",
            {
                "action": "added",
                "rack_number": rack.rack_number,
                "winner_id": winner_id,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "is_ready_for_validation": match.is_ready_for_validation(),
                "added_by": current_user.id,
            },
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "rack_number": rack.rack_number,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
                    "is_ready_for_validation": match.is_ready_for_validation(),
                }
            )
        else:
            flash("Rack aggiunto!", "success")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Errore: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/racks/remove", methods=["POST"])
@RoleRequirement.player_or_director_required
def remove_rack(match_id):
    """Remove last rack for a player (new simplified UX)."""
    try:
        data = request.get_json() if request.is_json else request.form

        # data.get + guard: data["player_id"] mancante era KeyError → 500.
        if data.get("player_id") is None:
            raise ValueError("Campo player_id mancante")
        player_id = int(data["player_id"])

        IndividualMatchService.remove_rack_for_player(
            match_id=match_id,
            user_id=current_user.id,
            player_id=player_id,
        )

        # Emit SSE event for real-time sync
        from routes.sse import emit_individual_match_event
        from models.base import db

        match = IndividualMatch.query.get(match_id)
        db.session.refresh(match)  # Force fresh state after @transactional commit
        emit_individual_match_event(
            match_id,
            "rack_updated",
            {
                "action": "removed",
                "player_id": player_id,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "is_ready_for_validation": match.is_ready_for_validation(),
                "removed_by": current_user.id,
            },
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
                    "is_ready_for_validation": match.is_ready_for_validation(),
                }
            )
        else:
            flash("Rack rimosso!", "success")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Errore: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/confirm", methods=["POST"])
@RoleRequirement.player_or_director_required
def confirm_result(match_id):
    """Confirm match result (new simplified UX)."""
    try:
        match = IndividualMatchService.confirm_match_result(
            match_id=match_id, user_id=current_user.id
        )

        # Emit SSE event for real-time sync
        from models.status_enum import MatchStatus
        from routes.sse import emit_individual_match_event

        # La conferma bilaterale porta lo status a VALIDATED (mai "completed"):
        # il confronto col letterale "completed" lasciava completed=False e
        # "In attesa dell'altro giocatore" anche a match appena chiuso.
        fully_confirmed = match.status.value == MatchStatus.VALIDATED.value

        event_type = "match_completed" if fully_confirmed else "result_confirmed"
        emit_individual_match_event(
            match_id,
            event_type,
            {
                "confirmed_by": current_user.id,
                "player1_confirmed": match.player1_confirmed,
                "player2_confirmed": match.player2_confirmed,
                "completed": fully_confirmed,
                "winner_id": match.winner_id,
            },
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "completed": fully_confirmed,
                    "player1_confirmed": match.player1_confirmed,
                    "player2_confirmed": match.player2_confirmed,
                    "message": (
                        "Match completato!"
                        if fully_confirmed
                        else "Risultato confermato!"
                    ),
                }
            )
        else:
            if fully_confirmed:
                flash("Match completato con successo!", "success")
            else:
                flash("Risultato confermato! In attesa dell'altro giocatore.", "info")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Errore: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/reject", methods=["POST"])
@RoleRequirement.player_or_director_required
def reject_result(match_id):
    """Reject match result - removes last rack (new simplified UX)."""
    try:
        match = IndividualMatchService.reject_match_result(
            match_id=match_id, user_id=current_user.id
        )

        # Emit SSE event for real-time sync
        from routes.sse import emit_individual_match_event

        emit_individual_match_event(
            match_id,
            "rack_updated",
            {
                "action": "rejected",
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "is_ready_for_validation": match.is_ready_for_validation(),
                "rejected_by": current_user.id,
            },
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
                    "message": "Ultimo rack rimosso. Continua a giocare.",
                }
            )
        else:
            flash("Risultato rifiutato. Ultimo rack rimosso.", "warning")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Errore: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/complete", methods=["POST"])
@RoleRequirement.player_or_director_required
def complete_match(match_id):
    """Complete an individual match - legacy route for backward compatibility."""
    try:
        data = request.get_json() if request.is_json else request.form

        # data.get + guard: data["winner_id"] mancante era KeyError → 500.
        if data.get("winner_id") is None:
            raise ValueError("Campo winner_id mancante")

        match = IndividualMatchService.complete_match(
            match_id=match_id,
            user_id=current_user.id,
            winner_id=int(data["winner_id"]),
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "winner_id": match.winner_id,
                    "final_score": f"{match.player1_score}-{match.player2_score}",
                    "message": "Match completed successfully",
                }
            )
        else:
            flash("Match completed successfully!", "success")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Error completing match: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/cancel", methods=["POST"])
@RoleRequirement.player_or_director_required
def cancel_match(match_id):
    """Cancel an individual match."""
    try:
        IndividualMatchService.cancel_match(match_id, current_user.id)

        if request.is_json:
            return jsonify({"success": True, "message": "Match cancelled successfully"})
        else:
            flash("Match cancelled successfully!", "success")
            return redirect(url_for("individual_match.match_list"))

    except ValueError as e:
        error_msg = f"Error cancelling match: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/update-times", methods=["POST"])
@RoleRequirement.player_or_director_required
def update_match_times(match_id):
    """Update individual match start and end times (proposer/admin only)."""
    try:
        data = request.get_json() if request.is_json else request.form
        if not data:
            return jsonify({"success": False, "error": "Dati mancanti"}), 400

        started_at_str = data.get("started_at")
        ended_at_str = data.get("ended_at")

        if not started_at_str and not ended_at_str:
            return (
                jsonify({"success": False, "error": "Specificare almeno un orario"}),
                400,
            )

        # Parse ISO datetime strings
        started_at = None
        ended_at = None
        if started_at_str:
            started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
        if ended_at_str:
            ended_at = datetime.fromisoformat(ended_at_str.replace("Z", "+00:00"))

        IndividualMatchService.update_times(
            match_id=match_id,
            started_at=started_at,
            ended_at=ended_at,
            user_id=current_user.id,
        )

        if request.is_json:
            return jsonify(
                {"success": True, "message": "Orari aggiornati con successo"}
            )
        else:
            flash("Orari aggiornati con successo!", "success")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = str(e)
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/forfeit", methods=["POST"])
@RoleRequirement.player_or_director_required
def forfeit_match(match_id):
    """Forfeit an individual match - current user loses, opponent wins."""
    from flask_babel import _

    try:
        match = IndividualMatchService.forfeit_match(
            match_id=match_id, user_id=current_user.id
        )

        # Emit SSE event for real-time sync
        from routes.sse import emit_individual_match_event

        emit_individual_match_event(
            match_id,
            "match_forfeited",
            {
                "forfeited_by": current_user.id,
                "winner_id": match.winner_id,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
            },
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "winner_id": match.winner_id,
                    "message": _("Forfait dichiarato"),
                }
            )
        else:
            flash(_("Forfait dichiarato. Match terminato."), "warning")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = str(e)
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/rematch")
@RoleRequirement.player_or_director_required
def rematch(match_id):
    """Nuovo match con lo stesso avversario: redirect a create_proposal
    con i parametri precompilati."""
    from flask_babel import _
    from models.base import utc_now

    match = IndividualMatch.query.get_or_404(match_id)

    # Verify user is part of this match
    if current_user.id not in (match.player1_id, match.player2_id):
        flash(_("Accesso negato a questo match."), "danger")
        return redirect(url_for("individual_match.match_list"))

    # Match must be completed
    if match.status.value not in ["completed", "validated"]:
        flash(_("Solo i match completati permettono di giocarne un altro."), "warning")
        return redirect(url_for("individual_match.match_detail", match_id=match_id))

    # Determine opponent
    opponent_id = (
        match.player2_id if current_user.id == match.player1_id else match.player1_id
    )

    # Build pre-fill parameters
    params = {
        "rematch": "true",
        "opponent_id": opponent_id,
        "location": match.location or "",
        "discipline": match.discipline or "palla_8",
        "distance": match.distance or 5,
        "is_race_to": "true" if match.is_race_to else "false",
        "break_rule": match.break_rule or "alternate",
    }

    # Add billiard_hall_id if present
    if match.billiard_hall_id:
        params["billiard_hall_id"] = match.billiard_hall_id

    # match_format: senza, create_proposal assume "single" e il rematch di
    # un multi-set/free diventava un single race-to-5.
    if match.distance is None:
        params["match_format"] = "free"
    elif getattr(match, "is_multi_set", False):
        params["match_format"] = "multi"
    else:
        params["match_format"] = "single"

    # Multi-set parameters if present
    if getattr(match, "is_multi_set", False):
        params["is_multi_set"] = "true"
        params["set_distance"] = match.distance or 5  # rack per set
        if getattr(match, "match_distance", None):
            params["match_distance"] = match.match_distance
        if getattr(match, "is_race_to_sets", None) is not None:
            params["is_race_to_sets"] = "true" if match.is_race_to_sets else "false"

    # Set scheduled_at to now (local time approximation)
    now = utc_now()
    params["scheduled_at"] = now.strftime("%Y-%m-%dT%H:%M")
    params["expires_hours"] = "0"  # 0 means "Never" (immediate match)

    return redirect(url_for("individual_match.create_proposal", **params))
