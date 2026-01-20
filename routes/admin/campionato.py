# routes/admin/campionato.py
"""Campionato management blueprint for admin interface.

Implements:
- Multi-step wizard for campionato creation (ADR-0001)
- Step 1: Base configuration (name, type, playoffs, challenge mode)
- Step 2: Default values for gare (venue, cost, rounds, odd policy)
"""

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, abort, session
)
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from flask_babel import _

from models import (
    db,
    Campionato,
)
from models.location.models import BilliardHall
from models.matchmaking.configuration import (
    MatchmakingStrategy,
    OddNumberPolicy,
    get_classification_compatibility_map,
)
from utils import (
    campionato_manager_required,
    admin_required,
    director_or_admin_required,
)
from models.campionato.services import TournamentService

# Initialize the TournamentService
campionato_service = TournamentService()

# Campionato management blueprint
campionato_bp = Blueprint("campionato", __name__)

# Session key for wizard data
WIZARD_SESSION_KEY = "campionato_wizard_data"


# =============================================================================
# WIZARD CREAZIONE CAMPIONATO (ADR-0001)
# =============================================================================


@campionato_bp.route("/wizard", methods=["GET"])
@login_required
@director_or_admin_required
def wizard_start():
    """Step 1: Mostra il form di configurazione base del campionato.

    Parametri Step 1:
    - name: Nome del campionato
    - planned_gare_count: Numero pianificato di gare (default: 10)
    - campionato_type: Tipo (amalfi/random)
    - challenge_mode: Abilita sfide individuali
    - playoff_elite_enabled: Abilita playoff Elite
    - playoff_elite_participants: Numero partecipanti Elite (default: 6)
    - playoff_academy_enabled: Abilita playoff Academy
    - playoff_academy_participants: Numero partecipanti Academy (default: 6)
    """
    # Clear any previous wizard data
    session.pop(WIZARD_SESSION_KEY, None)

    return render_template(
        "admin/campionato_wizard_step1.html",
        matchmaking_strategies=[
            (MatchmakingStrategy.AMALFI.value, "Amalfi"),
            (MatchmakingStrategy.RANDOM.value, "Random"),
        ],
        classification_compatibility=get_classification_compatibility_map(),
    )


@campionato_bp.route("/wizard/step2", methods=["POST"])
@login_required
@director_or_admin_required
def wizard_step2():
    """Step 2: Salva dati Step 1 e mostra form default gare.

    Parametri Step 2:
    - default_venue_id: Sede predefinita (opzionale)
    - default_entry_fee: Quota iscrizione predefinita (opzionale)
    - default_rounds_count: Numero turni predefinito (default: 3)
    - default_odd_policy: Politica numero dispari (bye/trio)
    - default_anti_rematch: Abilita anti-rematch (default: True)
    """
    # Validate Step 1 data
    name = request.form.get("name", "").strip()
    if not name:
        flash(_("Il nome del campionato è obbligatorio"), "error")
        return redirect(url_for("admin.campionato.wizard_start"))

    planned_gare_count = request.form.get("planned_gare_count", "10")
    try:
        planned_gare_count = int(planned_gare_count)
        if planned_gare_count < 1:
            raise ValueError()
    except ValueError:
        flash(_("Il numero di gare deve essere un numero positivo"), "error")
        return redirect(url_for("admin.campionato.wizard_start"))

    campionato_type = request.form.get("campionato_type", MatchmakingStrategy.AMALFI.value)
    if campionato_type not in [MatchmakingStrategy.AMALFI.value, MatchmakingStrategy.RANDOM.value]:
        campionato_type = MatchmakingStrategy.AMALFI.value

    classification_system = request.form.get("classification_system", "WINS")
    if classification_system not in ["WINS", "RACK", "POSITION"]:
        classification_system = "WINS"

    challenge_mode = "challenge_mode" in request.form

    # Playoff configuration
    playoff_elite_enabled = "playoff_elite_enabled" in request.form
    playoff_elite_participants = 6
    if playoff_elite_enabled:
        try:
            playoff_elite_participants = int(request.form.get("playoff_elite_participants", "6"))
        except ValueError:
            playoff_elite_participants = 6

    playoff_academy_enabled = "playoff_academy_enabled" in request.form
    playoff_academy_participants = 6
    if playoff_academy_enabled:
        try:
            playoff_academy_participants = int(request.form.get("playoff_academy_participants", "6"))
        except ValueError:
            playoff_academy_participants = 6

    # Store Step 1 data in session
    session[WIZARD_SESSION_KEY] = {
        "name": name,
        "planned_gare_count": planned_gare_count,
        "campionato_type": campionato_type,
        "classification_system": classification_system,
        "challenge_mode": challenge_mode,
        "playoff_elite_enabled": playoff_elite_enabled,
        "playoff_elite_participants": playoff_elite_participants,
        "playoff_academy_enabled": playoff_academy_enabled,
        "playoff_academy_participants": playoff_academy_participants,
    }

    # Get venues for dropdown
    venues = (
        BilliardHall.query.filter_by(is_active=True)
        .order_by(BilliardHall.name)
        .all()
    )

    # Filter odd policies based on classification system
    classification_system = session[WIZARD_SESSION_KEY].get("classification_system", "WINS")

    # All available policies with their compatible systems
    all_odd_policies = [
        (OddNumberPolicy.NO.value, _("Lista Attesa (solo pari)"), ["WINS", "RACK"]),
        (OddNumberPolicy.BYE.value, _("Bye (riposo)"), ["WINS"]),
        (OddNumberPolicy.BYE_WITH_CHALLENGE.value, _("Bye con Challenge"), ["WINS", "RACK"]),
        (OddNumberPolicy.TRIO.value, _("Trio (match a 3)"), ["WINS", "RACK"]),
    ]

    # Filter to only show compatible policies
    odd_policies = [
        (value, label)
        for value, label, systems in all_odd_policies
        if classification_system in systems
    ]

    return render_template(
        "admin/campionato_wizard_step2.html",
        wizard_data=session[WIZARD_SESSION_KEY],
        venues=venues,
        odd_policies=odd_policies,
        classification_system=classification_system,
    )


