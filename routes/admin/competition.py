# routes/admin/competition.py
"""Competition (Prova) management blueprint for admin interface."""

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
)
from flask_login import login_required, current_user
from datetime import datetime

from models import (
    db,
    Tournament,
    Prova,
    Inscription,
    Match,
)
from models.status_enum import (
    ProvaStatus,
    MatchStatus,
)
from models.competition.models import WithdrawPolicy
from utils import (
    prova_manager_required,
    admin_required,
    trio_manager_required,
)
from models.competition.services import ProvaService
from amalfi.engine import get_amalfi_classification, validate_amalfi_configuration
from models.classification.models import RoundClassification

# Competition management blueprint
competition_bp = Blueprint("competition", __name__)


@competition_bp.route("/create_standalone", methods=["GET", "POST"])
@login_required
@admin_required
def create_prova_standalone():
    """Crea prova standalone (solo admin)"""
    if request.method == "POST":
        try:
            # Campi base
            name = request.form.get("name", "").strip()
            if not name:
                flash("Il nome della competizione è obbligatorio!", "error")
                return redirect(url_for("admin.competition.create_prova_standalone"))

            date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            
            # Campi opzionali
            location = request.form.get("location", "").strip()
            description = request.form.get("description", "").strip()
            rounds_count = int(request.form.get("rounds_count", 3))
            min_participants = int(request.form.get("min_participants", 2))
            max_participants = request.form.get("max_participants")
            max_participants = int(max_participants) if max_participants else None
            entry_fee = float(request.form.get("entry_fee", 0.0))

            # Game settings
            discipline = request.form["discipline"]
            distance = int(request.form["distance"])
            exact_number = "exact_number" in request.form
            best_of = not exact_number
            withdraw_policy = request.form.get("withdraw_policy", WithdrawPolicy.EXCLUDE.value)

            # Crea la prova standalone usando il service layer (senza tournament_id)
            prova = ProvaService.create_prova(
                tournament_id=None,  # Prove standalone non hanno torneo
                number=1,  # Sempre 1 per prove standalone
                name=name,
                date=date,
                location=location,
                description=description,
                rounds_count=rounds_count,
                min_participants=min_participants,
                max_participants=max_participants,
                entry_fee=entry_fee,
                discipline=discipline,
                distance=distance,
                best_of=best_of,
                withdraw_policy=withdraw_policy,
                director_id=current_user.id  # L'admin che crea è il direttore
            )

            flash(f"Gara singola '{name}' creata con successo!", "success")
            return redirect(url_for("admin.competition.prova_detail", prova_id=prova.id))

        except ValueError as e:
            flash(f"Errore nella creazione: {str(e)}", "error")
            return redirect(url_for("admin.competition.create_prova_standalone"))
        except Exception as e:
            flash(f"Errore imprevisto: {str(e)}", "error")
            return redirect(url_for("admin.competition.create_prova_standalone"))

    # GET request - show form
    # Recupera luoghi utilizzati in precedenza
    recent_locations = db.session.query(Prova.location).distinct().filter(
        Prova.location.isnot(None), 
        Prova.location != ""
    ).limit(10).all()
    recent_locations = [loc[0] for loc in recent_locations if loc[0]]
    
    return render_template(
        "admin/prova_create_standalone.html",
        WithdrawPolicy=WithdrawPolicy,
        recent_locations=recent_locations
    )


