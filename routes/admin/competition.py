# routes/admin/competition.py
"""Competition (Gara) management blueprint for admin interface."""

from typing import Optional
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
from models.transaction.manager import transactional

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
    Discipline,
)
from models.competition.models import WithdrawPolicy
from utils import (
    gara_manager_required,
    admin_required,
    director_or_admin_required,
    trio_manager_required,
)
from models.competition.services import GaraService
from models.competition.state_service import StateService
from models.matchmaking.strategies.amalfi import AmalfiStrategy
from models.classification.models import RoundClassification
from models.classification.services import RoundClassificationService
from models.location.models import BilliardHall
from models.location.services import LocationService

# Competition management blueprint
competition_bp = Blueprint("competition", __name__)


def _handle_venue_creation(
    location: str, number_of_tables: Optional[int] = None
) -> str:
    """
    Handle venue creation/validation for competitions.
    If location doesn't match existing venues, create as disabled and non-verified.
    Returns the location string to use.
    """
    if not location or not location.strip():
        return location

    location = location.strip()

    # Check if location matches existing venue (both active and inactive)
    existing_venue = BilliardHall.query.filter_by(name=location).first()

    if existing_venue:
        return location

    # Create new disabled, non-verified venue
    if number_of_tables and number_of_tables > 0:
        try:
            # Create via LocationService first
            new_venue = LocationService.create_billiard_hall(
                name=location,
                added_by_id=current_user.id,
                number_of_tables=number_of_tables,
            )

            # Then modify to set as disabled and non-verified
            new_venue.is_active = False
            new_venue.verified = False

            flash(
                f"Nuovo luogo '{location}' aggiunto come disattivato. Sarà verificato dall'admin.",
                "info",
            )
        except Exception as e:
            # If creation fails, continue with original location
            flash(f"Errore nella creazione del luogo: {str(e)}", "warning")
    else:
        flash(
            f"Impossibile creare '{location}': specificare il numero di tavoli.",
            "warning",
        )

    return location


