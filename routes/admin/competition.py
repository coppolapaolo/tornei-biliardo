# routes/admin/competition.py
"""Competition (Prova) management blueprint for admin interface."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
import random

from models import (
    db,
    Tournament,
    Prova,
    Inscription,
    Match,
    User,
    RoundClassification,
    PlayerEncounter,
    TrioMatch,
)
from utils import (
    prova_manager_required,
    trio_manager_required,
    create_round_matches,
)
from amalfi import (
    get_amalfi_classification,
    validate_amalfi_configuration,
)
from models.matchmaking.bootstrap import get_matchmaking_service
from models.competition.services import ProvaService
from models.match.services import MatchService
from models.status_enum import ProvaStatus, MatchStatus
from models.competition.models import WithdrawPolicy

# Competition management blueprint
competition_bp = Blueprint("competition", __name__)


@competition_bp.route("/create_standalone", methods=["GET", "POST"])
@login_required
def create_prova_standalone():
    """Crea nuova prova standalone - Solo per Director"""
    if not (current_user.is_admin or current_user.is_director):
        flash("Non hai i permessi per creare una competizione standalone.", "error")
        return redirect(url_for("main.index"))

    if request.method == "POST":
        # Validazione dati
        errors = ProvaService.validate_prova_data(request.form)
        if errors:
            for field, error in errors.items():
                flash(f"{field}: {error}", "error")
            return render_template(
                "admin/prova_create_standalone.html", WithdrawPolicy=WithdrawPolicy
            )

        # Creazione Prova standalone
        try:
            withdraw_policy = request.form.get(
                "withdraw_policy", WithdrawPolicy.EXCLUDE.value
            )
            prova = ProvaService.create_prova(
                number=int(request.form.get("number", 1)),
                name=request.form["name"],
                date=datetime.strptime(request.form["date"], "%Y-%m-%d").date(),
                discipline=request.form["discipline"],
                distance=int(request.form["distance"]),
                director_id=current_user.id,  # Standalone con director
                tournament_id=None,  # Nessun torneo
                location=request.form.get("location", ""),
                description=request.form.get("description", ""),
                rounds_count=int(request.form.get("rounds_count", 3)),
                min_participants=int(request.form.get("min_participants", 2)),
                max_participants=int(request.form["max_participants"])
                if request.form.get("max_participants")
                else None,
                entry_fee=float(request.form.get("entry_fee", 0.0)),
                best_of=not ("exact_number" in request.form),
                withdraw_policy=withdraw_policy,
            )

            flash(f'Gara singola "{prova.name}" creata con successo!')
            return redirect(url_for("admin.competition.prova_detail", prova_id=prova.id))

        except Exception as e:
            flash(f"Errore nella creazione: {str(e)}", "error")
            return render_template(
                "admin/prova_create_standalone.html", WithdrawPolicy=WithdrawPolicy
            )

    # GET request - mostra form
    return render_template(
        "admin/prova_create_standalone.html", WithdrawPolicy=WithdrawPolicy
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
    tournament = Tournament.query.get_or_404(tournament_id)

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
        return redirect(url_for("admin.tournament.tournament_detail", tournament_id=tournament_id))

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

    # Crea la prova
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

    db.session.commit()

    flash(f"Prova {number} creata con successo!")
    return redirect(url_for("admin.tournament.tournament_detail", tournament_id=tournament_id))


@competition_bp.route("/<int:prova_id>/edit", methods=["GET", "POST"])
@login_required
@prova_manager_required
def edit_prova(prova_id):
    """Modifica prova"""
    prova = Prova.query.get_or_404(prova_id)

    if not prova.can_be_modified():
        flash("Impossibile modificare la prova: ci sono già delle iscrizioni!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    if request.method == "POST":
        # Aggiorna tutti i campi
        prova.name = request.form.get("name", prova.name)
        prova.date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        prova.location = request.form.get("location", "")
        prova.description = request.form.get("description", "")
        prova.rounds_count = int(request.form.get("rounds_count", 3))
        prova.min_participants = int(request.form.get("min_participants", 2))

        max_participants = request.form.get("max_participants")
        prova.max_participants = int(max_participants) if max_participants else None
        prova.entry_fee = float(request.form.get("entry_fee", 0.0))
        prova.discipline = request.form["discipline"]
        prova.distance = int(request.form["distance"])

        exact_number = "exact_number" in request.form
        prova.best_of = not exact_number
        prova.withdraw_policy = request.form.get(
            "withdraw_policy", WithdrawPolicy.EXCLUDE.value
        )

        db.session.commit()
        flash("Prova aggiornata con successo!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    return render_template(
        "admin/prova_edit.html", prova=prova, WithdrawPolicy=WithdrawPolicy
    )


@competition_bp.route("/<int:prova_id>/delete", methods=["POST"])
@login_required
@prova_manager_required
def delete_prova(prova_id):
    """Cancella prova"""
    prova = Prova.query.get_or_404(prova_id)
    tournament_id = prova.tournament_id

    if not prova.can_be_deleted():
        flash("Impossibile cancellare la prova: ci sono già delle iscrizioni!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    prova_name = f"Prova {prova.number}"
    db.session.delete(prova)
    db.session.commit()

    flash(f"{prova_name} cancellata con successo!")
    if not tournament_id:
        return redirect(url_for("dashboard.dashboard"))
    return redirect(url_for("admin.tournament.tournament_detail", tournament_id=tournament_id))


@competition_bp.route("/<int:prova_id>")
@login_required
@prova_manager_required
def prova_detail(prova_id):
    """Dettaglio prova con iscrizioni e partite"""
    prova = Prova.query.get_or_404(prova_id)
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
    prova = Prova.query.get_or_404(prova_id)

    # Ottieni le date UTC dal JavaScript
    inscription_start = datetime.strptime(
        request.form["inscription_start_utc"], "%Y-%m-%dT%H:%M:%S"
    )
    inscription_end = datetime.strptime(
        request.form["inscription_end_utc"], "%Y-%m-%dT%H:%M:%S"
    )

    # Validazioni
    if inscription_start > inscription_end:
        flash("Errore: La data di inizio deve essere precedente alla data di fine!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    prova.inscription_start = inscription_start
    prova.inscription_end = inscription_end
    ProvaService.to_inscription(prova.id)

    db.session.commit()
    flash(
        "Iscrizioni aperte! Gli orari sono gestiti "
        "automaticamente nel tuo timezone locale."
    )
    return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))


@competition_bp.route("/<int:prova_id>/modify_inscription_dates", methods=["POST"])
@login_required
@prova_manager_required
def modify_inscription_dates(prova_id):
    """Modifica date di iscrizione per una prova"""
    prova = Prova.query.get_or_404(prova_id)

    if not prova.can_modify_inscription_dates():
        flash("Impossibile modificare le date: il primo turno è già stato avviato!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    inscription_start = datetime.strptime(
        request.form["inscription_start_utc"], "%Y-%m-%dT%H:%M:%S"
    )
    inscription_end = datetime.strptime(
        request.form["inscription_end_utc"], "%Y-%m-%dT%H:%M:%S"
    )

    if inscription_start > inscription_end:
        flash("Errore: La data di inizio deve essere precedente alla data di fine!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    prova.inscription_start = inscription_start
    prova.inscription_end = inscription_end

    now = datetime.utcnow()
    if inscription_start > now:
        ProvaService.reopen_setup(prova.id)
    elif inscription_start <= now <= inscription_end:
        ProvaService.to_inscription(prova.id)

    db.session.commit()
    flash("Date di iscrizione aggiornate con successo!")
    return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))


@competition_bp.route("/<int:prova_id>/start_first_round", methods=["POST"])
@login_required
@prova_manager_required
def start_first_round(prova_id):
    """Avvia primo turno della prova"""
    prova = Prova.query.get_or_404(prova_id)

    if prova.current_round != 0:
        flash("La prova è già iniziata!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    # Verifica numero minimo partecipanti
    inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()
    if len(inscriptions) < prova.min_participants:
        flash(f"Servono almeno {prova.min_participants} iscritti per avviare la prova!")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

    # Genera il sorteggio iniziale
    random.shuffle(inscriptions)

    # Assegna ordine sorteggio
    for i, inscription in enumerate(inscriptions, 1):
        inscription.initial_order = i

    # Crea abbinamenti primo turno
    create_round_matches(prova, inscriptions, 1)

    prova.current_round = 1
    ProvaService.start_playing(prova.id)
    db.session.commit()

    flash("Primo turno avviato!")
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
            return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))
        if round_number <= prova.current_round:
            flash(f"Il turno {round_number} è già stato avviato!")
            return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))
        if round_number != prova.current_round + 1:
            flash(f"Devi avviare prima il turno {prova.current_round + 1}!")
            return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

        validation = validate_amalfi_configuration(prova)
        if not validation["is_valid"]:
            for error in validation["errors"]:
                flash(f"Errore Amalfi: {error}", "error")
            return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))
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
                return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))

        # Service/Strategy (adapter al legacy engine)
        svc = get_matchmaking_service()
        pairings = svc.run(strategy_name="Amalfi", prova=prova, round_number=round_number)

        # Stato prova
        prova.current_round = round_number
        if prova.status != ProvaStatus.PLAYING.value:
            ProvaService.start_playing(prova.id)
        db.session.commit()

        # Messaggi basati su pairings
        total = len(pairings)
        n_trio = sum(1 for p in pairings if len(p.players) == 3)
        n_bye = sum(1 for p in pairings if len(p.players) == 1)
        n_normal = total - n_trio - n_bye

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

    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante la creazione del turno: {str(e)}", "error")
        return redirect(url_for("admin.competition.prova_detail", prova_id=prova_id))


# ============ GESTIONE TRII ============


@competition_bp.route("/trio/<int:trio_id>/add_rack", methods=["POST"])
@login_required
@trio_manager_required
def trio_add_rack(trio_id):
    """Aggiungi rack a partita trio"""
    trio = TrioMatch.query.get_or_404(trio_id)

    try:
        winner_id = int(request.form["winner_id"])

        # Verifica che il vincitore sia tra i giocatori del trio
        if winner_id not in [trio.player1_id, trio.player2_id, trio.player3_id]:
            return jsonify({"error": "Vincitore non valido per questo trio"}), 400

        # Aggiungi rack e gestisci rotazione
        trio.add_rack_win(winner_id)

        db.session.commit()

        # Prepara risposta con nuovo stato
        state = trio.get_current_state()

        return jsonify(
            {
                "success": True,
                "trio_completed": trio.is_completed,
                "winner_id": trio.winner_id,
                "current_state": {
                    "current_players": [
                        {"id": p.id, "username": p.username}
                        for p in state["current_players"]
                    ],
                    "waiting_player": {
                        "id": state["waiting_player"].id,
                        "username": state["waiting_player"].username,
                    }
                    if state["waiting_player"]
                    else None,
                    "scores": state["scores"],
                },
            }
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Errore durante aggiunta rack: {str(e)}"}), 500


@competition_bp.route("/trio/<int:trio_id>/reset", methods=["POST"])
@login_required
@trio_manager_required
def trio_reset(trio_id):
    """Reset completo trio"""
    trio = TrioMatch.query.get_or_404(trio_id)

    try:
        # Reset scores
        trio.player1_racks = 0
        trio.player2_racks = 0
        trio.player3_racks = 0

        # Reset state
        trio.current_player1_id = trio.player1_id
        trio.current_player2_id = trio.player2_id
        trio.waiting_player_id = trio.player3_id
        trio.is_completed = False
        trio.winner_id = None

        # Reset match associato
        MatchService.reset_to_pending(trio.match.id, clear_validation=True)
        trio.match.winner_id = None

        db.session.commit()

        return jsonify({"success": True, "message": "Trio resettato con successo"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Errore durante reset trio: {str(e)}"}), 500