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
    from models.competition.invite_service import GaraInviteService
    from utils.safe_redirect import safe_next_url

    gara = Gara.query.get_or_404(gara_id)

    # Dove tornare dopo l'iscrizione: il pulsante sulla pagina della gara lo
    # valorizza, così chi si iscrive da lì ci resta invece di essere spedito
    # in dashboard senza sapere se ha funzionato.
    next_url = safe_next_url(request.form.get("next"))

    # Verifica che le iscrizioni siano aperte. Stessa lettura della finestra
    # usata dal link pubblico e dal pulsante (GaraInviteService): criteri
    # diversi qui e nel template fanno comparire un pulsante che poi rifiuta.
    if not GaraInviteService.inscription_open(gara):
        flash(_("Le iscrizioni non sono disponibili."))
        return redirect(next_url or url_for("main.index"))

    # Verifica che non sia già iscritto
    existing = Inscription.query.filter_by(
        user_id=current_user.id, gara_id=gara_id
    ).first()
    if existing:
        flash(_("Sei già iscritto a questa gara."))
        return redirect(next_url or url_for("player.dashboard"))

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
                    gara=gara.display_name,
                    position=inscription.waitlist_position,
                )
            )
        else:
            flash(_("Iscrizione a %(gara)s completata!", gara=gara.display_name))

        # Gara con le squadre: la scelta va chiesta **adesso**, non lasciata a
        # una card in fondo a una linguetta che chi si iscrive non apre mai
        # (US-8). Si torna sulla pagina della gara con il pannello gia' aperto;
        # resta comunque una scelta facoltativa — "senza squadra" e' una
        # risposta valida — e resta cambiabile fino al sorteggio.
        if gara.separate_teammates:
            target = next_url or url_for(
                "admin.competition.gara_detail", gara_id=gara_id
            )
            separator = "&" if "?" in target else "?"
            return redirect(f"{target}{separator}chiedi_squadra=1")
    else:
        flash(_("Errore durante l'iscrizione."), "error")
    # Redirect alla dashboard appropriata
    return redirect(next_url or url_for("dashboard.dashboard"))


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
        flash(_("Non sei iscritto a questa gara."))
        return redirect(url_for("player.dashboard"))

    # Verifica che la gara non sia ancora iniziata
    if gara.status not in [GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value]:
        flash(_("Impossibile disiscriversi: la gara è già iniziata!"))
        return redirect(url_for("player.dashboard"))

    # Verifica che non ci siano partite già create
    existing_matches = Match.query.filter(
        db.or_(
            Match.player1_id == current_user.id, Match.player2_id == current_user.id
        ),
        Match.gara_id == gara_id,
    ).first()

    if existing_matches:
        flash(_("Impossibile disiscriversi: ci sono già partite programmate!"))
        return redirect(url_for("player.dashboard"))

    # Procedi con la disiscrizione usando il servizio
    from models.competition.inscription_service import InscriptionService

    success = InscriptionService.uninscribe_user(current_user.id, gara_id)

    if success:
        flash(_("Disiscrizione da %(gara)s completata!", gara=gara.display_name))
    else:
        flash(_("Errore durante la disiscrizione."), "error")

    # Redirect mantenendo il campionato selezionato
    return redirect(url_for("player.dashboard", campionato_id=gara.campionato_id))


# ============ PLAYER HISTORY ============


@player_bp.route("/history/drill/<int:attempt_id>/delete", methods=["POST"])
@login_required
@player_only
def delete_drill_attempt(attempt_id):
    """Cancella una prova di esercizio dallo storico.

    L'annulla della schermata di allenamento toglie **l'ultima**, perché lì si
    sta giocando e l'errore da correggere è quello appena fatto. Qui si può
    togliere una prova qualsiasi: è il gesto da scrivania, per il punteggio
    inserito sbagliato che ci si accorge di avere in elenco.

    Stessa primitiva, stesse conseguenze: l'XP torna indietro e serie e
    traguardi si ricalcolano — se altri esercizi li reggono, non cambia niente.

    Le prove giocate **in gara** non passano di qui: hanno conseguenze in
    classifica, e non è chi le ha giocate a poterle togliere.
    """
    from models.challenge.models import ChallengeAttempt
    from models.challenge.services import ChallengeService

    attempt = db.session.get(ChallengeAttempt, attempt_id)
    if attempt is None or attempt.user_id != current_user.id:
        flash(_("Questa prova non è tua."), "danger")
        return redirect(url_for("player.history", tab="esercizi"))

    try:
        ChallengeService.delete_attempt(attempt_id=attempt_id, actor_id=current_user.id)
        flash(_("Prova cancellata."), "success")
    except Exception:
        flash(_("Non è stato possibile cancellare la prova."), "danger")

    # Il ritorno conserva i filtri: cancellare una riga non deve rimandare in
    # cima a un elenco che si era appena finito di restringere.
    argomenti = {
        chiave: valore
        for chiave, valore in request.args.items()
        if chiave not in ("tab",)
    }
    return redirect(url_for("player.history", tab="esercizi", **argomenti))


@player_bp.route("/history")
@login_required
@player_only
def history():
    """Storico completo del giocatore con filtri avanzati.

    Accessible to players and directors (blocked for pure admins).
    Cinque schede: partite, gare, campionati, esercizi, esami.

    La scheda «partite» tiene insieme le partite di torneo e le sfide
    individuali, che stanno su due tabelle diverse: prima interrogava solo la
    prima, e le sfide individuali non comparivano in nessuno storico.
    """
    from models.player.history_service import PlayerHistoryService, HistoryFilters

    # Get active tab (default: matches)
    tab = request.args.get("tab", "matches")
    if tab not in ("matches", "gare", "campionati", "esercizi", "esami"):
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
    drill_pagination = None
    drill_stats = None
    drill_trend = None
    drill_chart = None
    selected_drill = None
    match_donut = None
    exam_pagination = None
    exam_stats = None

    # Fetch data based on active tab
    if tab == "matches":
        match_pagination, match_stats = PlayerHistoryService.get_unified_match_history(
            user_id=current_user.id,
            filters=filters,
            page=page,
            per_page=20,
        )
        match_donut = PlayerHistoryService.context_donut(match_stats)
    elif tab == "esercizi":
        drill_pagination, drill_stats = PlayerHistoryService.get_drill_history(
            user_id=current_user.id,
            filters=filters,
            page=page,
            per_page=20,
        )
        # Selezionando un esercizio a punteggio si guarda il suo andamento nel
        # periodo filtrato. Senza selezione non si disegna niente: una media
        # di esercizi diversi non vuol dire nulla.
        challenge_id = request.args.get("challenge_id", type=int)
        if challenge_id:
            from models import Challenge

            selected_drill = db.session.get(Challenge, challenge_id)
            drill_trend = PlayerHistoryService.get_drill_trend(
                user_id=current_user.id,
                challenge_id=challenge_id,
                filters=filters,
            )
        if drill_trend:
            drill_chart = PlayerHistoryService.trend_chart(
                drill_trend,
                max_score=(selected_drill.max_score if selected_drill else None),
            )
    elif tab == "esami":
        exam_pagination, exam_stats = PlayerHistoryService.get_exam_history(
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
        drill_pagination=drill_pagination,
        drill_stats=drill_stats,
        drill_trend=drill_trend,
        drill_chart=drill_chart,
        selected_drill=selected_drill,
        match_donut=match_donut,
        exam_pagination=exam_pagination,
        exam_stats=exam_stats,
        filters=filters,
        filter_options=filter_options,
    )
