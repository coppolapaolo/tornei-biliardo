# routes/admin/competition/rounds.py
"""Round management routes for competitions."""

from flask import (
    abort,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
from flask_babel import _
from flask_login import login_required

from models import (
    db,
    Gara,
    Inscription,
    Match,
)
from models.status_enum import (
    GaraStatus,
    MatchStatus,
)
from models.competition.services import GaraService
from models.competition.round_service import RoundService
from models.matchmaking.strategies.amalfi import AmalfiStrategy
from models.classification.models import RoundClassification
from models.classification.services import RoundClassificationService
from utils import gara_manager_required
from utils.route_helpers import handle_service_action, get_or_ajax_404, safe_json_error

import logging

logger = logging.getLogger(__name__)

from . import competition_bp  # noqa: E402  (deferred import to avoid circular)


@competition_bp.route("/<int:gara_id>/start_first_round", methods=["POST"])
@login_required
@gara_manager_required
def start_first_round(gara_id):
    """Avvia primo turno della gara (o tutti i turni per strategia Random)"""
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        # Guard esplicito PRIMA del service: il pattern `gara and ...` a valle
        # mascherava il None e mostrava comunque il flash di successo.
        abort(404)

    try:
        RoundService.start_first_round(gara_id)

        if gara.matchmaking_strategy == "random":
            flash("Gara avviata! Tutti i turni sono stati creati.", "success")
        else:
            flash("Primo turno avviato!", "success")

    except ValueError as ve:
        flash(str(ve), "error")
    except Exception as e:
        logger.error(f"Error starting first round: {e}", exc_info=True)
        flash("Errore interno del server", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/cancel_first_round", methods=["POST"])
@login_required
@gara_manager_required
def cancel_first_round(gara_id):
    """Cancella l'avvio del primo turno se non ci sono risultati"""
    return handle_service_action(
        action=lambda: RoundService.cancel_first_round_startup(gara_id),
        redirect_url=url_for("admin.competition.gara_detail", gara_id=gara_id),
        success_message=(
            "Avvio del primo turno cancellato con successo! "
            "La gara è tornata allo stato di iscrizioni."
        ),
    )


@competition_bp.route("/<int:gara_id>/cancel_current_round", methods=["POST"])
@login_required
@gara_manager_required
def cancel_current_round(gara_id):
    """Cancella l'avvio del turno corrente se non ci sono risultati"""
    return handle_service_action(
        action=lambda: RoundService.cancel_current_round_startup(gara_id),
        redirect_url=url_for("admin.competition.gara_detail", gara_id=gara_id),
        success_message="Avvio del turno cancellato con successo!",
        error_prefix=None,
    )


@competition_bp.route("/<int:gara_id>/terminate", methods=["POST"])
@login_required
@gara_manager_required
def terminate_gara(gara_id):
    """Termina esplicitamente la gara dopo che tutti i turni sono completati.

    Workflow:
    - If status=playing and tiebreakers exist: suggest using start_ssr first
    - If status=awaiting_ssr and tiebreakers resolved: complete the gara
    - If status=playing and no tiebreakers: complete directly
    """
    from models.competition.spareggio_service import SpareggioService

    gara = Gara.query.get_or_404(gara_id)
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    # Accept both playing and awaiting_ssr statuses
    if gara.status not in [GaraStatus.PLAYING.value, GaraStatus.AWAITING_SSR.value]:
        if is_ajax:
            return jsonify({"success": False, "error": "La gara non è in corso!"}), 400
        flash("La gara non è in corso!", "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # For playing status, check if all rounds completed
    if gara.status == GaraStatus.PLAYING.value:
        real_status = gara.get_real_status()
        if real_status != "campionato_completed":
            if is_ajax:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Non tutti i turni sono ancora completati!",
                        }
                    ),
                    400,
                )
            flash("Non tutti i turni sono ancora completati!", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    try:
        # Check for unresolved tiebreakers
        tiebreakers = SpareggioService.detect_tiebreakers(gara_id)

        if tiebreakers:
            # Return tiebreaker data - suggest using SSR workflow
            if is_ajax:
                return jsonify(
                    {
                        "success": False,
                        "needs_tiebreaker": True,
                        "tiebreakers": tiebreakers,
                        "message": (
                            f"Ci sono parimerito nelle prime "
                            f"{gara.tiebreaker_until_position or 3} posizioni. "
                            f"Usa 'Avvia SSR' per inserire i punteggi."
                        ),
                    }
                )
            flash(
                (
                    f"Ci sono parimerito nelle prime "
                    f"{gara.tiebreaker_until_position or 3} posizioni. "
                    f"Usa 'Avvia SSR' per inserire i punteggi."
                ),
                "warning",
            )
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # No tiebreakers or all resolved - complete the gara
        GaraService.complete(gara_id)
        if is_ajax:
            return jsonify(
                {
                    "success": True,
                    "message": "Gara terminata con successo!",
                    "redirect": url_for(
                        "admin.competition.gara_detail", gara_id=gara_id
                    ),
                }
            )
        flash(
            "Gara terminata con successo! I risultati sono ora definitivi.", "success"
        )
    except Exception as e:
        if is_ajax:
            return safe_json_error(e, "terminating gara")
        logger.error(f"Error terminating gara: {e}", exc_info=True)
        flash("Errore interno del server", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/start_ssr", methods=["POST"])
@login_required
@gara_manager_required
def start_ssr(gara_id):
    """Avvia la fase SSR per risolvere i parimerito.

    Transition: playing → awaiting_ssr
    Returns JSON with SSR groups for display.
    """
    from models.competition.spareggio_service import SpareggioService
    from models.competition.state_service import StateService

    gara = Gara.query.get_or_404(gara_id)
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    # Must be in playing state
    if gara.status != GaraStatus.PLAYING.value:
        if is_ajax:
            return (
                jsonify(
                    {"success": False, "error": "La gara non è in stato 'in corso'!"}
                ),
                400,
            )
        flash("La gara non è in stato 'in corso'!", "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Check all rounds completed
    real_status = gara.get_real_status()
    if real_status != "campionato_completed":
        if is_ajax:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Non tutti i turni sono ancora completati!",
                    }
                ),
                400,
            )
        flash("Non tutti i turni sono ancora completati!", "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Check for tiebreakers
    tiebreakers = SpareggioService.detect_tiebreakers(gara_id)
    if not tiebreakers:
        if is_ajax:
            return (
                jsonify(
                    {"success": False, "error": "Non ci sono parimerito da risolvere!"}
                ),
                400,
            )
        flash("Non ci sono parimerito da risolvere!", "warning")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    try:
        # Transition to awaiting_ssr state
        StateService.start_ssr(gara)

        # Get all SSR groups for display
        all_groups = SpareggioService.get_all_ssr_groups(gara_id)

        if is_ajax:
            return jsonify(
                {
                    "success": True,
                    "message": (
                        "Fase SSR avviata. Inserire i punteggi per i parimerito."
                    ),
                    "ssr_groups": all_groups,
                    "redirect": url_for(
                        "admin.competition.gara_detail", gara_id=gara_id
                    ),
                }
            )
        flash("Fase SSR avviata. Inserire i punteggi per i parimerito.", "success")
    except Exception as e:
        if is_ajax:
            return safe_json_error(e, "starting SSR")
        logger.error(f"Error starting SSR: {e}", exc_info=True)
        flash("Errore interno del server", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/cancel_ssr", methods=["POST"])
@login_required
@gara_manager_required
def cancel_ssr(gara_id):
    """Annulla la fase SSR e riporta la gara in gioco.

    Transition: awaiting_ssr → playing

    Senza questa via di ritorno lo spareggio era un vicolo cieco: durante
    `awaiting_ssr` il reset dei match è bloccato, quindi un risultato
    sbagliato scoperto a spareggio avviato non era più correggibile.
    """
    from models.competition.state_service import StateService

    gara = Gara.query.get_or_404(gara_id)
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if gara.status != GaraStatus.AWAITING_SSR.value:
        message = _("La gara non è in fase di spareggio!")
        if is_ajax:
            return jsonify({"success": False, "error": str(message)}), 400
        flash(str(message), "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    try:
        StateService.cancel_ssr(gara)
        message = _(
            "Spareggio annullato: i punteggi SSR sono stati azzerati e "
            "puoi modificare di nuovo i risultati."
        )
        if is_ajax:
            return jsonify(
                {
                    "success": True,
                    "message": str(message),
                    "redirect": url_for(
                        "admin.competition.gara_detail", gara_id=gara_id
                    ),
                }
            )
        flash(str(message), "success")
    except Exception as e:
        if is_ajax:
            return safe_json_error(e, "cancelling SSR")
        logger.error(f"Error cancelling SSR: {e}", exc_info=True)
        flash(str(_("Errore interno del server")), "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/save_ssr_group", methods=["POST"])
@login_required
@gara_manager_required
def save_ssr_group(gara_id):
    """Save SSR scores for a single tiebreaker group.

    Expects JSON: {"group_position": 1, "scores": {"user_id": score, ...}}
    Validates scores only within the specified group.
    """
    from models.competition.spareggio_service import SpareggioService

    gara = Gara.query.get_or_404(gara_id)

    # Accept both playing and awaiting_ssr states
    if gara.status not in [GaraStatus.PLAYING.value, GaraStatus.AWAITING_SSR.value]:
        return jsonify({"success": False, "error": "La gara non è in corso!"}), 400

    # Parse request data
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Dati non validi"}), 400

    group_position = data.get("group_position")
    raw_scores = data.get("scores")

    if group_position is None or not raw_scores:
        return (
            jsonify(
                {"success": False, "error": "Posizione gruppo e punteggi richiesti"}
            ),
            400,
        )

    # Convert to integers
    try:
        group_position = int(group_position)
        scores = {int(k): int(v) for k, v in raw_scores.items()}
    except (ValueError, TypeError):
        return (
            jsonify(
                {"success": False, "error": "I punteggi devono essere numeri interi"}
            ),
            400,
        )

    # Save scores for this specific group
    success, message = SpareggioService.save_ssr_scores_for_group(
        gara_id, group_position, scores
    )
    if not success:
        return jsonify({"success": False, "error": message}), 400

    # Update classification with new positions
    success, message = SpareggioService.finalize_classification(gara_id)
    if not success:
        return jsonify({"success": False, "error": message}), 400

    # Check if all tiebreakers are now resolved
    remaining = SpareggioService.detect_tiebreakers(gara_id)
    all_resolved = len(remaining) == 0

    # Get updated groups for display
    all_groups = SpareggioService.get_all_ssr_groups(gara_id)

    return jsonify(
        {
            "success": True,
            "message": f"Punteggi SSR per posizione {group_position} salvati",
            "all_resolved": all_resolved,
            "ssr_groups": all_groups,
        }
    )


@competition_bp.route("/<int:gara_id>/save_ssr_scores", methods=["POST"])
@login_required
@gara_manager_required
def save_ssr_scores(gara_id):
    """Save SSR scores and optionally complete the gara.

    Expects JSON body with format: {"scores": {"user_id": score, ...}}

    Note: This is a legacy endpoint maintained for backward compatibility.
    New code should use save_ssr_group for per-group validation.
    """
    from models.competition.spareggio_service import SpareggioService

    gara = Gara.query.get_or_404(gara_id)

    # Accept both playing and awaiting_ssr states
    if gara.status not in [GaraStatus.PLAYING.value, GaraStatus.AWAITING_SSR.value]:
        return jsonify({"success": False, "error": "La gara non è in corso!"}), 400

    # For playing status, check rounds completed
    if gara.status == GaraStatus.PLAYING.value:
        real_status = gara.get_real_status()
        if real_status != "campionato_completed":
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Non tutti i turni sono ancora completati!",
                    }
                ),
                400,
            )

    # Parse scores from request
    data = request.get_json()
    if not data or "scores" not in data:
        return jsonify({"success": False, "error": "Dati non validi"}), 400

    # Convert string keys to integers and values to integers
    try:
        scores = {int(k): int(v) for k, v in data["scores"].items()}
    except (ValueError, TypeError):
        return (
            jsonify(
                {"success": False, "error": "I punteggi devono essere numeri interi"}
            ),
            400,
        )

    # Save SSR scores
    success, message = SpareggioService.save_ssr_scores(gara_id, scores)
    if not success:
        return jsonify({"success": False, "error": message}), 400

    # Finalize classification with new positions
    success, message = SpareggioService.finalize_classification(gara_id)
    if not success:
        return jsonify({"success": False, "error": message}), 400

    # Check if there are still unresolved tiebreakers
    remaining_tiebreakers = SpareggioService.detect_tiebreakers(gara_id)
    if remaining_tiebreakers:
        return jsonify(
            {
                "success": False,
                "needs_tiebreaker": True,
                "tiebreakers": remaining_tiebreakers,
                "message": "Alcuni spareggi non sono ancora risolti.",
            }
        )

    # All tiebreakers resolved - complete the gara
    try:
        GaraService.complete(gara_id)
        return jsonify(
            {
                "success": True,
                "message": "Gara terminata con successo!",
                "redirect": url_for("admin.competition.gara_detail", gara_id=gara_id),
            }
        )
    except Exception as e:
        return safe_json_error(e, "completing gara after SSR")


