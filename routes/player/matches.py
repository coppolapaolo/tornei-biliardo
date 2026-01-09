# routes/player/matches.py
"""Match operations and rack management routes."""

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.exceptions import abort

from models import db, Match, Rack
from models.status_enum import MatchStatus
from models.match.services import MatchService, RackService
from models.competition.services import GaraService
from models.transaction.manager import transactional
from utils import match_player_required, trio_player_required, rack_player_required

from . import player_bp


# ============ MATCH RACK OPERATIONS ============


@player_bp.route("/match/<int:match_id>/report_rack", methods=["POST"])
@login_required
@match_player_required
def report_rack_result(match_id):
    """Segnala risultato rack"""
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)

    winner_id = int(request.form["winner_id"])

    # Verifica che il vincitore sia uno dei giocatori della partita
    if winner_id not in [match.player1_id, match.player2_id]:
        flash("Giocatore non valido.", "error")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))

    # Usa il service layer invece del direct database access
    try:
        result = RackService.add_rack_with_score_update(
            match_id=match_id,
            winner_id=winner_id,
            reported_by_id=current_user.id,
            validated_by_admin=False,  # Player report, needs admin validation
        )
        return jsonify(result)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante aggiunta rack: {str(e)}"}), 500


@player_bp.route("/match/<int:match_id>/add_rack", methods=["POST"])
@login_required
@match_player_required
def add_rack(match_id):
    """Aggiunge un rack alla partita (stessa logica di report_rack_result)"""
    match = db.session.get(Match, match_id)
    if match is None:
        return jsonify({"error": "Partita non trovata"}), 404

    winner_id = int(request.form["winner_id"])

    # Verifica che il vincitore sia uno dei giocatori della partita
    if winner_id not in [match.player1_id, match.player2_id]:
        return jsonify({"error": "Giocatore non valido"}), 400

    # Usa il service layer
    try:
        result = RackService.add_rack_with_score_update(
            match_id=match_id,
            winner_id=winner_id,
            reported_by_id=current_user.id,
            validated_by_admin=False,  # Player report, needs admin validation
        )
        return jsonify(result)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante aggiunta rack: {str(e)}"}), 500


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
    """Confirm trio match result (player endpoint)"""
    try:
        # Get the trio match
        match = db.session.get(Match, match_id)
        if not match or not match.trio_match:
            return jsonify({"error": "Trio match non trovato"}), 404

        trio_id = match.trio_match.id

        # Use the service layer
        result = GaraService.confirm_trio_result(trio_id)
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


# ============ RACK CONFIRMATION/REMOVAL SYSTEM ============


@player_bp.route("/rack/<int:rack_id>/remove", methods=["POST"])
@login_required
@transactional(domain="match")
def remove_rack(rack_id):
    """Rimuovi un rack inserito per errore"""
    rack = Rack.query.get_or_404(rack_id)
    match = rack.match

    # Verifica autorizzazioni
    if current_user.id not in [match.player1_id, match.player2_id]:
        return jsonify({"error": "Non autorizzato"}), 403

    # Verifica che possa essere rimosso
    if not rack.can_be_removed(current_user.id):
        return jsonify({"error": "Impossibile rimuovere questo rack"}), 400

    # Salva il vincitore per aggiornare il punteggio
    winner_id = rack.winner_id

    # Rimuovi il rack
    db.session.delete(rack)

    # Aggiorna il punteggio del match
    if winner_id == match.player1_id:
        match.player1_score = max(0, match.player1_score - 1)
    else:
        match.player2_score = max(0, match.player2_score - 1)

    # Se il match era completato, rimettilo in playing
    if match.status == MatchStatus.COMPLETED.value:
        MatchService.to_playing(match.id)
        match.winner_id = None

    return jsonify(
        {
            "success": True,
            "message": "Rack rimosso",
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "status": match.status,
        }
    )


@player_bp.route("/rack/<int:rack_id>/confirm", methods=["POST"])
@login_required
@transactional(domain="match")
def confirm_rack(rack_id):
    """Conferma un rack inserito dall'altro giocatore"""
    rack = Rack.query.get_or_404(rack_id)
    match = rack.match

    # Verifica autorizzazioni
    if current_user.id not in [match.player1_id, match.player2_id]:
        return jsonify({"error": "Non autorizzato"}), 403

    # Verifica che possa essere confermato
    if not rack.can_be_confirmed(current_user.id):
        return jsonify({"error": "Impossibile confermare questo rack"}), 400

    # Conferma il rack
    rack.confirmed_by_player = True

    return jsonify({"success": True, "message": "Rack confermato"})


@player_bp.route("/rack/<int:rack_id>/unconfirm", methods=["POST"])
@login_required
@transactional(domain="match")
def unconfirm_rack(rack_id):
    """Rimuovi conferma da un rack"""
    rack = Rack.query.get_or_404(rack_id)
    match = rack.match

    # Verifica autorizzazioni
    if current_user.id not in [match.player1_id, match.player2_id]:
        return jsonify({"error": "Non autorizzato"}), 403

    # Verifica che possa rimuovere la conferma
    if not rack.can_remove_confirmation(current_user.id):
        return jsonify({"error": "Impossibile rimuovere la conferma"}), 400

    # Rimuovi la conferma
    rack.confirmed_by_player = False

    return jsonify({"success": True, "message": "Conferma rimossa"})


@player_bp.route("/rack/<int:rack_id>")
@login_required
@rack_player_required
def rack_detail(rack_id):
    """Dettaglio rack"""
    rack = db.session.get(Rack, rack_id)
    if rack is None:
        abort(404)

    return render_template("player/rack_detail.html", rack=rack)
