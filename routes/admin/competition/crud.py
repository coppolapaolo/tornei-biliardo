# routes/admin/competition/crud.py
"""CRUD operations for Gara (competition) management."""

import logging
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
from flask_babel import _, ngettext

from models import (
    db,
    Campionato,
    Gara,
    Inscription,
)
from models.status_enum import Discipline, GaraStatus
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
from models.exceptions import http_status_for_exception
from utils.route_helpers import ajax_error, ajax_success, is_ajax_request

from . import competition_bp

logger = logging.getLogger(__name__)


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


def _avviso_in_attesa(gara_id: int):
    from models.storia.avvisi import AvvisiModifiche

    return AvvisiModifiche.in_attesa(gara_id)


@competition_bp.route(
    "/<int:gara_id>/iscrizione/<int:inscription_id>/riconferma", methods=["POST"]
)
@login_required
@gara_manager_required
def riconferma_per_conto(gara_id, inscription_id):
    """Il direttore riconferma al posto del giocatore; resta nella storia."""
    from models.competition.riconferma import riconferma

    inscription = db.get_or_404(Inscription, inscription_id)
    if inscription.gara_id != gara_id:
        abort(404)
    try:
        riconferma(inscription.id, autore=current_user)
        flash(
            _(
                "Iscrizione di %(nome)s riconfermata: resta scritto che l'hai "
                "fatto tu.",
                nome=inscription.user.username,
            ),
            "success",
        )
    except ValueError as errore:
        flash(str(errore), "error")
    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/avviso/invia", methods=["POST"])