# ============ SISTEMA AMALFI ============


@competition_bp.route("/amalfi/classification/<int:gara_id>/<int:round_number>")
@login_required
@gara_manager_required
def amalfi_classification(gara_id, round_number):
    """Visualizza classifica Amalfi dopo un turno specifico"""
    gara = Gara.query.get_or_404(gara_id)

    # Verifica che il turno sia valido
    if round_number < 1 or round_number > gara.rounds_count:
        flash(f"Turno {round_number} non valido per questa gara!")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Verifica che il turno sia completato
    matches_in_round = Match.query.filter_by(
        gara_id=gara_id, round_number=round_number
    ).all()

    if not matches_in_round:
        flash(f"Il turno {round_number} non è ancora iniziato!")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Controlla se tutti i match del turno sono completati.
    # VALIDATED è uno stato post-COMPLETED (admin ha confermato): conta
    # comunque come "match finito" ai fini della progressione del turno.
    # Bye matches are considered completed automatically.
    finished_statuses = (MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value)
    incomplete_matches = [
        m
        for m in matches_in_round
        if m.status not in finished_statuses and not m.is_bye
    ]
    if incomplete_matches:
        flash(
            f"Il turno {round_number} non è ancora completato! "
            f"Mancano {len(incomplete_matches)} partite."
        )
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Ottieni o calcola classifica
    classification = RoundClassificationService.get_round_standings(
        gara_id, round_number
    )
    if not classification:
        # Calcola classifica se non esiste (questo metodo ritorna tuple, non oggetti)
        RoundClassification.calculate_classification_after_round(gara_id, round_number)
        # Ricarica la classifica dopo il calcolo (ora sono oggetti RoundClassification)
        classification = RoundClassificationService.get_round_standings(
            gara_id, round_number
        )

    # Statistiche aggiuntive
    total_players = len(classification)
    inscriptions = Inscription.query.filter_by(gara_id=gara_id).all()

    # Aggiungi tutti i matches per la navigazione turni
    all_matches = Match.query.filter_by(gara_id=gara_id).all()

    return render_template(
        "admin/amalfi_classification.html",
        gara=gara,
        round_number=round_number,
        classification=classification,
        total_players=total_players,
        inscriptions=inscriptions,
        matches=all_matches,
    )


