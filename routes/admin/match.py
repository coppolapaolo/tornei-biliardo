# routes/admin/match.py
"""Match and rack management blueprint for admin interface."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required

from models import (
    Match,
    Rack,
)
from utils import (
    match_manager_required,
    rack_manager_required,
)
from models.match.services import MatchService, RackService, MatchResultService
from models.status_enum import MatchStatus

# Match management blueprint
match_bp = Blueprint("match", __name__)


@match_bp.route("/<int:match_id>")
@login_required
@match_manager_required
def match_detail(match_id):
    """Dettaglio partita per admin"""
    match = Match.query.get_or_404(match_id)
    racks = Rack.query.filter_by(match_id=match_id).order_by(Rack.rack_number).all()

    return render_template("match_detail.html", match=match, racks=racks)


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
    try:
        player1_score = int(request.form["player1_score"])
        player2_score = int(request.form["player2_score"])
        
        # Usa il service layer invece del direct database access
        RackService.set_match_result_direct(match_id, player1_score, player2_score)
        
        flash("Risultato impostato con successo!")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))
        
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))
    except Exception as e:
        flash(f"Errore durante l'impostazione del risultato: {str(e)}", "error")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))


@match_bp.route("/<int:match_id>/reset", methods=["POST"])
@login_required
@match_manager_required
def reset_match(match_id):
    """Reset completo di una partita (admin)"""
    try:
        # Usa il service layer invece del direct database access
        RackService.reset_match_complete(match_id)
        
        flash("Partita resettata con successo!")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))
        
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))
    except Exception as e:
        flash(f"Errore durante il reset: {str(e)}", "error")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))


# ============ GESTIONE RACK ADMIN ============


@match_bp.route("/rack/<int:rack_id>/remove", methods=["POST"])
@login_required
@rack_manager_required
def remove_rack_admin(rack_id):
    """Rimuovi un rack (admin)"""
    try:
        # Usa il service layer invece del direct database access
        result = RackService.remove_rack_admin(rack_id)
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