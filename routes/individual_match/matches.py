"""Match scoring and lifecycle routes for individual matches."""

from flask import (
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
import logging

from flask_babel import gettext as _
from flask_login import current_user

from models import IndividualMatch
from models.base import db
from models.individual_match.services import IndividualMatchService
from models.status_enum import Discipline
from models.user.permissions import RoleRequirement
from utils.local_time import parse_local_datetime
from utils.status_ui import match_scoring_state

from . import individual_match_bp
from .tpa_choice import open_tpa_referto, wants_referto

logger = logging.getLogger(__name__)


@individual_match_bp.route("/matches")
@RoleRequirement.player_or_director_required
def match_list():
    """List individual matches for current user."""
    try:
        matches = IndividualMatchService.get_user_matches(current_user.id)
        from flask import render_template

        return render_template("individual_match/matches.html", matches=matches)
    except Exception as e:
        logger.error("Error loading matches: %s", e, exc_info=True)
        flash(_("Errore interno del server"), "danger")
        return redirect(url_for("individual_match.dashboard"))


@individual_match_bp.route("/matches/<int:match_id>")
@RoleRequirement.player_or_director_required
def match_detail(match_id):
    """View individual match details and submit results."""
    try:
        match = IndividualMatch.query.get_or_404(match_id)

        # Verify user is part of this match
        if current_user.id not in (match.player1_id, match.player2_id):
            flash(_("Accesso negato a questo match."), "danger")
            return redirect(url_for("individual_match.match_list"))

        from flask import render_template
        from models.tpa.services import (
            FEATURE_CODE as TPA_FEATURE,
            TpaRefertoService,
        )

        # Il referto TPA si propone solo dove si puo' davvero aprire: il perche'
        # lo sa il servizio, e la pagina del referto lo ripete per esteso.
        #
        # `tpa_alla_partenza` e' l'altra domanda: la spunta nel modulo di avvio,
        # che si offre a partita ancora da cominciare. Le condizioni sono le
        # stesse meno lo stato — piu' lo sblocco, che il servizio non guarda
        # perche' il gate della gamification sta sull'apertura.
        return render_template(
            "individual_match/match_detail.html",
            match=match,
            tpa_can_open=TpaRefertoService.can_open(match, current_user.id),
            tpa_alla_partenza=(
                TpaRefertoService.can_open_once_started(match, current_user.id)
                and current_user.can_access(TPA_FEATURE)
            ),
        )

    except Exception as e:
        logger.error("Error loading match: %s", e, exc_info=True)
        flash(_("Errore interno del server"), "danger")
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

        # Il referto TPA si sceglie **qui**, con la partita che sta partendo:
        # dopo, al segnapunti, la prima cosa che si fa e' segnare, e al primo
        # triangolo non si apre piu'. La spunta viaggia col modulo di avvio.
        match = db.session.get(IndividualMatch, match_id)
        data = request.get_json(silent=True) or request.form
        col_referto = open_tpa_referto(match, wants_referto(data))
        destinazione = url_for(
            (
                "individual_match.tpa_referto"
                if col_referto
                else "individual_match.match_detail"
            ),
            match_id=match_id,
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "message": "Match started successfully",
                    "url": destinazione,
                }
            )
        else:
            flash(
                (
                    _("Sfida avviata: il referto è tuo.")
                    if col_referto
                    else _("Match avviato con successo!")
                ),
                "success",
            )
            return redirect(destinazione)

    except ValueError as e:
        error_msg = f"Error starting match: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/sets/next", methods=["POST"])