@competition_bp.route(
    "/<int:gara_id>/amalfi/start_round/<int:round_number>", methods=["POST"]
)
@login_required
@gara_manager_required
def amalfi_start_round(gara_id, round_number):
    """Avvia un turno specifico con algoritmo Amalfi"""
    from models.competition.round_service import RoundService

    gara = Gara.query.get_or_404(gara_id)

    try:
        # Validazioni preliminari
        if round_number < 1 or round_number > gara.rounds_count:
            return jsonify(
                {"success": False, "error": f"Turno {round_number} non valido!"}
            )

        # Controlla se il turno è già stato avviato (idempotenza)
        existing_matches = Match.query.filter_by(
            gara_id=gara_id, round_number=round_number
        ).first()
        if existing_matches:
            return jsonify(
                {
                    "success": False,
                    "error": f"Il turno {round_number} è già stato avviato!",
                }
            )

        if round_number != gara.current_round + 1:
            return jsonify(
                {
                    "success": False,
                    "error": f"Devi avviare prima il turno {gara.current_round + 1}!",
                }
            )

        # Validate Amalfi configuration using strategy
        strategy = AmalfiStrategy()
        validation_result = strategy._validate_strategy_specific(gara)
        if validation_result["errors"]:
            errors = "; ".join(validation_result["errors"])
            return jsonify({"success": False, "error": f"Errore Amalfi: {errors}"})

        if round_number > 1:
            prev_matches = Match.query.filter_by(
                gara_id=gara_id, round_number=round_number - 1
            ).all()
            # VALIDATED conta come "match finito" (post-COMPLETED, admin-confirmed).
            finished = (MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value)
            incomplete_prev = [m for m in prev_matches if m.status not in finished]
            if incomplete_prev:
                return jsonify(
                    {
                        "success": False,
                        "error": f"Completa prima tutte le partite del "
                        f"turno {round_number-1}!",
                    }
                )

        # Create round + advance gara state in one transaction
        total, n_normal, n_bye, n_trio, _tables = RoundService.start_next_round(
            gara_id, round_number
        )

        # Costruisci il messaggio di successo
        message = (
            f"Turno {round_number} avviato con successo! "
            f"Creati {total} abbinamenti Amalfi."
        )
        details = []
        if n_normal:
            details.append(f"Abbinamenti normali: {n_normal}")
        if n_bye:
            details.append(f"Partite vs X: {n_bye}")
        if n_trio:
            details.append(f"Trii: {n_trio}")

        return jsonify(
            {
                "success": True,
                "message": message,
                "details": details,
                "redirect": url_for("admin.competition.gara_detail", gara_id=gara_id),
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)})
    except Exception as e:
        return safe_json_error(e, "creating Amalfi round")