@campionato_bp.route("/wizard/create", methods=["POST"])
@login_required
@director_or_admin_required
def wizard_create():
    """Crea il campionato con tutti i dati del wizard.

    Combina i dati di Step 1 (dalla sessione) con Step 2 (dal form).
    """
    # Retrieve Step 1 data from session
    wizard_data = session.get(WIZARD_SESSION_KEY)
    if not wizard_data:
        flash(_("Sessione wizard scaduta. Ricomincia la creazione."), "error")
        return redirect(url_for("admin.campionato.wizard_start"))

    # Get Step 2 data from form
    default_venue_id = request.form.get("default_venue_id")
    if default_venue_id:
        try:
            default_venue_id = int(default_venue_id)
        except ValueError:
            default_venue_id = None
    else:
        default_venue_id = None

    default_entry_fee = request.form.get("default_entry_fee")
    if default_entry_fee:
        try:
            default_entry_fee = float(default_entry_fee)
        except ValueError:
            default_entry_fee = None
    else:
        default_entry_fee = None

    default_rounds_count = request.form.get("default_rounds_count", "3")
    try:
        default_rounds_count = int(default_rounds_count)
        if default_rounds_count < 1:
            default_rounds_count = 3
    except ValueError:
        default_rounds_count = 3

    default_odd_policy = request.form.get("default_odd_policy", OddNumberPolicy.BYE.value)
    valid_policies = [
        OddNumberPolicy.NO.value,
        OddNumberPolicy.BYE.value,
        OddNumberPolicy.BYE_WITH_CHALLENGE.value,
        OddNumberPolicy.TRIO.value,
    ]
    if default_odd_policy not in valid_policies:
        default_odd_policy = OddNumberPolicy.BYE.value

    default_anti_rematch = "default_anti_rematch" in request.form

    # Get classification system from Step 1
    classification_system = wizard_data.get("classification_system", "WINS")

    # Create the campionato
    try:
        campionato = campionato_service.create_campionato_with_director(
            name=wizard_data["name"],
            creator_user_id=current_user.id,
            campionato_type=wizard_data["campionato_type"],
            challenge_mode=wizard_data["challenge_mode"],
            is_active=True,
            planned_gare_count=wizard_data["planned_gare_count"],
            default_venue_id=default_venue_id,
            default_entry_fee=default_entry_fee,
            default_rounds_count=default_rounds_count,
            default_odd_policy=default_odd_policy,
            default_anti_rematch=default_anti_rematch,
            default_classification_system=classification_system,
        )

        # Create playoff configurations if enabled
        if wizard_data.get("playoff_elite_enabled"):
            _create_playoff_config(
                campionato_id=campionato.id,
                name=_("Playoff Elite"),
                max_participants=wizard_data.get("playoff_elite_participants", 6),
                positions_from=1,
                positions_to=wizard_data.get("playoff_elite_participants", 6),
            )

        if wizard_data.get("playoff_academy_enabled"):
            elite_size = wizard_data.get("playoff_elite_participants", 6) if wizard_data.get("playoff_elite_enabled") else 0
            academy_size = wizard_data.get("playoff_academy_participants", 6)
            _create_playoff_config(
                campionato_id=campionato.id,
                name=_("Playoff Academy"),
                max_participants=academy_size,
                positions_from=elite_size + 1,
                positions_to=elite_size + academy_size,
            )

        # Clear wizard session
        session.pop(WIZARD_SESSION_KEY, None)

        flash(_('Campionato "%(name)s" creato con successo!', name=wizard_data["name"]), "success")
        return redirect(url_for("admin.campionato.campionato_detail", campionato_id=campionato.id))

    except Exception as e:
        flash(_("Errore durante la creazione: %(error)s", error=str(e)), "error")
        return redirect(url_for("admin.campionato.wizard_start"))


