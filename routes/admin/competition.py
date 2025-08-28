# routes/admin/competition.py
"""Competition (Prova) management blueprint for admin interface."""

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
    current_app,
)
from flask_login import login_required, current_user
from datetime import datetime

from models import (
    db,
    Tournament,
    Prova,
    Inscription,
    Match,
    User,
)
from models.status_enum import (
    ProvaStatus,
    MatchStatus,
)
from models.competition.models import WithdrawPolicy
from utils import (
    prova_manager_required,
    tournament_manager_required,
    admin_required,
    trio_manager_required,
)
from models.competition.services import ProvaService
from models.match.services import MatchService
from models.matchmaking.service import MatchmakingService
from amalfi.engine import get_amalfi_classification, validate_amalfi_configuration
from models.classification.models import RoundClassification

# Competition management blueprint
competition_bp = Blueprint("competition", __name__)


@competition_bp.route("/create_standalone", methods=["GET", "POST"])
@login_required
@admin_required
def create_prova_standalone():
    """Crea prova standalone (solo admin)"""
    if request.method == "POST":
        tournament_id = request.form.get("tournament_id")
        if not tournament_id:
            flash("Tournament ID mancante!", "error")
            return redirect(url_for("dashboard.dashboard"))

        tournament_id = int(tournament_id)
        tournament = db.session.get(Tournament, tournament_id)
        if tournament is None:
            abort(404)

        # Verifica permessi sul torneo
        if not (
            current_user.is_admin
            or (
                current_user.is_director
                and any(
                    td.user_id == current_user.id
                    for td in tournament.directors_association
                )
            )
        ):
            flash("Non puoi creare prove in questo torneo.", "error")
            return redirect(url_for("dashboard.dashboard"))

        number = int(request.form["number"])

        # Verifica che il numero prova non esista già
        existing = Prova.query.filter_by(
            tournament_id=tournament_id, number=number
        ).first()
        if existing:
            flash(f"La prova {number} esiste già!")
            return redirect(
                url_for(
                    "admin.tournament.tournament_detail", tournament_id=tournament_id
                )
            )

        # Campi base
        name = request.form.get("name", f"Prova {number}")
        date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()

        # Nuovi campi
        location = request.form.get("location", "")
        description = request.form.get("description", "")
        rounds_count = int(request.form.get("rounds_count", 3))
        min_participants = int(request.form.get("min_participants", 2))
        max_participants = request.form.get("max_participants")
        max_participants = int(max_participants) if max_participants else None
        entry_fee = float(request.form.get("entry_fee", 0.0))

        # Game settings
        discipline = request.form["discipline"]
        distance = int(request.form["distance"])
        exact_number = "exact_number" in request.form
        best_of = not exact_number

        # Crea la prova usando il service layer
        withdraw_policy = request.form.get(
            "withdraw_policy", WithdrawPolicy.EXCLUDE.value
        )
        ProvaService.create_prova(
            tournament_id=tournament_id,
            number=number,
            name=name,
            date=date,
            location=location,
            description=description,
            rounds_count=rounds_count,
            min_participants=min_participants,
            max_participants=max_participants,
            entry_fee=entry_fee,
            discipline=discipline,
            distance=distance,
            best_of=best_of,
            withdraw_policy=withdraw_policy,
        )

        flash(f"Prova {number} creata con successo!")
        return redirect(
            url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
        )

    # GET request - show form
    tournaments = Tournament.query.filter_by(is_active=True).all()
    return render_template(
        "admin/prova_create_standalone.html",
        tournaments=tournaments,
        WithdrawPolicy=WithdrawPolicy,
    )