@competition_bp.route("/create_standalone", methods=["GET", "POST"])
@login_required
@director_or_admin_required
@transactional(domain="competition")
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
            time = datetime_obj.time()

            # Campi opzionali
            location = request.form.get("location", "").strip()
            number_of_tables = request.form.get("number_of_tables")
            number_of_tables = int(number_of_tables) if number_of_tables else None

            # Handle venue auto-creation
            location = _handle_venue_creation(location, number_of_tables)
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
            withdraw_policy = request.form.get(
                "withdraw_policy", WithdrawPolicy.EXCLUDE.value
            )

            # Strategy configuration
            matchmaking_strategy = request.form.get("matchmaking_strategy", "amalfi")
            first_round_policy = request.form.get("first_round_policy", "random")
            odd_number_policy = request.form.get("odd_number_policy", "bye")
            anti_rematch_enabled = request.form.get("anti_rematch_enabled") == "on"

            # Validazione della configurazione delle strategie
            from models.matchmaking.configuration import (
                StrategyConfiguration,
                MatchmakingStrategy,
                FirstRoundPolicy,
                OddNumberPolicy,
            )

            try:
                strategy_config = StrategyConfiguration(
                    strategy=MatchmakingStrategy(matchmaking_strategy),
                    first_round_policy=FirstRoundPolicy(first_round_policy),
                    odd_number_policy=OddNumberPolicy(odd_number_policy),
                    anti_rematch_enabled=anti_rematch_enabled,
                    rounds_count=rounds_count,
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
                time=time,
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
    # Get verified venues for location suggestions
    from models.location.models import BilliardHall

    verified_venues = (
        BilliardHall.query.filter_by(is_active=True, verified=True)
        .order_by(BilliardHall.name)
        .all()
    )

    # Ottieni le strategie disponibili
    available_strategies = GaraService.get_available_strategies()

    return render_template(
        "admin/gara_create_standalone.html",
        WithdrawPolicy=WithdrawPolicy,
        verified_venues=verified_venues,
        available_strategies=available_strategies,
        discipline_choices=Discipline.get_choices(),
    )


@competition_bp.route("/api/strategy_constraints/<strategy>")
@login_required
@admin_required
def get_strategy_constraints(strategy):
    """API endpoint per ottenere i vincoli di una strategia."""
    from models.matchmaking.configuration import (
        STRATEGY_CONSTRAINTS,
        MatchmakingStrategy,
    )

    try:
        strategy_enum = MatchmakingStrategy(strategy)
        constraints = STRATEGY_CONSTRAINTS.get(strategy_enum, {})

        return jsonify(
            {
                "success": True,
                "constraints": constraints,
                "display_name": strategy.replace("_", " ").title(),
                "description": constraints.get("description", ""),
            }
        )
    except ValueError:
        return (
            jsonify({"success": False, "error": f"Strategia '{strategy}' non valida"}),
            400,
        )


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
            DirectorAssignment.entity_type == "campionato",
            DirectorAssignment.entity_id == campionato_id,
            DirectorAssignment.user_id == current_user.id,
        )
        .first()
        is not None
    )

    if not (
        current_user.is_admin or (current_user.is_director and is_campionato_director)
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
    location = request.form.get("location", "").strip()
    number_of_tables = request.form.get("number_of_tables")
    number_of_tables = int(number_of_tables) if number_of_tables else None

    # Handle venue auto-creation
    location = _handle_venue_creation(location, number_of_tables)
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
@transactional(domain="competition")
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

            # Handle venue auto-creation for location
            location = request.form.get("location", "").strip()
            number_of_tables = request.form.get("number_of_tables")
            number_of_tables = int(number_of_tables) if number_of_tables else None

            location = _handle_venue_creation(location, number_of_tables)

            # Estratti i parametri di configurazione matchmaking
            matchmaking_strategy = request.form.get(
                "matchmaking_strategy", gara.matchmaking_strategy
            )
            first_round_policy = request.form.get(
                "first_round_policy", gara.first_round_policy
            )
            odd_number_policy = request.form.get(
                "odd_number_policy", gara.odd_number_policy
            )
            anti_rematch_enabled = request.form.get("anti_rematch_enabled") == "on"

            GaraService.update_gara(
                gara_id=gara_id,
                name=request.form.get("name", gara.name),
                date_str=request.form["date"],
                location=location,
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
                # Aggiunti i parametri di configurazione matchmaking
                matchmaking_strategy=matchmaking_strategy,
                first_round_policy=first_round_policy,
                odd_number_policy=odd_number_policy,
                anti_rematch_enabled=anti_rematch_enabled,
            )

            # Handle round discipline configuration (only for random strategy)
            if matchmaking_strategy == "random":
                from models.competition.round_configuration import RoundConfiguration

                # Get rounds count from form (in case it changed)
                rounds_count = int(request.form.get("rounds_count", 3))

                # Clear existing configurations first (if any)
                RoundConfiguration.delete_for_gara(gara_id)
                db.session.flush()  # Ensure deletion is processed

                # Process round discipline configurations
                for round_num in range(1, rounds_count + 1):
                    round_discipline = request.form.get(
                        f"round_{round_num}_discipline", ""
                    ).strip()

                    # Only create configuration if discipline is specified (not empty)
                    if round_discipline:
                        RoundConfiguration.create_or_update(
                            gara_id=gara_id,
                            round_number=round_num,
                            discipline=round_discipline,
                        )

                # Round configurations will be committed by transaction decorator
            else:
                # For non-random strategies, clear any existing round configurations
                from models.competition.round_configuration import RoundConfiguration

                RoundConfiguration.delete_for_gara(gara_id)
                # Changes will be committed by transaction decorator

            flash("Gara aggiornata con successo!")
        except ValueError as ve:
            flash(str(ve), "error")

        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Get available strategies for the form
    available_strategies = GaraService.get_available_strategies()

    # Get verified venues for location suggestions
    from models.location.models import BilliardHall

    verified_venues = (
        BilliardHall.query.filter_by(is_active=True, verified=True)
        .order_by(BilliardHall.name)
        .all()
    )

    # Get existing round configurations for the form
    from models.competition.round_configuration import RoundConfiguration

    round_configurations = {}
    existing_configs = RoundConfiguration.get_all_for_gara(gara_id)
    for config in existing_configs:
        round_configurations[config.round_number] = {
            "discipline": config.discipline,
            "distance": config.distance,
            "best_of": config.best_of,
            "notes": config.notes,
        }

    return render_template(
        "admin/gara_edit.html",
        gara=gara,
        WithdrawPolicy=WithdrawPolicy,
        available_strategies=available_strategies,
        verified_venues=verified_venues,
        discipline_choices=Discipline.get_choices(),
        round_configurations=round_configurations,
    )


@competition_bp.route("/<int:gara_id>/delete", methods=["POST"])
@login_required
@gara_manager_required
def delete_gara(gara_id):
    """Cancella gara"""
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        abort(404)

    # Determina se è standalone prima della cancellazione
    is_standalone = gara.campionato_id is None
    campionato_id = gara.campionato_id
    gara_name = gara.name if gara.name else f"Gara {gara.number}"

    # Usa il service layer invece del direct database access
    try:
        GaraService.delete_gara(gara_id)
        flash(f"{gara_name} cancellata con successo!")
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Redirect appropriato: home per standalone, campionato detail per gare di campionato
    if is_standalone:
        return redirect(url_for("dashboard.dashboard"))
    else:
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
    if gara.status not in ["setup", "inscription"]:
        flash("La gara non può essere cancellata in questo stato!", "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    try:
        # Usa il service layer per cancellare con notifiche
        GaraService.cancel_gara_with_notifications(gara_id, current_user.id)
        flash(
            f"{gara_name} cancellata con successo! I partecipanti sono stati notificati."
        )
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
            DirectorAssignment.entity_type == "gara",
            DirectorAssignment.entity_id == gara.id,
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
            DirectorAssignment.entity_type == "gara",
            DirectorAssignment.entity_id == gara.id,
            DirectorAssignment.user_id == current_user.id,
        )
        .first()
        is not None
    )

    # Check if user is a director of the campionato (if gara is not standalone)
    is_campionato_director = False
    if not gara.is_standalone and gara.campionato_id:
        is_campionato_director = (
            db.session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == gara.campionato_id,
                DirectorAssignment.user_id == current_user.id,
            )
            .first()
            is not None
        )

    # Any director (principal or co-director) can manage other directors
    can_manage_directors = current_user.is_admin or (
        current_user.is_director
        and (
            is_gara_director
            or is_campionato_director
            or (gara.is_standalone and gara.director_id == current_user.id)
        )
    )
    show_admin_management = current_user.is_admin
    show_director_management = current_user.is_director and can_manage_directors

    # Ottieni l'ultima classificazione disponibile per turni completati
    current_round_classification = None
    latest_round_with_classification = None

    if gara.current_round > 0:
        # Helper function to check if a round is completed
        def is_round_completed(round_number):
            round_matches = Match.query.filter_by(
                gara_id=gara_id, round_number=round_number
            ).all()
            if not round_matches:
                return False
            return all(
                match.status == MatchStatus.COMPLETED.value for match in round_matches
            )

        # Cerca la classificazione del turno completato più recente
        for round_num in range(gara.current_round, 0, -1):
            if is_round_completed(round_num):
                # SEMPRE ricalcola la classificazione per garantire dati aggiornati
                # Questo è necessario perché i risultati dei match potrebbero essere stati modificati
                # dopo che la classificazione è stata calcolata inizialmente
                RoundClassification.calculate_classification_after_round(
                    gara_id, round_num
                )

                # Carica la classificazione appena ricalcolata
                classification = (
                    RoundClassification.query.filter_by(
                        gara_id=gara_id, round_number=round_num
                    )
                    .order_by(RoundClassification.position)
                    .all()
                )

                if classification:
                    current_round_classification = classification
                    latest_round_with_classification = round_num
                    break

    # Get challenge classification data for random strategy garas
    challenge_classification = None
    gara_challenges = None
    if gara.matchmaking_strategy == "random":
        from models.challenge import GaraChallengeService

        if GaraChallengeService.has_active_challenges(gara_id):
            challenge_classification = GaraChallengeService.update_gara_classification(
                gara_id
            )
            gara_challenges = GaraChallengeService.get_gara_challenges(gara_id)

    # Add match modification permissions for each match based on round locking rules
    from models.competition.round_manager import AdvancedRoundManager

    match_can_modify = {}
    for match in matches:
        can_modify, _ = AdvancedRoundManager.can_modify_match(match.id)
        match_can_modify[match.id] = can_modify

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
        challenge_classification=challenge_classification,
        gara_challenges=gara_challenges,
        match_can_modify=match_can_modify,
        discipline_choices=Discipline.get_choices(),
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
    """Avvia primo turno della gara (o tutti i turni per strategia Random)"""
    # Usa il service layer invece del direct database access
    try:
        from models import db, Gara

        gara = db.session.get(Gara, gara_id)

        GaraService.start_first_round(gara_id)

        if gara and gara.matchmaking_strategy == "random":
            flash("Gara avviata! Tutti i turni sono stati creati.", "success")
        else:
            flash("Primo turno avviato!", "success")
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
        flash(
            "Avvio del primo turno cancellato con successo! La gara è tornata allo stato di iscrizioni.",
            "success",
        )
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/close_inscriptions", methods=["POST"])
@login_required
@gara_manager_required
def close_inscriptions(gara_id):
    """Chiude le iscrizioni e torna la gara allo stato setup se non ci sono iscritti"""
    try:
        gara = db.session.get(Gara, gara_id)
        if not gara:
            flash("Gara non trovata.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Verifica che la gara sia in stato inscription
        if gara.status != GaraStatus.INSCRIPTION.value:
            flash("La gara non è in stato di iscrizione.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Verifica che non ci siano iscrizioni attive
        if gara.get_active_inscriptions_count() > 0:
            flash(
                "Non è possibile chiudere le iscrizioni quando ci sono già degli iscritti.",
                "error",
            )
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Usa il service layer per tornare allo stato setup
        StateService.reopen_setup(gara)
        flash(
            "Iscrizioni chiuse con successo! La gara è tornata allo stato di setup.",
            "success",
        )

    except Exception as e:
        flash(f"Errore durante la chiusura delle iscrizioni: {str(e)}", "error")

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
        logging.warning(
            f"DEBUG results_overview: Round {round_num} has {len(matches)} matches"
        )

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
    classification = RoundClassificationService.get_round_standings(gara_id, round_number)
    if not classification:
        # Calcola classifica se non esiste (questo metodo ritorna tuple, non oggetti)
        RoundClassification.calculate_classification_after_round(gara_id, round_number)
        # Ricarica la classifica dopo il calcolo (ora sono oggetti RoundClassification)
        classification = RoundClassificationService.get_round_standings(gara_id, round_number)

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
                        "error": f"Completa prima tutte le partite del turno {round_number-1}!",
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
        message = f"Turno {round_number} avviato con successo! Creati {total} abbinamenti Amalfi."
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
                        "error": f"Completa prima tutte le partite del turno {round_number-1}!",
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
            flash(
                "Non è possibile disiscrivere utenti quando il primo turno è già iniziato.",
                "error",
            )
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Esegui la disiscrizione
        success = InscriptionService.admin_uninscribe_user(
            user_id, gara_id, current_user.id
        )

        if success:
            flash(f"Utente {user.username} discritto con successo.", "success")
        else:
            flash("Errore: utente non iscritto a questa gara.", "error")

    except Exception as e:
        flash(f"Errore durante la disiscrizione: {str(e)}", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


# ────────────────────────────────────────────────────────────────────────────────
# CHALLENGE MANAGEMENT (Random Tournaments only)
# ────────────────────────────────────────────────────────────────────────────────


@competition_bp.route("/<int:gara_id>/challenges")
@login_required
@gara_manager_required
def get_gara_challenges(gara_id):
    """Get active challenges for a gara (AJAX endpoint)."""
    from models.challenge import GaraChallengeService

    gara = db.session.get(Gara, gara_id)
    if not gara:
        return jsonify({"success": False, "error": "Gara non trovata"}), 404

    # Solo per gare Random
    if gara.matchmaking_strategy != "random":
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Challenge disponibili solo per tornei Random",
                }
            ),
            400,
        )

    try:
        gara_challenges = GaraChallengeService.get_gara_challenges(gara_id)
        challenges_data = []

        for gara_challenge in gara_challenges:
            challenges_data.append(
                {
                    "id": gara_challenge.id,
                    "challenge_id": gara_challenge.challenge_id,
                    "challenge_name": gara_challenge.challenge.get_display_name(),
                    "challenge_description": gara_challenge.challenge.description,
                    "challenge_image_filename": gara_challenge.challenge.image_filename,
                    "round_number": gara_challenge.round_number,
                    "max_attempts": gara_challenge.max_attempts,
                    "is_active": gara_challenge.is_active,
                }
            )

        return jsonify({"success": True, "challenges": challenges_data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@competition_bp.route("/<int:gara_id>/add_challenge", methods=["POST"])
@login_required
@gara_manager_required
def add_challenge_to_gara(gara_id):
    """Add a challenge to a gara (AJAX endpoint)."""
    from models.challenge import GaraChallengeService

    gara = db.session.get(Gara, gara_id)
    if not gara:
        return jsonify({"success": False, "error": "Gara non trovata"}), 404

    # Solo per gare Random
    if gara.matchmaking_strategy != "random":
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Challenge disponibili solo per tornei Random",
                }
            ),
            400,
        )

    # Solo se la gara non è ancora iniziata (SETUP o INSCRIPTION)
    if gara.status not in [GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value]:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Non è possibile aggiungere challenge dopo l'inizio della gara",
                }
            ),
            400,
        )

    try:
        # Validazione input
        challenge_id_str = request.form.get("challenge_id", "").strip()
        if not challenge_id_str:
            return (
                jsonify({"success": False, "error": "Devi selezionare una challenge"}),
                400,
            )

        challenge_id = int(challenge_id_str)
        round_number = int(request.form["round_number"])
        max_attempts = int(request.form["max_attempts"])

        gara_challenge = GaraChallengeService.add_challenge_to_gara(
            gara_id=gara_id,
            challenge_id=challenge_id,
            round_number=round_number,
            max_attempts=max_attempts,
            added_by_id=current_user.id,
        )

        return jsonify(
            {
                "success": True,
                "message": "Challenge aggiunta con successo",
                "gara_challenge_id": gara_challenge.id,
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Errore durante l'aggiunta della challenge: {str(e)}",
                }
            ),
            500,
        )


