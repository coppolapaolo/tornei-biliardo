"""Match scoring, validation, reset, and rack management routes."""

from typing import Optional

from flask import (
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
from flask_babel import lazy_gettext as _
from flask_login import current_user, login_required

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
from models.status_enum import MatchStatus
from models.kpi import track_match_played
from routes.sse import emit_gara_event
from utils.route_helpers import handle_service_action, safe_json_error
from utils.safe_redirect import safe_next_url

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
            reported_by_id=current_user.id,
            validated_by_admin=True,  # Admin validation immediate
        )

        # Emit SSE event for gara detail page polling
        match = db.session.get(Match, match_id)
        if match and match.gara_id:
            emit_gara_event(
                match.gara_id,
                "match_updated",
                {
                    "match_id": match_id,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
                    "winner_id": winner_id,
                },
            )

        return jsonify(result)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "admin add rack")


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
        from models.competition.round_service import RoundService

        match = Match.query.get(match_id)
        if match and match.gara_id:
            RoundService.update_round_progression(match.gara_id)

    return handle_service_action(
        action=action,
        redirect_url=url_for("admin.match.match_detail", match_id=match_id),
        success_message="Risultato impostato con successo!",
        error_prefix=None,
    )


@match_bp.route("/<int:match_id>/punteggio", methods=["POST"])
@login_required
@match_manager_required
def punteggio_partita(match_id):
    """Il punteggio dagli stepper della card (canvas 3C): risponde in JSON.

    Stesso servizio del risultato secco (`set_match_result_direct`): alla
    distanza del turno la partita si chiude e il tavolo passa alla prima in
    attesa. La card si aggiorna sul posto con quello che torna; l'evento
    live porta `autore`, cosi' la pagina di chi ha toccato non si ricarica
    per un fatto che ha gia' visto.
    """
    from models.competition.round_service import RoundService

    try:
        player1_score = int(request.form["player1_score"])
        player2_score = int(request.form["player2_score"])
    except (KeyError, ValueError):
        return (
            jsonify({"success": False, "error": str(_("Punteggio non valido."))}),
            400,
        )

    from models.competition.round_manager import AdvancedRoundManager

    corrente = db.session.get(Match, match_id)
    if corrente is None:
        return jsonify({"success": False, "error": str(_("Partita non trovata"))}), 404
    # La card segna solo partite aperte, a due giocatori e a set singolo: la
    # X, il trio e il multi-set hanno il loro segnapunti, e una partita chiusa
    # si cambia solo con la correzione, che ne lascia traccia (issue #90).
    # Nascondere gli stepper non basta: e' la route che rifiuta (rilievo della
    # revisione automatica sulla PR #349).
    if corrente.is_bye or corrente.is_trio or corrente.is_multi_set:
        errore = _("Questa partita si segna dal suo segnapunti.")
        return jsonify({"success": False, "error": str(errore)}), 400
    if MatchStatus.is_finished(corrente.status):
        errore = _("La partita è chiusa: si cambia con «Correggi il risultato».")
        return jsonify({"success": False, "error": str(errore)}), 409
    consentito, motivo = AdvancedRoundManager.can_modify_match(match_id)
    if not consentito:
        return jsonify({"success": False, "error": str(motivo)}), 409

    try:
        # Gli stepper mandano un punteggio a ogni tocco: a meta' partita il
        # totale non e' ancora la distanza, e con «esattamente N» il controllo
        # del risultato secco rifiutava ogni triangolo (2026-09-13).
        RackService.set_match_result_direct(
            match_id, player1_score, player2_score, parziale=True
        )
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400

    match = db.session.get(Match, match_id)
    if match is None:
        return jsonify({"success": False, "error": str(_("Partita non trovata"))}), 404
    if match.gara_id:
        RoundService.update_round_progression(match.gara_id)
        emit_gara_event(
            match.gara_id,
            (
                "match_completed"
                if MatchStatus.is_finished(match.status)
                else "match_updated"
            ),
            {
                "match_id": match_id,
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "winner_id": match.winner_id,
                "autore": current_user.id,
            },
        )
    return jsonify(
        {
            "success": True,
            "match_id": match_id,
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "finished": MatchStatus.is_finished(match.status),
            "at_distance": match.is_at_distance,
            "table_assignment": match.table_assignment,
        }
    )