@competition_bp.route("/create", methods=["POST"])
@login_required
def create_prova():
    """Crea nuova prova - Aggiornata per supportare standalone"""

    # Determina se è standalone o per torneo
    tournament_id = request.form.get("tournament_id")
    is_standalone = tournament_id == "standalone" or not tournament_id

    if is_standalone:
        # Redirect alla route standalone
        return redirect(url_for("admin.competition.create_prova_standalone"))

    # Codice esistente per prove con torneo...
    if not tournament_id:
        flash("Tournament ID mancante!", "error")
        return redirect(url_for("dashboard.dashboard"))

    tournament_id = int(tournament_id)
    tournament = db.session.get(Tournament, tournament_id)
    if tournament is None:
        abort(404)

    # Verifica permessi sul torneo
    if not (
        current_user.is_admin
        or (
            current_user.is_director
            and any(
                td.user_id == current_user.id for td in tournament.directors_association
            )
        )
    ):
        flash("Non puoi creare prove in questo torneo.", "error")
        return redirect(url_for("dashboard.dashboard"))

    number = int(request.form["number"])

    # Verifica che il numero prova non esista già
    existing = Prova.query.filter_by(tournament_id=tournament_id, number=number).first()
    if existing:
        flash(f"La prova {number} esiste già!")
        return redirect(
            url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
        )

    # Campi base
    name = request.form.get("name", f"Prova {number}")
    date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()

    # Nuovi campi
    location = request.form.get("location", "")
    description = request.form.get("description", "")
    rounds_count = int(request.form.get("rounds_count", 3))
    min_participants = int(request.form.get("min_participants", 2))
    max_participants = request.form.get("max_participants")
    max_participants = int(max_participants) if max_participants else None
    entry_fee = float(request.form.get("entry_fee", 0.0))

    # Game settings
    discipline = request.form["discipline"]
    distance = int(request.form["distance"])
    exact_number = "exact_number" in request.form
    best_of = not exact_number

    # Crea la prova usando il service layer
    withdraw_policy = request.form.get("withdraw_policy", WithdrawPolicy.EXCLUDE.value)
    ProvaService.create_prova(
        tournament_id=tournament_id,
        number=number,
        name=name,
        date=date,
        location=location,
        description=description,
        rounds_count=rounds_count,
        min_participants=min_participants,
        max_participants=max_participants,
        entry_fee=entry_fee,
        discipline=discipline,
        distance=distance,
        best_of=best_of,
        withdraw_policy=withdraw_policy,
    )

    flash(f"Prova {number} creata con successo!")
    return redirect(
        url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
    )


