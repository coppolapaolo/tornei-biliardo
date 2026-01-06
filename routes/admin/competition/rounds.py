# routes/admin/competition/rounds.py
"""Round management routes for competitions."""

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
)
from flask_login import login_required
from models.transaction.manager import transactional

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
from models.matchmaking.strategies.amalfi import AmalfiStrategy
from models.classification.models import RoundClassification
from models.classification.services import RoundClassificationService
from utils import gara_manager_required

from . import competition_bp


@competition_bp.route("/<int:gara_id>/start_first_round", methods=["POST"])
@login_required
@gara_manager_required
@transactional()
def start_first_round(gara_id):
    """Avvia primo turno della gara (o tutti i turni per strategia Random)"""
    try:
        gara = db.session.get(Gara, gara_id)

        GaraService.start_first_round(gara_id)

        if gara and gara.matchmaking_strategy == "random":
            flash("Gara avviata! Tutti i turni sono stati creati.", "success")
        else:
            flash("Primo turno avviato!", "success")

    except ValueError as ve:
        flash(str(ve), "error")
    except Exception as e:
        # Log the full error for debugging
        import traceback

        print(f"ERROR starting first round: {str(e)}")
        print(traceback.format_exc())
        flash(f"Errore nell'avvio del turno: {str(e)}", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/cancel_first_round", methods=["POST"])
@login_required
@gara_manager_required
def cancel_first_round(gara_id):
    """Cancella l'avvio del primo turno se non ci sono risultati"""
    try:
        GaraService.cancel_first_round_startup(gara_id)
        flash(
            "Avvio del primo turno cancellato con successo! "
            "La gara è tornata allo stato di iscrizioni.",
            "success",
        )
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/cancel_current_round", methods=["POST"])
@login_required
@gara_manager_required
def cancel_current_round(gara_id):
    """Cancella l'avvio del turno corrente se non ci sono risultati"""
    try:
        gara = GaraService.cancel_current_round_startup(gara_id)
        flash(
            f"Avvio del turno {gara.current_round + 1} cancellato con successo!",
            "success",
        )
    except ValueError as ve:
        flash(str(ve), "error")
    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/terminate", methods=["POST"])
@login_required
@gara_manager_required
def terminate_gara(gara_id):
    """Termina esplicitamente la gara dopo che tutti i turni sono completati"""
    gara = Gara.query.get_or_404(gara_id)

    # Verifica che la gara sia in stato "campionato_completed" (tutti i turni finiti)
    if gara.status != GaraStatus.PLAYING.value:
        flash("La gara non è in corso!", "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    real_status = gara.get_real_status()
    if real_status != "campionato_completed":
        flash("Non tutti i turni sono ancora completati!", "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    try:
        GaraService.complete(gara_id)
        flash("Gara terminata con successo! I risultati sono ora definitivi.", "success")
    except Exception as e:
        flash(f"Errore durante la terminazione della gara: {str(e)}", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


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

    # Controlla se tutti i match del turno sono completati
    # Bye matches are considered completed automatically
    incomplete_matches = [
        m for m in matches_in_round
        if m.status != MatchStatus.COMPLETED.value and not m.is_bye
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
@transactional(domain="competition")
def amalfi_start_round(gara_id, round_number):
    """Avvia un turno specifico con algoritmo Amalfi"""
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
            incomplete_prev = [
                m for m in prev_matches if m.status != MatchStatus.COMPLETED.value
            ]
            if incomplete_prev:
                return jsonify(
                    {
                        "success": False,
                        "error": f"Completa prima tutte le partite del "
                        f"turno {round_number-1}!",
                    }
                )

        # Crea il turno Amalfi usando il service layer
        total, n_normal, n_bye, n_trio = GaraService.create_amalfi_round(
            gara_id, round_number
        )

        # Aggiorna lo stato della gara
        if gara.status != GaraStatus.PLAYING.value:
            gara = GaraService.start_playing(gara.id)

        # Ricarica sempre l'oggetto per assicurarsi di lavorare con i dati freschi
        db.session.refresh(gara)

        # Aggiorna il turno corrente DOPO il cambio di stato
        gara.current_round = round_number
        db.session.add(gara)
        # Changes will be committed by transaction decorator

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
        return jsonify(
            {
                "success": False,
                "error": f"Errore durante la creazione del turno: {str(e)}",
            }
        )


@competition_bp.route("/<int:gara_id>/start_round/<int:round_number>", methods=["POST"])
@login_required
@gara_manager_required
@transactional(domain="competition")
def start_round_generic(gara_id, round_number):
    """Avvia un turno specifico con la strategia configurata nella gara"""
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
            incomplete_prev = [
                m for m in prev_matches if m.status != MatchStatus.COMPLETED.value
            ]
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

        # Crea il turno usando la strategia configurata
        total, n_normal, n_bye, n_trio = GaraService.create_round_with_strategy(
            gara_id, round_number, discipline_override
        )

        # Aggiorna lo stato della gara
        if gara.status != GaraStatus.PLAYING.value:
            gara = GaraService.start_playing(gara.id)

        # Ricarica sempre l'oggetto per assicurarsi di lavorare con i dati freschi
        db.session.refresh(gara)

        # Aggiorna il turno corrente DOPO il cambio di stato
        gara.current_round = round_number
        db.session.add(gara)
        # Changes will be committed by transaction decorator

        # Assign tables to new round matches
        from models.match.table_assignment_service import TableAssignmentService
        tables_assigned = TableAssignmentService.assign_tables_to_round(gara_id, round_number)

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
        return jsonify(
            {
                "success": False,
                "error": f"Errore durante la creazione del turno: {str(e)}",
            }
        )


# ====================================================================
# ADVANCED ROUND MANAGEMENT ROUTES - Use Case 8
# ====================================================================


@competition_bp.route("/<int:gara_id>/round_management")
@login_required
@gara_manager_required
def round_management_overview(gara_id):
    """Overview of round management with modification capabilities."""
    from models.competition.round_manager import AdvancedRoundManager

    gara = db.session.get(Gara, gara_id)
    if not gara:
        abort(404)

    # Get round modification summary
    rounds_summary = AdvancedRoundManager.get_round_modification_summary(gara_id)

    # Get all matches grouped by round
    matches_by_round = {}
    all_matches = (
        Match.query.filter_by(gara_id=gara_id)
        .order_by(Match.round_number, Match.id)
        .all()
    )

    for match in all_matches:
        round_num = match.round_number
        if round_num not in matches_by_round:
            matches_by_round[round_num] = []
        matches_by_round[round_num].append(match)

    return render_template(
        "admin/round_management.html",
        gara=gara,
        rounds_summary=rounds_summary,
        matches_by_round=matches_by_round,
    )


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

    # No more admin_override support (removed October 2025)
    success, message = AdvancedRoundManager.reset_match_with_validation(match_id)

    if success:
        flash(message, "success")
    else:
        flash(message, "danger")

    return redirect(
        url_for("admin.competition.round_management_overview", gara_id=gara_id)
    )


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

    # No more admin_override support (removed October 2025)
    success, message = AdvancedRoundManager.cancel_round(gara_id, round_number)

    if success:
        flash(message, "success")
    else:
        flash(message, "danger")

    return redirect(
        url_for("admin.competition.round_management_overview", gara_id=gara_id)
    )


@competition_bp.route(
    "/<int:gara_id>/round/<int:round_number>/bulk_reset", methods=["POST"]
)
@login_required
@gara_manager_required
def bulk_reset_round_matches(gara_id, round_number):
    """Reset all matches in a round."""
    from models.competition.round_manager import AdvancedRoundManager

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

    return redirect(
        url_for("admin.competition.round_management_overview", gara_id=gara_id)
    )


@competition_bp.route("/<int:gara_id>/match/<int:match_id>/modification_check")
@login_required
@gara_manager_required
def check_match_modification(gara_id, match_id):
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

    gara = db.session.get(Gara, gara_id)
    if not gara:
        return jsonify({"error": "Gara non trovata"}), 404

    rounds_summary = AdvancedRoundManager.get_round_modification_summary(gara_id)

    return jsonify(
        {
            "current_round": gara.current_round,
            "total_rounds": gara.rounds_count,
            "gara_status": gara.status,
            "rounds_summary": rounds_summary,
        }
    )