def _create_playoff_config(
    campionato_id: int,
    name: str,
    max_participants: int,
    positions_from: int,
    positions_to: int,
) -> None:
    """Helper per creare una configurazione playoff."""
    from models.playoff.models import PlayoffConfiguration, PlayoffType

    config = PlayoffConfiguration(
        campionato_id=campionato_id,
        name=name,
        playoff_type=PlayoffType.TOP_N,
        max_participants=max_participants,
        positions_from=positions_from,
        positions_to=positions_to,
        is_active=True,
        auto_generate=True,
    )
    db.session.add(config)
    db.session.commit()


@campionato_bp.route("/wizard/cancel", methods=["GET", "POST"])
@login_required
def wizard_cancel():
    """Annulla il wizard e torna alla dashboard."""
    session.pop(WIZARD_SESSION_KEY, None)
    flash(_("Creazione campionato annullata"), "info")
    return redirect(url_for("dashboard.dashboard"))


# =============================================================================
# ROUTE LEGACY (compatibilità con vecchi form)
# =============================================================================


@campionato_bp.route("/create", methods=["POST"])
@login_required
def create_campionato():
    """Crea nuovo campionato (LEGACY - mantiene compatibilità).

    DEPRECATO: Usa /wizard per il nuovo flusso multi-step.
    Questa route è mantenuta per retrocompatibilità con form esistenti.
    """
    if not (current_user.is_admin or current_user.is_director):
        flash(_("Non hai i permessi per creare un campionato."), "error")
        return redirect(url_for("dashboard.dashboard"))

    name = request.form.get("name", "").strip()
    if not name:
        flash(_("Il nome del campionato è obbligatorio"), "error")
        return redirect(url_for("dashboard.dashboard"))

    campionato_type = request.form.get("campionato_type", "amalfi")
    challenge_mode = "challenge_mode" in request.form

    # Deprecated fields (still supported for backwards compatibility)
    without_x = "without_x" in request.form
    final_playoffs = "final_playoffs" in request.form

    # Map without_x to default_odd_policy
    default_odd_policy = OddNumberPolicy.TRIO.value if without_x else OddNumberPolicy.BYE.value

    # Usa il service layer
    campionato = campionato_service.create_campionato_with_director(
        name=name,
        creator_user_id=current_user.id,
        campionato_type=campionato_type,
        challenge_mode=challenge_mode,
        is_active=True,
        default_odd_policy=default_odd_policy,
        # Legacy fields (deprecated but still passed for compatibility)
        without_x=without_x,
        final_playoffs=final_playoffs,
    )

    flash(_('Campionato "%(name)s" creato con successo!', name=name), "success")
    return redirect(url_for("dashboard.dashboard"))


@campionato_bp.route("/<int:campionato_id>")
@login_required
@campionato_manager_required(lambda campionato_id: campionato_id)
def campionato_detail(campionato_id):
    """Dettaglio campionato con gare"""
    # Use the service layer instead of direct database access
    campionato_data = campionato_service.get_campionato_detail_data(campionato_id)
    campionato = campionato_data["campionato"]
    gare = campionato_data["gare"]
    candidate_directors = campionato_data["candidate_directors"]

    # Controlla se l'utente può gestire director per questo campionato
    from models.user.models import DirectorAssignment

    can_manage_directors = current_user.is_admin or (
        db.session.query(DirectorAssignment)
        .filter(
            DirectorAssignment.entity_type == "campionato",
            DirectorAssignment.entity_id == campionato.id,
            DirectorAssignment.user_id == current_user.id,
        )
        .first()
        is not None
    )

    # Calcola statistiche avanzate del campionato
    campionato_stats = campionato_service.calculate_campionato_statistics(campionato_id)

    # Calcola classifica generale se ci sono gare completate o gare in corso con tutti i round completati
    general_classification = None
    last_completed_gara_number = None

    # Trova gare completate o gare "playing" ma con tutti i round completati
    eligible_garas = []
    for p in gare:
        if p.status == "completed":
            eligible_garas.append(p)
        elif p.status == "playing" and p.current_round > p.rounds_count:
            # Gara tecnicamente completata ma non ancora marcata come tale
            eligible_garas.append(p)

    if eligible_garas:
        last_completed_gara_number = max(p.number for p in eligible_garas)
        general_classification = campionato_service.calculate_general_classification(
            campionato_id
        )

    # Get verified venues for location suggestions
    from models.location.models import BilliardHall

    verified_venues = (
        BilliardHall.query.filter_by(is_active=True, verified=True)
        .order_by(BilliardHall.name)
        .all()
    )

    return render_template(
        "admin/campionato_detail.html",
        campionato=campionato,
        gare=gare,
        provas=gare,  # Alias per compatibilità con il template
        users=candidate_directors,
        can_manage_directors=can_manage_directors,
        campionato_stats=campionato_stats,
        general_classification=general_classification,
        last_completed_gara_number=last_completed_gara_number,
        verified_venues=verified_venues,
    )


@campionato_bp.route("/<int:campionato_id>/edit", methods=["GET", "POST"])
@campionato_manager_required(lambda campionato_id: campionato_id)
def edit_campionato(campionato_id):
    """Modifica campionato - allineato al wizard di creazione"""
    from models.location.models import BilliardHall

    campionato = db.session.get(Campionato, campionato_id)
    if campionato is None:
        abort(404)

    if not campionato.can_be_modified():
        flash(
            "Impossibile modificare il campionato: alcune gare hanno già delle iscrizioni!"
        )
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    if request.method == "POST":
        # Usa il service layer invece del direct database access
        try:
            # Parse default_venue_id (can be empty string)
            default_venue_id = request.form.get("default_venue_id")
            default_venue_id = int(default_venue_id) if default_venue_id else None

            # Parse default_entry_fee (can be empty string)
            default_entry_fee = request.form.get("default_entry_fee")
            default_entry_fee = (
                float(default_entry_fee) if default_entry_fee else None
            )

            # Parse planned_gare_count
            planned_gare_count = request.form.get("planned_gare_count")
            planned_gare_count = (
                int(planned_gare_count) if planned_gare_count else None
            )

            campionato_service.update_campionato(
                campionato_id=campionato_id,
                # Step 1 fields
                name=request.form["name"],
                campionato_type=request.form.get("campionato_type", "amalfi"),
                planned_gare_count=planned_gare_count,
                challenge_mode="challenge_mode" in request.form,
                scoring_policy=request.form.get("scoring_policy", "classic"),
                # Step 2 fields - Default gare settings
                default_venue_id=default_venue_id,
                default_entry_fee=default_entry_fee,
                default_rounds_count=int(
                    request.form.get("default_rounds_count", 3)
                ),
                default_odd_policy=request.form.get("default_odd_policy", "bye"),
                default_anti_rematch="default_anti_rematch" in request.form,
            )
            flash("Campionato aggiornato con successo!")
        except ValueError as ve:
            flash(str(ve), "error")

        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    # GET: Prepare data for template
    venues = BilliardHall.query.order_by(BilliardHall.name).all()
    matchmaking_strategies = [
        ("amalfi", "Amalfi"),
        ("random", "Random"),
    ]
    odd_policies = [
        ("bye", "X (vinto a tavolino)"),
        ("bye_with_challenge", "X con Challenge"),
        ("trio", "Match a 3 Giocatori"),
    ]

    return render_template(
        "admin/campionato_edit.html",
        campionato=campionato,
        venues=venues,
        matchmaking_strategies=matchmaking_strategies,
        odd_policies=odd_policies,
    )


