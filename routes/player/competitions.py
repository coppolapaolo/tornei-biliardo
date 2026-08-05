# routes/player/competitions.py
"""Competition-related routes: inscriptions, unsubscriptions, history."""

from flask import render_template, request, redirect, url_for, flash
from flask_babel import _
from flask_login import login_required, current_user

from models import db, Gara, Inscription, Match
from models.status_enum import GaraStatus
from models.kpi import track_gara_inscription
from utils import player_only, player_required
from utils.analytics import AnalyticsEvent, track_event

from . import player_bp
from models.base import utc_now

# ============ REDIRECTS (legacy compatibility) ============


@player_bp.route("/")
@login_required
def dashboard():
    return redirect(url_for("dashboard.dashboard"))


@player_bp.route("/gara/<int:gara_id>")
@login_required
@player_required
def gara_detail(gara_id):
    """
    DEPRECATED: Redirect to unified gara_detail view.
    La vista unificata in admin.competition.gara_detail si adatta
    automaticamente in base ai permessi dell'utente.
    """
    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


# ============ INSCRIPTIONS ============


@player_bp.route("/gara/<int:gara_id>/inscribe", methods=["POST"])
@login_required
@player_only
def inscribe_to_gara(gara_id):
    """Iscriviti a una gara"""
    gara = Gara.query.get_or_404(gara_id)

    # Verifica che le iscrizioni siano aperte
    now = utc_now()
    if (
        gara.status != GaraStatus.INSCRIPTION.value
        or now < gara.inscription_start
        or now > gara.inscription_end
    ):
        flash(_("Le iscrizioni non sono disponibili."))
        return redirect(url_for("main.index"))

    # Verifica che non sia già iscritto
    existing = Inscription.query.filter_by(
        user_id=current_user.id, gara_id=gara_id
    ).first()
    if existing:
        flash(_("Sei già iscritto a questa gara."))
        return redirect(url_for("player.dashboard"))

    # Usa il service per gestire automaticamente la logica waitlist
    from models.competition.inscription_service import InscriptionService

    inscription = InscriptionService.inscribe_user(
        user_id=current_user.id, gara_id=gara_id
    )

    if inscription:
        track_gara_inscription()  # KPI tracking
        track_event(
            AnalyticsEvent.GARA_INSCRIPTION,
            gara_id=gara_id,
            waitlist=inscription.is_waitlist,
        )
        if inscription.is_waitlist:
            flash(
                _(
                    "Aggiunto alla lista d'attesa per %(gara)s "
                    "(posizione %(position)d)!",
                    gara=gara.name,
                    position=inscription.waitlist_position,
                )
            )
        else:
            flash(_("Iscrizione a %(gara)s completata!", gara=gara.name))
    else:
        flash(_("Errore durante l'iscrizione."), "error")
    # Redirect alla dashboard appropriata
    return redirect(url_for("dashboard.dashboard"))


# ============ UNSUBSCRIPTION ============


@player_bp.route("/gara/<int:gara_id>/unsubscribe", methods=["POST"])
@login_required
@player_only
def unsubscribe_from_gara(gara_id):
    """Disiscrizione da una gara"""
    gara = Gara.query.get_or_404(gara_id)

    # Verifica che l'utente sia iscritto
    inscription = Inscription.query.filter_by(
        user_id=current_user.id, gara_id=gara_id
    ).first()
    if not inscription:
        flash("Non sei iscritto a questa gara.")
        return redirect(url_for("player.dashboard"))

    # Verifica che la gara non sia ancora iniziata
    if gara.status not in [GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value]:
        flash("Impossibile disiscriversii: la gara è già iniziata!")
        return redirect(url_for("player.dashboard"))

    # Verifica che non ci siano partite già create
    existing_matches = Match.query.filter(
        db.or_(
            Match.player1_id == current_user.id, Match.player2_id == current_user.id
        ),
        Match.gara_id == gara_id,
    ).first()

    if existing_matches:
        flash("Impossibile disiscriversii: ci sono già partite programmate!")
        return redirect(url_for("player.dashboard"))

    # Procedi con la disiscrizione usando il servizio
    from models.competition.inscription_service import InscriptionService

    success = InscriptionService.uninscribe_user(current_user.id, gara_id)

    if success:
        flash(f"Disiscrizione da {gara.name} completata!")
    else:
        flash("Errore durante la disiscrizione.", "error")

    # Redirect mantenendo il campionato selezionato
    return redirect(url_for("player.dashboard", campionato_id=gara.campionato_id))


# ============ PLAYER HISTORY ============


@player_bp.route("/history")
@login_required
@player_only
def history():
    """Storico completo del giocatore con filtri avanzati.

    Accessible to players and directors (blocked for pure admins).
    Supports three tabs: matches, gare, campionati.
    """
    from models.player.history_service import PlayerHistoryService, HistoryFilters

    # Get active tab (default: matches)
    tab = request.args.get("tab", "matches")
    if tab not in ("matches", "gare", "campionati"):
        tab = "matches"

    # Parse filters from request
    filters = HistoryFilters.from_request(request.args)
    page = request.args.get("page", 1, type=int)

    # Initialize data containers
    match_pagination = None
    match_stats = None
    gara_pagination = None
    gara_stats = None
    campionato_pagination = None

    # Fetch data based on active tab
    if tab == "matches":
        match_pagination, match_stats = PlayerHistoryService.get_match_history(
            user_id=current_user.id,
            filters=filters,
            page=page,
            per_page=20,
        )
    elif tab == "gare":
        gara_pagination, gara_stats = PlayerHistoryService.get_gara_history(
            user_id=current_user.id,
            filters=filters,
            page=page,
            per_page=20,
        )
    elif tab == "campionati":
        campionato_pagination = PlayerHistoryService.get_campionato_history(
            user_id=current_user.id,
            page=page,
            per_page=20,
            filters=filters,
        )

    # Get filter options for dropdowns
    filter_options = PlayerHistoryService.get_filter_options(current_user.id)

    return render_template(
        "player/history.html",
        active_tab=tab,
        match_pagination=match_pagination,
        match_stats=match_stats,
        gara_pagination=gara_pagination,
        gara_stats=gara_stats,
        campionato_pagination=campionato_pagination,
        filters=filters,
        filter_options=filter_options,
    )