@competition_bp.route("/<int:gara_id>/remove_challenge", methods=["POST"])
@login_required
@gara_manager_required
def remove_challenge_from_gara(gara_id):
    """Remove a challenge from a gara (AJAX endpoint)."""
    from models.challenge import GaraChallengeService, GaraChallenge

    gara = db.session.get(Gara, gara_id)
    if not gara:
        return jsonify({"success": False, "error": "Gara non trovata"}), 404

    # Solo per gare Random
    if gara.matchmaking_strategy != "random":
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Challenge disponibili solo per tornei Random",
                }
            ),
            400,
        )

    try:
        data = request.get_json()
        gara_challenge_id = data.get("gara_challenge_id")

        if not gara_challenge_id:
            return (
                jsonify({"success": False, "error": "ID gara challenge mancante"}),
                400,
            )

        # Verifica che la gara challenge appartenga alla gara corretta
        gara_challenge = GaraChallenge.query.get(gara_challenge_id)
        if not gara_challenge or gara_challenge.gara_id != gara_id:
            return jsonify({"success": False, "error": "Challenge non trovata"}), 404

        # Rimuovi la challenge (o disattivala se ci sono già tentativi)
        success = GaraChallengeService.remove_challenge_from_gara(
            gara_id, gara_challenge.challenge_id, gara_challenge.round_number
        )

        if success:
            return jsonify(
                {"success": True, "message": "Challenge rimossa con successo"}
            )
        else:
            return jsonify({"success": False, "error": "Challenge non trovata"}), 404

    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Errore durante la rimozione della challenge: {str(e)}",
                }
            ),
            500,
        )


