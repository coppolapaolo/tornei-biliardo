# routes/admin/competition.py
"""Competition (Gara) management blueprint for admin interface."""

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
    Campionato,
    Gara,
    Inscription,
    Match,
)
from models.status_enum import (
    GaraStatus,
    MatchStatus,
)
from models.competition.models import WithdrawPolicy
from utils import (
    gara_manager_required,
    admin_required,
    director_or_admin_required,
    trio_manager_required,
)
from models.competition.services import GaraService
from amalfi.engine import get_amalfi_classification, validate_amalfi_configuration
from models.classification.models import RoundClassification

# Competition management blueprint
competition_bp = Blueprint("competition", __name__)


@competition_bp.route("/create_standalone", methods=["GET", "POST"])
@login_required
@director_or_admin_required
def create_gara_standalone():
    """Crea gara standalone (admin o director)"""
    if request.method == "POST":
        try:
            # Campi base
            name = request.form.get("name", "").strip()
            if not name:
                flash("Il nome della competizione è obbligatorio!", "error")
                return redirect(url_for("admin.competition.create_gara_standalone"))

            date_str = request.form["date"]
            time_str = request.form.get("time", "20:00")
            datetime_obj = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            date = datetime_obj.date()
            
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

            # Strategy configuration
            matchmaking_strategy = request.form.get("matchmaking_strategy", "amalfi")
            first_round_policy = request.form.get("first_round_policy", "random")
            odd_number_policy = request.form.get("odd_number_policy", "bye")
            anti_rematch_enabled = request.form.get("anti_rematch_enabled") == "on"
            rating_type = request.form.get("rating_type", "fargo")
            
            # Validazione della configurazione delle strategie
            from models.matchmaking.configuration import StrategyConfiguration, MatchmakingStrategy, FirstRoundPolicy, OddNumberPolicy, RatingType
            
            try:
                strategy_config = StrategyConfiguration(
                    strategy=MatchmakingStrategy(matchmaking_strategy),
                    first_round_policy=FirstRoundPolicy(first_round_policy),
                    odd_number_policy=OddNumberPolicy(odd_number_policy),
                    anti_rematch_enabled=anti_rematch_enabled,
                    rounds_count=rounds_count,
                    rating_type=RatingType(rating_type) if first_round_policy == "rating" else None
                )
                
                # Valida la configurazione con la distanza
                errors = strategy_config.validate(distance=distance)
                if errors:
                    flash(f"Configurazione non valida: {', '.join(errors)}", "error")
                    return redirect(url_for("admin.competition.create_gara_standalone"))
            except ValueError as e:
                flash(f"Configurazione strategia non valida: {str(e)}", "error")
                return redirect(url_for("admin.competition.create_gara_standalone"))

            # Crea la gara standalone usando il service layer (senza campionato_id)
            gara = GaraService.create_gara(
                campionato_id=None,  # Gare standalone non hanno campionato
                number=1,  # Sempre 1 per gare standalone
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
                director_id=current_user.id,  # L'admin che crea è il direttore
                matchmaking_strategy=matchmaking_strategy,
                first_round_policy=first_round_policy,
                odd_number_policy=odd_number_policy,
                anti_rematch_enabled=anti_rematch_enabled,
                rating_type=rating_type
            )

            flash(f"Gara singola '{name}' creata con successo!", "success")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara.id))

        except ValueError as e:
            flash(f"Errore nella creazione: {str(e)}", "error")
            return redirect(url_for("admin.competition.create_gara_standalone"))
        except Exception as e:
            flash(f"Errore imprevisto: {str(e)}", "error")
            return redirect(url_for("admin.competition.create_gara_standalone"))

    # GET request - show form
    # Recupera luoghi utilizzati in precedenza
    recent_locations = db.session.query(Gara.location).distinct().filter(
        Gara.location.isnot(None), 
        Gara.location != ""
    ).limit(10).all()
    recent_locations = [loc[0] for loc in recent_locations if loc[0]]
    
    # Ottieni le strategie disponibili
    available_strategies = GaraService.get_available_strategies()
    
    return render_template(
        "admin/gara_create_standalone.html",
        WithdrawPolicy=WithdrawPolicy,
        recent_locations=recent_locations,
        available_strategies=available_strategies
    )


