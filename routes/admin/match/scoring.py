"""Match scoring, validation, reset, and rack management routes."""

from flask import (
    request,
    redirect,
    url_for,
    flash,
    jsonify,
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
from models.kpi import track_match_played
from routes.sse import emit_gara_event
from utils.route_helpers import handle_service_action, get_or_ajax_404

from . import match_bp


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
        match = get_or_ajax_404(Match, match_id, "Match")

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