@match_bp.route("/<int:match_id>/forfeit", methods=["POST"])
@login_required
@match_manager_required
def ritiro_partita(match_id):
    """Il ritiro di un giocatore deciso dal direttore, dal menu della partita.

    Stessa strada di dominio del forfait che dichiara il giocatore
    (`MatchService.forfeit_match`): la partita si chiude a tavolino, le altre
    partite aperte di chi si ritira pure, e la regola della gara
    (`withdraw_policy`) decide se resta negli abbinamenti o ne esce. Cambia
    solo chi puo' chiederlo: al posto di «e' un giocatore della partita»
    (`match_player_required`) c'e' il permesso del direttore, e il giocatore
    si passa in `player_id`.

    Prima del servizio i rifiuti della card (`rifiuto_punteggio_card`): una
    partita chiusa non si riscrive, un turno bloccato dal turno dopo non si
    tocca. La X non ha avversario, il trio ha il suo ritiro
    (`/admin/gara/trio/<id>/forfeit`).
    """
    from models.competition.withdraw_policy_service import WithdrawPolicyService
    from routes.sse import emit_match_event
    from utils.card_partita import rifiuto_del_dominio, rifiuto_punteggio_card

    match = db.session.get(Match, match_id)
    if match is None:
        return jsonify({"success": False, "error": str(_("Partita non trovata"))}), 404
    if match.is_bye:
        errore = _(
            "La X a tavolino non ha un avversario: non c'è ritiro da registrare."
        )
        return jsonify({"success": False, "error": str(errore)}), 400
    if match.is_trio:
        errore = _("Il ritiro nella partita a tre si registra dal trio.")
        return jsonify({"success": False, "error": str(errore)}), 400
    player_id = request.form.get("player_id", type=int)
    if player_id not in (match.player1_id, match.player2_id) or player_id is None:
        errore = _("Scegli uno dei due giocatori della partita.")
        return jsonify({"success": False, "error": str(errore)}), 400
    rifiuto = rifiuto_punteggio_card(
        match, _("La partita è chiusa: il ritiro non si registra più.")
    )
    if rifiuto is not None:
        return rifiuto

    # Un'operazione sola, tutto o niente: il forfait, la regola della gara e
    # la notifica al giocatore. Gli eventi live partono dopo il salvataggio.
    try:
        match = WithdrawPolicyService.ritira_dalla_partita(
            match_id, player_id, current_user.id
        )
    except ValueError as errore:
        return rifiuto_del_dominio(errore)

    gara_id = match.gara_id
    if gara_id:
        from models.competition.round_service import RoundService

        RoundService.update_round_progression(gara_id)
    # Gli stessi due eventi del forfait del giocatore, con `autore`.
    emit_match_event(
        match_id,
        "forfeit",
        {
            "match_id": match_id,
            "forfeit_by": player_id,
            "winner_id": match.winner_id,
            "status": match.status,
            "autore": current_user.id,
        },
    )
    if gara_id:
        emit_gara_event(
            gara_id,
            "match_completed",
            {
                "match_id": match_id,
                "winner_id": match.winner_id,
                "forfeit": True,
                "autore": current_user.id,
            },
        )
    return jsonify(
        {"success": True, "status": match.status, "winner_id": match.winner_id}
    )