@RoleRequirement.player_or_director_required
def start_next_set(match_id):
    """Comincia il set successivo di una sfida al meglio dei set.

    Il segnapunti condiviso offre «Inizia il set N» anche sulle sfide
    individuali, ma l'endpoint esisteva solo per le partite di gara: qui il
    pulsante chiamava una funzione che non c'era, e la partita restava
    bloccata dopo il primo set — senza modo di segnare né di chiuderla.
    """
    try:
        nuovo_set = IndividualMatchService.start_next_set(match_id, current_user.id)

        from routes.sse import emit_individual_match_event

        emit_individual_match_event(
            match_id,
            "set_started",
            {"started_by": current_user.id, "set_number": nuovo_set.set_number},
        )

        if request.is_json:
            return jsonify({"success": True, "set_number": nuovo_set.set_number})

        flash(_("Set %(n)s iniziato.", n=nuovo_set.set_number), "success")
        return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        if request.is_json:
            return jsonify({"success": False, "error": str(e)}), 400
        flash(str(e), "danger")
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
                # `can_add` viaggia anche nell'evento: chi lo riceve ha il
                # tabellone aperto e deve decidere se gli basta riscrivere le
                # cifre. Non dipende da chi guarda (vedi `match_scoring_state`).
                "can_add": match_scoring_state(match, current_user)["can_add"],
                "added_by": current_user.id,
            },
        )

        if request.is_json:
            # `can_add`: si può ancora segnare? Non è `is_ready_for_validation`,
            # che nel **formato libero** è vera fin dal primo triangolo pur
            # restando la partita apertissima. Serve al tabellone per sapere se
            # gli basta riscrivere due cifre o se deve cambiare quel che offre
            # — e quindi se la pagina va ricaricata.
            return jsonify(
                {
                    "success": True,
                    # `rack_id`: senza, il trattino che si accende sul
                    # tabellone resta muto — non saprebbe **quale** triangolo
                    # marcherebbe, e il tabellone non si ricarica (ADR-056).
                    "rack_id": rack.id,
                    "rack_number": rack.rack_number,
                    "winner_id": winner_id,
                    "player1_score": match.player1_score,
                    "player2_score": match.player2_score,
                    "is_ready_for_validation": match.is_ready_for_validation(),
                    "can_add": match_scoring_state(match, current_user)["can_add"],
                }
            )
        else:
            flash(_("Triangolo aggiunto!"), "success")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))

    except ValueError as e:
        error_msg = f"Errore: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/lag", methods=["POST"])
@RoleRequirement.player_or_director_required
def register_lag(match_id):
    """Esito dell'acchito: chi ha vinto, e chi esegue il tiro di apertura.

    Due campi e non uno: chi vince l'acchito **sceglie chi** apre, e può
    scegliere l'avversario («Regole generali pool» 1.2).
    """
    data = request.get_json() if request.is_json else request.form
    try:
        if (
            data.get("lag_winner_id") is None
            or data.get("first_break_player_id") is None
        ):
            raise ValueError(_("Scegli uno dei due giocatori."))

        IndividualMatchService.register_lag(
            match_id=match_id,
            lag_winner_id=int(data["lag_winner_id"]),
            first_break_player_id=int(data["first_break_player_id"]),
        )
        if request.is_json:
            return jsonify({"success": True})
        return redirect(url_for("individual_match.match_detail", match_id=match_id))
    except ValueError as e:
        if request.is_json:
            return jsonify({"success": False, "error": str(e)}), 400
        flash(str(e), "danger")
        return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route(
    "/matches/<int:match_id>/racks/<int:rack_id>/runout", methods=["POST"]
)
@RoleRequirement.player_or_director_required
def toggle_run_out(match_id, rack_id):
    """Marca (o smarca) un triangolo come chiuso in una visita (ADR-056)."""
    try:
        stato = IndividualMatchService.toggle_run_out(
            match_id=match_id, rack_id=rack_id
        )
        if request.is_json:
            # `letter`: la sigla la decide il server, non il tabellone —
            # dipende da chi apriva quel triangolo. Resta in inglese perché nel
            # regolamento FIBiS un termine italiano per run-out e break and run
            # non esiste (ADR-056).
            sigla = ""
            if stato["is_run_out"]:
                sigla = "B" if stato["is_break_and_run"] else "R"
            return jsonify({"success": True, "letter": sigla, **stato})
        return redirect(url_for("individual_match.match_detail", match_id=match_id))
    except ValueError as e:
        if request.is_json:
            return jsonify({"success": False, "error": str(e)}), 400
        flash(str(e), "danger")
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
            flash(_("Triangolo rimosso!"), "success")
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

        # La conferma bilaterale porta il match a VALIDATED (flusso nuovo) o a
        # COMPLETED (legacy): entrambi sono lo stato "concluso". Prima si
        # confrontava col letterale "completed" → dopo la 2ª conferma il match
        # era validato ma la route riportava "in attesa" (incongruenza UX).
        fully_confirmed = MatchStatus.is_finished(match.status.value)

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
                flash(_("Match completato con successo!"), "success")
            else:
                flash(
                    _("Risultato confermato! In attesa dell'altro giocatore."), "info"
                )
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
            flash(_("Risultato rifiutato. Ultimo triangolo rimosso."), "warning")
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
            flash(_("Match completato con successo!"), "success")
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
            flash(_("Match annullato con successo!"), "success")
            return redirect(url_for("individual_match.match_list"))

    except ValueError as e:
        error_msg = f"Error cancelling match: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("individual_match.match_detail", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/edit", methods=["GET", "POST"])
