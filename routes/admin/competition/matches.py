# routes/admin/competition/matches.py
"""Match and trio operations for competitions."""

from flask import (
    request,
    jsonify,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models.base import db
from models.competition.trio_service import TrioMatchService
from models.exceptions import http_status_for_exception
from utils import trio_manager_required
from utils.card_partita import (
    annuncia_punteggio,
    rifiuto_del_dominio,
    rifiuto_punteggio_card,
)
from utils.route_helpers import safe_json_error

from . import competition_bp

# ============ GESTIONE TRII ============


@competition_bp.route("/trio/<int:trio_id>/add_rack", methods=["POST"])
@login_required
@trio_manager_required
def trio_add_rack(trio_id):
    """Aggiungi rack a partita trio"""
    try:
        winner_id = int(request.form["winner_id"])

        # Usa il service layer invece del direct database access.
        # `authoritative`: qui ci si arriva solo passando da
        # `@trio_manager_required`, quindi chi segna dirige per costruzione e
        # il suo punteggio non ha bisogno della firma dei giocatori.
        result = TrioMatchService.add_trio_rack(
            trio_id,
            winner_id,
            added_by_id=current_user.id,
            authoritative=True,
        )
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "trio add rack")


@competition_bp.route("/trio/<int:trio_id>/remove_rack", methods=["POST"])
@login_required
@trio_manager_required
def trio_remove_rack(trio_id):
    """Rimuovi ultimo rack da partita trio (undo)"""
    try:
        # Usa il service layer
        result = TrioMatchService.remove_trio_rack(trio_id, current_user.id)
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "trio remove rack")


@competition_bp.route("/trio/<int:trio_id>/confirm", methods=["POST"])
@login_required
@trio_manager_required
def trio_confirm(trio_id):
    """Conferma il risultato del trio e completa la partita."""
    try:
        result = TrioMatchService.confirm_trio_result(trio_id)
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "trio confirm")


@competition_bp.route("/trio/<int:trio_id>/forfeit", methods=["POST"])
@login_required
@trio_manager_required
def trio_forfeit(trio_id):
    """Handle player forfeit in trio match (admin endpoint)."""
    try:
        forfeiting_player_id = request.form.get("player_id", type=int)
        if not forfeiting_player_id:
            return jsonify({"error": "Player ID richiesto"}), 400

        result = TrioMatchService.forfeit_trio(
            trio_id, forfeiting_player_id, current_user.id
        )
        return jsonify(result)

    except ValueError as ve:
        # Un turno superato e' un conflitto, 409: il resto resta 400.
        return jsonify({"error": str(ve)}), http_status_for_exception(ve)
    except Exception as e:
        return safe_json_error(e, "trio forfeit")


@competition_bp.route("/trio/<int:trio_id>/reset", methods=["POST"])
@login_required
@trio_manager_required
def trio_reset(trio_id):
    """Reset completo trio"""
    try:
        # Usa il service layer invece del direct database access
        TrioMatchService.reset_trio(trio_id)
        return jsonify({"success": True, "message": "Trio resettato con successo"})

    except ValueError as ve:
        # Un rifiuto del dominio e' una risposta, non un guasto del server:
        # fino al 2026-09-13 qui usciva un 500.
        return (
            jsonify({"success": False, "error": str(ve)}),
            http_status_for_exception(ve),
        )
    except Exception as e:
        return safe_json_error(e, "trio reset")


def _trio_e_match(trio_id):
    from models.match.models import TrioMatch

    trio = db.session.get(TrioMatch, trio_id)
    return trio, (trio.match if trio else None)


@competition_bp.route("/trio/<int:trio_id>/set_result", methods=["POST"])
@login_required
@trio_manager_required
def trio_set_result(trio_id):
    """Imposta risultato diretto per trio (Quick Result)"""
    trio, match = _trio_e_match(trio_id)
    if match is not None:
        # Fino al 2026-09-13 questa route non guardava ne' il turno bloccato ne'
        # la partita chiusa: un risultato secco riscriveva un trio agli atti.
        rifiuto = rifiuto_punteggio_card(
            match,
            _("La partita è chiusa: per cambiarla azzerala dal segnapunti."),
        )
        if rifiuto is not None:
            return rifiuto
    try:
        player1_racks = int(request.form["player1_racks"])
        player2_racks = int(request.form["player2_racks"])
        player3_racks = int(request.form["player3_racks"])

        result = TrioMatchService.set_trio_result(
            trio_id, player1_racks, player2_racks, player3_racks
        )

        # Aggiorna progressione turno
        trio, match = _trio_e_match(trio_id)
        if match is not None and match.gara_id:
            from models.competition.round_service import RoundService

            RoundService.update_round_progression(match.gara_id)
            annuncia_punteggio(match, current_user.id, trio_id=trio_id)

        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "trio set result")


@competition_bp.route("/trio/<int:trio_id>/punteggio", methods=["POST"])
@login_required
@trio_manager_required
def trio_punteggio(trio_id):
    """I triangoli vinti dagli stepper della card del trio: risponde in JSON.

    Stesse guardie di `punteggio_partita`: partita chiusa o turno bloccato 409,
    punteggio impossibile 400. Al totale dei triangoli il trio si chiude e il
    tavolo si libera. La risposta dice anche quali «+» restano accesi
    (`piu`), perche' dipendono dall'ordine del girone e non solo dai numeri.
    """
    from models.match.trio_punteggio import piu_ammessi
    from models.match.trio_scoring_service import TrioScoringService
    from models.status_enum import MatchStatus

    trio, match = _trio_e_match(trio_id)
    if trio is None or match is None:
        return jsonify({"success": False, "error": str(_("Partita non trovata"))}), 404
    try:
        punti = (
            int(request.form["player1_racks"]),
            int(request.form["player2_racks"]),
            int(request.form["player3_racks"]),
        )
    except (KeyError, ValueError):
        return (
            jsonify({"success": False, "error": str(_("Punteggio non valido."))}),
            400,
        )

    rifiuto = rifiuto_punteggio_card(
        match, _("La partita è chiusa: per cambiarla azzerala dal segnapunti.")
    )
    if rifiuto is not None:
        return rifiuto

    try:
        TrioScoringService.set_racks_won(trio_id, punti, current_user.id)
    except ValueError as ve:
        return rifiuto_del_dominio(ve)

    trio, match = _trio_e_match(trio_id)
    assert trio is not None and match is not None
    finita = MatchStatus.is_finished(match.status)
    if finita and match.gara_id:
        from models.competition.round_service import RoundService

        RoundService.update_round_progression(match.gara_id)
    annuncia_punteggio(match, current_user.id, trio_id=trio_id)
    attuali = trio.player_racks_list
    return jsonify(
        {
            "success": True,
            "match_id": match.id,
            "punti": attuali,
            "piu": piu_ammessi(trio.trio_config, attuali),
            "finished": finita,
            "at_distance": match.is_at_distance and not finita,
            "winner_id": trio.winner_id,
        }
    )