@competition_bp.route("/create", methods=["POST"])
@login_required
def create_prova():
    """Crea nuova prova - Aggiornata per supportare standalone"""

    # Determina se è standalone o per torneo
    tournament_id = request.form.get("tournament_id")
    is_standalone = tournament_id == "standalone" or not tournament_id

    if is_standalone:
        # Redirect alla route standalone
        return redirect(url_for("admin.competition.create_prova_standalone"))

    # Codice esistente per prove con torneo...
    if not tournament_id:
        flash("Tournament ID mancante!", "error")
        return redirect(url_for("dashboard.dashboard"))

    tournament_id = int(tournament_id)
    tournament = db.session.get(Tournament, tournament_id)
    if tournament is None:
        abort(404)

    # Verifica permessi sul torneo
    if not (
        current_user.is_admin
        or (
            current_user.is_director
            and any(
                td.user_id == current_user.id for td in tournament.directors_association
            )
        )
    ):
        flash("Non puoi creare prove in questo torneo.", "error")
        return redirect(url_for("dashboard.dashboard"))

    number = int(request.form["number"])

    # Verifica che il numero prova non esista già
    existing = Prova.query.filter_by(tournament_id=tournament_id, number=number).first()
    if existing:
        flash(f"La prova {number} esiste già!")
        return redirect(
            url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
        )

    # Campi base
    name = request.form.get("name", f"Prova {number}")
    date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()

    # Nuovi campi
    location = request.form.get("location", "")
    description = request.form.get("description", "")
    rounds_count = int(request.form.get("rounds_count", 3))
    min_participants = int(request.form.get("min_participants", 2))
    max_participants = request.form.get("max_participants")
    max_participants = int(max_participants) if max_participants else None
    entry_fee = float(request.form.get("entry_fee", 0.0))

    # Game settings
    discipline = request.form["discipline"]
    distance = int(request.form["distance"])
    exact_number = "exact_number" in request.form
    best_of = not exact_number

    # Crea la prova usando il service layer
    withdraw_policy = request.form.get("withdraw_policy", WithdrawPolicy.EXCLUDE.value)
    ProvaService.create_prova(
        tournament_id=tournament_id,
        number=number,
        name=name,
        date=date,
        location=location,
        description=description,
        rounds_count=rounds_count,
        min_participants=min_participants,
        max_participants=max_participants,
        entry_fee=entry_fee,
        discipline=discipline,
        distance=distance,
        best_of=best_of,
        withdraw_policy=withdraw_policy,
    )

    flash(f"Prova {number} creata con successo!")
    return redirect(
        url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
    )


@competition_bp.route("/<int:prova_id>/edit", methods=["GET", "POST"])
@login_required
@prova_manager_required
def edit_prova(prova_id):
    """Modifica prova"""
    prova = db.session.get(Prova, prova_id)
    if prova is None:
        abort(404)

    if not prova.can_be_modified():
        flash("Impossibile modificare la prova: ci sono già delle iscrizioni!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    if request.method == "POST":
        # Usa il service layer invece del direct database access
        try:
            max_participants = request.form.get("max_participants")
            max_participants = int(max_participants) if max_participants else None

            exact_number = "exact_number" in request.form
            best_of = not exact_number

            ProvaService.update_prova(
                prova_id=prova_id,
                name=request.form.get("name", prova.name),
                date_str=request.form["date"],
                location=request.form.get("location", ""),
                description=request.form.get("description", ""),
                rounds_count=int(request.form.get("rounds_count", 3)),
                min_participants=int(request.form.get("min_participants", 2)),
                max_participants=max_participants,
                entry_fee=float(request.form.get("entry_fee", 0.0)),
                discipline=request.form["discipline"],
                distance=int(request.form["distance"]),
                best_of=best_of,
                withdraw_policy=request.form.get(
                    "withdraw_policy", WithdrawPolicy.EXCLUDE.value
                ),
            )
            flash("Prova aggiornata con successo!")
        except ValueError as ve:
            flash(str(ve), "error")

        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    return render_template(
        "admin/prova_edit.html", prova=prova, WithdrawPolicy=WithdrawPolicy
    )


@competition_bp.route("/<int:prova_id>/delete", methods=["POST"])
@login_required
@prova_manager_required
def delete_prova(prova_id):
    """Cancella prova"""
    prova = db.session.get(Prova, prova_id)
    if prova is None:
        abort(404)
    tournament_id = prova.tournament_id
    prova_name = f"Prova {prova.number}"

    # Usa il service layer invece del direct database access
    try:
        ProvaService.delete_prova(prova_id)
        flash(f"{prova_name} cancellata con successo!")
    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    if not tournament_id:
        return redirect(url_for("dashboard.dashboard"))
    return redirect(
        url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
    )


@competition_bp.route("/<int:prova_id>")
@login_required
@prova_manager_required
def prova_detail(prova_id):
    """Dettaglio prova con iscrizioni e partite"""
    prova = db.session.get(Prova, prova_id)
    if prova is None:
        abort(404)
    inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()
    matches = (
        Match.query.filter_by(prova_id=prova_id)
        .order_by(Match.round_number, Match.id)
        .all()
    )

    return render_template(
        "admin/prova_detail.html",
        prova=prova,
        inscriptions=inscriptions,
        matches=matches,
    )


@competition_bp.route("/<int:prova_id>/open_inscriptions", methods=["POST"])
@login_required
@prova_manager_required
def open_inscriptions(prova_id):
    """Apri iscrizioni per una prova"""
    # Ottieni le date UTC dal JavaScript
    inscription_start = datetime.strptime(
        request.form["inscription_start_utc"], "%Y-%m-%dT%H:%M:%S"
    )
    inscription_end = datetime.strptime(
        request.form["inscription_end_utc"], "%Y-%m-%dT%H:%M:%S"
    )

    # Usa il service layer invece del direct database access
    try:
        ProvaService.open_inscriptions(prova_id, inscription_start, inscription_end)
        flash(
            "Iscrizioni aperte! Gli orari sono gestiti "
            "automaticamente nel tuo timezone locale."
        )
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))


@competition_bp.route("/<int:prova_id>/modify_inscription_dates", methods=["POST"])
@login_required
@prova_manager_required
def modify_inscription_dates(prova_id):
    """Modifica date di iscrizione per una prova"""
    inscription_start = datetime.strptime(
        request.form["inscription_start_utc"], "%Y-%m-%dT%H:%M:%S"
    )
    inscription_end = datetime.strptime(
        request.form["inscription_end_utc"], "%Y-%m-%dT%H:%M:%S"
    )

    # Usa il service layer invece del direct database access
    try:
        ProvaService.modify_inscription_dates(
            prova_id, inscription_start, inscription_end
        )
        flash("Date di iscrizione aggiornate con successo!")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))


@competition_bp.route("/<int:prova_id>/start_first_round", methods=["POST"])
@login_required
@prova_manager_required
def start_first_round(prova_id):
    """Avvia primo turno della prova"""
    # Usa il service layer invece del direct database access
    try:
        ProvaService.start_first_round(prova_id)
        flash("Primo turno avviato!")
    except ValueError as ve:
        flash(str(ve), "error")

    return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))


@competition_bp.route("/<int:prova_id>/results_overview")
@login_required
@prova_manager_required
def prova_results_overview(prova_id):
    """Overview risultati prova per inserimento rapido (admin)"""
    prova = Prova.query.get_or_404(prova_id)

    # Organizza partite per turno
    matches_by_round = {}
    for round_num in range(1, prova.rounds_count + 1):
        matches_by_round[round_num] = (
            Match.query.filter_by(prova_id=prova_id, round_number=round_num)
            .order_by(Match.id)
            .all()
        )

    return render_template(
        "admin/prova_result_overview.html",
        prova=prova,
        matches_by_round=matches_by_round,
    )


# ============ SISTEMA AMALFI ============