@competition_bp.route("/<int:gara_id>/challenges/available")
@login_required
@gara_manager_required
def get_available_challenges_for_gara(gara_id):
    """Get available challenges for selection, excluding those already added to the gara (AJAX endpoint)."""
    from models.challenge import Challenge
    from models.challenge.gara_challenge_service import GaraChallengeService

    try:
        gara = Gara.query.get_or_404(gara_id)

        # Get all active challenges
        all_challenges = (
            Challenge.query.filter_by(is_active=True)
            .order_by(Challenge.description)
            .all()
        )

        # Get challenge IDs already assigned to this gara
        assigned_challenges = GaraChallengeService.get_gara_challenges(gara_id)
        assigned_challenge_ids = {gc.challenge_id for gc in assigned_challenges}

        # Filter out challenges already assigned to this gara
        available_challenges = [
            c for c in all_challenges if c.id not in assigned_challenge_ids
        ]

        challenges_data = []
        for challenge in available_challenges:
            # Assicura che il percorso dell'immagine sia corretto
            image_filename = None
            if challenge.image_path:
                if challenge.image_path.startswith("uploads/"):
                    image_filename = challenge.image_path.split("/")[-1]
                else:
                    image_filename = challenge.image_path

            challenges_data.append(
                {
                    "id": challenge.id,
                    "name": challenge.get_display_name(),
                    "description": challenge.description,
                    "pass_fail_only": challenge.pass_fail_only,
                    "image_filename": image_filename,
                }
            )

        return jsonify({"success": True, "challenges": challenges_data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@competition_bp.route("/challenges/available")
@login_required
@admin_required
def get_available_challenges():
    """Get all available challenges for selection (AJAX endpoint)."""
    from models.challenge import Challenge

    try:
        challenges = (
            Challenge.query.filter_by(is_active=True)
            .order_by(Challenge.description)
            .all()
        )

        challenges_data = []
        for challenge in challenges:
            # Assicura che il percorso dell'immagine sia corretto
            image_filename = None
            if challenge.image_path:
                if challenge.image_path.startswith("uploads/"):
                    image_filename = challenge.image_path.split("/")[-1]
                else:
                    image_filename = challenge.image_path

            challenges_data.append(
                {
                    "id": challenge.id,
                    "name": challenge.get_display_name(),
                    "description": challenge.description,
                    "pass_fail_only": challenge.pass_fail_only,
                    "image_filename": image_filename,
                }
            )

        return jsonify({"success": True, "challenges": challenges_data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@competition_bp.route("/challenges/create", methods=["POST"])
@login_required
@admin_required
def create_new_challenge():
    """Create a new challenge (AJAX endpoint)."""
    from models.challenge import ChallengeService
    import os
    from werkzeug.utils import secure_filename
    from flask import current_app

    try:
        description = request.form["description"].strip()
        pass_fail_only = request.form.get("pass_fail_only", "false").lower() == "true"

        if not description:
            return (
                jsonify({"success": False, "error": "La descrizione è obbligatoria"}),
                400,
            )

        # Handle image upload (required)
        if "image" not in request.files or not request.files["image"].filename:
            return (
                jsonify({"success": False, "error": "L'immagine è obbligatoria"}),
                400,
            )

        file = request.files["image"]
        if not file or not file.filename:
            return (
                jsonify({"success": False, "error": "L'immagine è obbligatoria"}),
                400,
            )

        # Check file size (max 5MB)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > 5 * 1024 * 1024:  # 5MB
            return (
                jsonify(
                    {"success": False, "error": "Immagine troppo grande (max 5MB)"}
                ),
                400,
            )

        import uuid

        filename = secure_filename(file.filename)
        if not filename:
            return (
                jsonify({"success": False, "error": "Nome file non valido"}),
                400,
            )

        # Check file extension
        allowed_extensions = {"png", "jpg", "jpeg", "gif", "webp"}
        file_extension = filename.rsplit(".", 1)[1].lower() if "." in filename else None

        if not file_extension or file_extension not in allowed_extensions:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Formato file non supportato. Usa JPG, PNG, GIF o WebP",
                    }
                ),
                400,
            )

        # Generate unique filename
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"

        # Use centralized image path management
        from utils.image_paths import ImagePathManager

        # Ensure uploads directory exists
        ImagePathManager.ensure_challenge_upload_dir()

        # Get upload directory and save file
        uploads_dir = ImagePathManager.get_challenge_upload_dir()
        file_path = os.path.join(uploads_dir, unique_filename)
        file.save(file_path)

        # Get database path using centralized utility
        image_path = ImagePathManager.get_challenge_db_path(unique_filename)

        # Create the challenge
        challenge = ChallengeService.create_challenge(
            description=description,
            pass_fail_only=pass_fail_only,
            image_path=image_path,
            created_by_id=current_user.id,
        )

        return jsonify(
            {
                "success": True,
                "message": "Challenge creata con successo",
                "challenge_id": challenge.id,
                "challenge_name": challenge.get_display_name(),
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Errore durante la creazione della challenge: {str(e)}",
                }
            ),
            500,
        )


