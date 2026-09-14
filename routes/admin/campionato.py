# routes/admin/campionato.py
"""Campionato management blueprint for admin interface.

Implements:
- Multi-step wizard for campionato creation (ADR-0001)
- Step 1: Base configuration (name, type, playoffs, challenge mode)
- Step 2: Default values for gare (venue, cost, rounds, odd policy)
"""

from flask import (
    Blueprint,
    abort,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)
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
from utils.jinja import opzioni_dispari
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

    from models.prova.service import LIMITE_PROVE_ATTIVE, ProvaService

    return render_template(
        "admin/campionato_wizard_step1.html",
        matchmaking_strategies=CAMPIONATO_TYPES,
        classification_compatibility=get_classification_compatibility_map(),
        prove_attive=len(ProvaService.prove_attive(current_user.id)),
        limite_prove=LIMITE_PROVE_ATTIVE,
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
        # Competizione di prova (ADR-058): la spunta viaggia con il resto del
        # passo 1 e si applica alla creazione.
        "is_prova": CampionatoFormParser.parse_prova(request.form),
    }

    # Get venues for dropdown
    venues = (
        BilliardHall.query.filter_by(is_active=True).order_by(BilliardHall.name).all()
    )

    # Le formule dei dispari compatibili col sistema scelto al passo 1, coi
    # nomi che la gara mostrera' poi (unica fonte: utils.jinja).
    classification_system = session[WIZARD_SESSION_KEY].get(
        "default_classification_system", "WINS"
    )
    odd_policies = opzioni_dispari(classification_system)

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

    # Competizione di prova (ADR-058): stesso campionato, con il flag e la
    # scadenza. Il limite si controlla qui, prima di creare, ed è lo stesso
    # delle gare singole.
    e_prova = bool(wizard_data.get("is_prova"))
    if e_prova:
        from models.exceptions import ConflictError
        from models.prova.service import ProvaService

        try:
            ProvaService.verifica_limite(current_user.id)
        except ConflictError as errore:
            flash(str(errore), "error")
            return redirect(url_for("admin.campionato.wizard_start"))
        settings.update(ProvaService.campi_di_creazione())

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

        if e_prova:
            from models.prova.visibility import invalida_ambito

            invalida_ambito()
            flash(
                _(
                    "Prova «%(name)s» creata: solo tu la vedi.",
                    name=wizard_data["name"],
                ),
                "success",
            )
        else:
            flash(
                _(
                    'Campionato "%(name)s" creato con successo!',
                    name=wizard_data["name"],
                ),
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

    # La zona playoff nella classifica generale (canvas 7.1): chi verrebbe
    # invitato, o chi lo e' stato. Senza configurazioni non c'e' zona.
    from models.campionato.esito import (
        campionato_concluso,
        podio_da_classifica,
        vincitori_delle_gare,
    )
    from models.playoff.fase import FasePlayoff, fase_playoff
    from models.playoff.zona import zone_playoff

    # A campionato concluso (canvas «campionato-concluso») la fascia annuncia
    # il campione — il primo della classifica, non il vincitore della finale —
    # e la classifica perde la zona playoff, che non segna più niente.
    concluso = campionato_concluso(campionato)
    zone = (
        zone_playoff(campionato)
        if general_classification
        and campionato.has_playoff_configurations()
        and not concluso
        else []
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
        zone_playoff=zone,
        verified_venues=verified_venues,
        default_distance=DEFAULT_DISTANCE,
        discipline_choices=Discipline.get_choices(),
        default_discipline=Discipline.NINE_BALL.value,
        playoff_feasibility=playoff_feasibility,
        playoff_status=playoff_status,
        # A che punto sono i playoff: la fascia e gli invitati ne dipendono.
        fase_playoff=fase_playoff(campionato),
        FasePlayoff=FasePlayoff,
        concluso=concluso,
        podio=podio_da_classifica(general_classification) if concluso else [],
        # Chi ha vinto ogni gara conclusa, finale compresa: la stessa query
        # della vetrina.
        vincitori_gare=vincitori_delle_gare(gare),
        campionato_players=campionato_players,
        # La data con cui il modale «Nuova gara» si presenta: oggi o una
        # settimana dopo l'ultima; in una prova, domani o il giorno dopo
        # l'ultima (ADR-016 vuole le gare in ordine).
        data_proposta_gara=TournamentService.data_proposta_gara(campionato_id),
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
    # Tutte e quattro: il sistema di classifica si cambia nella stessa pagina,
    # e un campionato nato con la lista d'attesa deve ritrovarla nel menu —
    # senza la voce, il salvataggio la sostituiva in silenzio con la X.
    odd_policies = opzioni_dispari()

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
    """Avvia i playoff: genera qualificazioni dalla classifica.

    Data dei playoff e scadenza degli inviti arrivano dal foglio «Avvia i
    playoff», nel fuso di chi scrive (ADR-043). Il foglio le chiede entrambe;
    senza, il servizio tiene i valori di sempre.
    """
    from utils.local_time import parse_local_datetime

    try:
        results = campionato_service.start_playoff(
            campionato_id,
            scheduled_date=parse_local_datetime(request.form.get("scheduled_date")),
            response_deadline=parse_local_datetime(
                request.form.get("response_deadline")
            ),
        )
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
    "/<int:campionato_id>/playoff/<int:config_id>/calendario", methods=["POST"]
)
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def playoff_calendario(campionato_id, config_id):
    """Sposta la data dei playoff o la scadenza degli inviti, fino all'avvio."""
    from models.playoff.models import PlayoffConfiguration
    from models.playoff.services import PlayoffService
    from utils.local_time import parse_local_datetime

    config = db.session.get(PlayoffConfiguration, config_id)
    if not config or config.campionato_id != campionato_id:
        flash(_("Configurazione playoff non trovata."), "error")
    else:
        try:
            PlayoffService.aggiorna_calendario(
                config_id,
                scheduled_date=parse_local_datetime(request.form.get("scheduled_date")),
                response_deadline=parse_local_datetime(
                    request.form.get("response_deadline")
                ),
            )
            flash(_("Data e scadenza del playoff aggiornate."), "success")
        except ValueError as errore:
            flash(str(errore), "error")

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


# ────────────────────────────────────────────────────────────────────────────
# VETRINA: LOCANDINA E LINK EREDITATI DALLE GARE (issue #235)
# ────────────────────────────────────────────────────────────────────────────


@campionato_bp.route("/<int:campionato_id>/vetrina")
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def campionato_vetrina(campionato_id):
    """Locandina e link del campionato, che tutte le sue gare ereditano.

    È il caso normale: una grafica sola, caricata una volta, e ogni tappa si
    presenta allo stesso modo sui social. Una singola gara può sempre
    scavalcarla dalla propria vetrina — vedi `Gara.effective_banner_path`.

    Da qui si cura anche la **vetrina del campionato stessa** (`/c/<link>`),
    che è il secondo lotto della issue: descrizione, indirizzo leggibile e
    link esterno. I campi sono gli stessi della gara e fanno due mestieri
    insieme — quello che il campionato mostra sulla propria pagina, e quello
    che le sue gare ereditano quando non hanno niente di proprio.
    """
    from models.competition.showcase_service import ensure_campionato_public_token
    from utils.image_paths import ImagePathManager

    campionato = db.get_or_404(Campionato, campionato_id)

    # Una prova non ha una pagina pubblica: da fuori non esiste (ADR-058).
    if campionato.is_prova:
        flash(
            _(
                "Una competizione di prova non ha vetrina né link pubblico: "
                "in un campionato vero qui trovi il link da condividere."
            ),
            "info",
        )
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    banner = (
        ImagePathManager.url_from_db_path(campionato.banner_path)
        if campionato.banner_path
        else None
    )
    gare_che_ereditano = [g for g in campionato.gare if not g.banner_path]

    # Il token può mancare su un campionato costruito prima della migration
    # in un ambiente che non l'ha eseguita: si assegna qui, che è una
    # schermata di **scrittura** del direttore — non nella pagina pubblica,
    # dove una scrittura innescata da un crawler sarebbe un difetto.
    ensure_campionato_public_token(campionato)

    return render_template(
        "admin/campionato_vetrina.html",
        campionato=campionato,
        banner=banner,
        gare_che_ereditano=len(gare_che_ereditano),
        url_pubblica=url_for(
            "main.campionato_invite",
            identificatore=campionato.public_slug_or_token,
            _external=True,
        ),
        url_anteprima=url_for(
            "main.campionato_invite",
            identificatore=campionato.public_slug_or_token,
        ),
    )


# =============================================================================
# COMPETIZIONE DI PROVA (ADR-058)
# =============================================================================


def _torna_al_campionato(campionato_id: int) -> str:
    return url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)