@competition_bp.route("/<int:prova_id>/edit", methods=["GET", "POST"])
@login_required
@prova_manager_required
def edit_prova(prova_id):
    """Modifica prova"""
    prova = db.session.get(Prova, prova_id)
    if prova is None:
        abort(404)

    if not prova.can_be_modified():
        flash("Impossibile modificare la prova: ci sono già delle iscrizioni!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    if request.method == "POST":
        # Usa il service layer invece del direct database access
        try:
            max_participants = request.form.get("max_participants")
            max_participants = int(max_participants) if max_participants else None

            exact_number = "exact_number" in request.form
            best_of = not exact_number

            ProvaService.update_prova(
                prova_id=prova_id,
                name=request.form.get("name", prova.name),
                date_str=request.form["date"],
                location=request.form.get("location", ""),
                description=request.form.get("description", ""),
                rounds_count=int(request.form.get("rounds_count", 3)),
                min_participants=int(request.form.get("min_participants", 2)),
                max_participants=max_participants,
                entry_fee=float(request.form.get("entry_fee", 0.0)),
                discipline=request.form["discipline"],
                distance=int(request.form["distance"]),
                best_of=best_of,
                withdraw_policy=request.form.get(
                    "withdraw_policy", WithdrawPolicy.EXCLUDE.value
                ),
            )
            flash("Prova aggiornata con successo!")
        except ValueError as ve:
            flash(str(ve), "error")

        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    return render_template(
        "admin/prova_edit.html", prova=prova, WithdrawPolicy=WithdrawPolicy
    )


@competition_bp.route("/<int:prova_id>/delete", methods=["POST"])
@login_required
@prova_manager_required
def delete_prova(prova_id):
    """Cancella prova"""
    prova = db.session.get(Prova, prova_id)
    if prova is None:
        abort(404)
    tournament_id = prova.tournament_id
    prova_name = f"Prova {prova.number}"

    # Usa il service layer invece del direct database access
    try:
        ProvaService.delete_prova(prova_id)
        flash(f"{prova_name} cancellata con successo!")
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    if not tournament_id:
        return redirect(url_for("dashboard.dashboard"))
    return redirect(
        url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
    )


@competition_bp.route("/<int:prova_id>/cancel", methods=["POST"])
@login_required
@prova_manager_required
def cancel_prova(prova_id):
    """Cancella prova con notifiche ai partecipanti"""
    prova = db.session.get(Prova, prova_id)
    if prova is None:
        abort(404)
    
    tournament_id = prova.tournament_id
    prova_name = f"Prova {prova.number}"
    
    # Verifica che la prova possa essere cancellata
    if prova.status not in ['setup', 'inscription']:
        flash("La prova non può essere cancellata in questo stato!", "error")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    try:
        # Usa il service layer per cancellare con notifiche
        ProvaService.cancel_prova_with_notifications(prova_id, current_user.id)
        flash(f"{prova_name} cancellata con successo! I partecipanti sono stati notificati.")
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    if not tournament_id:
        return redirect(url_for("dashboard.dashboard"))
    return redirect(
        url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
    )


@competition_bp.route("/<int:prova_id>")
@login_required
@prova_manager_required
def prova_detail(prova_id):
    """Dettaglio prova con iscrizioni e partite"""
    prova = db.session.get(Prova, prova_id)
    if prova is None:
        abort(404)
    
    # Forza un refresh per assicurarsi di avere i dati più aggiornati
    db.session.refresh(prova)
    
    # Ottieni iscrizioni ordinate per classifica attuale
    inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()
    
    # Se ci sono turni giocati, ordina per classifica
    if prova.current_round > 0:
        from models.classification.models import RoundClassification
        
        # Cerca la classifica più recente disponibile (partendo dal turno corrente e scendendo)
        latest_classification = None
        for round_num in range(prova.current_round, 0, -1):
            latest_classification = RoundClassification.query.filter_by(
                prova_id=prova_id, round_number=round_num
            ).order_by(RoundClassification.position).all()
            if latest_classification:
                break
        
        if latest_classification:
            # Crea un dizionario per ordinare le iscrizioni per posizione in classifica
            position_map = {cls.user_id: cls.position for cls in latest_classification}
            inscriptions.sort(key=lambda ins: position_map.get(ins.user_id, 999))
        else:
            # Fallback: ordina per initial_order se non c'è classifica
            inscriptions.sort(key=lambda ins: ins.initial_order or 999)
    else:
        # Prima dell'inizio: ordina per initial_order
        inscriptions.sort(key=lambda ins: ins.initial_order or 999)
    
    matches = (
        Match.query.filter_by(prova_id=prova_id)
        .order_by(Match.round_number, Match.id)
        .all()
    )

    return render_template(
        "admin/prova_detail.html",
        prova=prova,
        inscriptions=inscriptions,
        matches=matches,
    )


@competition_bp.route("/<int:prova_id>/open_inscriptions", methods=["POST"])
@login_required
@prova_manager_required
def open_inscriptions(prova_id):
    """Apri iscrizioni per una prova"""
    # Ottieni le date UTC dal JavaScript
    inscription_start = datetime.strptime(
        request.form["inscription_start_utc"], "%Y-%m-%dT%H:%M:%S"
    )
    inscription_end = datetime.strptime(
        request.form["inscription_end_utc"], "%Y-%m-%dT%H:%M:%S"
    )

    # Usa il service layer invece del direct database access
    try:
        ProvaService.open_inscriptions(prova_id, inscription_start, inscription_end)
        flash(
            "Iscrizioni aperte! Gli orari sono gestiti "
            "automaticamente nel tuo timezone locale."
        )
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))


@competition_bp.route("/<int:prova_id>/modify_inscription_dates", methods=["POST"])
@login_required
@prova_manager_required
def modify_inscription_dates(prova_id):
    """Modifica date di iscrizione per una prova"""
    inscription_start = datetime.strptime(
        request.form["inscription_start_utc"], "%Y-%m-%dT%H:%M:%S"
    )
    inscription_end = datetime.strptime(
        request.form["inscription_end_utc"], "%Y-%m-%dT%H:%M:%S"
    )

    # Usa il service layer invece del direct database access
    try:
        ProvaService.modify_inscription_dates(
            prova_id, inscription_start, inscription_end
        )
        flash("Date di iscrizione aggiornate con successo!")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))