@competition_bp.route("/<int:gara_id>/start_round/<int:round_number>", methods=["POST"])
@login_required
@gara_manager_required
def start_round_generic(gara_id, round_number):
    """Avvia un turno specifico con la strategia configurata nella gara"""
    from models.competition.round_service import RoundService

    gara = Gara.query.get_or_404(gara_id)

    try:
        # Validazioni preliminari
        if round_number < 1 or round_number > gara.rounds_count:
            return jsonify(
                {"success": False, "error": f"Turno {round_number} non valido!"}
            )

        # Controlla se il turno è già stato avviato (idempotenza)
        existing_matches = Match.query.filter_by(
            gara_id=gara_id, round_number=round_number
        ).first()
        if existing_matches:
            return jsonify(
                {
                    "success": False,
                    "error": f"Il turno {round_number} è già stato avviato!",
                }
            )

        if round_number != gara.current_round + 1:
            return jsonify(
                {
                    "success": False,
                    "error": f"Devi avviare prima il turno {gara.current_round + 1}!",
                }
            )

        # Validazione specifica per strategia (solo Amalfi ha validazioni speciali)
        if gara.matchmaking_strategy == "amalfi":
            strategy = AmalfiStrategy()
            validation_result = strategy._validate_strategy_specific(gara)
            if validation_result["errors"]:
                errors = "; ".join(validation_result["errors"])
                return jsonify(
                    {"success": False, "error": f"Errore configurazione: {errors}"}
                )

        # Controlla turni precedenti completati
        if round_number > 1:
            prev_matches = Match.query.filter_by(
                gara_id=gara_id, round_number=round_number - 1
            ).all()
            # VALIDATED conta come "match finito" (post-COMPLETED, admin-confirmed).
            finished = (MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value)
            incomplete_prev = [m for m in prev_matches if m.status not in finished]
            if incomplete_prev:
                return jsonify(
                    {
                        "success": False,
                        "error": f"Completa prima tutte le partite del "
                        f"turno {round_number-1}!",
                    }
                )

        # Ottieni disciplina personalizzata se fornita
        discipline_override = request.form.get("discipline")
        if discipline_override and discipline_override == gara.discipline:
            # Se è uguale alla disciplina della gara, non serve override
            discipline_override = None

        # Create round + advance gara state in one transaction
        total, n_normal, n_bye, n_trio, tables_assigned = RoundService.start_next_round(
            gara_id, round_number, discipline_override
        )

        # Refresh gara to get updated strategy name
        db.session.refresh(gara)

        # Messaggio di successo
        strategy_name = gara.matchmaking_strategy.replace("_", " ").title()
        message = f"Turno {round_number} avviato con strategia {strategy_name}!"
        details = [f"Partite totali: {total}"]

        # Aggiungi info sulla disciplina se diversa da quella di default
        if discipline_override:
            discipline_display = discipline_override.replace("_", " ").title()
            details.append(f"Disciplina: {discipline_display}")
        else:
            default_discipline = gara.discipline.replace("_", " ").title()
            details.append(f"Disciplina: {default_discipline} (Default)")

        if n_normal:
            details.append(f"Partite normali: {n_normal}")
        if n_bye:
            details.append(f"Partite vs X: {n_bye}")
        if n_trio:
            details.append(f"Trii: {n_trio}")
        if tables_assigned:
            details.append(f"Tavoli assegnati: {tables_assigned}")

        return jsonify(
            {
                "success": True,
                "message": message,
                "details": details,
                "redirect": url_for("admin.competition.gara_detail", gara_id=gara_id),
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)})
    except Exception as e:
        return safe_json_error(e, "creating round")


