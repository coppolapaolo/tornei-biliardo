# routes/main.py - AGGIORNATO per correggere import path
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, logout_user
from models import db, Campionato, Gara, User
from config import Config


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


@main_bp.route("/reset")
def reset_database():
    """Reset completo del database - SOLO in modalità debug"""
    if not Config.DEBUG_MODE:
        return "Reset non disponibile in produzione", 403

    from utils.reset_manager import ResetManager

    manager = ResetManager()
    reset_options = manager.get_reset_options()

    return render_template("reset.html", reset_options=reset_options)


@main_bp.route("/reset/confirm", methods=["POST"])
def reset_database_confirm():
    """Conferma reset database"""
    if not Config.DEBUG_MODE:
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
    from config import Config
    from flask_login import login_user

    if not Config.DEBUG_MODE:
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
    query = Campionato.query.filter_by(is_deleted=False)
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
    completed_garas = [g for g in garas if g.status == "completed"]
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


@main_bp.route("/gara/<int:gara_id>")
@main_bp.route("/public/gara/<int:gara_id>")
def gara_detail_public(gara_id):
    """
    DEPRECATED: Redirect to unified gara_detail view.
    La vista unificata in admin.competition.gara_detail si adatta
    automaticamente in base ai permessi dell'utente (anche per guest).
    """
    return redirect(url_for('admin.competition.gara_detail', gara_id=gara_id))


@main_bp.route("/reset/save", methods=["POST"])
def save_reset_snapshot():
    """Salva lo stato corrente del database come snapshot"""
    if not Config.DEBUG_MODE:
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
    if not Config.DEBUG_MODE:
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
        send_verification_email=False  # Skip email for debug users
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
        i.user_id
        for i in Inscription.query.filter_by(gara_id=gara_id).all()
    }
    return [
        u for u in get_quick_login_users(limit=32)
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
    if not Config.DEBUG_MODE:
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
    if not Config.DEBUG_MODE:
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


def _debug_random_score_match(match) -> bool:
    """Assegna un risultato random a `match` (skip bye/trio). True se completato.

    ADR-027: usa match.effective_* / match.distance_config per rispettare
    gli override RoundConfiguration.
    """
    from models.status_enum import MatchStatus
    from models.classification.encounter_service import PlayerEncounterService
    import random

    if match.is_bye or match.is_trio:
        return False

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

    match.status = MatchStatus.COMPLETED.value
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


@main_bp.route("/debug/complete_current_round/<int:gara_id>")
def debug_complete_current_round(gara_id):
    """Completa i match del turno attuale con risultati random (debug only)."""
    if not Config.DEBUG_MODE:
        return "Funzione non disponibile in produzione", 403

    gara = Gara.query.get_or_404(gara_id)

    if gara.current_round == 0:
        flash("La gara non è ancora iniziata!", "warning")
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    incomplete_matches = _debug_incomplete_matches_in_round(
        gara_id, gara.current_round
    )

    if not incomplete_matches:
        flash("Nessun match da completare nel turno attuale!", "info")
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    completed_count = sum(
        1 for m in incomplete_matches if _debug_random_score_match(m)
    )

    from models.competition.round_service import RoundService
    RoundService.update_round_progression(gara_id)
    assigned = _debug_release_tables_and_reassign(incomplete_matches, gara_id)

    flash(
        f"Completati {completed_count} match del turno attuale "
        f"({assigned} tavoli riassegnati ai turni successivi).",
        "success",
    )
    return redirect(
        request.referrer or url_for("admin.competition.gara_detail", gara_id=gara_id)
    )


@main_bp.route("/debug/complete_next_match/<int:gara_id>")
def debug_complete_next_match(gara_id):
    """Completa UN match pending/playing del turno corrente con scoring random."""
    if not Config.DEBUG_MODE:
        return "Funzione non disponibile in produzione", 403

    import random

    gara = Gara.query.get_or_404(gara_id)
    if gara.current_round == 0:
        flash("La gara non è ancora iniziata!", "warning")
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    candidates = [
        m for m in _debug_incomplete_matches_in_round(gara_id, gara.current_round)
        if not m.is_bye and not m.is_trio
    ]
    if not candidates:
        flash("Nessun match da completare nel turno attuale!", "info")
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
        f"Completato 1 match (#{chosen.id}) del turno {gara.current_round} "
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
    if not Config.DEBUG_MODE:
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

        # Stop se gara terminata
        if gara.status == GaraStatus.COMPLETED.value:
            break

        incomplete = _debug_incomplete_matches_in_round(gara_id, gara.current_round)
        if incomplete:
            for m in incomplete:
                if _debug_random_score_match(m):
                    total_completed += 1
            RoundService.update_round_progression(gara_id)
            _debug_release_tables_and_reassign(incomplete, gara_id)
            db.session.refresh(gara)

        # Se siamo all ultimo turno e tutto completato: fine
        if gara.current_round >= (gara.rounds_count or 0):
            # Verifica che davvero non ci siano residui
            if not _debug_incomplete_matches_in_round(gara_id, gara.current_round):
                break

        # Prova ad avanzare al turno successivo (idempotente per strategie
        # che pre-generano i match, es. random / round_robin)
        next_round = gara.current_round + 1
        if next_round > (gara.rounds_count or 0):
            break
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
    if not Config.DEBUG_MODE:
        return "Funzione non disponibile in produzione", 403

    from utils.reset_manager import ResetManager

    manager = ResetManager()
    result = manager.delete_snapshot(snapshot_id)

    if result["status"] == "success":
        flash(result["message"], "success")
    else:
        flash(result["message"], "danger")

    return redirect(url_for("main.reset_database"))
