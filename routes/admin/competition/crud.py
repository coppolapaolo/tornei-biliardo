# routes/admin/competition/crud.py
"""CRUD operations for Gara (competition) management."""

from typing import Optional
from flask import (
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
)
from models.status_enum import Discipline
from models.competition.models import WithdrawPolicy
from utils import (
    gara_manager_required,
    admin_required,
    director_or_admin_required,
)
from models.competition.services import GaraService
from models.location.models import BilliardHall
from models.location.services import LocationService
from models.kpi import track_gara_create
from models.competition.constants import (
    DEFAULT_MIN_PARTICIPANTS,
    DEFAULT_ROUNDS_COUNT,
    DEFAULT_ENTRY_FEE,
    DEFAULT_WITHDRAW_POLICY,
)

from . import competition_bp


def _handle_venue_creation(
    location: str, tables_input: Optional[str] = None
) -> tuple[str, Optional[int]]:
    """
    Handle venue creation/validation for competitions.
    If location doesn't match existing venues, create as disabled and non-verified.

    Args:
        location: Name of the venue
        tables_input: Either a single number ("5") or comma-separated list ("2,3,5")
                     If single number, creates venue with that many tables.

    Returns:
        Tuple of (location_str, billiard_hall_id):
        - (location, venue.id) if venue exists or was created
        - (location, None) if venue doesn't exist and couldn't be created
        - ("", None) if location is empty
    """
    if not location or not location.strip():
        return ("", None)

    location = location.strip()

    # Check if location matches existing venue (both active and inactive)
    existing_venue = BilliardHall.query.filter_by(name=location).first()

    if existing_venue:
        return (location, existing_venue.id)

    # New venue - try to create it if we have table info
    if tables_input and tables_input.strip():
        # Parse the input to determine number of tables for venue
        parsed_tables = Gara.parse_tables_input(tables_input)
        if parsed_tables:
            # Use the count of tables for the venue
            number_of_tables = len(parsed_tables)

            # Check if input was an explicit list vs a single number
            # If input contains comma or non-digit chars, it's an explicit list
            is_explicit_list = "," in tables_input.strip() or not tables_input.strip().isdigit()

            try:
                # Create via LocationService first
                new_venue = LocationService.create_billiard_hall(
                    name=location,
                    added_by_id=current_user.id,
                    number_of_tables=number_of_tables,
                )

                # If user provided an explicit list (not just a number),
                # save the table names on the venue for future reference
                if is_explicit_list:
                    new_venue.set_table_names(parsed_tables)

                # Then modify to set as disabled and non-verified
                new_venue.is_active = False
                new_venue.verified = False

                flash(
                    f"Nuovo luogo '{location}' aggiunto come disattivato. "
                    f"Sarà verificato dall'admin.",
                    "info",
                )
                return (location, new_venue.id)
            except Exception as e:
                # If creation fails, continue with original location string only
                flash(f"Errore nella creazione del luogo: {str(e)}", "warning")
    else:
        flash(
            f"Impossibile creare '{location}': specificare il numero di tavoli.",
            "warning",
        )

    # Venue not found and couldn't be created - return string only
    return (location, None)


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
            time = datetime_obj.time()

            # Campi opzionali
            location_input = request.form.get("location", "").strip()
            tables_input = request.form.get("available_tables", "").strip()

            # Handle venue auto-creation - returns (location_str, billiard_hall_id)
            location, billiard_hall_id = _handle_venue_creation(location_input, tables_input)

            # Parse tables for gara-specific configuration
            available_tables = Gara.parse_tables_input(tables_input) if tables_input else []

            description = request.form.get("description", "").strip()
            rounds_count = int(request.form.get("rounds_count", DEFAULT_ROUNDS_COUNT))
            min_participants = int(request.form.get("min_participants", DEFAULT_MIN_PARTICIPANTS))
            max_participants = request.form.get("max_participants")
            max_participants = int(max_participants) if max_participants else None
            entry_fee = float(request.form.get("entry_fee", DEFAULT_ENTRY_FEE))

            # Game settings
            discipline = request.form["discipline"]
            distance = int(request.form["distance"])
            exact_number = "exact_number" in request.form
            is_race_to = not exact_number
            withdraw_policy = request.form.get(
                "withdraw_policy", DEFAULT_WITHDRAW_POLICY
            )

            # Multi-set configuration (Phase 6: Frontend Integration)
            is_multi_set = "is_multi_set" in request.form
            match_distance = request.form.get("match_distance")
            match_distance = int(match_distance) if match_distance else None
            is_race_to_sets = "is_race_to_sets" in request.form

            # Strategy configuration
            matchmaking_strategy = request.form.get("matchmaking_strategy", "amalfi")
            first_round_policy = request.form.get("first_round_policy", "random")
            odd_number_policy = request.form.get("odd_number_policy", "bye")
            anti_rematch_enabled = request.form.get("anti_rematch_enabled") == "on"

            # SSR (Spot Shot Rally) tiebreaker configuration
            tiebreaker_enabled = request.form.get("tiebreaker_enabled") == "on"
            tiebreaker_until_position = int(request.form.get("tiebreaker_until_position", 3))

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
                errors = strategy_config.validate(distance=distance, is_race_to=is_race_to)
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
                billiard_hall_id=billiard_hall_id,  # FK to BilliardHall
                location=location,  # String for backward compat/display cache
                description=description,
                rounds_count=rounds_count,
                min_participants=min_participants,
                max_participants=max_participants,
                entry_fee=entry_fee,
                discipline=discipline,
                distance=distance,
                is_race_to=is_race_to,
                withdraw_policy=withdraw_policy,
                director_id=current_user.id,  # L'admin che crea è il direttore
                matchmaking_strategy=matchmaking_strategy,
                first_round_policy=first_round_policy,
                odd_number_policy=odd_number_policy,
                anti_rematch_enabled=anti_rematch_enabled,
                # Phase 6: Multi-set configuration
                is_multi_set=is_multi_set,
                match_distance=match_distance,
                is_race_to_sets=is_race_to_sets,
                # SSR (Spot Shot Rally) tiebreaker configuration
                tiebreaker_enabled=tiebreaker_enabled,
                tiebreaker_until_position=tiebreaker_until_position,
                # Gara-specific available tables
                available_tables=available_tables,
            )

            track_gara_create()  # KPI tracking
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
    # Support both date and datetime-local formats (for backward compatibility)
    date_str = request.form["date"]
    if "T" in date_str:
        # datetime-local format: YYYY-MM-DDTHH:MM
        parsed_datetime = datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
        date = parsed_datetime.date()
        gara_time = parsed_datetime.time()
    else:
        # date format: YYYY-MM-DD (with separate time field)
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        time_str = request.form.get("time", "20:00")
        gara_time = datetime.strptime(time_str, "%H:%M").time()

    # Nuovi campi
    location = request.form.get("location", "").strip()
    tables_input = request.form.get("available_tables", "").strip()

    # Handle venue auto-creation - returns tuple (location_str, billiard_hall_id)
    location, billiard_hall_id = _handle_venue_creation(location, tables_input)

    # Parse tables for gara-specific configuration
    available_tables = Gara.parse_tables_input(tables_input) if tables_input else []

    description = request.form.get("description", "")
    # Use campionato defaults as fallback (ADR-0001)
    default_rounds = campionato.default_rounds_count if campionato.default_rounds_count else DEFAULT_ROUNDS_COUNT
    default_fee = campionato.default_entry_fee if campionato.default_entry_fee is not None else DEFAULT_ENTRY_FEE
    rounds_count = int(request.form.get("rounds_count", default_rounds))
    min_participants = int(request.form.get("min_participants", DEFAULT_MIN_PARTICIPANTS))
    max_participants = request.form.get("max_participants")
    max_participants = int(max_participants) if max_participants else None
    entry_fee = float(request.form.get("entry_fee", default_fee))

    # Game settings
    discipline = request.form["discipline"]
    distance = int(request.form["distance"])
    exact_number = "exact_number" in request.form
    is_race_to = not exact_number
    withdraw_policy = request.form.get("withdraw_policy", DEFAULT_WITHDRAW_POLICY)

    # Strategy settings from form with campionato defaults as fallback (ADR-0001)
    matchmaking_strategy = campionato.campionato_type  # Always inherit from campionato
    # Read form values, using campionato defaults as fallback
    default_anti_rematch = campionato.default_anti_rematch if campionato.default_anti_rematch is not None else True
    default_odd_policy = campionato.default_odd_policy if campionato.default_odd_policy else "bye"
    default_first_round = "random"
    # Inherit classification_system from campionato (fix: was using model default "WINS")
    classification_system = campionato.default_classification_system or "WINS"

    anti_rematch = request.form.get("anti_rematch_enabled") == "on" if "anti_rematch_enabled" in request.form else default_anti_rematch
    odd_policy = request.form.get("odd_number_policy", default_odd_policy)
    first_round_policy = request.form.get("first_round_policy", default_first_round)

    # SSR (Spot Shot Rally) tiebreaker configuration
    tiebreaker_enabled = request.form.get("tiebreaker_enabled") == "on"
    tiebreaker_until_position = int(request.form.get("tiebreaker_until_position", 3))

    # Per ADR-005: Trio IS compatible with both "Race to N" AND "Exactly N" modes
    # (when using rack-based classification, ties are acceptable)
    # No need to force is_race_to=True for trio

    try:
        gara = GaraService.create_gara(
            campionato_id=campionato_id,
            number=number,
            name=name,
            date=date,
            time=gara_time,
            billiard_hall_id=billiard_hall_id,  # FK to BilliardHall
            location=location,  # String for backward compat/display cache
            description=description,
            rounds_count=rounds_count,
            min_participants=min_participants,
            max_participants=max_participants,
            entry_fee=entry_fee,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            withdraw_policy=withdraw_policy,
            matchmaking_strategy=matchmaking_strategy,
            first_round_policy=first_round_policy,
            anti_rematch_enabled=anti_rematch,
            odd_number_policy=odd_policy,
            tiebreaker_enabled=tiebreaker_enabled,
            tiebreaker_until_position=tiebreaker_until_position,
            classification_system=classification_system,
            # Gara-specific available tables
            available_tables=available_tables,
        )

        flash(f"Gara {number} creata con successo!")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara.id))
    except ValueError as e:
        flash(str(e), "error")
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
        # Handle venue auto-creation for location - returns tuple (location_str, billiard_hall_id)
        location = request.form.get("location", "").strip()
        tables_input = request.form.get("available_tables", "").strip()

        location, billiard_hall_id = _handle_venue_creation(location, tables_input)

        # Parse tables for gara-specific configuration
        available_tables = Gara.parse_tables_input(tables_input) if tables_input else []

        try:
            max_participants = request.form.get("max_participants")
            max_participants = int(max_participants) if max_participants else None

            exact_number = "exact_number" in request.form
            is_race_to = not exact_number

            # Multi-set configuration (Phase 6: Frontend Integration)
            is_multi_set = "is_multi_set" in request.form
            match_distance = request.form.get("match_distance")
            match_distance = int(match_distance) if match_distance else None
            is_race_to_sets = "is_race_to_sets" in request.form

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

            # SSR (Spot Shot Rally) tiebreaker configuration
            tiebreaker_enabled = request.form.get("tiebreaker_enabled") == "on"
            tiebreaker_until_position = int(request.form.get("tiebreaker_until_position", 3))

            # Estrai il campo time
            time_str = request.form.get("time", "20:00")

            GaraService.update_gara(
                gara_id=gara_id,
                name=request.form.get("name", gara.name),
                date_str=request.form["date"],
                time_str=time_str,
                billiard_hall_id=billiard_hall_id,  # FK to BilliardHall
                location=location,  # String for backward compat/display cache
                description=request.form.get("description", ""),
                rounds_count=int(request.form.get("rounds_count", 3)),
                min_participants=int(request.form.get("min_participants", 2)),
                max_participants=max_participants,
                entry_fee=float(request.form.get("entry_fee", 0.0)),
                discipline=request.form["discipline"],
                distance=int(request.form["distance"]),
                is_race_to=is_race_to,
                withdraw_policy=request.form.get(
                    "withdraw_policy", WithdrawPolicy.EXCLUDE.value
                ),
                # Aggiunti i parametri di configurazione matchmaking
                matchmaking_strategy=matchmaking_strategy,
                first_round_policy=first_round_policy,
                odd_number_policy=odd_number_policy,
                anti_rematch_enabled=anti_rematch_enabled,
                # Phase 6: Multi-set configuration
                is_multi_set=is_multi_set,
                match_distance=match_distance,
                is_race_to_sets=is_race_to_sets,
                # SSR (Spot Shot Rally) tiebreaker configuration
                tiebreaker_enabled=tiebreaker_enabled,
                tiebreaker_until_position=tiebreaker_until_position,
                # Operational settings (tables, location)
                available_tables=available_tables,
            )

            flash("Gara aggiornata con successo!")
        except ValueError as ve:
            flash(str(ve), "error")

        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Get available strategies for the form
    available_strategies = GaraService.get_available_strategies()

    # Get verified venues for location suggestions
    verified_venues = (
        BilliardHall.query.filter_by(is_active=True, verified=True)
        .order_by(BilliardHall.name)
        .all()
    )

    return render_template(
        "admin/gara_edit.html",
        gara=gara,
        WithdrawPolicy=WithdrawPolicy,
        available_strategies=available_strategies,
        verified_venues=verified_venues,
        discipline_choices=Discipline.get_choices(),
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
    gara_name = gara.name

    # Usa il service layer invece del direct database access
    try:
        GaraService.delete_gara(gara_id)
        flash(f"{gara_name} cancellata con successo!")
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Redirect: home per standalone, campionato detail per gare campionato
    if is_standalone:
        return redirect(url_for("dashboard.dashboard"))
    else:
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )


@competition_bp.route("/<int:gara_id>/soft-delete", methods=["POST"])
@login_required
@admin_required
def soft_delete_gara(gara_id):
    """Soft delete gara - admin only.

    Marks the gara as deleted without physical removal.
    Supports cascade options for related matches.
    """
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        abort(404)

    # Get cascade option from form
    cascade_option = request.form.get("cascade_option", "delete_all")
    reason = request.form.get("reason", "").strip()

    # Determine redirect before soft delete
    is_standalone = gara.campionato_id is None
    campionato_id = gara.campionato_id
    gara_name = gara.name

    try:
        GaraService.soft_delete_gara(
            gara_id=gara_id,
            deleted_by_id=current_user.id,
            cascade_option=cascade_option,
            reason=reason
        )

        if cascade_option == "keep_matches":
            flash(
                f"{gara_name} eliminata. I match sono stati mantenuti come match individuali.",
                "success"
            )
        else:
            flash(f"{gara_name} eliminata con successo!", "success")

    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Redirect: home for standalone, campionato detail for campionato gare
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
    gara_name = gara.name

    # Verifica che la gara possa essere cancellata
    if gara.status not in ["setup", "inscription"]:
        flash("La gara non può essere cancellata in questo stato!", "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    try:
        # Usa il service layer per cancellare con notifiche
        GaraService.cancel_gara_with_notifications(gara_id, current_user.id)
        flash(
            f"{gara_name} cancellata con successo! "
            f"I partecipanti sono stati notificati."
        )
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    if not campionato_id:
        return redirect(url_for("dashboard.dashboard"))
    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )
