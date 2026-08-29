# routes/admin/campionato.py
"""Campionato management blueprint for admin interface.

Implements:
- Multi-step wizard for campionato creation (ADR-0001)
- Step 1: Base configuration (name, type, playoffs, challenge mode)
- Step 2: Default values for gare (venue, cost, rounds, odd policy)
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from flask_babel import _, lazy_gettext as _l

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
from models.competition.constants import DEFAULT_DISTANCE
from models.status_enum import Discipline, GaraStatus
from utils import (
    campionato_manager_required,
    admin_required,
    director_or_admin_required,
)
from models.campionato.services import TournamentService
from models.challenge.services import ChallengeService
from .campionato_form_parser import CampionatoFormParser
from .competition.form_parser import BRACKET_STRATEGIES

# Initialize the TournamentService
campionato_service = TournamentService()

# Campionato management blueprint
campionato_bp = Blueprint("campionato", __name__)

# Session key for wizard data
WIZARD_SESSION_KEY = "campionato_wizard_data"

# Formati selezionabili per un campionato. Elenco unico: prima era ripetuto in
# tre punti (wizard, salvataggio, modifica) e i tre erano liberi di divergere.
# L'ordine è quello mostrato all'utente.
CAMPIONATO_TYPES = [
    (MatchmakingStrategy.AMALFI.value, _l("Amalfi")),
    (MatchmakingStrategy.RANDOM.value, _l("Random")),
    (MatchmakingStrategy.DIRECT_ELIMINATION.value, _l("Eliminazione diretta")),
    (MatchmakingStrategy.DOUBLE_KNOCKOUT.value, _l("Doppio KO")),
]
CAMPIONATO_TYPE_VALUES = {value for value, _label in CAMPIONATO_TYPES}


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
    - challenge_mode: Abilita gli esercizi nelle gare del campionato
    - playoff_elite_enabled: Abilita playoff Elite
    - playoff_elite_participants: Numero partecipanti Elite (default: 6)
    - playoff_academy_enabled: Abilita playoff Academy
    - playoff_academy_participants: Numero partecipanti Academy (default: 6)
    """
    # Clear any previous wizard data
    session.pop(WIZARD_SESSION_KEY, None)

    return render_template(
        "admin/campionato_wizard_step1.html",
        matchmaking_strategies=CAMPIONATO_TYPES,
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

    campionato_type = request.form.get(
        "campionato_type", MatchmakingStrategy.AMALFI.value
    )
    if campionato_type not in CAMPIONATO_TYPE_VALUES:
        campionato_type = MatchmakingStrategy.AMALFI.value

    classification_system = request.form.get("default_classification_system", "WINS")
    if classification_system not in ["WINS", "RACK", "POSITION"]:
        classification_system = "WINS"

    # I formati a tabellone ammettono solo POSITION: imporlo qui evita che la
    # scelta del sistema di classifica e quella del formato possano divergere
    # (il wizard le presenta in due campi distinti).
    if campionato_type in BRACKET_STRATEGIES:
        classification_system = "POSITION"

    challenge_mode = "challenge_mode" in request.form

    # Playoff configuration
    playoff_elite_enabled = "playoff_elite_enabled" in request.form
    playoff_elite_participants = 6
    if playoff_elite_enabled:
        try:
            playoff_elite_participants = int(
                request.form.get("playoff_elite_participants", "6")
            )
        except ValueError:
            playoff_elite_participants = 6

    playoff_academy_enabled = "playoff_academy_enabled" in request.form
    playoff_academy_participants = 6
    if playoff_academy_enabled:
        try:
            playoff_academy_participants = int(
                request.form.get("playoff_academy_participants", "6")
            )
        except ValueError:
            playoff_academy_participants = 6

    # Store Step 1 data in session
    session[WIZARD_SESSION_KEY] = {
        "name": name,
        "planned_gare_count": planned_gare_count,
        "campionato_type": campionato_type,
        "default_classification_system": classification_system,
        "challenge_mode": challenge_mode,
        "playoff_elite_enabled": playoff_elite_enabled,
        "playoff_elite_participants": playoff_elite_participants,
        "playoff_academy_enabled": playoff_academy_enabled,
        "playoff_academy_participants": playoff_academy_participants,
    }

    # Get venues for dropdown
    venues = (
        BilliardHall.query.filter_by(is_active=True).order_by(BilliardHall.name).all()
    )

    # Filter odd policies based on classification system
    classification_system = session[WIZARD_SESSION_KEY].get(
        "default_classification_system", "WINS"
    )

    # All available policies with their compatible systems
    all_odd_policies = [
        (OddNumberPolicy.NO.value, _("Lista Attesa (solo pari)"), ["WINS", "RACK"]),
        (OddNumberPolicy.BYE.value, _("Bye (riposo)"), ["WINS"]),
        (
            OddNumberPolicy.BYE_WITH_CHALLENGE.value,
            _("Bye con esercizio"),
            ["WINS", "RACK"],
        ),
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

    # Step 2 default-gare settings (single source shared with edit_campionato)
    settings = CampionatoFormParser.parse_default_settings(request.form)

    # Classification system comes from Step 1 (session)
    classification_system = wizard_data.get("default_classification_system", "WINS")

    # Create the campionato
    try:
        campionato = campionato_service.create_campionato_with_director(
            name=wizard_data["name"],
            creator_user_id=current_user.id,
            campionato_type=wizard_data["campionato_type"],
            challenge_mode=wizard_data["challenge_mode"],
            is_active=True,
            planned_gare_count=wizard_data["planned_gare_count"],
            default_classification_system=classification_system,
            **settings,
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
            elite_size = (
                wizard_data.get("playoff_elite_participants", 6)
                if wizard_data.get("playoff_elite_enabled")
                else 0
            )
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

        flash(
            _('Campionato "%(name)s" creato con successo!', name=wizard_data["name"]),
            "success",
        )
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato.id)
        )

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
    campionato_service.create_playoff_config(
        campionato_id=campionato_id,
        name=name,
        max_participants=max_participants,
        positions_from=positions_from,
        positions_to=positions_to,
    )


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
    default_odd_policy = (
        OddNumberPolicy.TRIO.value if without_x else OddNumberPolicy.BYE.value
    )

    # Usa il service layer
    campionato_service.create_campionato_with_director(
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
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
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

    # Calcola classifica generale se ci sono gare completate o gare in corso con tutti i
    # round completati
    general_classification = None
    last_completed_gara_number = None

    # Trova gare completate o gare "playing" ma con tutti i round completati
    eligible_garas = []
    for p in gare:
        if p.status == GaraStatus.COMPLETED.value:
            eligible_garas.append(p)
        elif p.status == GaraStatus.PLAYING.value and p.current_round > p.rounds_count:
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

    # Playoff feasibility check (for terminate button warning)
    playoff_feasibility = None
    if campionato.has_playoff_configurations() and not campionato.terminated_at:
        playoff_feasibility = campionato_service.check_playoff_feasibility(
            campionato_id
        )

    # Playoff status (for terminated campionati with playoff configs)
    playoff_status = None
    campionato_players = []
    if campionato.terminated_at and campionato.has_playoff_configurations():
        from models.playoff.services import PlayoffService

        # Lazy expiration: check deadlines on page load
        PlayoffService.expire_old_qualifications()

        playoff_status = PlayoffService.get_campionato_playoff_status(campionato_id)

        # Get campionato players for manual add dropdown
        from models.competition.models import Inscription, Gara
        from models.user.models import User

        player_ids = (
            db.session.query(Inscription.user_id)
            .join(Gara)
            .filter(Gara.campionato_id == campionato_id)
            .distinct()
            .all()
        )
        campionato_players = (
            User.query.filter(User.id.in_([pid for (pid,) in player_ids]))
            .order_by(User.username)
            .all()
        )

    return render_template(
        "admin/campionato_detail.html",
        campionato=campionato,
        # Gli esercizi offribili per la X (issue #267): il modale di creazione
        # gara li mostra solo con `odd_number_policy = bye_with_challenge`.
        x_challenges=ChallengeService.get_challenges_for_x_choice(),
        gare=gare,
        users=candidate_directors,
        can_manage_directors=can_manage_directors,
        campionato_stats=campionato_stats,
        general_classification=general_classification,
        last_completed_gara_number=last_completed_gara_number,
        verified_venues=verified_venues,
        default_distance=DEFAULT_DISTANCE,
        discipline_choices=Discipline.get_choices(),
        default_discipline=Discipline.NINE_BALL.value,
        playoff_feasibility=playoff_feasibility,
        playoff_status=playoff_status,
        campionato_players=campionato_players,
    )


@campionato_bp.route("/<int:campionato_id>/edit", methods=["GET", "POST"])
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def edit_campionato(campionato_id):
    """Modifica campionato - allineato al wizard di creazione"""
    from models.location.models import BilliardHall

    campionato = db.get_or_404(Campionato, campionato_id)

    if not campionato.can_be_modified():
        flash(
            (
                "Impossibile modificare il campionato: alcune gare hanno già delle "
                "iscrizioni!"
            )
        )
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    if request.method == "POST":
        # Usa il service layer invece del direct database access
        try:
            # Parse planned_gare_count (Step 1 field)
            planned_gare_count = request.form.get("planned_gare_count")
            planned_gare_count = int(planned_gare_count) if planned_gare_count else None

            # Default-gare settings (single source shared with wizard_create)
            settings = CampionatoFormParser.parse_default_settings(request.form)

            campionato_service.update_campionato(
                campionato_id=campionato_id,
                # Step 1 fields
                name=request.form["name"],
                campionato_type=request.form.get("campionato_type", "amalfi"),
                planned_gare_count=planned_gare_count,
                challenge_mode="challenge_mode" in request.form,
                default_classification_system=request.form.get(
                    "default_classification_system", "WINS"
                ),
                # Step 2 fields - Default gare settings (shared parser)
                **settings,
            )
            flash("Campionato aggiornato con successo!")
        except ValueError as ve:
            flash(str(ve), "error")

        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    # GET: Prepare data for template
    venues = BilliardHall.query.order_by(BilliardHall.name).all()
    matchmaking_strategies = CAMPIONATO_TYPES
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
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
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
    campionato = db.get_or_404(Campionato, campionato_id)

    # Get cascade option from form
    cascade_option = request.form.get("cascade_option", "delete_all")
    reason = request.form.get("reason", "").strip()

    campionato_name = campionato.name

    try:
        success = campionato_service.soft_delete_campionato(
            campionato_id=campionato_id,
            deleted_by_id=current_user.id,
            cascade_option=cascade_option,
            reason=reason,
        )

        if success:
            if cascade_option == "keep_matches":
                flash(
                    f'Campionato "{campionato_name}" eliminato. '
                    f"I match sono stati mantenuti come match individuali.",
                    "success",
                )
            else:
                flash(
                    f'Campionato "{campionato_name}" eliminato con successo!', "success"
                )
        else:
            flash(f'Campionato "{campionato_name}" era già eliminato.', "warning")

    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    return redirect(url_for("dashboard.dashboard"))


@campionato_bp.route("/<int:campionato_id>/terminate", methods=["POST"])
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def terminate_campionato(campionato_id):
    """Termina manualmente il campionato."""
    campionato = db.get_or_404(Campionato, campionato_id)
    campionato_name = campionato.name
    try:
        success = campionato_service.terminate_campionato(campionato_id)
        if success:
            flash(
                _(
                    'Campionato "%(name)s" terminato con successo.',
                    name=campionato_name,
                ),
                "success",
            )
        else:
            flash(_("Il campionato è già stato terminato."), "warning")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@campionato_bp.route("/<int:campionato_id>/update-playoff-min", methods=["POST"])
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def update_playoff_min(campionato_id):
    """Aggiorna min_garas_played di una configurazione playoff."""
    config_id = request.form.get("config_id", type=int)
    new_min = request.form.get("new_min", type=int)

    if not config_id or new_min is None or new_min < 0:
        flash(_("Parametri non validi."), "error")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    try:
        campionato_service.update_playoff_min_garas(campionato_id, config_id, new_min)
        flash(_("Requisito minimo gare aggiornato."), "success")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


# ── Playoff routes ──────────────────────────────────────────────


@campionato_bp.route("/<int:campionato_id>/start-playoff", methods=["POST"])
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def start_playoff(campionato_id):
    """Avvia i playoff: genera qualificazioni dalla classifica."""
    try:
        results = campionato_service.start_playoff(campionato_id)
        total = sum(len(qs) for qs in results.values())
        if total == 0:
            flash(
                _(
                    (
                        "Playoff avviati ma nessun giocatore qualificato. Verifica la "
                        "classifica."
                    )
                ),
                "warning",
            )
        else:
            flash(
                _("Playoff avviati: %(count)s giocatori qualificati.", count=total),
                "success",
            )
    except ValueError as ve:
        msg = str(ve)
        if "già avviati" in msg:
            flash(msg, "info")
        else:
            flash(msg, "error")

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@campionato_bp.route(
    "/<int:campionato_id>/create-playoff-gara/<int:config_id>", methods=["POST"]
)
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def create_playoff_gara(campionato_id, config_id):
    """Crea la gara playoff e iscrive i giocatori confermati."""
    from models.playoff.services import PlayoffService
    from models.playoff.models import PlayoffConfiguration

    config = db.session.get(PlayoffConfiguration, config_id)
    if not config or config.campionato_id != campionato_id:
        flash(_("Configurazione playoff non trovata."), "error")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    # If gara already exists, redirect to it
    if config.gara is not None:
        return redirect(
            url_for("admin.competition.gara_detail", gara_id=config.gara.id)
        )

    try:
        gara = PlayoffService.create_playoff_gara(config_id)
        flash(
            _('Gara playoff "%(name)s" creata con successo.', name=gara.name),
            "success",
        )
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara.id))
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )


@campionato_bp.route(
    "/<int:campionato_id>/playoff/<int:config_id>/add-player", methods=["POST"]
)
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def playoff_add_player(campionato_id, config_id):
    """Aggiunge manualmente un giocatore alla lista playoff."""
    from models.playoff.services import PlayoffService

    user_id = request.form.get("user_id", type=int)
    if not user_id:
        flash(_("Seleziona un giocatore."), "error")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    try:
        PlayoffService.admin_add_player(config_id, user_id, current_user.username)
        flash(_("Giocatore aggiunto ai playoff."), "success")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@campionato_bp.route(
    "/<int:campionato_id>/playoff/<int:config_id>/remove-player", methods=["POST"]
)
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def playoff_remove_player(campionato_id, config_id):
    """Rimuove un giocatore dalla lista playoff."""
    from models.playoff.services import PlayoffService

    qualification_id = request.form.get("qualification_id", type=int)
    if not qualification_id:
        flash(_("Qualificazione non specificata."), "error")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    try:
        PlayoffService.admin_remove_player(qualification_id, current_user.username)
        flash(_("Giocatore rimosso dai playoff."), "success")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@campionato_bp.route(
    "/<int:campionato_id>/playoff/<int:config_id>/respond", methods=["POST"]
)
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def playoff_respond_for_player(campionato_id, config_id):
    """Registra la risposta che un qualificato ha dato a voce al direttore."""
    from models.playoff.services import PlayoffService

    qualification_id = request.form.get("qualification_id", type=int)
    answer = (request.form.get("answer") or "").strip()

    if not qualification_id or answer not in ("accept", "decline"):
        flash(_("Risposta non valida."), "error")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    try:
        replacement = PlayoffService.respond_on_behalf(
            qualification_id,
            accept=(answer == "accept"),
            responded_by_id=current_user.id,
        )
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    if answer == "accept":
        flash(_("Partecipazione confermata per conto del giocatore."), "success")
    elif replacement is not None:
        flash(
            _(
                "Rifiuto registrato: l'invito passa a %(name)s.",
                name=replacement.user.username if replacement.user else "—",
            ),
            "success",
        )
    else:
        flash(
            _("Rifiuto registrato. Nessun altro giocatore idoneo da invitare."),
            "info",
        )

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@campionato_bp.route(
    "/<int:campionato_id>/playoff/<int:config_id>/scoring", methods=["POST"]
)
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def playoff_update_scoring(campionato_id, config_id):
    """Decide se la classifica finale è quella dei playoff, e con che peso."""
    from models.playoff.services import PlayoffService

    try:
        PlayoffService.update_scoring(
            config_id,
            final_ranking_mode=request.form.get("final_ranking_mode"),
            playoff_weight=request.form.get("playoff_weight", type=int),
        )
        flash(_("Regole della classifica finale aggiornate."), "success")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@campionato_bp.route(
    "/<int:campionato_id>/playoff/config/<int:config_id>/edit", methods=["POST"]
)
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def playoff_edit_config(campionato_id, config_id):
    """Modifica una configurazione playoff (solo pre-avvio)."""
    from models.playoff.services import PlayoffService

    fields = {}
    for key in (
        "name",
        "positions_from",
        "positions_to",
        "max_participants",
        "min_garas_played",
        "discipline",
        "distance",
        "rounds_count",
        "strategy_type",
        "odd_number_policy",
    ):
        val = request.form.get(key)
        if val is not None and val != "":
            if key in (
                "positions_from",
                "positions_to",
                "max_participants",
                "min_garas_played",
                "distance",
                "rounds_count",
            ):
                fields[key] = int(val)
            else:
                fields[key] = val
        elif val == "" and key in (
            "discipline",
            "strategy_type",
            "odd_number_policy",
            "min_garas_played",
            "distance",
            "rounds_count",
        ):
            fields[key] = None  # Clear override → inherit from campionato

    try:
        PlayoffService.update_configuration(config_id, **fields)
        flash(_("Configurazione playoff aggiornata."), "success")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@campionato_bp.route("/<int:campionato_id>/playoff/config/add", methods=["POST"])
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def playoff_add_config(campionato_id):
    """Aggiunge una nuova configurazione playoff."""
    from models.playoff.services import PlayoffService

    name = request.form.get("name", "").strip()
    positions_from = request.form.get("positions_from", type=int)
    positions_to = request.form.get("positions_to", type=int)
    max_participants = request.form.get("max_participants", type=int)

    if not name or not positions_from or not positions_to or not max_participants:
        flash(_("Tutti i campi obbligatori devono essere compilati."), "error")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    kwargs = {}
    min_garas = request.form.get("min_garas_played", type=int)
    if min_garas is not None:
        kwargs["min_garas_played"] = min_garas

    try:
        PlayoffService.add_configuration(
            campionato_id=campionato_id,
            name=name,
            positions_from=positions_from,
            positions_to=positions_to,
            max_participants=max_participants,
            **kwargs,
        )
        flash(_("Configurazione playoff aggiunta."), "success")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@campionato_bp.route(
    "/<int:campionato_id>/playoff/config/<int:config_id>/deactivate", methods=["POST"]
)
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def playoff_deactivate_config(campionato_id, config_id):
    """Disattiva una configurazione playoff."""
    from models.playoff.services import PlayoffService

    try:
        PlayoffService.deactivate_configuration(config_id)
        flash(_("Configurazione playoff disattivata."), "success")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@campionato_bp.route("/<int:campionato_id>/toggle_active", methods=["POST"])
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def toggle_campionato_active(campionato_id):
    """Attiva/disattiva campionato"""
    # Usa il service layer invece del direct database access
    campionato = campionato_service.toggle_active_status(campionato_id)

    status = "attivato" if campionato.is_active else "disattivato"
    flash(f'Campionato "{campionato.name}" {status}!')
    return redirect(url_for("dashboard.dashboard"))


@campionato_bp.route("/<int:campionato_id>/add_director", methods=["POST"])
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
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
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
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