# ====================================================================
# ADVANCED ROUND MANAGEMENT ROUTES - Use Case 8
# ====================================================================


# NOTA: qui viveva `round_management_overview` (`GET /<gara_id>/round_management`),
# una pagina a sé che renderizzava `admin/round_management.html`. Quel template non
# esiste (né esiste nella storia del repo): la route sollevava `TemplateNotFound`,
# cioè 500, per chiunque la aprisse. La gestione dei turni sta da tempo dentro
# `templates/components/_round_management.html`, incluso nella pagina della gara.
# Le tre azioni qui sotto ci rimandavano dopo aver lavorato: il direttore vedeva un
# 500 al posto dell'esito, e `resetLastRound` in `gara_detail.html` mostrava
# "errore" su un reset andato a buon fine. Ora rimandano alla pagina della gara.


@competition_bp.route(
    "/<int:gara_id>/match/<int:match_id>/reset_advanced", methods=["POST"]
)
@login_required
@gara_manager_required
def reset_match_advanced(gara_id, match_id):
    """Reset a match with advanced validation and classification updates.

    Note: This route is functionally identical to /admin/match/<id>/reset
          and is maintained for backward compatibility with existing links.
          New code should use the simpler route.
    """
    from models.competition.round_manager import AdvancedRoundManager

    try:
        success, message = AdvancedRoundManager.reset_match_with_validation(match_id)

        if success:
            flash(message, "success")
        else:
            flash(message, "danger")
    except Exception as e:
        logger.error(f"Error resetting match: {e}", exc_info=True)
        flash("Errore interno del server", "danger")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route(
    "/<int:gara_id>/round/<int:round_number>/cancel", methods=["POST"]
)
@login_required
@gara_manager_required
def cancel_round_advanced(gara_id, round_number):
    """Cancel an entire round with proper validation.

    Business Rules:
    - Can only cancel current round or future rounds
    - Blocked if matches have partial results
    - Admin must reset matches before canceling round
    """
    from models.competition.round_manager import AdvancedRoundManager

    try:
        success, message = AdvancedRoundManager.cancel_round(gara_id, round_number)

        if success:
            flash(message, "success")
        else:
            flash(message, "danger")
    except Exception as e:
        logger.error(f"Error cancelling round: {e}", exc_info=True)
        flash("Errore interno del server", "danger")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route(
    "/<int:gara_id>/round/<int:round_number>/bulk_reset", methods=["POST"]
)
@login_required
@gara_manager_required
def bulk_reset_round_matches(gara_id, round_number):
    """Reset all matches in a round."""
    from models.competition.round_manager import AdvancedRoundManager

    try:
        success, message, stats = AdvancedRoundManager.bulk_reset_round_matches(
            gara_id, round_number
        )

        if success:
            flash(f"{message}. {stats['reset_count']} match resettati.", "success")
        else:
            flash(
                f"{message}. {stats.get('reset_count', 0)} match resettati, "
                f"{stats.get('error_count', 0)} errori.",
                "warning",
            )
    except Exception as e:
        logger.error(f"Error in bulk reset: {e}", exc_info=True)
        flash("Errore interno del server", "danger")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/match/<int:match_id>/modification_check")