@match_bp.route("/<int:match_id>/validate", methods=["POST"])
@login_required
@match_manager_required
def validate_match(match_id):
    """Valida risultato match e completa la partita (admin/director).

    Questa azione:
    - Completa il match (status = completed): la validazione del direttore
      *è* quello stato, non un flag a parte — `Match` non ha nessun
      `validated_by_admin`, quella colonna vive su `Rack`
    - Libera il tavolo e lo assegna alla prima partita in attesa

    Note: Se winner_id non è impostato ma la distanza è raggiunta,
    determina automaticamente il vincitore in base al punteggio.
    Per match con pareggio (es. "Esattamente N"), accetta winner_id dalla request.
    """
    from models.match.validation_service import MatchValidationService

    try:
        result = MatchValidationService.validate_and_complete(match_id)

        # Emit SSE event for gara detail page polling (no DB writes)
        if result["gara_id"]:
            emit_gara_event(
                result["gara_id"],
                "match_completed",
                {
                    "match_id": match_id,
                    "winner_id": result["winner_id"],
                    "player1_score": result["player1_score"],
                    "player2_score": result["player2_score"],
                },
            )

        track_match_played()  # KPI tracking
        flash("Risultato validato e partita completata!")
        return jsonify(
            {
                "success": True,
                "message": "Risultato validato con successo",
                "match_completed": True,
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return (
            jsonify(
                {"success": False, "error": f"Errore durante la validazione: {str(e)}"}
            ),
            500,
        )


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


def _set_dal_form(form) -> Optional[list]:
    """I set della partita a set: `set_N_player1` e `set_N_player2`, in ordine.

    Li mandano il foglio della pagina della gara e il form della pagina della
    partita, che ha una riga per ogni set possibile: ci si ferma alla prima
    riga vuota. `None` quando il form non parla di set.
    """
    sets = []
    numero = 1
    while f"set_{numero}_player1" in form:
        primo = (form.get(f"set_{numero}_player1") or "").strip()
        secondo = (form.get(f"set_{numero}_player2") or "").strip()
        if not primo and not secondo:
            break
        sets.append((int(primo), int(secondo)))
        numero += 1
    return sets or None


@match_bp.route("/<int:match_id>/correct", methods=["POST"])
@login_required
@match_manager_required
def correct_match_result(match_id):
    """Corregge il risultato di una partita già chiusa, lasciandone traccia.

    Non è un reset: il reset cancella e basta, e chi aveva visto il risultato
    di ieri non ha modo di sapere perché oggi la classifica dice un'altra
    cosa. Qui il risultato precedente resta scritto, con chi l'ha corretto e
    quando (issue #90).
    """
    from models.match.correction_service import MatchCorrectionService

    try:
        # La partita a set manda i set, e i set vinti discendono da quelli.
        sets = _set_dal_form(request.form)
        if sets is None:
            player1_score = int(request.form["player1_score"])
            player2_score = int(request.form["player2_score"])
        else:
            player1_score = sum(1 for a, b in sets if a > b)
            player2_score = sum(1 for a, b in sets if b > a)
    except (KeyError, ValueError):
        flash(_("Punteggio non valido."), "error")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))
    # Il trio manda anche il terzo numero; la partita a due non ce l'ha.
    player3_score = request.form.get("player3_score", type=int)

    try:
        MatchCorrectionService.correct_result(
            match_id=match_id,
            player1_score=player1_score,
            player2_score=player2_score,
            player3_score=player3_score,
            sets=sets,
            corrected_by_id=current_user.id,
            note=request.form.get("note"),
        )
        flash(
            _("Risultato corretto. La correzione resta visibile sulla partita."),
            "success",
        )
    except ValueError as e:
        flash(str(e), "error")

    # Dalla pagina della gara si torna alla pagina della gara (canvas 3.4):
    # `next` e' un percorso interno o niente.
    return redirect(
        safe_next_url(request.form.get("next"))
        or url_for("admin.match.match_detail", match_id=match_id)
    )


# ============ GESTIONE RACK ADMIN ============


@match_bp.route("/rack/<int:rack_id>/remove", methods=["POST"])
@login_required
@rack_manager_required
def remove_rack_admin(rack_id):
    """Rimuovi un rack (admin)"""
    try:
        # Prima ottieni le info del match per il round update e SSE
        from models.competition.round_service import RoundService

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
            RoundService.update_round_progression(gara_id)

            # Emit SSE event for gara detail page polling
            match = db.session.get(Match, match_id)
            if match:
                emit_gara_event(
                    gara_id,
                    "match_updated",
                    {
                        "match_id": match_id,
                        "player1_score": match.player1_score,
                        "player2_score": match.player2_score,
                    },
                )

        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return safe_json_error(e, "admin remove rack")


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
        return safe_json_error(e, "admin validate rack")