@competition_bp.route("/<int:prova_id>/start_first_round", methods=["POST"])
@login_required
@prova_manager_required
def start_first_round(prova_id):
    """Avvia primo turno della prova"""
    # Usa il service layer invece del direct database access
    try:
        ProvaService.start_first_round(prova_id)
        flash("Primo turno avviato!")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))


@competition_bp.route("/<int:prova_id>/results_overview")
@login_required
@prova_manager_required
def prova_results_overview(prova_id):
    """Overview risultati prova per inserimento rapido (admin)"""
    prova = Prova.query.get_or_404(prova_id)

    # Organizza partite per turno
    matches_by_round = {}
    for round_num in range(1, prova.rounds_count + 1):
        matches_by_round[round_num] = (
            Match.query.filter_by(prova_id=prova_id, round_number=round_num)
            .order_by(Match.id)
            .all()
        )

    # Debug
    import logging
    logging.warning(f"DEBUG results_overview: prova.rounds_count = {prova.rounds_count}")
    for round_num, matches in matches_by_round.items():
        logging.warning(f"DEBUG results_overview: Round {round_num} has {len(matches)} matches")

    return render_template(
        "admin/prova_result_overview.html",
        prova=prova,
        matches_by_round=matches_by_round,
    )


# ============ SISTEMA AMALFI ============