@login_required
@gara_manager_required
def check_match_modification(_gara_id, match_id):
    """AJAX endpoint to check if a match can be modified."""
    from models.competition.round_manager import AdvancedRoundManager

    can_modify, reason = AdvancedRoundManager.can_modify_match(match_id)

    return jsonify(
        {
            "can_modify": can_modify,
            "reason": reason if not can_modify else "",
            "match_id": match_id,
        }
    )


@competition_bp.route("/<int:gara_id>/round_status")
@login_required
@gara_manager_required
def get_round_status(gara_id):
    """AJAX endpoint to get current round status."""
    from models.competition.round_manager import AdvancedRoundManager

    gara = get_or_ajax_404(Gara, gara_id, "Gara")

    rounds_summary = AdvancedRoundManager.get_round_modification_summary(gara_id)

    return jsonify(
        {
            "current_round": gara.current_round,
            "total_rounds": gara.rounds_count,
            "gara_status": gara.status,
            "rounds_summary": rounds_summary,
        }
    )


# ─────────────────────────────────────────────────────────────────────────
# Round configuration overrides (ADR-027)
#
# Persistono gli override per turno (disciplina, distanza, modalità) che la
# UI in templates/components/_round_management.html prima salvava solo in
# localStorage. Il valore di RoundConfiguration viene letto dal round-creation
# (models/competition/round_creation.py) per popolare i Match.
#
# Vincolo di stato: gli override sono modificabili solo in setup. Una volta
# aperte le iscrizioni il backend rifiuta le modifiche (parallelo del
# can_be_modified() della gara). Lo stato è leggibile sempre.
# ─────────────────────────────────────────────────────────────────────────