@campionato_bp.route("/<int:campionato_id>/prova/elimina", methods=["POST"])
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def prova_elimina(campionato_id):
    """Elimina il campionato di prova con tutto ciò che gli appartiene."""
    from models.exceptions import DomainError
    from models.prova.service import ProvaService

    campionato = db.get_or_404(Campionato, campionato_id)
    if not campionato.is_prova:
        abort(404)
    nome = campionato.name
    try:
        ProvaService.elimina_prova(campionato_id=campionato_id)
    except DomainError as errore:
        flash(str(errore), "error")
        return redirect(_torna_al_campionato(campionato_id))
    flash(_("Prova «%(nome)s» eliminata.", nome=nome), "success")
    return redirect(url_for("dashboard.dashboard"))


@campionato_bp.route(
    "/<int:campionato_id>/prova/invito/<int:qualification_id>/<risposta>",
    methods=["POST"],
)
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def prova_rispondi_invito(campionato_id, qualification_id, risposta):
    """Il fittizio accetta o rifiuta l'invito ai playoff.

    Non è la risposta «per conto del giocatore» di
    `playoff_respond_for_player`: qui il fittizio risponde da solo, con i
    servizi della route del giocatore, e un rifiuto fa scattare il primo
    degli esclusi come nella realtà.
    """
    from models.exceptions import DomainError
    from models.playoff.models import PlayoffQualification
    from models.prova.simulation_service import SimulationService

    campionato = db.get_or_404(Campionato, campionato_id)
    if not campionato.is_prova or risposta not in ("accetta", "rifiuta"):
        abort(404)
    invito = db.session.get(PlayoffQualification, qualification_id)
    if (
        invito is None
        or invito.configuration is None
        or invito.configuration.campionato_id != campionato_id
    ):
        abort(404)
    try:
        sostituto = SimulationService.rispondi_invito(
            qualification_id, accetta=(risposta == "accetta")
        )
    except DomainError as errore:
        flash(str(errore), "error")
        return redirect(_torna_al_campionato(campionato_id))

    if risposta == "accetta":
        flash(_("Invito accettato."), "success")
    elif sostituto is not None:
        flash(
            _(
                "Rifiuto registrato: l'invito passa a %(name)s.",
                name=sostituto.user.username if sostituto.user else "—",
            ),
            "success",
        )
    else:
        flash(
            _("Rifiuto registrato. Nessun altro giocatore idoneo da invitare."),
            "info",
        )
    return redirect(_torna_al_campionato(campionato_id))


