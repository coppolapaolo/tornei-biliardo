# routes/main.py - AGGIORNATO per correggere import path
from typing import Optional

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
)
from flask_login import current_user, logout_user
from models import db, Campionato, Gara, User

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Homepage pubblica; se autenticato → dashboard utente"""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    from models.campionato.homepage_service import HomepageService

    data = HomepageService.get_homepage_data()
    if data is None:
        return render_template("no_campionato.html")

    return render_template("index.html", **data)


@main_bp.route("/privacy")
def privacy_policy():
    """Informativa privacy e cookie - pagina pubblica.

    Necessaria perché il sito usa uno strumento di analisi del traffico
    (Google Analytics). Il template legge da sé `config.GA_MEASUREMENT_ID`
    per mostrare la sezione sui cookie analitici solo quando il tracking è
    effettivamente attivo.
    """
    return render_template("privacy.html")


@main_bp.route("/reset")
def reset_database():
    """Reset completo del database - SOLO in modalità debug"""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Reset non disponibile in produzione", 403

    from utils.reset_manager import ResetManager

    manager = ResetManager()
    reset_options = manager.get_reset_options()

    return render_template("reset.html", reset_options=reset_options)


@main_bp.route("/reset/confirm", methods=["POST"])
def reset_database_confirm():
    """Conferma reset database"""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Reset non disponibile in produzione", 403

    password = request.form.get("password", "")
    reset_type = request.form.get("reset_type", "base")

    if password != "RESET_DB_CONFIRM":
        flash("Password di conferma errata!")
        return redirect(url_for("main.reset_database"))

    try:
        # LOGOUT dell'utente corrente prima del reset
        if current_user.is_authenticated:
            logout_user()

        from utils.reset_manager import ResetManager

        manager = ResetManager()
        result = manager.execute_reset(reset_type)

        if result["status"] == "success":
            flash(result["message"])
            flash("Sei stato disconnesso automaticamente. Rieffettua il login.", "info")
        else:
            flash(f"Errore: {result['message']}", "danger")

        return redirect(url_for("main.index"))

    except Exception as e:
        flash(f"Errore durante il reset: {str(e)}")
        return redirect(url_for("main.reset_database"))


@main_bp.route("/debug/login/<username>")
def quick_login(username):
    """Quick login per debug - SOLO in modalità debug"""
    from flask_login import login_user

    if not current_app.config.get("DEBUG_MODE", False):
        return "Quick login non disponibile in produzione", 403

    user = User.query.filter_by(username=username).first()
    if not user:
        flash(f"Utente {username} non trovato!")
        return redirect(url_for("main.index"))

    login_user(user)
    flash(f"Quick login effettuato come {username}!")

    return redirect(url_for("dashboard.dashboard"))


@main_bp.route("/campionatos")
def public_campionatos_list():
    """Lista pubblica dei campionati - visibile ai guest.

    Supporta filtro di stato derivato (in_corso/completati/terminati/all) e
    ricerca per nome. Lo stato è calcolato da `compute_campionato_status`
    via `Campionato.get_status()` e quindi va filtrato in Python — non c'è
    una colonna SQL equivalente.
    """
    from models.status_enum import TournamentStatus

    raw_status = (request.args.get("status") or "all").strip().lower()
    raw_query = (request.args.get("q") or "").strip()

    valid_statuses = {"all", "in_corso", "completati", "terminati"}
    status_filter = raw_status if raw_status in valid_statuses else "all"

    # is_deleted=False include i terminated come archivio storico
    # (vedi ADR-030 §"Scope"). is_active=False (terminated) appare
    # sotto filtro status="terminati".
    # Eager-load playoff config + tournament SEMPRE: get_status() viene chiamato
    # sia dal filtro per status sotto, sia dal template (badge status_badge_class
    # / status_text per OGNI campionato), e per i terminated consulta queste
    # relationship → senza eager-load resterebbe N+1 anche con status=all.
    from sqlalchemy.orm import joinedload
    from models.playoff.models import PlayoffConfiguration

    query = Campionato.query.filter_by(is_deleted=False).options(
        joinedload(Campionato.playoff_configurations).joinedload(
            PlayoffConfiguration.playoff_campionato
        )
    )
    if raw_query:
        query = query.filter(Campionato.name.ilike(f"%{raw_query}%"))

    campionatos = query.order_by(Campionato.created_at.desc()).all()

    if status_filter != "all":
        wanted = {
            "in_corso": {
                TournamentStatus.SETUP.value,
                TournamentStatus.REGISTRATION_OPEN.value,
                TournamentStatus.IN_PROGRESS.value,
            },
            "completati": {TournamentStatus.COMPLETED.value},
            "terminati": {TournamentStatus.TERMINATED.value},
        }[status_filter]
        campionatos = [c for c in campionatos if c.get_status() in wanted]

    return render_template(
        "public/campionatos_list.html",
        campionatos=campionatos,
        status_filter=status_filter,
        search_query=raw_query,
    )


@main_bp.route("/campionato/<int:campionato_id>/public")
def campionato_detail_public(campionato_id):
    """Dettaglio campionato pubblico - visibile ai guest"""
    from models.campionato.services import TournamentService
    from models.status_enum import GaraStatus

    campionato = db.get_or_404(Campionato, campionato_id)

    # Get all garas for this campionato
    garas = (
        Gara.query.filter_by(campionato_id=campionato_id).order_by(Gara.number).all()
    )

    # Calculate general classification using the service (handles Amalfi, Random, etc.)
    campionato_service = TournamentService()
    general_classification = campionato_service.calculate_general_classification(
        campionato_id
    )

    # Determine last completed gara number
    last_completed_gara_number = None
    completed_garas = [g for g in garas if g.status == GaraStatus.COMPLETED.value]
    if completed_garas:
        last_completed_gara_number = max(g.number for g in completed_garas)

    return render_template(
        "public/campionato_detail.html",
        campionato=campionato,
        garas=garas,
        general_classification=general_classification,
        last_completed_gara_number=last_completed_gara_number,
    )


@main_bp.route("/garas")
def public_garas_list():
    """Lista pubblica delle gare standalone - visibile ai guest.

    B5: split active vs completed gare so the guest sees two distinct
    sections instead of completed gare mixed with active ones.
    """
    from models.status_enum import GaraStatus
    from datetime import date as _date
    from sqlalchemy import and_, or_

    # SETUP con data passata = zombie, visibili solo al director (ADR-030
    # rev 2026-05-14). Le SETUP con data futura/NULL restano visibili al
    # pubblico come "in preparazione".
    today = _date.today()
    standalone_garas = (
        Gara.query.filter_by(campionato_id=None)
        .filter(
            or_(
                Gara.status != GaraStatus.SETUP.value,
                and_(
                    Gara.status == GaraStatus.SETUP.value,
                    or_(Gara.date.is_(None), Gara.date >= today),
                ),
            )
        )
        .order_by(Gara.date.desc())
        .all()
    )

    completed_status = GaraStatus.COMPLETED.value
    active_garas = [g for g in standalone_garas if g.status != completed_status]
    completed_garas = [g for g in standalone_garas if g.status == completed_status]

    return render_template(
        "public/garas_list.html",
        active_garas=active_garas,
        completed_garas=completed_garas,
    )


@main_bp.route("/g/<token>")
def gara_invite(token):
    """Link pubblico di iscrizione a una gara (issue #61).

    È l'indirizzo che il direttore stampa su una locandina o incolla in un
    post: chi lo segue arriva sulla pagina della gara con l'iscrizione in
    evidenza e conferma con un click. Chi non è autenticato passa da
    login/registrazione e torna qui, allo stesso punto.

    L'iscrizione non avviene aprendo il link. Quell'indirizzo è pubblico per
    costruzione, quindi chiunque lo conosca potrebbe incorporarlo altrove
    (`<img src="...">`) e iscrivere a sua insaputa chi passa di lì con la
    sessione aperta, sottraendo un posto a qualcun altro; il token casuale
    protegge dall'indovinarlo, non da questo. Resta la POST protetta da CSRF.

    Ogni altro caso (gara inesistente, iscrizioni non ancora aperte o già
    chiuse, gara in corso o conclusa) risponde con una dialog che dice cosa
    sta succedendo: chi arriva da una locandina non ha altro contesto.
    """
    from flask_babel import gettext as _
    from models.competition.invite_service import (
        GaraInviteService,
        InviteOutcome,
    )
    from utils.jinja import format_datetime_local_text
    from utils.page_modal import flash_page_modal

    gara = Gara.query.filter_by(public_token=token).first()
    if gara is None:
        # Il token non dice se la gara non è mai esistita o è stata
        # cancellata, e va bene così: la pagina non deve fare da oracolo.
        return render_template("public/invite_not_found.html"), 404

    if not current_user.is_authenticated:
        return redirect(
            url_for("auth.login", next=url_for("main.gara_invite", token=token))
        )

    result = GaraInviteService.evaluate(gara, current_user)

    gara_name = gara.display_name
    # Le due date vanno trattate una per una: `format_datetime_local_text`
    # rende "N/A" su None, e una finestra con una sola data impostata
    # diventerebbe "Iscrizioni dal N/A al 12/09" — peggio che tacere.
    inscription_window = None
    if gara.inscription_start and gara.inscription_end:
        inscription_window = _(
            "Iscrizioni dal %(start)s al %(end)s.",
            start=format_datetime_local_text(gara.inscription_start),
            end=format_datetime_local_text(gara.inscription_end),
        )
    elif gara.inscription_end:
        inscription_window = _(
            "Iscrizioni aperte fino al %(end)s.",
            end=format_datetime_local_text(gara.inscription_end),
        )
    elif gara.inscription_start:
        inscription_window = _(
            "Iscrizioni aperte dal %(start)s.",
            start=format_datetime_local_text(gara.inscription_start),
        )

    if result.outcome == InviteOutcome.ALREADY_INSCRIBED:
        flash_page_modal(
            title=_("Sei già iscritto"),
            body=_("Risulti iscritto a %(gara)s.", gara=gara_name),
            variant="success",
            icon="fa-circle-check",
        )
    elif result.outcome == InviteOutcome.ALREADY_WAITLISTED:
        flash_page_modal(
            title=_("Sei in lista d'attesa"),
            body=_(
                "Sei in lista d'attesa per %(gara)s, in posizione "
                "%(position)s. Se si libera un posto entri automaticamente.",
                gara=gara_name,
                position=result.waitlist_position,
            ),
            variant="warning",
            icon="fa-hourglass-half",
        )
    elif result.outcome == InviteOutcome.CONFIRM_NEEDED:
        flash_page_modal(
            title=_("Puoi iscriverti"),
            body=_(
                "Le iscrizioni a %(gara)s sono aperte: premi «Iscriviti» "
                "per confermare.",
                gara=gara_name,
            ),
            variant="info",
            icon="fa-user-plus",
            detail=inscription_window,
        )
    elif result.outcome == InviteOutcome.NOT_OPEN_YET:
        flash_page_modal(
            title=_("Iscrizioni non ancora aperte"),
            body=_(
                "Le iscrizioni a %(gara)s non sono ancora aperte.",
                gara=gara_name,
            ),
            variant="info",
            icon="fa-clock",
            detail=inscription_window,
        )
    elif result.outcome == InviteOutcome.CLOSED:
        flash_page_modal(
            title=_("Iscrizioni chiuse"),
            body=_("Le iscrizioni a %(gara)s sono chiuse.", gara=gara_name),
            variant="warning",
            icon="fa-lock",
            detail=inscription_window,
        )
    elif result.outcome == InviteOutcome.IN_PROGRESS:
        flash_page_modal(
            title=_("Gara già iniziata"),
            body=_(
                "%(gara)s è già iniziata: non è più possibile iscriversi, "
                "ma puoi seguire i risultati da questa pagina.",
                gara=gara_name,
            ),
            variant="info",
            icon="fa-play",
        )
    elif result.outcome == InviteOutcome.COMPLETED:
        flash_page_modal(
            title=_("Gara conclusa"),
            body=_(
                "%(gara)s è conclusa: qui trovi la classifica finale.",
                gara=gara_name,
            ),
            variant="info",
            icon="fa-flag-checkered",
        )
    elif result.outcome == InviteOutcome.CANCELLED:
        flash_page_modal(
            title=_("Gara annullata"),
            body=_("%(gara)s è stata annullata.", gara=gara_name),
            variant="danger",
            icon="fa-ban",
        )
    elif result.outcome == InviteOutcome.ERROR:
        flash_page_modal(
            title=_("Iscrizione non riuscita"),
            body=_(
                "Non è stato possibile iscriverti a %(gara)s. Riprova dal "
                "pulsante «Iscriviti».",
                gara=gara_name,
            ),
            variant="danger",
            icon="fa-triangle-exclamation",
        )
    # InviteOutcome.NOT_ELIGIBLE: admin, direttore della gara o playoff.
    # Nessuna dialog — la pagina che si apre gli dice già tutto quello che
    # può fare, e un avviso "non puoi iscriverti" al direttore che apre il
    # proprio link sarebbe rumore.

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara.id))


@main_bp.route("/gara/<int:gara_id>")
@main_bp.route("/public/gara/<int:gara_id>")
def gara_detail_public(gara_id):
    """
    DEPRECATED: Redirect to unified gara_detail view.
    La vista unificata in admin.competition.gara_detail si adatta
    automaticamente in base ai permessi dell'utente (anche per guest).
    """
    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@main_bp.route("/reset/save", methods=["POST"])
def save_reset_snapshot():
    """Salva lo stato corrente del database come snapshot"""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    name = request.form.get("name", "")
    description = request.form.get("description", "")

    if not name:
        flash("Il nome dello snapshot è obbligatorio!", "danger")
        return redirect(request.referrer or url_for("main.reset_database"))

    from utils.reset_manager import ResetManager

    manager = ResetManager()
    result = manager.save_current_state(name, description)

    if result["status"] == "success":
        flash(result["message"], "success")
    else:
        flash(result["message"], "danger")

    return redirect(request.referrer or url_for("main.reset_database"))


@main_bp.route("/debug/create_player")
def debug_create_player():
    """Crea un nuovo player con username 'player N' - SOLO in modalità debug"""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    from models.user.models import User

    # Trova il prossimo numero disponibile
    counter = 1
    while True:
        username = f"player{counter}"
        existing = User.query.filter_by(username=username).first()
        if not existing:
            break
        counter += 1

    # Crea il nuovo utente usando il servizio
    from models.user.services import UserService

    UserService.create_user(
        username=username,
        email=f"{username}@debug.local",
        role="player",
        password="123456",  # Il servizio si occupa dell'hashing
        send_verification_email=False,  # Skip email for debug users
    )

    flash(f"Player '{username}' creato con successo! Password: 123456", "success")
    return redirect(request.referrer or url_for("dashboard.dashboard"))


def _available_quick_login_players(gara_id: int):
    """Quick-login players (role=PLAYER) non già iscritti alla gara,
    in ordine quick-login (admin/director esclusi)."""
    from models.competition.models import Inscription
    from utils.database_utils import get_quick_login_users
    from models.user.role_enum import UserRole

    inscribed_ids = {
        i.user_id for i in Inscription.query.filter_by(gara_id=gara_id).all()
    }
    return [
        u
        for u in get_quick_login_users(limit=32)
        if u.role == UserRole.PLAYER.value and u.id not in inscribed_ids
    ]


def _current_active_inscriptions(gara_id: int) -> int:
    from models.competition.models import Inscription

    return Inscription.query.filter_by(
        gara_id=gara_id, is_waitlist=False, is_withdrawn=False
    ).count()


@main_bp.route("/debug/fill_gara/<int:gara_id>")
def debug_fill_gara(gara_id):
    """Riempi la gara fino al MIN partecipanti pescando dai quick-login."""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    gara = Gara.query.get_or_404(gara_id)
    current_active = _current_active_inscriptions(gara_id)

    min_required = gara.min_participants or 0
    if min_required <= 0:
        flash(
            "min_participants non impostato per questa gara: nulla da fare.",
            "info",
        )
        return redirect(request.referrer or url_for("dashboard.dashboard"))

    slots_needed = max(0, min_required - current_active)
    if slots_needed == 0:
        flash(
            f"Minimo già raggiunto ({current_active}/{min_required}).",
            "info",
        )
        return redirect(request.referrer or url_for("dashboard.dashboard"))

    # Rispetta anche il limite massimo, se più stringente
    if gara.max_participants and gara.max_participants > 0:
        slots_needed = min(slots_needed, gara.max_participants - current_active)

    candidates = _available_quick_login_players(gara_id)
    if not candidates:
        flash(
            "Nessun giocatore quick-login disponibile da iscrivere.",
            "info",
        )
        return redirect(request.referrer or url_for("dashboard.dashboard"))

    from models.competition.inscription_service import InscriptionService

    new_inscriptions = 0
    for player in candidates[:slots_needed]:
        inscription = InscriptionService.inscribe_user(player.id, gara_id)
        if inscription:
            new_inscriptions += 1

    flash(
        f"Aggiunti {new_inscriptions} iscritti dai quick-login. "
        f"Totale attivi: {current_active + new_inscriptions}/{min_required}",
        "success",
    )
    return redirect(
        request.referrer or url_for("admin.competition.gara_detail", gara_id=gara_id)
    )


@main_bp.route("/debug/inscribe_next_player/<int:gara_id>")
def debug_inscribe_next_player(gara_id):
    """Iscrive il prossimo quick-login player non ancora iscritto."""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    gara = Gara.query.get_or_404(gara_id)
    current_active = _current_active_inscriptions(gara_id)

    if gara.max_participants and current_active >= gara.max_participants:
        flash(
            f"Massimo raggiunto ({current_active}/{gara.max_participants}).",
            "info",
        )
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    candidates = _available_quick_login_players(gara_id)
    if not candidates:
        flash(
            "Nessun giocatore quick-login disponibile da iscrivere.",
            "info",
        )
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    from models.competition.inscription_service import InscriptionService

    player = candidates[0]
    inscription = InscriptionService.inscribe_user(player.id, gara_id)

    if inscription:
        flash(
            f"Iscritto '{player.username}'. "
            f"Totale attivi: {current_active + 1}"
            f"{'/' + str(gara.max_participants) if gara.max_participants else ''}",
            "success",
        )
    else:
        flash(f"Iscrizione di '{player.username}' fallita.", "warning")

    return redirect(
        request.referrer or url_for("admin.competition.gara_detail", gara_id=gara_id)
    )


def _debug_random_score_trio(match) -> bool:
    """Assegna un risultato random al TrioMatch associato a `match`.

    Distribuisce `total_played_racks` vittorie tra i 3 player rispettando
    il vincolo `max_per_player = 2 * num_rounds`. Chiama
    `TrioScoringService.set_result_direct` che si occupa di creare i
    TrioRack sintetici, calcolare il winner e completare il match.
    """
    import random
    from models.match.trio_scoring_service import TrioScoringService

    trio = match.trio_match
    if trio is None:
        return False

    config = trio.trio_config
    total = config.total_played_racks
    max_per = 2 * config.num_rounds
    pids = [trio.player1_id, trio.player2_id, trio.player3_id]

    def _distribute():
        counts = {pid: 0 for pid in pids}
        for _ in range(total):
            eligible = [pid for pid, c in counts.items() if c < max_per]
            if not eligible:
                return None
            counts[random.choice(eligible)] += 1
        return counts

    # Genera una distribuzione con un vincitore NETTO (top unico). Un pareggio
    # in testa lascerebbe winner_id=None (set_result_direct ripiega su Schulze
    # sui rack sintetici, che può restituire pareggio), rendendo il trio
    # incompleto ai fini di classifica/playoff — inutile per il debug footer
    # che deve far progredire la gara. I pareggi sono ~1/4 dei casi: rigenerare
    # converge immediatamente (P(100 pareggi consecutivi) ~ 0).
    counts = None
    for _ in range(100):
        candidate = _distribute()
        if candidate is None:
            return False
        top = max(candidate.values())
        if list(candidate.values()).count(top) == 1:
            counts = candidate
            break
    if counts is None:
        return False

    TrioScoringService.set_result_direct(
        trio.id,
        counts[trio.player1_id],
        counts[trio.player2_id],
        counts[trio.player3_id],
    )
    return True


def _debug_random_score_match(match) -> bool:
    """Assegna un risultato random a `match` (skip bye). True se completato.

    ADR-027: usa match.effective_* / match.distance_config per rispettare
    gli override RoundConfiguration. Per i match trio delega a
    `_debug_random_score_trio` che usa `TrioScoringService.set_result_direct`.
    """
    from models.status_enum import MatchStatus
    from models.classification.encounter_service import PlayerEncounterService
    import random

    if match.is_bye:
        return False
    if match.is_trio:
        return _debug_random_score_trio(match)

    if match.effective_is_race_to:
        winning_score = match.distance_config.get_winning_racks()
        loser_score = random.randint(0, winning_score - 1)
        if random.choice([True, False]):
            match.player1_score = winning_score
            match.player2_score = loser_score
            match.winner_id = match.player1_id
        else:
            match.player1_score = loser_score
            match.player2_score = winning_score
            match.winner_id = match.player2_id
    else:
        total = match.effective_distance
        p1 = random.randint(0, total)
        p2 = total - p1
        if p1 > p2:
            match.winner_id = match.player1_id
        elif p2 > p1:
            match.winner_id = match.player2_id
        else:
            match.winner_id = random.choice([match.player1_id, match.player2_id])
        match.player1_score = p1
        match.player2_score = p2

    match.status = MatchStatus.CLOSED_UNILATERALLY.value
    PlayerEncounterService.record_match_encounters(match)
    return True


def _debug_release_tables_and_reassign(matches, gara_id: int) -> int:
    """Rilascia table_assignment dei match completed e richiama il pull.

    Ritorna il numero di tavoli riassegnati ai match pending (anche dei
    turni successivi, grazie al sorting (round_number, id) di
    assign_available_tables).
    """
    from models.match.table_assignment_service import TableAssignmentService

    for m in matches:
        if m.table_assignment:
            m.table_assignment = None
            db.session.add(m)
    return TableAssignmentService.assign_available_tables(gara_id)


def _debug_incomplete_matches_in_round(gara_id: int, round_number: int):
    from models.match.models import Match
    from models.status_enum import MatchStatus

    return (
        Match.query.filter_by(gara_id=gara_id, round_number=round_number)
        .filter(
            Match.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value])
        )
        .all()
    )


def _debug_all_incomplete_matches(gara_id: int):
    """Tutti i match della gara in stato PENDING o PLAYING, ordinati per
    round e poi id. Necessario per strategie pre-generate (es. random)
    dove `gara.current_round` resta indietro rispetto al primo round che
    ha ancora match attivi.
    """
    from models.match.models import Match
    from models.status_enum import MatchStatus

    return (
        Match.query.filter_by(gara_id=gara_id)
        .filter(
            Match.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value])
        )
        .order_by(Match.round_number, Match.id)
        .all()
    )


def _debug_completable_matches(gara_id: int):
    """Match completabili da 'Complete Match': solo quelli con tavolo
    assegnato e in corso (PLAYING).

    Un match senza tavolo è PENDING (in attesa che un tavolo si liberi) e
    non è ancora "al tavolo": completarlo salterebbe la fase di gioco reale.
    In questo dominio `table_assignment` e stato PLAYING sono accoppiati
    (vedi TableAssignmentService.assign_available_tables), ma filtriamo su
    entrambi per esplicitare l'intento (bug 13 docs/debug20260528.md).
    """
    from models.match.models import Match
    from models.status_enum import MatchStatus

    return (
        Match.query.filter_by(gara_id=gara_id, status=MatchStatus.PLAYING.value)
        .filter(Match.is_bye == False)  # noqa: E712
        .filter(Match.table_assignment.isnot(None))
        .order_by(Match.round_number, Match.id)
        .all()
    )


def _debug_first_active_round(gara_id: int) -> Optional[int]:
    """Primo round_number con almeno un match non completato.

    Per gare random/round_robin che pre-generano tutti i turni,
    `gara.current_round` resta al valore raggiunto dalla progressione
    "stretta" (= tutti i match del turno N completati). Le debug action
    devono invece operare sul primo turno con match attivi, anche se
    `current_round` non è stato avanzato.
    """
    matches = _debug_all_incomplete_matches(gara_id)
    if not matches:
        return None
    return matches[0].round_number


@main_bp.route("/debug/complete_current_round/<int:gara_id>")
def debug_complete_current_round(gara_id):
    """Completa i match del primo round attivo con risultati random."""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    gara = Gara.query.get_or_404(gara_id)

    if gara.current_round == 0:
        flash("La gara non è ancora iniziata!", "warning")
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    # Per strategie pre-generate (random), `gara.current_round` può non
    # avanzare anche se il turno è di fatto concluso: usa il primo turno
    # con match attivi.
    target_round = _debug_first_active_round(gara_id)
    if target_round is None:
        flash("Nessun match da completare nella gara!", "info")
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    incomplete_matches = _debug_incomplete_matches_in_round(gara_id, target_round)

    completed_count = sum(1 for m in incomplete_matches if _debug_random_score_match(m))

    from models.competition.round_service import RoundService

    RoundService.update_round_progression(gara_id)
    assigned = _debug_release_tables_and_reassign(incomplete_matches, gara_id)

    flash(
        f"Completati {completed_count} match del turno {target_round} "
        f"({assigned} tavoli riassegnati ai turni successivi).",
        "success",
    )
    return redirect(
        request.referrer or url_for("admin.competition.gara_detail", gara_id=gara_id)
    )


@main_bp.route("/debug/complete_next_match/<int:gara_id>")
def debug_complete_next_match(gara_id):
    """Completa UN match con tavolo assegnato e in corso (PLAYING).

    Cerca in tutti i round, non solo `gara.current_round`: per strategie
    pre-generate (random) molti match dei turni successivi sono già
    PLAYING quando il current_round non si è ancora avanzato. Esclude i
    match PENDING senza tavolo: non sono ancora "al tavolo" (bug 13).
    """
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    import random

    gara = Gara.query.get_or_404(gara_id)
    if gara.current_round == 0:
        flash("La gara non è ancora iniziata!", "warning")
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    candidates = _debug_completable_matches(gara_id)
    if not candidates:
        flash(
            "Nessun match con tavolo assegnato e in corso da completare!",
            "info",
        )
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    chosen = random.choice(candidates)
    _debug_random_score_match(chosen)

    from models.competition.round_service import RoundService

    RoundService.update_round_progression(gara_id)
    assigned = _debug_release_tables_and_reassign([chosen], gara_id)

    flash(
        f"Completato 1 match (#{chosen.id}) del turno {chosen.round_number} "
        f"({assigned} tavoli riassegnati).",
        "success",
    )
    return redirect(
        request.referrer or url_for("admin.competition.gara_detail", gara_id=gara_id)
    )


@main_bp.route("/debug/complete_gara/<int:gara_id>")
def debug_complete_gara(gara_id):
    """Completa l intera gara: cicla su match pending/playing fino a fine gara.

    Per ogni iterazione:
    1. completa tutti i match del current_round
    2. update_round_progression avanza il current_round
    3. assign_available_tables assegna tavoli ai pending (sorting per round)
    4. start_next_round per strategie che generano on-demand (es. Amalfi)
    """
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    from models.competition.round_service import RoundService
    from models.status_enum import GaraStatus

    gara = Gara.query.get_or_404(gara_id)
    if gara.current_round == 0:
        flash("La gara non è ancora iniziata!", "warning")
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    total_completed = 0
    total_rounds_advanced = 0
    safety_iter = 0
    MAX_ITER = (gara.rounds_count or 1) + 5

    while safety_iter < MAX_ITER:
        safety_iter += 1
        db.session.refresh(gara)

        if gara.status == GaraStatus.COMPLETED.value:
            break

        # Per strategie pre-generate (random) usa il primo round con match
        # attivi, non `gara.current_round` (che resta indietro se i match
        # del round corrente sono tutti completi ma quelli successivi no).
        target_round = _debug_first_active_round(gara_id)
        if target_round is not None:
            incomplete = _debug_incomplete_matches_in_round(gara_id, target_round)
            for m in incomplete:
                if _debug_random_score_match(m):
                    total_completed += 1
            RoundService.update_round_progression(gara_id)
            _debug_release_tables_and_reassign(incomplete, gara_id)
            continue

        # Nessun match attivo: o la gara è finita, o siamo su una strategia
        # on-demand (es. Amalfi) e dobbiamo generare il prossimo turno.
        if gara.current_round >= (gara.rounds_count or 0):
            break
        next_round = gara.current_round + 1
        try:
            RoundService.start_next_round(gara_id, next_round)
            total_rounds_advanced += 1
        except Exception as e:
            flash(
                f"Stop al turno {gara.current_round}: "
                f"impossibile avviare il turno {next_round} ({e}).",
                "warning",
            )
            break

    flash(
        f"Complete gara: {total_completed} match completati, "
        f"{total_rounds_advanced} turni avanzati.",
        "success",
    )
    return redirect(
        request.referrer or url_for("admin.competition.gara_detail", gara_id=gara_id)
    )


@main_bp.route("/reset/delete/<snapshot_id>", methods=["POST"])
def delete_reset_snapshot(snapshot_id):
    """Elimina uno snapshot salvato"""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    from utils.reset_manager import ResetManager

    manager = ResetManager()
    result = manager.delete_snapshot(snapshot_id)

    if result["status"] == "success":
        flash(result["message"], "success")
    else:
        flash(result["message"], "danger")

    return redirect(url_for("main.reset_database"))