def _serialize_round_config(config) -> dict:
    """Serializza RoundConfiguration in JSON. NULL → None (default ereditato)."""
    return {
        "round_number": config.round_number,
        "discipline": config.discipline,
        "distance": config.distance,
        "is_race_to": config.is_race_to,
        "is_multi_set": config.is_multi_set,
        "match_distance": config.match_distance,
        "is_race_to_sets": config.is_race_to_sets,
    }


@competition_bp.route("/<int:gara_id>/round-config", methods=["GET"])
@login_required
@gara_manager_required
def list_round_configs(gara_id: int):
    """Restituisce gli override per turno della gara come lista JSON."""
    from models.competition.round_configuration import RoundConfiguration

    gara = get_or_ajax_404(Gara, gara_id, "Gara")
    configs = RoundConfiguration.get_all_for_gara(gara.id)
    return jsonify(
        {
            "gara_id": gara.id,
            "rounds_count": gara.rounds_count,
            "defaults": {
                "discipline": gara.discipline,
                "distance": gara.distance,
                "is_race_to": gara.is_race_to,
                "is_multi_set": gara.is_multi_set,
                "match_distance": gara.match_distance,
                "is_race_to_sets": getattr(gara, "is_race_to_sets", True),
            },
            "overrides": [_serialize_round_config(c) for c in configs],
        }
    )