@competition_bp.route("/amalfi/classification/<int:prova_id>/<int:round_number>")
@login_required
@prova_manager_required
def amalfi_classification(prova_id, round_number):
    """Visualizza classifica Amalfi dopo un turno specifico"""
    prova = Prova.query.get_or_404(prova_id)

    # Verifica che il turno sia valido
    if round_number < 1 or round_number > prova.rounds_count:
        flash(f"Turno {round_number} non valido per questa prova!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    # Verifica che il turno sia completato
    matches_in_round = Match.query.filter_by(
        prova_id=prova_id, round_number=round_number
    ).all()

    if not matches_in_round:
        flash(f"Il turno {round_number} non è ancora iniziato!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    # Controlla se tutti i match del turno sono completati
    incomplete_matches = [
        m for m in matches_in_round if m.status != MatchStatus.COMPLETED.value
    ]
    if incomplete_matches:
        flash(
            f"Il turno {round_number} non è ancora completato! "
            f"Mancano {len(incomplete_matches)} partite."
        )
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    # Ottieni o calcola classifica
    classification = get_amalfi_classification(prova_id, round_number)
    if not classification:
        # Calcola classifica se non esiste (questo metodo ritorna tuple, non oggetti)
        RoundClassification.calculate_classification_after_round(
            prova_id, round_number
        )
        # Ricarica la classifica dopo il calcolo (ora sono oggetti RoundClassification)
        classification = get_amalfi_classification(prova_id, round_number)

    # Statistiche aggiuntive
    total_players = len(classification)
    inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()

    return render_template(
        "admin/amalfi_classification.html",
        prova=prova,
        round_number=round_number,
        classification=classification,
        total_players=total_players,
        inscriptions=inscriptions,
    )


@competition_bp.route("/<int:prova_id>/amalfi/preview_round/<int:round_number>")
@login_required
@prova_manager_required
def amalfi_preview_round(prova_id, round_number):
    """Anteprima di un turno Amalfi senza creare le partite"""
    from amalfi.engine import AmalfiEngine
    
    prova = db.session.get(Prova, prova_id)
    if prova is None:
        return jsonify({"success": False, "error": "Prova non trovata"}), 404
    
    try:
        # Validazioni preliminari
        if round_number < 1 or round_number > prova.rounds_count:
            return jsonify({"success": False, "error": f"Turno {round_number} non valido!"})
            
        if round_number <= prova.current_round:
            return jsonify({"success": False, "error": f"Il turno {round_number} è già stato avviato!"})
            
        if round_number != prova.current_round + 1:
            return jsonify({"success": False, "error": f"Devi avviare prima il turno {prova.current_round + 1}!"})

        # Usa il motore Amalfi per calcolare gli abbinamenti senza crearli
        engine = AmalfiEngine(prova)
        preview_data = engine.preview_round_pairings(round_number)
        
        return jsonify({
            "success": True,
            "matches": preview_data["matches"],
            "stats": preview_data["stats"],
            "salto": preview_data.get("salto", 0)
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@competition_bp.route(
    "/<int:prova_id>/amalfi/start_round/<int:round_number>", methods=["POST"]
)
@login_required
@prova_manager_required
def amalfi_start_round(prova_id, round_number):
    """Avvia un turno specifico con algoritmo Amalfi"""
    prova = Prova.query.get_or_404(prova_id)

    try:
        # Validazioni preliminari
        if round_number < 1 or round_number > prova.rounds_count:
            return jsonify({"success": False, "error": f"Turno {round_number} non valido!"})
            
        # Controlla se il turno è già stato avviato (idempotenza)
        existing_matches = Match.query.filter_by(
            prova_id=prova_id, round_number=round_number
        ).first()
        if existing_matches:
            return jsonify({"success": False, "error": f"Il turno {round_number} è già stato avviato!"})
            
        if round_number != prova.current_round + 1:
            return jsonify({"success": False, "error": f"Devi avviare prima il turno {prova.current_round + 1}!"})

        validation = validate_amalfi_configuration(prova)
        if not validation["is_valid"]:
            errors = "; ".join(validation["errors"])
            return jsonify({"success": False, "error": f"Errore Amalfi: {errors}"})

        if round_number > 1:
            prev_matches = Match.query.filter_by(
                prova_id=prova_id, round_number=round_number - 1
            ).all()
            incomplete_prev = [
                m for m in prev_matches if m.status != MatchStatus.COMPLETED.value
            ]
            if incomplete_prev:
                return jsonify({"success": False, "error": f"Completa prima tutte le partite del turno {round_number-1}!"})

        # Crea il turno Amalfi usando il service layer
        total, n_normal, n_bye, n_trio = ProvaService.create_amalfi_round(
            prova_id, round_number
        )

        # Aggiorna lo stato della prova
        if prova.status != ProvaStatus.PLAYING.value:
            prova = ProvaService.start_playing(prova.id)
        
        # Ricarica sempre l'oggetto per assicurarsi di lavorare con i dati freschi
        db.session.refresh(prova)
        
        # Aggiorna il turno corrente DOPO il cambio di stato
        prova.current_round = round_number
        db.session.add(prova)
        db.session.commit()

        # Costruisci il messaggio di successo
        message = f"Turno {round_number} avviato con successo! Creati {total} abbinamenti Amalfi."
        details = []
        if n_normal:
            details.append(f"Abbinamenti normali: {n_normal}")
        if n_bye:
            details.append(f"Partite vs X: {n_bye}")
        if n_trio:
            details.append(f"Trii: {n_trio}")

        return jsonify({
            "success": True, 
            "message": message,
            "details": details,
            "redirect": url_for("admin.competition.prova_detail", prova_id=prova_id)
        })

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)})
    except Exception as e:
        return jsonify({"success": False, "error": f"Errore durante la creazione del turno: {str(e)}"})


# ============ GESTIONE TRII ============


@competition_bp.route("/trio/<int:trio_id>/add_rack", methods=["POST"])
@login_required
@trio_manager_required
def trio_add_rack(trio_id):
    """Aggiungi rack a partita trio"""
    try:
        winner_id = int(request.form["winner_id"])

        # Usa il service layer invece del direct database access
        result = ProvaService.add_trio_rack(trio_id, winner_id)
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
        ProvaService.reset_trio(trio_id)
        return jsonify({"success": True, "message": "Trio resettato con successo"})

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 500
    except Exception as e:
        return jsonify({"error": f"Errore durante reset trio: {str(e)}"}), 500