@login_required
@gara_manager_required
def invia_avviso_modifiche(gara_id):
    """Manda subito agli iscritti la notifica delle modifiche (ADR-075)."""
    from models.storia.avvisi import AvvisiModifiche

    db.get_or_404(Gara, gara_id)
    arrivate = AvvisiModifiche.invia(gara_id)
    flash(
        ngettext(
            "Notifica mandata a %(num)d giocatore.",
            "Notifica mandata a %(num)d giocatori.",
            arrivate,
        ),
        "success",
    )
    return redirect(url_for("admin.competition.edit_gara", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/edit", methods=["GET", "POST"])
@login_required
@gara_manager_required
def edit_gara(gara_id):
    """Modifica gara"""
    gara = db.get_or_404(Gara, gara_id)

    # A gara finita si corregge solo quanto conta nel campionato (ADR-075):
    # la pagina è quella della gara avviata, con il solo peso.
    if gara.status == GaraStatus.COMPLETED.value and gara.campionato_id:
        return _edit_gara_avviata(gara)

    if not gara.can_be_modified():
        flash(_("La gara è chiusa: non si modifica più."), "warning")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

    from .form_parser import GaraFormParser

    # A gara avviata la pagina è un'altra: mostra solo ciò che si può ancora
    # cambiare, e dice da che turno valgono le regole (ADR-075).
    if gara.is_avviata:
        return _edit_gara_avviata(gara)

    if request.method == "POST":
        import json

        # Venue auto-creation -> (location_str, billiard_hall_id)
        location = request.form.get("location", "").strip()
        tables_input = request.form.get("available_tables", "").strip()

        location, billiard_hall_id = _handle_venue_creation(location, tables_input)

        # Lo stato che il modulo mostrava all'apertura (ADR-075): dice quali
        # campi il direttore ha cambiato, e se qualcun altro li ha toccati.
        try:
            originali = json.loads(request.form.get("stato_iniziale") or "{}")
        except ValueError:
            originali = {}
        if not isinstance(originali, dict):
            originali = {}

        try:
            # Single source of truth for form↔model mapping: reuse the same parser
            # as create (and wizard). A campionato gara inherits its strategy and
            # classification system from the campionato; a standalone gara reads
            # them from the form. Hand-rolling the parsing here is what caused the
            # silent loss of `classification_system` (regression F9.2 / F7.5).
            parser = GaraFormParser(campionato=gara.campionato, gara=gara)
            data = parser.parse()

            errors = GaraFormParser.validate_strategy(data)
            if errors:
                flash(f"Configurazione non valida: {', '.join(errors)}", "error")
                return redirect(url_for("admin.competition.edit_gara", gara_id=gara_id))

            data["name"] = request.form.get("name", gara.name)
            data["location"] = location  # String for backward compat/display cache
            cambiati = GaraFormParser.campi_cambiati(data, originali)
            if "location" in cambiati:
                cambiati["billiard_hall_id"] = billiard_hall_id  # FK to BilliardHall

            if not cambiati:
                flash(_("Nessuna modifica da salvare."), "info")
            else:
                GaraService.update_gara(
                    gara_id=gara_id,
                    autore=current_user,
                    motivo=request.form.get("motivo"),
                    originali=originali,
                    **cambiati,
                )
                flash(_("Gara aggiornata: la modifica resta nella sua storia."))
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
    from models.storia.service import StoriaModificheService

    return render_template(
        "admin/gara_edit.html",
        gara=gara,
        stato_iniziale=GaraFormParser.valori_attuali(gara),
        storia=StoriaModificheService.voci_della_gara(gara.id),
        avviso_in_attesa=_avviso_in_attesa(gara.id),
        # Gli esercizi offribili per la X (issue #267).
        x_challenges=ChallengeService.get_challenges_for_x_choice(
            includi_id=gara.x_challenge_id
        ),
        WithdrawPolicy=WithdrawPolicy,
        available_strategies=available_strategies,
        verified_venues=verified_venues,
        discipline_choices=Discipline.get_choices(),
    )


def _stato_iniziale_dal_modulo() -> dict:
    """Lo stato che il modulo mostrava all'apertura (ADR-075)."""
    import json

    try:
        originali = json.loads(request.form.get("stato_iniziale") or "{}")
    except ValueError:
        return {}
    return originali if isinstance(originali, dict) else {}


def _edit_gara_avviata(gara: Gara):
    """Modifica di una gara avviata: logistica, regole dal turno dopo, spareggio."""
    from models.challenge.services import ChallengeService
    from models.competition.campi_modificabili import (
        LOGISTICA,
        PESO,
        REGOLE,
        SPAREGGIO,
        campi_bloccati,
        dal_turno,
    )
    from models.matchmaking.configuration import (
        FirstRoundPolicy,
        MatchmakingStrategy,
        OddNumberPolicy,
        StrategyConfiguration,
    )
    from models.storia.service import StoriaModificheService

    from .form_parser import GaraFormParser

    bloccati = campi_bloccati(gara)
    ammessi = (LOGISTICA | REGOLE | SPAREGGIO | PESO) - set(bloccati)

    if request.method == "POST":
        originali = _stato_iniziale_dal_modulo()
        try:
            parser = GaraFormParser(campionato=gara.campionato, gara=gara)
            data = parser.parse_a_gara_avviata(ammessi)
            if "name" in ammessi and "name" in request.form:
                data["name"] = request.form.get("name", gara.name)
            billiard_hall_id = None
            if "location" in ammessi and "location" in request.form:
                location, billiard_hall_id = _handle_venue_creation(
                    request.form.get("location", "").strip(), ""
                )
                data["location"] = location

            # Le regole nuove devono stare in piedi con la struttura che resta.
            if {"odd_number_policy", "distance", "is_race_to"} & data.keys():
                errori = StrategyConfiguration(
                    strategy=MatchmakingStrategy(gara.matchmaking_strategy),
                    first_round_policy=FirstRoundPolicy(
                        gara.first_round_policy or "random"
                    ),
                    odd_number_policy=OddNumberPolicy(
                        data.get("odd_number_policy", gara.odd_number_policy)
                    ),
                    anti_rematch_enabled=bool(gara.anti_rematch_enabled),
                    rounds_count=gara.rounds_count,
                ).validate(
                    distance=data.get("distance", gara.distance),
                    is_race_to=data.get("is_race_to", gara.is_race_to),
                )
                if errori:
                    raise ValueError(
                        _("Configurazione non valida: %(e)s", e=", ".join(errori))
                    )

            cambiati = GaraFormParser.campi_cambiati(data, originali)
            if "location" in cambiati:
                cambiati["billiard_hall_id"] = billiard_hall_id
            if not cambiati:
                flash(_("Nessuna modifica da salvare."), "info")
            else:
                GaraService.update_gara(
                    gara_id=gara.id,
                    autore=current_user,
                    motivo=request.form.get("motivo"),
                    originali=originali,
                    **cambiati,
                )
                flash(_("Gara aggiornata: la modifica resta nella sua storia."))
        except ValueError as ve:
            flash(str(ve), "error")
        return redirect(url_for("admin.competition.gara_detail", gara_id=gara.id))

    verified_venues = (
        BilliardHall.query.filter_by(is_active=True, verified=True)
        .order_by(BilliardHall.name)
        .all()
    )
    return render_template(
        "admin/gara_edit_avviata.html",
        gara=gara,
        chiusa=gara.status == GaraStatus.COMPLETED.value,
        stato_iniziale=GaraFormParser.valori_attuali(gara),
        storia=StoriaModificheService.voci_della_gara(gara.id),
        avviso_in_attesa=_avviso_in_attesa(gara.id),
        bloccati=bloccati,
        ammessi=ammessi,
        dal_turno=dal_turno(gara),
        x_challenges=ChallengeService.get_challenges_for_x_choice(
            includi_id=gara.x_challenge_id
        ),
        WithdrawPolicy=WithdrawPolicy,
        verified_venues=verified_venues,
        discipline_choices=Discipline.get_choices(),
    )


@competition_bp.route("/<int:gara_id>/tables-config", methods=["POST"])
@login_required
@gara_manager_required
def update_tables_config(gara_id):
    """Salva i tavoli della gara (in ordine di pregio) e il flag di
    assegnazione in base alla classifica (solo strategia random).

    In ogni stato della gara (canvas, decisione 1). Il form sta in piu'
    pagine — la preparazione, «Impostazioni gara» — e `next` riporta a
    quella da cui si e' salvato.
    """
    from utils.safe_redirect import safe_next_url

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
        flash(_("Tavoli salvati."), "success")
    except ValueError as e:
        flash(str(e), "error")

    ritorno = safe_next_url(request.form.get("next"))
    return redirect(
        ritorno or url_for("admin.competition.gara_detail", gara_id=gara_id)
    )


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
        flash(_("Gara «%(nome)s» eliminata.", nome=gara_name), "success")
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
    """Annulla la gara avvisando gli iscritti.

    La chiama il pulsante «Annulla la gara» con `fetch`, che su errore mostra il
    corpo della risposta: per quella chiamata si risponde in JSON anche quando
    il servizio fallisce. Prima un errore imprevisto usciva come pagina di
    Werkzeug e finiva incollato, HTML compreso, nel messaggio all'utente.
    """
    gara = db.get_or_404(Gara, gara_id)

    gara_name = gara.name
    if gara.campionato_id:
        destinazione = url_for(
            "admin.campionato.campionato_detail", campionato_id=gara.campionato_id
        )
    else:
        destinazione = url_for("dashboard.dashboard")
    pagina_gara = url_for("admin.competition.gara_detail", gara_id=gara_id)
    vuole_json = is_ajax_request() or request.is_json

    try:
        # Lo stato ammesso lo verifica il servizio, che solleva ValueError.
        GaraService.cancel_gara_with_notifications(gara_id, current_user.id)
    except (ValueError, PermissionError) as ve:
        if vuole_json:
            return ajax_error(str(ve), status=http_status_for_exception(ve))
        flash(str(ve), "error")
        return redirect(pagina_gara)
    except Exception as e:
        logger.error("Annullo della gara %s fallito: %s", gara_id, e, exc_info=True)
        messaggio = _("La gara non è stata annullata per un errore imprevisto.")
        if vuole_json:
            return ajax_error(messaggio, status=500)
        flash(messaggio, "error")
        return redirect(pagina_gara)

    messaggio = _(
        "«%(nome)s» annullata: gli iscritti ricevono la notifica.", nome=gara_name
    )
    flash(messaggio, "success")
    if vuole_json:
        return ajax_success(message=messaggio, data={"redirect": destinazione})
    return redirect(destinazione)