@competition_bp.route("/<int:gara_id>/challenge_classification")
@login_required
@gara_manager_required
def get_gara_challenge_classification(gara_id):
    """Get challenge classification for a gara."""
    from models.challenge import GaraChallengeService

    gara = db.session.get(Gara, gara_id)
    if not gara:
        abort(404)

    # Solo per gare Random
    if gara.matchmaking_strategy != "random":
        flash("Classifica challenge disponibile solo per tornei Random", "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Verifica se ci sono challenge attive
    if not GaraChallengeService.has_active_challenges(gara_id):
        flash("Nessuna challenge attiva per questa gara", "info")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Aggiorna e ottieni la classificazione
    classification = GaraChallengeService.update_gara_classification(gara_id)
    challenge_stats = GaraChallengeService.get_challenge_statistics(gara_id)
    gara_challenges = GaraChallengeService.get_gara_challenges(gara_id)

    return render_template(
        "admin/gara_challenge_classification.html",
        gara=gara,
        classification=classification,
        challenge_stats=challenge_stats,
        gara_challenges=gara_challenges,
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
    """Reset a match with advanced validation and classification updates."""
    from models.competition.round_manager import AdvancedRoundManager

    admin_override = request.form.get("admin_override") == "true"

    success, message = AdvancedRoundManager.reset_match_with_validation(
        match_id, admin_override=admin_override
    )

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
    """Cancel an entire round with proper validation."""
    from models.competition.round_manager import AdvancedRoundManager

    admin_override = request.form.get("admin_override") == "true"

    success, message = AdvancedRoundManager.cancel_round(
        gara_id, round_number, admin_override=admin_override
    )

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