@RoleRequirement.player_or_director_required
def edit_match(match_id):
    """Corregge come si gioca una sfida, finché non è stato segnato niente.

    Stessi campi dell'avvio rapido e **stesso** normalizzatore
    (`QuickMatchService.resolve_settings`): un secondo parser qui vorrebbe dire
    due moduli che accettano cose diverse.
    """
    from flask import render_template
    from models.exceptions import DomainError, http_status_for_exception
    from models.individual_match.quick_match_service import QuickMatchService
    from models.location.models import BilliardHall

    match = IndividualMatch.query.get_or_404(match_id)

    if not match.is_player(current_user.id):
        flash(_("Accesso negato a questo match."), "danger")
        return redirect(url_for("individual_match.match_list"))

    if not match.can_be_revised():
        flash(
            _("La sfida è cominciata: come si gioca non si cambia più."),
            "warning",
        )
        return redirect(url_for("individual_match.match_detail", match_id=match_id))

    if request.method == "GET":
        return render_template(
            "individual_match/edit_match.html",
            match=match,
            settings=QuickMatchService.settings_of(match),
            verified_venues=(
                BilliardHall.query.filter_by(is_active=True, verified=True)
                .order_by(BilliardHall.name)
                .all()
            ),
        )

    data = request.get_json() if request.is_json else request.form
    config = {
        "billiard_hall_id": data.get("billiard_hall_id") or None,
        "location": data.get("location"),
        "discipline": data.get("discipline") or None,
        "match_format": data.get("match_format") or None,
        "distance": data.get("distance") or None,
        "match_distance": data.get("match_distance") or None,
        "break_rule": data.get("break_rule") or None,
    }
    if data.get("is_race_to") is not None:
        config["is_race_to"] = str(data.get("is_race_to")).lower() == "true"

    try:
        settings = QuickMatchService.resolve_settings(
            QuickMatchService.settings_of(match), config
        )
        IndividualMatchService.update_settings(
            match_id,
            current_user.id,
            discipline=settings["discipline"],
            distance=settings["distance"],
            is_race_to=settings["is_race_to"],
            break_rule=settings["break_rule"],
            is_multi_set=settings["is_multi_set"],
            match_distance=settings["match_distance"],
            is_race_to_sets=True if settings["is_multi_set"] else None,
            billiard_hall_id=settings["billiard_hall_id"],
            location=settings["location"] or None,
        )
    except (DomainError, ValueError) as exc:
        if request.is_json:
            stato = (
                http_status_for_exception(exc) if isinstance(exc, DomainError) else 400
            )
            return jsonify({"success": False, "error": str(exc)}), stato
        flash(str(exc), "danger")
        return redirect(url_for("individual_match.edit_match", match_id=match_id))

    if request.is_json:
        return jsonify({"success": True, "match_id": match_id})

    flash(_("Sfida aggiornata."), "success")
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

        # I due valori arrivano da un `<input type="datetime-local">`, quindi in
        # **ora italiana**, mentre `started_at`/`ended_at` li scrive `utc_now()`
        # quando il match parte: leggerli grezzi mischia due scale sulla stessa
        # colonna, e la durata del match risulta sfalsata di un fuso.
        started_at = parse_local_datetime(started_at_str) if started_at_str else None
        ended_at = parse_local_datetime(ended_at_str) if ended_at_str else None
        if (started_at_str and not started_at) or (ended_at_str and not ended_at):
            return jsonify({"success": False, "error": "Orario non valido"}), 400

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
            flash(_("Orari aggiornati con successo!"), "success")
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
        "discipline": match.discipline or Discipline.EIGHT_BALL.value,
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