@campionato_bp.route("/<int:campionato_id>/delete", methods=["POST"])
@campionato_manager_required(lambda campionato_id: campionato_id)
def delete_campionato(campionato_id):
    """Elimina campionato (service layer, gestione errori user-friendly)"""
    try:
        campionato_service.delete_campionato(campionato_id)
        flash("Campionato cancellato con successo!")
        return redirect(url_for("dashboard.dashboard"))
    except ValueError as ve:
        flash(str(ve))
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )
    except IntegrityError:
        flash("Cancellazione bloccata da vincoli di integrità.")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )


@campionato_bp.route("/<int:campionato_id>/soft-delete", methods=["POST"])
@login_required
@admin_required
def soft_delete_campionato(campionato_id):
    """Soft delete campionato - admin only.

    Marks the campionato and all its garas as deleted.
    Supports cascade options for related matches.
    """
    campionato = db.session.get(Campionato, campionato_id)
    if campionato is None:
        abort(404)

    # Get cascade option from form
    cascade_option = request.form.get("cascade_option", "delete_all")
    reason = request.form.get("reason", "").strip()

    campionato_name = campionato.name

    try:
        success = campionato_service.soft_delete_campionato(
            campionato_id=campionato_id,
            deleted_by_id=current_user.id,
            cascade_option=cascade_option,
            reason=reason
        )

        if success:
            if cascade_option == "keep_matches":
                flash(
                    f'Campionato "{campionato_name}" eliminato. '
                    f"I match sono stati mantenuti come match individuali.",
                    "success"
                )
            else:
                flash(f'Campionato "{campionato_name}" eliminato con successo!', "success")
        else:
            flash(f'Campionato "{campionato_name}" era già eliminato.', "warning")

    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    return redirect(url_for("dashboard.dashboard"))


@campionato_bp.route("/<int:campionato_id>/toggle_active", methods=["POST"])
@campionato_manager_required(lambda campionato_id: campionato_id)
def toggle_campionato_active(campionato_id):
    """Attiva/disattiva campionato"""
    # Usa il service layer invece del direct database access
    campionato = campionato_service.toggle_active_status(campionato_id)

    status = "attivato" if campionato.is_active else "disattivato"
    flash(f'Campionato "{campionato.name}" {status}!')
    return redirect(url_for("dashboard.dashboard"))


@campionato_bp.route("/<int:campionato_id>/add_director", methods=["POST"])
@login_required
@campionato_manager_required(lambda campionato_id: campionato_id)
def add_director(campionato_id):
    """Aggiunge un co‑direttore"""
    new_director_id = int(request.form["user_id"])

    # Usa il service layer invece del direct database access
    try:
        success = campionato_service.add_director(
            campionato_id=campionato_id,
            user_id=new_director_id,
            assigned_by_id=current_user.id,
        )

        if success:
            flash("Direttore aggiunto con successo.")
        else:
            flash("Questo utente è già un direttore.", "warning")

    except ValueError as ve:
        flash(str(ve), "warning")

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@campionato_bp.route("/<int:campionato_id>/remove_director", methods=["POST"])
@login_required
@campionato_manager_required(lambda campionato_id: campionato_id)
def remove_director(campionato_id):
    """Rimuove un co‑direttore"""
    director_id = int(request.form["user_id"])

    # Usa il service layer invece del direct database access
    success = campionato_service.remove_director(
        campionato_id=campionato_id, user_id=director_id
    )

    if success:
        flash("Direttore rimosso con successo.")
    else:
        flash("Direttore non trovato.", "warning")

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )
