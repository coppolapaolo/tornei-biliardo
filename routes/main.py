# routes/main.py - AGGIORNATO per correggere import path
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user, logout_user
from datetime import date
from models import db, Campionato, Gara, Classification, User, Inscription, Match
from config import Config


def _role_truthy(user, attr_name: str) -> bool:
    val = getattr(user, attr_name, None)
    if val is None:
        return False
    try:
        return bool(val() if callable(val) else val)
    except TypeError:
        return bool(val)


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Homepage pubblica; se autenticato → dashboard utente"""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    # Mostra TUTTI i campionati attivi
    active_campionatos = (
        Campionato.query.filter_by(is_active=True)
        .order_by(Campionato.created_at.desc())
        .all()
    )

    # Mostra anche le gare standalone pubbliche
    from models.status_enum import GaraStatus

    standalone_garas = (
        Gara.query.filter_by(campionato_id=None)
        .filter(Gara.status != GaraStatus.SETUP.value)  # Hide setup garas
        .order_by(Gara.date.desc())
        .limit(5)
        .all()
    )

    if not active_campionatos and not standalone_garas:
        return render_template("no_campionato.html")

    # Raccogli dati per TUTTI i campionati attivi
    tournaments_data = []
    for campionato in active_campionatos:
        # Prossime gare per questo campionato
        upcoming_garas = (
            Gara.query.filter(
                Gara.campionato_id == campionato.id, Gara.date >= date.today()
            )
            .order_by(Gara.date)
            .limit(3)
            .all()
        )

        # Classifica generale per questo campionato (top 5)
        top_classifications = (
            Classification.query.filter(Classification.campionato_id == campionato.id)
            .order_by(Classification.position)
            .limit(5)
            .all()
        )

        # Se non c'è classifica generale, gara a prendere la classifica della gara più recente
        if not top_classifications and campionato.campionato_type == "Amalfi":
            from models.classification.models import RoundClassification
            from models.status_enum import GaraStatus

            # Trova la gara completata più recente
            latest_completed_gara = (
                Gara.query.filter(
                    Gara.campionato_id == campionato.id,
                    Gara.status == GaraStatus.COMPLETED.value,
                )
                .order_by(Gara.date.desc())
                .first()
            )

            if latest_completed_gara:
                # Prendi la classifica dell'ultimo turno di questa gara
                top_classifications = (
                    RoundClassification.query.filter(
                        RoundClassification.gara_id == latest_completed_gara.id
                    )
                    .filter(
                        RoundClassification.round_number
                        == latest_completed_gara.current_round
                    )
                    .order_by(RoundClassification.position)
                    .limit(5)
                    .all()
                )

        tournaments_data.append(
            {
                "campionato": campionato,
                "upcoming_garas": upcoming_garas,
                "top_classifications": top_classifications,
            }
        )

    return render_template(
        "index.html",
        tournaments_data=tournaments_data,
        active_campionatos=active_campionatos,
        standalone_garas=standalone_garas,
    )


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
    """Lista pubblica dei campionati - visibile ai guest"""
    active_campionatos = (
        Campionato.query.filter_by(is_active=True)
        .order_by(Campionato.created_at.desc())
        .all()
    )

    return render_template(
        "public/campionatos_list.html", campionatos=active_campionatos
    )


@main_bp.route("/campionato/<int:campionato_id>/public")
def campionato_detail_public(campionato_id):
    """Dettaglio campionato pubblico - visibile ai guest"""
    campionato = db.session.get(Campionato, campionato_id)
    if campionato is None:
        abort(404)

    # Get all garas for this campionato
    garas = (
        Gara.query.filter_by(campionato_id=campionato_id).order_by(Gara.number).all()
    )

    # Get overall classification
    classifications = (
        Classification.query.filter_by(campionato_id=campionato_id)
        .order_by(Classification.position)
        .all()
    )

    return render_template(
        "public/campionato_detail.html",
        campionato=campionato,
        garas=garas,
        classifications=classifications,
    )


@main_bp.route("/garas")
def public_garas_list():
    """Lista pubblica delle gare standalone - visibile ai guest"""
    from models.status_enum import GaraStatus

    # Get all standalone garas
    standalone_garas = (
        Gara.query.filter_by(campionato_id=None)
        .filter(Gara.status != GaraStatus.SETUP.value)  # Hide setup garas
        .order_by(Gara.date.desc())
        .all()
    )

    return render_template("public/garas_list.html", garas=standalone_garas)


@main_bp.route("/gara/<int:gara_id>")
def gara_detail_public(gara_id):
    """Dettaglio gara pubblico - visibile anche ai guest non loggati"""
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        abort(404)

    # Per i guest (non loggati), inscription è sempre None e matches è sempre vuoto
    inscription = None
    matches = []

    # Se l'utente è loggato, controlla se è iscritto
    if current_user.is_authenticated:
        inscription = Inscription.query.filter_by(
            gara_id=gara_id, user_id=current_user.id
        ).first()

        # Se è iscritto, mostra le sue partite
        if inscription:
            matches = (
                Match.query.filter_by(gara_id=gara_id)
                .filter(
                    db.or_(
                        Match.player1_id == current_user.id,
                        Match.player2_id == current_user.id,
                    )
                )
                .order_by(Match.round_number, Match.id)
                .all()
            )

    # Recupera tutte le partite per mostrare l'andamento della gara
    all_matches = (
        Match.query.filter_by(gara_id=gara_id)
        .order_by(Match.round_number, Match.id)
        .all()
    )

    # Ottieni l'ultima classificazione disponibile
    current_round_classification = None
    latest_round_with_classification = None

    if gara.current_round > 0:
        from models.classification.models import RoundClassification

        for round_num in range(gara.current_round, 0, -1):
            classification = (
                RoundClassification.query.filter_by(
                    gara_id=gara_id, round_number=round_num
                )
                .order_by(RoundClassification.position)
                .all()
            )

            if classification:
                current_round_classification = classification
                latest_round_with_classification = round_num
                break

    # Usa un template pubblico dedicato
    return render_template(
        "public/gara_detail.html",
        gara=gara,
        inscription=inscription,
        matches=matches,
        all_matches=all_matches,
        current_round_classification=current_round_classification,
        latest_round_with_classification=latest_round_with_classification,
    )


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
    from werkzeug.security import generate_password_hash

    # Trova il prossimo numero disponibile
    counter = 1
    while True:
        username = f"player{counter}"
        existing = User.query.filter_by(username=username).first()
        if not existing:
            break
        counter += 1

    # Crea il nuovo utente
    new_user = User(
        username=username,
        email=f"{username}@debug.local",
        role="player",
        password_hash=generate_password_hash("123456"),
    )

    db.session.add(new_user)
    db.session.commit()

    flash(f"Player '{username}' creato con successo! Password: 123456", "success")
    return redirect(request.referrer or url_for("dashboard.dashboard"))


@main_bp.route("/debug/fill_gara/<int:gara_id>")
def debug_fill_gara(gara_id):
    """Riempie una gara fino al minimo di partecipanti - SOLO in modalità debug"""
    if not Config.DEBUG_MODE:
        return "Funzione non disponibile in produzione", 403

    from models.user.models import User
    from models.competition.models import Inscription
    from werkzeug.security import generate_password_hash

    gara = Gara.query.get_or_404(gara_id)

    # Conta iscritti attuali
    current_inscriptions = Inscription.query.filter_by(gara_id=gara_id).count()

    if current_inscriptions >= gara.min_participants:
        flash(
            f"La gara ha già {current_inscriptions} iscritti (min: {gara.min_participants})",
            "info",
        )
        return redirect(request.referrer or url_for("dashboard.dashboard"))

    # Calcola quanti giocatori servono
    needed = gara.min_participants - current_inscriptions

    # Trova giocatori esistenti non iscritti
    existing_player_ids = (
        db.session.query(Inscription.user_id).filter_by(gara_id=gara_id).subquery()
    )
    available_players = (
        User.query.filter(User.role == "player")
        .filter(User.deleted_at.is_(None))
        .filter(~User.id.in_(existing_player_ids))
        .limit(needed)
        .all()
    )

    # Se non ci sono abbastanza giocatori esistenti, creane di nuovi
    players_to_add = []
    players_to_add.extend(available_players)

    if len(available_players) < needed:
        # Trova il prossimo numero per i nuovi player
        counter = 1
        while len(players_to_add) < needed:
            username = f"player{counter}"
            existing = User.query.filter_by(username=username).first()
            if not existing:
                # Crea nuovo player
                new_player = User(
                    username=username,
                    email=f"{username}@debug.local",
                    role="player",
                    password_hash=generate_password_hash("123456"),
                )
                db.session.add(new_player)
                db.session.flush()  # Per ottenere l'ID
                players_to_add.append(new_player)
            counter += 1

    # Iscrive i giocatori alla gara
    new_inscriptions = 0
    for player in players_to_add[:needed]:
        inscription = Inscription(user_id=player.id, gara_id=gara_id)
        db.session.add(inscription)
        new_inscriptions += 1

    db.session.commit()

    flash(
        f"Aggiunti {new_inscriptions} iscritti alla gara. Totale: {current_inscriptions + new_inscriptions}",
        "success",
    )
    return redirect(
        request.referrer or url_for("admin.competition.gara_detail", gara_id=gara_id)
    )


@main_bp.route("/debug/complete_current_round/<int:gara_id>")
def debug_complete_current_round(gara_id):
    """Completa tutti i match in corso del turno attuale con risultati random - SOLO in modalità debug"""
    if not Config.DEBUG_MODE:
        return "Funzione non disponibile in produzione", 403

    from models.match.models import Match
    from models.status_enum import MatchStatus
    import random

    gara = Gara.query.get_or_404(gara_id)

    # Trova tutti i match in corso (status = 'pending')
    pending_matches = Match.query.filter_by(
        gara_id=gara_id, status=MatchStatus.PENDING.value
    ).all()

    if not pending_matches:
        flash("Nessun match in corso da completare!", "info")
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    completed_count = 0
    for match in pending_matches:
        # Skip se è un bye match (già completato)
        if match.is_bye:
            continue

        # Genera risultati random basati sulla modalità gara
        if gara.best_of:
            # Al meglio di N - il vincitore deve arrivare a get_winning_score()
            winning_score = gara.get_winning_score()
            loser_score = random.randint(0, winning_score - 1)

            # Random winner
            if random.choice([True, False]):
                match.player1_score = winning_score
                match.player2_score = loser_score
                match.winner_id = match.player1_id
            else:
                match.player1_score = loser_score
                match.player2_score = winning_score
                match.winner_id = match.player2_id
        else:
            # N rack esatti - la somma deve essere gara.distance
            total_score = gara.distance
            player1_score = random.randint(0, total_score)
            player2_score = total_score - player1_score

            # Il vincitore è chi ha più punti
            if player1_score > player2_score:
                match.winner_id = match.player1_id
            elif player2_score > player1_score:
                match.winner_id = match.player2_id
            else:
                # Pareggio - forza una vittoria random
                match.winner_id = random.choice([match.player1_id, match.player2_id])

            match.player1_score = player1_score
            match.player2_score = player2_score

        match.status = MatchStatus.COMPLETED.value
        # Check if all matches in gara are completed and auto-complete gara
        match._check_and_complete_gara_if_needed(match)
        completed_count += 1

    db.session.commit()

    # Dopo aver completato i match, controlla se ci sono turni da aggiornare
    from models.competition.services import GaraService

    GaraService.update_round_progression(gara_id)

    flash(
        f"Completati {completed_count} match del turno attuale con risultati random!",
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
