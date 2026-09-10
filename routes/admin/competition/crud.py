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
)
from flask_login import login_required, current_user
from flask_babel import _, ngettext

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
from utils.analytics import AnalyticsEvent, track_event
from models.competition.services import GaraService
from models.matchmaking.configuration import get_available_strategies
from models.location.models import BilliardHall
from models.location.services import LocationService
from models.kpi import track_gara_create

from . import competition_bp


def _handle_venue_creation(
    location: str, tables_input: Optional[str] = None
) -> tuple[str, Optional[int]]:
    """Handle venue creation/validation for competitions.

    Delegates to LocationService.find_or_create_venue and flashes any user message.
    """
    loc, hall_id, msg = LocationService.find_or_create_venue(
        location=location,
        tables_input=tables_input,
        added_by_id=current_user.id,
    )
    if msg:
        flash(msg, "info" if hall_id else "warning")
    return (loc, hall_id)


@competition_bp.route("/create_standalone", methods=["GET", "POST"])
@login_required
@director_or_admin_required
def create_gara_standalone():
    """Crea gara standalone (admin o director)"""
    if request.method == "POST":
        try:
            from .form_parser import GaraFormParser

            name = request.form.get("name", "").strip()
            if not name:
                flash("Il nome della competizione è obbligatorio!", "error")
                return redirect(url_for("admin.competition.create_gara_standalone"))

            # Parse common fields
            parser = GaraFormParser(campionato=None)
            data = parser.parse()

            # Venue handling
            location_input = request.form.get("location", "").strip()
            tables_input = request.form.get("available_tables", "").strip()
            location, billiard_hall_id = _handle_venue_creation(
                location_input, tables_input
            )

            # Validate strategy configuration
            errors = GaraFormParser.validate_strategy(data)
            if errors:
                flash(f"Configurazione non valida: {', '.join(errors)}", "error")
                return redirect(url_for("admin.competition.create_gara_standalone"))

            # Competizione di prova (ADR-058): stessa gara, con il flag e la
            # scadenza. Il limite si controlla qui, prima di creare.
            e_prova = request.form.get("is_prova") == "on"
            if e_prova:
                from models.prova.service import ProvaService

                ProvaService.verifica_limite(current_user.id)
                data.update(ProvaService.campi_di_creazione())

            gara = GaraService.create_gara(
                campionato_id=None,
                number=1,
                name=name,
                billiard_hall_id=billiard_hall_id,
                location=location,
                director_id=current_user.id,
                **data,
            )

            if e_prova:
                from models.prova.visibility import invalida_ambito

                invalida_ambito()
                flash(
                    _("Prova «%(name)s» creata: solo tu la vedi.", name=name),
                    "success",
                )
            else:
                track_gara_create()
                track_event(
                    AnalyticsEvent.GARA_CREATED, gara_id=gara.id, standalone=True
                )
                flash(
                    _("Gara singola '%(name)s' creata con successo!", name=name),
                    "success",
                )
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
    available_strategies = get_available_strategies()

    from models.prova.service import LIMITE_PROVE_ATTIVE, ProvaService

    return render_template(
        "admin/gara_create_standalone.html",
        WithdrawPolicy=WithdrawPolicy,
        verified_venues=verified_venues,
        available_strategies=available_strategies,
        discipline_choices=Discipline.get_choices(),
        prove_attive=len(ProvaService.prove_attive(current_user.id)),
        limite_prove=LIMITE_PROVE_ATTIVE,
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
    campionato = db.get_or_404(Campionato, campionato_id)

    if not campionato.can_create_gara():
        flash(_("Non è possibile creare gare in un campionato terminato."), "error")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

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

    from .form_parser import GaraFormParser

    name = request.form.get("name", f"Gara {number}")

    # Venue handling
    location = request.form.get("location", "").strip()
    tables_input = request.form.get("available_tables", "").strip()
    location, billiard_hall_id = _handle_venue_creation(location, tables_input)

    try:
        # Parse common fields (campionato defaults as fallback per ADR-0001)
        # Dentro il `try`: `parse()` solleva su un modulo malformato — il peso
        # non positivo lo fa di proposito, ma `int(request.form["distance"])`
        # lo faceva gia' da sempre — e fuori di qui diventava un 500 invece di
        # un messaggio. `edit_gara` e `create_gara_standalone` lo chiamavano
        # gia' protetto: questa era l'unica delle tre a non farlo.
        parser = GaraFormParser(campionato=campionato)
        data = parser.parse()

        gara = GaraService.create_gara(
            campionato_id=campionato_id,
            number=number,
            name=name,
            billiard_hall_id=billiard_hall_id,
            location=location,
            **data,
        )

        track_event(AnalyticsEvent.GARA_CREATED, gara_id=gara.id, standalone=False)
        flash(_("Gara %(number)d creata con successo!", number=number))

        # "Auto-copia iscritti": il flag pilotava solo il precompilamento dei
        # campi lato client, nessuno copiava le iscrizioni (issue #58).
        if request.form.get("copy_from_previous"):
            from models.competition.inscription_service import InscriptionService

            previous = InscriptionService.find_previous_gara_in_campionato(gara)
            if previous is None:
                flash(
                    _("Nessuna gara precedente da cui copiare gli iscritti."),
                    "warning",
                )
            else:
                copied = InscriptionService.copy_inscriptions_from_gara(
                    previous.id, gara.id
                )
                if copied:
                    flash(
                        ngettext(
                            "%(num)d iscritto copiato dalla gara precedente.",
                            "%(num)d iscritti copiati dalla gara precedente.",
                            copied,
                        ),
                        "success",
                    )
                else:
                    flash(
                        _("Nessun iscritto da copiare dalla gara precedente."),
                        "warning",
                    )

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
    gara = db.get_or_404(Gara, gara_id)

    if not gara.can_be_modified():
        flash("Impossibile modificare la gara: ci sono già delle iscrizioni!")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    if request.method == "POST":
        from .form_parser import GaraFormParser

        # Venue auto-creation -> (location_str, billiard_hall_id)
        location = request.form.get("location", "").strip()
        tables_input = request.form.get("available_tables", "").strip()

        location, billiard_hall_id = _handle_venue_creation(location, tables_input)

        try:
            # Single source of truth for form↔model mapping: reuse the same parser
            # as create (and wizard). A campionato gara inherits its strategy and
            # classification system from the campionato; a standalone gara reads
            # them from the form. Hand-rolling the parsing here is what caused the
            # silent loss of `classification_system` (regression F9.2 / F7.5).
            parser = GaraFormParser(campionato=gara.campionato)
            data = parser.parse()

            errors = GaraFormParser.validate_strategy(data)
            if errors:
                flash(f"Configurazione non valida: {', '.join(errors)}", "error")
                return redirect(url_for("admin.competition.edit_gara", gara_id=gara_id))

            GaraService.update_gara(
                gara_id=gara_id,
                name=request.form.get("name", gara.name),
                billiard_hall_id=billiard_hall_id,  # FK to BilliardHall
                location=location,  # String for backward compat/display cache
                **data,
            )

            flash("Gara aggiornata con successo!")
        except ValueError as ve:
            flash(str(ve), "error")

        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    # Get available strategies for the form
    available_strategies = get_available_strategies()

    # Get verified venues for location suggestions
    verified_venues = (
        BilliardHall.query.filter_by(is_active=True, verified=True)
        .order_by(BilliardHall.name)
        .all()
    )

    from models.challenge.services import ChallengeService

    return render_template(
        "admin/gara_edit.html",
        gara=gara,
        # Gli esercizi offribili per la X (issue #267).
        x_challenges=ChallengeService.get_challenges_for_x_choice(
            includi_id=gara.x_challenge_id
        ),
        WithdrawPolicy=WithdrawPolicy,
        available_strategies=available_strategies,
        verified_venues=verified_venues,
        discipline_choices=Discipline.get_choices(),
    )


@competition_bp.route("/<int:gara_id>/tables-config", methods=["POST"])
@login_required
@gara_manager_required
def update_tables_config(gara_id):
    """Salva i tavoli della gara (in ordine di pregio) e il flag di
    assegnazione in base alla classifica (solo strategia random).

    Disponibile solo tra apertura iscrizioni e avvio gara (lo stato è
    validato da GaraService.update_tables_config).
    """
    db.get_or_404(Gara, gara_id)

    tables_input = request.form.get("available_tables", "").strip()
    tables = Gara.parse_tables_input(tables_input) if tables_input else []
    assign_by_ranking = "assign_tables_by_ranking" in request.form

    try:
        GaraService.update_tables_config(
            gara_id=gara_id,
            tables=tables,
            assign_tables_by_ranking=assign_by_ranking,
        )
        flash(_("Configurazione tavoli salvata!"), "success")
    except ValueError as e:
        flash(str(e), "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/delete", methods=["POST"])
@login_required
@gara_manager_required
def delete_gara(gara_id):
    """Cancella gara"""
    gara = db.get_or_404(Gara, gara_id)

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
    gara = db.get_or_404(Gara, gara_id)

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
            reason=reason,
        )

        if cascade_option == "keep_matches":
            flash(
                f"{gara_name} eliminata. I match sono stati mantenuti "
                "come match individuali.",
                "success",
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
    gara = db.get_or_404(Gara, gara_id)

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