@campionato_bp.route(
    "/<int:campionato_id>/prova/inviti/accetta-tutti", methods=["POST"]
)
@login_required
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def prova_accetta_inviti(campionato_id):
    """Accetta tutti gli inviti ai playoff ancora in attesa dei fittizi."""
    from models.exceptions import DomainError
    from models.prova.simulation_service import SimulationService

    campionato = db.get_or_404(Campionato, campionato_id)
    if not campionato.is_prova:
        abort(404)
    try:
        quanti = SimulationService.accetta_tutti_gli_inviti(campionato_id)
    except DomainError as errore:
        flash(str(errore), "error")
        return redirect(_torna_al_campionato(campionato_id))
    if quanti == 0:
        flash(_("Nessun invito in attesa."), "info")
    else:
        flash(_("%(quanti)s inviti accettati.", quanti=quanti), "success")
    return redirect(_torna_al_campionato(campionato_id))


@campionato_bp.route("/<int:campionato_id>/vetrina", methods=["POST"])
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def salva_campionato_vetrina(campionato_id):
    """Descrizione, indirizzo leggibile e link esterno del campionato."""
    from models.competition.showcase_service import update_campionato_showcase
    from models.exceptions import DomainError

    db.get_or_404(Campionato, campionato_id)
    try:
        update_campionato_showcase(
            campionato_id,
            slug=request.form.get("slug"),
            external_url=request.form.get("external_url"),
            external_label=request.form.get("external_label"),
            description=request.form.get("description"),
        )
        flash(_("Vetrina del campionato aggiornata."), "success")
    except DomainError as errore:
        flash(str(errore), "danger")
    return redirect(
        url_for("admin.campionato.campionato_vetrina", campionato_id=campionato_id)
    )


@campionato_bp.route("/<int:campionato_id>/vetrina/banner", methods=["POST"])
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def carica_banner_campionato(campionato_id):
    """Carica la locandina del campionato."""
    import os

    from werkzeug.utils import secure_filename

    from models.base import utc_now
    from models.competition.showcase_service import set_campionato_banner
    from routes.admin.competition.vetrina import MISURA_BANNER
    from utils.image_paths import ImagePathManager
    from utils.image_upload import estensione_ammessa, salva_immagine_ridimensionata

    db.get_or_404(Campionato, campionato_id)
    destinazione = url_for(
        "admin.campionato.campionato_vetrina", campionato_id=campionato_id
    )

    file = request.files.get("banner")
    if file is None or not file.filename:
        flash(_("Nessuna immagine selezionata."), "warning")
        return redirect(destinazione)
    if not estensione_ammessa(file.filename):
        flash(_("Formato non supportato. Usa JPG, PNG o GIF."), "danger")
        return redirect(destinazione)

    try:
        nome = secure_filename(
            f"campionato_{campionato_id}_"
            f"{utc_now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        )
        ImagePathManager.ensure_banner_upload_dir()
        percorso = os.path.join(ImagePathManager.get_banner_upload_dir(), nome)
        salva_immagine_ridimensionata(file, percorso, max_size=MISURA_BANNER)
        set_campionato_banner(campionato_id, ImagePathManager.get_banner_db_path(nome))
        flash(
            _("Locandina caricata: la useranno tutte le gare senza una propria."),
            "success",
        )
    except Exception as errore:  # noqa: BLE001 — il messaggio va all'utente
        flash(
            _("Non è stato possibile caricare l'immagine: %(errore)s", errore=errore),
            "danger",
        )
    return redirect(destinazione)


@campionato_bp.route("/<int:campionato_id>/vetrina/banner/rimuovi", methods=["POST"])
@campionato_manager_required(lambda campionato_id, **_: campionato_id)
def rimuovi_banner_campionato(campionato_id):
    """Toglie la locandina del campionato."""
    from models.competition.showcase_service import set_campionato_banner

    db.get_or_404(Campionato, campionato_id)
    set_campionato_banner(campionato_id, None)
    flash(_("Locandina rimossa."), "info")
    return redirect(
        url_for("admin.campionato.campionato_vetrina", campionato_id=campionato_id)
    )