@competition_bp.route("/amalfi/classification/<int:prova_id>/<int:round_number>")
@login_required
@prova_manager_required
def amalfi_classification(prova_id, round_number):
    """Visualizza classifica Amalfi dopo un turno specifico"""
    prova = Prova.query.get_or_404(prova_id)

    # Verifica che il turno sia valido
    if round_number < 1 or round_number > prova.rounds_count:
        flash(f"Turno {round_number} non valido per questa prova!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    # Verifica che il turno sia completato
    matches_in_round = Match.query.filter_by(
        prova_id=prova_id, round_number=round_number
    ).all()

    if not matches_in_round:
        flash(f"Il turno {round_number} non è ancora iniziato!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    # Controlla se tutti i match del turno sono completati
    incomplete_matches = [
        m for m in matches_in_round if m.status != MatchStatus.COMPLETED.value
    ]
    if incomplete_matches:
        flash(
            f"Il turno {round_number} non è ancora completato! "
            f"Mancano {len(incomplete_matches)} partite."
        )
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    # Ottieni o calcola classifica
    classification = get_amalfi_classification(prova_id, round_number)
    if not classification:
        # Calcola classifica se non esiste
        classification = RoundClassification.calculate_classification_after_round(
            prova_id, round_number
        )

    # Statistiche aggiuntive
    total_players = len(classification)
    inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()

    return render_template(
        "admin/amalfi_classification.html",
        prova=prova,
        round_number=round_number,
        classification=classification,
        total_players=total_players,
        inscriptions=inscriptions,
    )


@competition_bp.route(
    "/amalfi/start_round/<int:prova_id>/<int:round_number>", methods=["POST"]
)
@login_required
@prova_manager_required
def amalfi_start_round(prova_id, round_number):
    """Avvia un turno specifico con algoritmo Amalfi"""
    prova = Prova.query.get_or_404(prova_id)

    try:
        # Validazioni preliminari
        if round_number < 1 or round_number > prova.rounds_count:
            flash(f"Turno {round_number} non valido!")
            return redirect(
                url_for("admin.competition.prova_detail", prova_id=prova_id)
            )
        if round_number <= prova.current_round:
            flash(f"Il turno {round_number} è già stato avviato!")
            return redirect(
                url_for("admin.competition.prova_detail", prova_id=prova_id)
            )
        if round_number != prova.current_round + 1:
            flash(f"Devi avviare prima il turno {prova.current_round + 1}!")
            return redirect(
                url_for("admin.competition.prova_detail", prova_id=prova_id)
            )

        validation = validate_amalfi_configuration(prova)
        if not validation["is_valid"]:
            for error in validation["errors"]:
                flash(f"Errore Amalfi: {error}", "error")
            return redirect(
                url_for("admin.competition.prova_detail", prova_id=prova_id)
            )
        for warning in validation["warnings"]:
            flash(f"Attenzione: {warning}", "warning")

        if round_number > 1:
            prev_matches = Match.query.filter_by(
                prova_id=prova_id, round_number=round_number - 1
            ).all()
            incomplete_prev = [
                m for m in prev_matches if m.status != MatchStatus.COMPLETED.value
            ]
            if incomplete_prev:
                flash(f"Completa prima tutte le partite del turno {round_number-1}!")
                return redirect(
                    url_for("admin.competition.prova_detail", prova_id=prova_id)
                )

        # Crea il turno Amalfi usando il service layer
        total, n_normal, n_bye, n_trio = ProvaService.create_amalfi_round(
            prova_id, round_number
        )

        # Aggiorna lo stato della prova
        prova.current_round = round_number
        if prova.status != ProvaStatus.PLAYING.value:
            ProvaService.start_playing(prova.id)

        # Messaggi basati sui risultati
        flash(
            f"Turno {round_number} avviato con successo! "
            f"Creati {total} abbinamenti Amalfi."
        )
        if n_normal:
            flash(f"Abbinamenti normali: {n_normal}", "info")
        if n_bye:
            flash(f"Partite vs X: {n_bye}", "info")
        if n_trio:
            flash(f"Trii: {n_trio}", "info")

        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    except ValueError as ve:
        flash(str(ve), "error")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))
    except Exception as e:
        flash(f"Errore durante la creazione del turno: {str(e)}", "error")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))


# ============ GESTIONE TRII ============


@competition_bp.route("/trio/<int:trio_id>/add_rack", methods=["POST"])
@login_required
@trio_manager_required
def trio_add_rack(trio_id):
    """Aggiungi rack a partita trio"""
    try:
        winner_id = int(request.form["winner_id"])

        # Usa il service layer invece del direct database access
        result = ProvaService.add_trio_rack(trio_id, winner_id)
        return jsonify(result)

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante aggiunta rack: {str(e)}"}), 500


@competition_bp.route("/trio/<int:trio_id>/reset", methods=["POST"])
@login_required
@trio_manager_required
def trio_reset(trio_id):
    """Reset completo trio"""
    try:
        # Usa il service layer invece del direct database access
        ProvaService.reset_trio(trio_id)
        return jsonify({"success": True, "message": "Trio resettato con successo"})

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 500
    except Exception as e:
        return jsonify({"error": f"Errore durante reset trio: {str(e)}"}), 500