@competition_bp.route(
    "/<int:gara_id>/round-config/<int:round_number>", methods=["POST"]
)
@login_required
@gara_manager_required
def upsert_round_config(gara_id: int, round_number: int):
    """Crea o aggiorna l'override per il turno indicato.

    Body JSON: { discipline?, distance?, is_race_to?, is_multi_set?,
                 match_distance?, is_race_to_sets? }

    NULL omesso = nessun override per quel campo.
    Risponde 409 se la gara non è in stato setup.
    """
    from models.competition.round_configuration import RoundConfiguration
    from models.transaction.manager import transactional

    gara = get_or_ajax_404(Gara, gara_id, "Gara")

    if gara.status != GaraStatus.SETUP.value:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Gli override per turno sono modificabili "
                    "solo in stato setup.",
                }
            ),
            409,
        )

    if round_number < 1 or round_number > gara.rounds_count:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Turno {round_number} non valido per questa gara.",
                }
            ),
            400,
        )

    payload = request.get_json(silent=True) or {}

    # Sui formati a tabellone il numero esatto di rack non e' ammesso (conta
    # solo chi passa il turno), e l'override per turno era l'ultima porta
    # rimasta aperta: `Match.effective_is_race_to` legge la RoundConfiguration
    # **prima** dei default della gara (ADR-027), quindi da qui si poteva
    # ancora ottenere un match a rack esatti — e con un numero pari un nodo
    # senza vincitore, che blocca la generazione del turno successivo.
    from models.matchmaking.configuration import BRACKET_STRATEGIES

    if gara.matchmaking_strategy in BRACKET_STRATEGIES:
        chiede_esatto = payload.get("is_race_to") is False
        chiede_set_esatti = payload.get("is_race_to_sets") is False
        if chiede_esatto or chiede_set_esatti:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Sul tabellone si gioca sempre a chi arriva "
                        "prima: il numero esatto di rack non è ammesso, "
                        "nemmeno per un singolo turno.",
                    }
                ),
                400,
            )

    @transactional(domain="competition")
    def _persist() -> RoundConfiguration:
        return RoundConfiguration.create_or_update(
            gara_id=gara.id,
            round_number=round_number,
            discipline=payload.get("discipline"),
            distance=payload.get("distance"),
            is_race_to=payload.get("is_race_to"),
            is_multi_set=payload.get("is_multi_set"),
            match_distance=payload.get("match_distance"),
            is_race_to_sets=payload.get("is_race_to_sets"),
        )

    try:
        config = _persist()
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400

    return jsonify({"success": True, "config": _serialize_round_config(config)})


@competition_bp.route(
    "/<int:gara_id>/round-config/<int:round_number>", methods=["DELETE"]
)
@login_required
@gara_manager_required
def delete_round_config(gara_id: int, round_number: int):
    """Rimuove l'override per il turno indicato. Idempotente."""
    from models.competition.round_configuration import RoundConfiguration
    from models.transaction.manager import transactional

    gara = get_or_ajax_404(Gara, gara_id, "Gara")

    if gara.status != GaraStatus.SETUP.value:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Gli override per turno sono modificabili "
                    "solo in stato setup.",
                }
            ),
            409,
        )

    @transactional(domain="competition")
    def _delete() -> bool:
        return RoundConfiguration.delete_for_round(gara.id, round_number)

    deleted = _delete()
    return jsonify({"success": True, "deleted": deleted})
