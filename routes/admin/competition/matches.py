# routes/admin/competition/matches.py
"""Match and trio operations for competitions."""

from flask import (
    request,
    jsonify,
)
from flask_login import login_required

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
