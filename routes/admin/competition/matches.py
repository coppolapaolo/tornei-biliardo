# routes/admin/competition/matches.py
"""Match and trio operations for competitions."""

from flask import (
    request,
    jsonify,
)
from flask_login import current_user, login_required

from models.competition.services import GaraService
from utils import trio_manager_required

from . import competition_bp


# ============ GESTIONE TRII ============


@competition_bp.route("/trio/<int:trio_id>/add_rack", methods=["POST"])
@login_required
@trio_manager_required
def trio_add_rack(trio_id):
    """Aggiungi rack a partita trio"""
    try:
        winner_id = int(request.form["winner_id"])

        # Usa il service layer invece del direct database access
        result = GaraService.add_trio_rack(trio_id, winner_id)
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante aggiunta rack: {str(e)}"}), 500


@competition_bp.route("/trio/<int:trio_id>/remove_rack", methods=["POST"])
@login_required
@trio_manager_required
def trio_remove_rack(trio_id):
    """Rimuovi ultimo rack da partita trio (undo)"""
    try:
        # Usa il service layer
        result = GaraService.remove_trio_rack(trio_id, current_user.id)
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante rimozione rack: {str(e)}"}), 500


@competition_bp.route("/trio/<int:trio_id>/confirm", methods=["POST"])
@login_required
@trio_manager_required
def trio_confirm(trio_id):
    """Conferma il risultato del trio e completa la partita."""
    try:
        result = GaraService.confirm_trio_result(trio_id)
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante conferma risultato: {str(e)}"}), 500


@competition_bp.route("/trio/<int:trio_id>/forfeit", methods=["POST"])
@login_required
@trio_manager_required
def trio_forfeit(trio_id):
    """Handle player forfeit in trio match (admin endpoint)."""
    try:
        forfeiting_player_id = request.form.get("player_id", type=int)
        if not forfeiting_player_id:
            return jsonify({"error": "Player ID richiesto"}), 400

        result = GaraService.forfeit_trio(trio_id, forfeiting_player_id, current_user.id)
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante registrazione forfait: {str(e)}"}), 500


@competition_bp.route("/trio/<int:trio_id>/reset", methods=["POST"])
@login_required
@trio_manager_required
def trio_reset(trio_id):
    """Reset completo trio"""
    try:
        # Usa il service layer invece del direct database access
        GaraService.reset_trio(trio_id)
        return jsonify({"success": True, "message": "Trio resettato con successo"})

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 500
    except Exception as e:
        return jsonify({"error": f"Errore durante reset trio: {str(e)}"}), 500


@competition_bp.route("/trio/<int:trio_id>/set_result", methods=["POST"])
@login_required
@trio_manager_required
def trio_set_result(trio_id):
    """Imposta risultato diretto per trio (Quick Result)"""
    try:
        player1_racks = int(request.form["player1_racks"])
        player2_racks = int(request.form["player2_racks"])
        player3_racks = int(request.form["player3_racks"])

        result = GaraService.set_trio_result(
            trio_id, player1_racks, player2_racks, player3_racks
        )

        # Aggiorna progressione turno
        from models.match.models import TrioMatch

        trio = TrioMatch.query.get(trio_id)
        if trio and trio.match and trio.match.gara_id:
            GaraService.update_round_progression(trio.match.gara_id)

        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante impostazione risultato: {str(e)}"}), 500