@competition_bp.route("/api/strategy_constraints/<strategy>")
@login_required
@admin_required
def get_strategy_constraints(strategy):
    """API endpoint per ottenere i vincoli di una strategia."""
    from models.matchmaking.configuration import STRATEGY_CONSTRAINTS, MatchmakingStrategy
    
    try:
        strategy_enum = MatchmakingStrategy(strategy)
        constraints = STRATEGY_CONSTRAINTS.get(strategy_enum, {})
        
        return jsonify({
            "success": True,
            "constraints": constraints,
            "display_name": strategy.replace("_", " ").title(),
            "description": constraints.get("description", "")
        })
    except ValueError:
        return jsonify({
            "success": False,
            "error": f"Strategia '{strategy}' non valida"
        }), 400


@competition_bp.route("/create", methods=["POST"])
@login_required
def create_gara():
    """Crea nuova gara - Aggiornata per supportare standalone"""

    # Determina se è standalone o per campionato
    campionato_id = request.form.get("campionato_id")
    is_standalone = campionato_id == "standalone" or not campionato_id

    if is_standalone:
        # Redirect alla route standalone
        return redirect(url_for("admin.competition.create_gara_standalone"))

    # Codice esistente per gare con campionato...
    if not campionato_id:
        flash("Campionato ID mancante!", "error")
        return redirect(url_for("dashboard.dashboard"))

    campionato_id = int(campionato_id)
    campionato = db.session.get(Campionato, campionato_id)
    if campionato is None:
        abort(404)

    # Verifica permessi sul campionato
    from models.user.models import DirectorAssignment
    is_campionato_director = (
        db.session.query(DirectorAssignment)
        .filter(
            DirectorAssignment.entity_type == 'campionato',
            DirectorAssignment.entity_id == campionato_id,
            DirectorAssignment.user_id == current_user.id
        )
        .first() is not None
    )
    
    if not (
        current_user.is_admin
        or (current_user.is_director and is_campionato_director)
    ):
        flash("Non puoi creare gare in questo campionato.", "error")
        return redirect(url_for("dashboard.dashboard"))

    number = int(request.form["number"])

    # Verifica che il numero gara non esista già
    existing = Gara.query.filter_by(campionato_id=campionato_id, number=number).first()
    if existing:
        flash(f"La gara {number} esiste già!")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    # Campi base
    name = request.form.get("name", f"Gara {number}")
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

    # Crea la gara usando il service layer
    withdraw_policy = request.form.get("withdraw_policy", WithdrawPolicy.EXCLUDE.value)
    GaraService.create_gara(
        campionato_id=campionato_id,
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

    flash(f"Gara {number} creata con successo!")
    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@competition_bp.route("/<int:gara_id>/edit", methods=["GET", "POST"])
@login_required
@gara_manager_required
def edit_gara(gara_id):
    """Modifica gara"""
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        abort(404)

    if not gara.can_be_modified():
        flash("Impossibile modificare la gara: ci sono già delle iscrizioni!")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    if request.method == "POST":
        # Usa il service layer invece del direct database access
        try:
            max_participants = request.form.get("max_participants")
            max_participants = int(max_participants) if max_participants else None

            exact_number = "exact_number" in request.form
            best_of = not exact_number

            GaraService.update_gara(
                gara_id=gara_id,
                name=request.form.get("name", gara.name),
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
            flash("Gara aggiornata con successo!")
        except ValueError as ve:
            flash(str(ve), "error")

        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Get available strategies for the form
    available_strategies = GaraService.get_available_strategies()
    
    # Get recent locations for datalist
    recent_locations = db.session.query(Gara.location).distinct().filter(
        Gara.location.isnot(None), Gara.location != ""
    ).limit(10).all()
    recent_locations = [loc[0] for loc in recent_locations if loc[0]]
    
    return render_template(
        "admin/gara_edit.html", 
        gara=gara, 
        WithdrawPolicy=WithdrawPolicy,
        available_strategies=available_strategies,
        recent_locations=recent_locations
    )


@competition_bp.route("/<int:gara_id>/delete", methods=["POST"])
@login_required
@gara_manager_required
def delete_gara(gara_id):
    """Cancella gara"""
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        abort(404)
    campionato_id = gara.campionato_id
    gara_name = f"Gara {gara.number}"

    # Usa il service layer invece del direct database access
    try:
        GaraService.delete_gara(gara_id)
        flash(f"{gara_name} cancellata con successo!")
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    if not campionato_id:
        return redirect(url_for("dashboard.dashboard"))
    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@competition_bp.route("/<int:gara_id>/cancel", methods=["POST"])
@login_required
@gara_manager_required
def cancel_gara(gara_id):
    """Cancella gara con notifiche ai partecipanti"""
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        abort(404)
    
    campionato_id = gara.campionato_id
    gara_name = f"Gara {gara.number}"
    
    # Verifica che la gara possa essere cancellata
    if gara.status not in ['setup', 'inscription']:
        flash("La gara non può essere cancellata in questo stato!", "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    try:
        # Usa il service layer per cancellare con notifiche
        GaraService.cancel_gara_with_notifications(gara_id, current_user.id)
        flash(f"{gara_name} cancellata con successo! I partecipanti sono stati notificati.")
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    if not campionato_id:
        return redirect(url_for("dashboard.dashboard"))
    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@competition_bp.route("/<int:gara_id>")
@login_required
@gara_manager_required
def gara_detail(gara_id):
    """Dettaglio gara con iscrizioni e partite"""
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        abort(404)
    
    # Forza un refresh per assicurarsi di avere i dati più aggiornati
    db.session.refresh(gara)
    
    matches = (
        Match.query.filter_by(gara_id=gara_id)
        .order_by(Match.round_number, Match.id)
        .all()
    )

    # Director management context
    from models.user.models import User, DirectorAssignment
    
    # Ottieni iscrizioni ordinate alfabeticamente per username (dopo import User)
    inscriptions = (
        Inscription.query.filter_by(gara_id=gara_id)
        .join(User, Inscription.user_id == User.id)
        .order_by(User.username)
        .all()
    )
    
    # Get already assigned directors for this gara
    assigned_director_ids = (
        db.session.query(DirectorAssignment.user_id)
        .filter(
            DirectorAssignment.entity_type == 'gara',
            DirectorAssignment.entity_id == gara.id
        )
        .all()
    )
    assigned_director_ids = [d[0] for d in assigned_director_ids]
    
    # Also add the principal director if it's a standalone gara
    if gara.is_standalone and gara.director_id:
        assigned_director_ids.append(gara.director_id)
    
    # Get available users for director selection (directors only, exclude admins, already assigned, and current user)
    query = (
        User.query.filter(User.role == "director")
        .filter(User.deleted_at.is_(None))
        .filter(User.id != current_user.id)  # Exclude current user
    )
    
    # Exclude already assigned directors only if there are any
    if assigned_director_ids:
        query = query.filter(~User.id.in_(assigned_director_ids))
    
    users = query.order_by(User.username).all()
    
    # Permission checks for director management
    # Check if user is a director of this specific gara OR the campionato
    
    # Check if user is a director of this gara
    is_gara_director = (
        db.session.query(DirectorAssignment)
        .filter(
            DirectorAssignment.entity_type == 'gara',
            DirectorAssignment.entity_id == gara.id,
            DirectorAssignment.user_id == current_user.id
        )
        .first() is not None
    )
    
    # Check if user is a director of the campionato (if gara is not standalone)
    is_campionato_director = False
    if not gara.is_standalone and gara.campionato_id:
        is_campionato_director = (
            db.session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == 'campionato',
                DirectorAssignment.entity_id == gara.campionato_id,
                DirectorAssignment.user_id == current_user.id
            )
            .first() is not None
        )
    
    # Any director (principal or co-director) can manage other directors
    can_manage_directors = current_user.is_admin or (
        current_user.is_director and (
            is_gara_director or is_campionato_director or
            (gara.is_standalone and gara.director_id == current_user.id)
        )
    )
    show_admin_management = current_user.is_admin
    show_director_management = current_user.is_director and can_manage_directors
    
    # Ottieni l'ultima classificazione disponibile (sempre mostrata dal round 1 in poi)
    current_round_classification = None
    latest_round_with_classification = None
    
    if gara.current_round > 0:
        # Cerca la classificazione più recente disponibile (partendo dal round corrente)
        for round_num in range(gara.current_round, 0, -1):
            classification = RoundClassification.query.filter_by(
                gara_id=gara_id, round_number=round_num
            ).order_by(RoundClassification.position).all()
            
            if classification:
                current_round_classification = classification
                latest_round_with_classification = round_num
                break
    
    return render_template(
        "admin/gara_detail.html",
        gara=gara,
        inscriptions=inscriptions,
        matches=matches,
        users=users,
        can_manage_directors=can_manage_directors,
        show_admin_management=show_admin_management,
        show_director_management=show_director_management,
        current_round_classification=current_round_classification,
        latest_round_with_classification=latest_round_with_classification,
    )


@competition_bp.route("/<int:gara_id>/open_inscriptions", methods=["POST"])
@login_required
@gara_manager_required
def open_inscriptions(gara_id):
    """Apri iscrizioni per una gara"""
    # Ottieni le date UTC dal JavaScript
    inscription_start = datetime.strptime(
        request.form["inscription_start_utc"], "%Y-%m-%dT%H:%M:%S"
    )
    inscription_end = datetime.strptime(
        request.form["inscription_end_utc"], "%Y-%m-%dT%H:%M:%S"
    )

    # Usa il service layer invece del direct database access
    try:
        GaraService.open_inscriptions(gara_id, inscription_start, inscription_end)
        flash("Iscrizioni aperte!")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/modify_inscription_dates", methods=["POST"])
@login_required
@gara_manager_required
def modify_inscription_dates(gara_id):
    """Modifica date di iscrizione per una gara"""
    inscription_start = datetime.strptime(
        request.form["inscription_start_utc"], "%Y-%m-%dT%H:%M:%S"
    )
    inscription_end = datetime.strptime(
        request.form["inscription_end_utc"], "%Y-%m-%dT%H:%M:%S"
    )

    # Usa il service layer invece del direct database access
    try:
        GaraService.modify_inscription_dates(
            gara_id, inscription_start, inscription_end
        )
        flash("Date di iscrizione aggiornate con successo!")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/start_first_round", methods=["POST"])
@login_required
@gara_manager_required
def start_first_round(gara_id):
    """Avvia primo turno della gara"""
    # Usa il service layer invece del direct database access
    try:
        GaraService.start_first_round(gara_id)
        flash("Primo turno avviato!")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/cancel_first_round", methods=["POST"])
@login_required
@gara_manager_required
def cancel_first_round(gara_id):
    """Cancella l'avvio del primo turno se non ci sono risultati"""
    try:
        GaraService.cancel_first_round_startup(gara_id)
        flash("Avvio del primo turno cancellato con successo! La gara è tornata allo stato di iscrizioni.", "success")
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
        flash(f"Avvio del turno {gara.current_round + 1} cancellato con successo!", "success")
    except ValueError as ve:
        flash(str(ve), "error")
    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/results_overview")
@login_required
@gara_manager_required
def gara_results_overview(gara_id):
    """Overview risultati gara per inserimento rapido (admin)"""
    gara = Gara.query.get_or_404(gara_id)

    # Organizza partite per turno
    matches_by_round = {}
    for round_num in range(1, gara.rounds_count + 1):
        matches_by_round[round_num] = (
            Match.query.filter_by(gara_id=gara_id, round_number=round_num)
            .order_by(Match.id)
            .all()
        )

    # Debug
    import logging
    logging.warning(f"DEBUG results_overview: gara.rounds_count = {gara.rounds_count}")
    for round_num, matches in matches_by_round.items():
        logging.warning(f"DEBUG results_overview: Round {round_num} has {len(matches)} matches")

    return render_template(
        "admin/gara_result_overview.html",
        gara=gara,
        matches_by_round=matches_by_round,
    )


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
    incomplete_matches = [
        m for m in matches_in_round if m.status != MatchStatus.COMPLETED.value
    ]
    if incomplete_matches:
        flash(
            f"Il turno {round_number} non è ancora completato! "
            f"Mancano {len(incomplete_matches)} partite."
        )
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Ottieni o calcola classifica
    classification = get_amalfi_classification(gara_id, round_number)
    if not classification:
        # Calcola classifica se non esiste (questo metodo ritorna tuple, non oggetti)
        RoundClassification.calculate_classification_after_round(
            gara_id, round_number
        )
        # Ricarica la classifica dopo il calcolo (ora sono oggetti RoundClassification)
        classification = get_amalfi_classification(gara_id, round_number)

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


@competition_bp.route("/<int:gara_id>/amalfi/preview_round/<int:round_number>")
@login_required
@gara_manager_required
def amalfi_preview_round(gara_id, round_number):
    """Anteprima di un turno Amalfi senza creare le partite"""
    from amalfi.engine import AmalfiEngine
    
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        return jsonify({"success": False, "error": "Gara non trovata"}), 404
    
    try:
        # Validazioni preliminari
        if round_number < 1 or round_number > gara.rounds_count:
            return jsonify({"success": False, "error": f"Turno {round_number} non valido!"})
            
        if round_number <= gara.current_round:
            return jsonify({"success": False, "error": f"Il turno {round_number} è già stato avviato!"})
            
        if round_number != gara.current_round + 1:
            return jsonify({"success": False, "error": f"Devi avviare prima il turno {gara.current_round + 1}!"})

        # Usa il motore Amalfi per calcolare gli abbinamenti senza crearli
        engine = AmalfiEngine(gara)
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
    "/<int:gara_id>/amalfi/start_round/<int:round_number>", methods=["POST"]
)
@login_required
@gara_manager_required
def amalfi_start_round(gara_id, round_number):
    """Avvia un turno specifico con algoritmo Amalfi"""
    gara = Gara.query.get_or_404(gara_id)

    try:
        # Validazioni preliminari
        if round_number < 1 or round_number > gara.rounds_count:
            return jsonify({"success": False, "error": f"Turno {round_number} non valido!"})
            
        # Controlla se il turno è già stato avviato (idempotenza)
        existing_matches = Match.query.filter_by(
            gara_id=gara_id, round_number=round_number
        ).first()
        if existing_matches:
            return jsonify({"success": False, "error": f"Il turno {round_number} è già stato avviato!"})
            
        if round_number != gara.current_round + 1:
            return jsonify({"success": False, "error": f"Devi avviare prima il turno {gara.current_round + 1}!"})

        validation = validate_amalfi_configuration(gara)
        if not validation["is_valid"]:
            errors = "; ".join(validation["errors"])
            return jsonify({"success": False, "error": f"Errore Amalfi: {errors}"})

        if round_number > 1:
            prev_matches = Match.query.filter_by(
                gara_id=gara_id, round_number=round_number - 1
            ).all()
            incomplete_prev = [
                m for m in prev_matches if m.status != MatchStatus.COMPLETED.value
            ]
            if incomplete_prev:
                return jsonify({"success": False, "error": f"Completa prima tutte le partite del turno {round_number-1}!"})

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
            "redirect": url_for("admin.competition.gara_detail", gara_id=gara_id)
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


# ────────────────────────────────────────────────────────────────────────────────
# DIRECTOR MANAGEMENT
# ────────────────────────────────────────────────────────────────────────────────

@competition_bp.route("/<int:gara_id>/add_director", methods=["POST"])
@login_required
@gara_manager_required
def add_director(gara_id):
    """Aggiunge un co‑direttore alla gara"""
    new_director_id = int(request.form["user_id"])

    try:
        success = GaraService.add_director(
            gara_id=gara_id,
            user_id=new_director_id,
            assigned_by_id=current_user.id,
        )

        if success:
            flash("Direttore aggiunto con successo.")
        else:
            flash("Utente già presente come direttore.", "warning")

    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:
        flash(f"Errore durante l'aggiunta del direttore: {str(e)}", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/remove_director", methods=["POST"])
@login_required
@gara_manager_required
def remove_director(gara_id):
    """Rimuove un co‑direttore dalla gara"""
    director_id = int(request.form["user_id"])

    success = GaraService.remove_director(gara_id=gara_id, user_id=director_id)

    if success:
        flash("Direttore rimosso con successo.")
    else:
        flash("Errore: direttore non trovato.", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/admin_uninscribe/<int:user_id>", methods=["POST"])
@login_required
@gara_manager_required
def admin_uninscribe_user(gara_id, user_id):
    """Disiscrive un utente dalla gara (solo admin/direttori)."""
    from models.competition.services import InscriptionService
    from models.notification.services import NotificationService
    from models.user.models import User
    from models.competition.models import Gara
    
    try:
        # Verifica che l'utente esista
        user = db.session.get(User, user_id)
        if not user:
            flash("Utente non trovato.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))
        
        # Verifica che la gara esista
        gara = db.session.get(Gara, gara_id)
        if not gara:
            flash("Gara non trovata.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))
        
        # Verifica che la gara sia ancora in fase di iscrizioni
        if gara.status != GaraStatus.INSCRIPTION.value:
            flash("Non è possibile disiscrivere utenti quando il primo turno è già iniziato.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))
        
        # Esegui la disiscrizione
        success = InscriptionService.admin_uninscribe_user(user_id, gara_id, current_user.id)
        
        if success:
            flash(f"Utente {user.username} discritto con successo.", "success")
        else:
            flash("Errore: utente non iscritto a questa gara.", "error")
            
    except Exception as e:
        flash(f"Errore durante la disiscrizione: {str(e)}", "error")
    
    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))
