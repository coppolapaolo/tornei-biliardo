# routes/admin.py - STEP 1: Aggiornato per nuovi models
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
    Rack,
    User,
    Classification,
    DirectorRequest,
)
from utils import (
    admin_required,
    create_round_matches,
    tournament_manager_required,
    prova_manager_required,
    rack_manager_required,
    match_manager_required,
    trio_manager_required,
)
from sqlalchemy import func, desc, case, not_
from sqlalchemy.exc import IntegrityError
from amalfi import (
    get_amalfi_classification,
    validate_amalfi_configuration,
)
from models import RoundClassification, PlayerEncounter, TrioMatch
from models.matchmaking.bootstrap import get_matchmaking_service
from models.competition.services import ProvaService
from models.match.services import MatchService, RackService, MatchResultService
from models.status_enum import DirectorRequestStatus, ProvaStatus, MatchStatus
from models.competition.models import WithdrawPolicy
from models.tournament.services import TournamentService

admin_bp = Blueprint("admin", __name__)

# ============ DASHBOARD E TORNEI ============


@admin_bp.route("/")
@admin_required
def dashboard():
    return redirect(url_for("dashboard.dashboard"))


@admin_bp.route("/tournament/create", methods=["POST"])
@login_required
def create_tournament():
    """Crea nuovo torneo: accessibile ad admin e direttori"""
    if not (current_user.is_admin or current_user.is_director):
        flash("Non hai i permessi per creare un torneo.", "error")
        return redirect(url_for("admin.dashboard"))

    name = request.form["name"]
    tournament_type = request.form.get("tournament_type", "Amalfi")
    without_x = "without_x" in request.form
    final_playoffs = "final_playoffs" in request.form
    challenge_mode = "challenge_mode" in request.form

    tournament = Tournament(
        name=name,
        tournament_type=tournament_type,
        without_x=without_x,
        final_playoffs=final_playoffs,
        challenge_mode=challenge_mode,
        is_active=True,
    )
    db.session.add(tournament)
    db.session.commit()

    # Se l'utente è un direttore (non admin), assegnalo automaticamente al torneo creato
    if current_user.is_director and not current_user.is_admin:
        from models import TournamentDirector

        assignment = TournamentDirector(
            user_id=current_user.id,
            tournament_id=tournament.id,
            assigned_by_id=current_user.id,
        )
        db.session.add(assignment)
        db.session.commit()

    flash(f'Torneo "{name}" creato con successo!')
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/tournament/<int:tournament_id>")
@login_required
@tournament_manager_required(lambda tournament_id: tournament_id)
def tournament_detail(tournament_id):
    """Dettaglio torneo con prove"""
    tournament = Tournament.query.get_or_404(tournament_id)
    provas = (
        Prova.query.filter_by(tournament_id=tournament_id).order_by(Prova.number).all()
    )

    # ID dei direttori già assegnati a questo torneo
    assigned_ids = [td.user_id for td in tournament.directors_association]

    # Solo utenti role='director' che non sono già assegnati
    candidate_directors = (
        User.query.filter_by(role="director")
        .filter(not_(User.id.in_(assigned_ids)))
        .order_by(User.username)
        .all()
    )

    can_manage_directors = current_user.is_admin or any(
        td.user_id == current_user.id for td in tournament.directors_association
    )

    return render_template(
        "admin/tournament_detail.html",
        tournament=tournament,
        provas=provas,
        users=candidate_directors,
        can_manage_directors=can_manage_directors,
    )


@admin_bp.route("/tournament/<int:tournament_id>/edit", methods=["GET", "POST"])
@tournament_manager_required(lambda tournament_id: tournament_id)
def edit_tournament(tournament_id):
    """Modifica torneo - AGGIORNATO per nuovo model"""
    tournament = Tournament.query.get_or_404(tournament_id)

    if not tournament.can_be_modified():
        flash(
            "Impossibile modificare il torneo: alcune prove hanno già delle iscrizioni!"
        )
        return redirect(url_for("admin.tournament_detail", tournament_id=tournament_id))

    if request.method == "POST":
        tournament.name = request.form["name"]
        tournament.tournament_type = request.form.get("tournament_type", "Amalfi")
        tournament.without_x = "without_x" in request.form
        tournament.final_playoffs = "final_playoffs" in request.form
        tournament.challenge_mode = "challenge_mode" in request.form
        tournament.updated_at = datetime.utcnow()

        db.session.commit()
        flash("Torneo aggiornato con successo!")
        return redirect(url_for("admin.tournament_detail", tournament_id=tournament_id))

    return render_template("admin/tournament_edit.html", tournament=tournament)


@admin_bp.route("/tournament/<int:tournament_id>/delete", methods=["POST"])
@tournament_manager_required(lambda tournament_id: tournament_id)
def delete_tournament(tournament_id):
    """Elimina torneo (service layer, gestione errori user-friendly)"""
    try:
        TournamentService.delete_tournament(tournament_id)
        flash("Torneo cancellato con successo!")
        return redirect(url_for("admin.dashboard"))
    except ValueError as ve:
        flash(str(ve))
        return redirect(url_for("admin.tournament_detail", tournament_id=tournament_id))
    except IntegrityError:
        flash("Cancellazione bloccata da vincoli di integrità.")
        return redirect(url_for("admin.tournament_detail", tournament_id=tournament_id))


@admin_bp.route("/tournament/<int:tournament_id>/toggle_active", methods=["POST"])
@tournament_manager_required(lambda tournament_id: tournament_id)
def toggle_tournament_active(tournament_id):
    """Attiva/disattiva torneo"""
    tournament = Tournament.query.get_or_404(tournament_id)
    tournament.is_active = not tournament.is_active
    tournament.updated_at = datetime.utcnow()
    db.session.commit()

    status = "attivato" if tournament.is_active else "disattivato"
    flash(f'Torneo "{tournament.name}" {status}!')
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/tournament/<int:tournament_id>/add_director", methods=["POST"])
@login_required
@tournament_manager_required(lambda tournament_id: tournament_id)
def add_director(tournament_id):
    """Aggiunge un co‑direttore"""
    new_director_id = int(request.form["user_id"])
    user = User.query.get_or_404(new_director_id)

    if user.role == "admin":
        flash("Gli admin non vanno assegnati come direttori.", "warning")
        return redirect(url_for("admin.tournament_detail", tournament_id=tournament_id))

    from models import TournamentDirector

    existing = TournamentDirector.query.filter_by(
        user_id=new_director_id, tournament_id=tournament_id
    ).first()
    if existing:
        flash("Questo utente è già un direttore.", "warning")
    else:
        assignment = TournamentDirector(
            user_id=new_director_id,
            tournament_id=tournament_id,
            assigned_by_id=current_user.id,
        )
        db.session.add(assignment)
        db.session.commit()
        flash("Direttore aggiunto con successo.")
    return redirect(url_for("admin.tournament_detail", tournament_id=tournament_id))


@admin_bp.route("/tournament/<int:tournament_id>/remove_director", methods=["POST"])
@login_required
@tournament_manager_required(lambda tournament_id: tournament_id)
def remove_director(tournament_id):
    """Rimuove un co‑direttore"""
    director_id = int(request.form["user_id"])
    from models import TournamentDirector

    assignment = TournamentDirector.query.filter_by(
        user_id=director_id, tournament_id=tournament_id
    ).first()
    if assignment:
        db.session.delete(assignment)
        db.session.commit()
        flash("Direttore rimosso con successo.")
    else:
        flash("Direttore non trovato.", "warning")
    return redirect(url_for("admin.tournament_detail", tournament_id=tournament_id))


# ============ PROVE STANDALONE (Sprint 2) ============


@admin_bp.route("/prova/create_standalone", methods=["GET", "POST"])
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
                max_participants=int(request.form.get("max_participants"))
                if request.form.get("max_participants")
                else None,
                entry_fee=float(request.form.get("entry_fee", 0.0)),
                best_of=not ("exact_number" in request.form),
                withdraw_policy=withdraw_policy,
            )

            flash(f'Gara singola "{prova.name}" creata con successo!')
            return redirect(url_for("admin.prova_detail", prova_id=prova.id))

        except Exception as e:
            flash(f"Errore nella creazione: {str(e)}", "error")
            return render_template(
                "admin/prova_create_standalone.html", WithdrawPolicy=WithdrawPolicy
            )

    # GET request - mostra form
    return render_template(
        "admin/prova_create_standalone.html", WithdrawPolicy=WithdrawPolicy
    )


# Modifica la route create_prova esistente per supportare entrambi i casi
@admin_bp.route("/prova/create", methods=["POST"])
@login_required  # Rimosso @admin_required per permettere ai director
def create_prova():
    """Crea nuova prova - Aggiornata per supportare standalone"""

    # Determina se è standalone o per torneo
    tournament_id = request.form.get("tournament_id")
    is_standalone = tournament_id == "standalone" or not tournament_id

    if is_standalone:
        # Redirect alla route standalone
        return redirect(url_for("admin.create_prova_standalone"))

    # Codice esistente per prove con torneo...
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
        return redirect(url_for("admin.dashboard"))

    number = int(request.form["number"])

    # Verifica che il numero prova non esista già
    existing = Prova.query.filter_by(tournament_id=tournament_id, number=number).first()
    if existing:
        flash(f"La prova {number} esiste già!")
        return redirect(url_for("admin.tournament_detail", tournament_id=tournament_id))

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
    # CORREZIONE: exact_number è il contrario di best_of
    exact_number = "exact_number" in request.form
    best_of = not exact_number  # Inverti la logica

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

    # Auto-popolamento da prova precedente (non serve più, è gestito lato client)
    # Il checkbox copy_from_previous è gestito dinamicamente dal JavaScript

    db.session.commit()

    flash(f"Prova {number} creata con successo!")
    return redirect(url_for("admin.tournament_detail", tournament_id=tournament_id))


@admin_bp.route("/prova/<int:prova_id>/edit", methods=["GET", "POST"])
@login_required
@prova_manager_required
def edit_prova(prova_id):
    """Modifica prova - AGGIORNATO per exact_number"""
    prova = Prova.query.get_or_404(prova_id)

    if not prova.can_be_modified():
        flash("Impossibile modificare la prova: ci sono già delle iscrizioni!")
        return redirect(url_for("admin.prova_detail", prova_id=prova_id))

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

        # CORREZIONE: exact_number è il contrario di best_of
        exact_number = "exact_number" in request.form
        prova.best_of = not exact_number  # Inverti la logica
        prova.withdraw_policy = request.form.get(
            "withdraw_policy", WithdrawPolicy.EXCLUDE.value
        )

        db.session.commit()
        flash("Prova aggiornata con successo!")
        return redirect(url_for("admin.prova_detail", prova_id=prova_id))

    return render_template(
        "admin/prova_edit.html", prova=prova, WithdrawPolicy=WithdrawPolicy
    )


@admin_bp.route("/prova/<int:prova_id>/delete", methods=["POST"])
@login_required
@prova_manager_required
def delete_prova(prova_id):
    """Cancella prova - NUOVO"""
    prova = Prova.query.get_or_404(prova_id)
    tournament_id = prova.tournament_id

    if not prova.can_be_deleted():
        flash("Impossibile cancellare la prova: ci sono già delle iscrizioni!")
        return redirect(url_for("admin.prova_detail", prova_id=prova_id))

    prova_name = f"Prova {prova.number}"
    db.session.delete(prova)
    db.session.commit()

    flash(f"{prova_name} cancellata con successo!")
    return redirect(url_for("admin.tournament_detail", tournament_id=tournament_id))


@admin_bp.route("/prova/<int:prova_id>")
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


@admin_bp.route("/prova/<int:prova_id>/open_inscriptions", methods=["POST"])
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
        return redirect(url_for("admin.prova_detail", prova_id=prova_id))

    prova.inscription_start = inscription_start
    prova.inscription_end = inscription_end
    ProvaService.to_inscription(prova.id)

    db.session.commit()
    flash(
        "Iscrizioni aperte! Gli orari sono gestiti "
        "automaticamente nel tuo timezone locale."
    )
    return redirect(url_for("admin.prova_detail", prova_id=prova_id))


@admin_bp.route("/prova/<int:prova_id>/modify_inscription_dates", methods=["POST"])
@login_required
@prova_manager_required
def modify_inscription_dates(prova_id):
    """Modifica date di iscrizione per una prova"""
    prova = Prova.query.get_or_404(prova_id)

    # Verifica che sia possibile modificare
    if not prova.can_modify_inscription_dates():
        flash("Impossibile modificare le date: il primo turno è già stato avviato!")
        return redirect(url_for("admin.prova_detail", prova_id=prova_id))

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
        return redirect(url_for("admin.prova_detail", prova_id=prova_id))

    # Aggiorna le date
    prova.inscription_start = inscription_start
    prova.inscription_end = inscription_end

    # Se le iscrizioni ora sono nel futuro, torna a setup
    now = datetime.utcnow()
    if inscription_start > now:
        ProvaService.reopen_setup(prova.id)
    elif inscription_start <= now <= inscription_end:
        ProvaService.to_inscription(prova.id)
    # Se sono passate, lascia lo status attuale (verrà gestito dai template)

    db.session.commit()
    flash("Date di iscrizione aggiornate con successo!")
    return redirect(url_for("admin.prova_detail", prova_id=prova_id))


@admin_bp.route("/prova/<int:prova_id>/start_first_round", methods=["POST"])
@login_required
@prova_manager_required
def start_first_round(prova_id):
    """Avvia primo turno della prova - AGGIORNATO per min_participants"""
    prova = Prova.query.get_or_404(prova_id)

    if prova.current_round != 0:
        flash("La prova è già iniziata!")
        return redirect(url_for("admin.prova_detail", prova_id=prova_id))

    # Verifica numero minimo partecipanti
    inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()
    if len(inscriptions) < prova.min_participants:
        flash(f"Servono almeno {prova.min_participants} iscritti per avviare la prova!")
        return redirect(url_for("admin.prova_detail", prova_id=prova_id))

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
    return redirect(url_for("admin.prova_detail", prova_id=prova_id))


@admin_bp.route("/prova/<int:prova_id>/results_overview")
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
        "admin/prova_results_overview.html",
        prova=prova,
        matches_by_round=matches_by_round,
    )


# ============ GESTIONE PARTITE ============


@admin_bp.route("/match/<int:match_id>")
@login_required
@match_manager_required
def match_detail(match_id):
    """Dettaglio partita per admin"""
    match = Match.query.get_or_404(match_id)
    racks = Rack.query.filter_by(match_id=match_id).order_by(Rack.rack_number).all()

    return render_template("match_detail.html", match=match, racks=racks)


@admin_bp.route("/match/<int:match_id>/add_rack", methods=["POST"])
@login_required
@match_manager_required
def add_rack_result(match_id):
    """Aggiungi risultato rack (admin)"""
    match = Match.query.get_or_404(match_id)
    winner_id = int(request.form["winner_id"])

    # Trova il prossimo numero rack
    last_rack = (
        Rack.query.filter_by(match_id=match_id)
        .order_by(Rack.rack_number.desc())
        .first()
    )
    next_rack_number = (last_rack.rack_number + 1) if last_rack else 1

    # Crea il rack tramite il service (reporter = admin; validazione admin attiva)
    RackService.add_rack_result(
        match_id=match.id,
        rack_number=next_rack_number,
        winner_id=winner_id,
        reported_by_id=1,  # Admin user ID
        validated_by_admin=True,  # Admin validation immediate
    )

    # Aggiorna punteggio match
    if winner_id == match.player1_id:
        match.player1_score += 1
    else:
        match.player2_score += 1

    # Se il match è finito, imposta il vincitore tramite il service dedicato
    if match.prova.is_match_finished(match.player1_score, match.player2_score):
        final_winner_id = (
            match.player1_id
            if match.player1_score > match.player2_score
            else match.player2_id
        )
        MatchResultService.submit_result(match.id, final_winner_id)

    # Persisti l’aggiornamento dei punteggi (il rack è già stato committato dal service)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "status": match.status,
        }
    )


# ============ GESTIONE RISULTATI DIRETTI ADMIN ============


@admin_bp.route("/match/<int:match_id>/set_result", methods=["POST"])
@login_required
@match_manager_required
def set_match_result_direct(match_id):
    """Imposta risultato completo di una partita (admin)"""
    match = Match.query.get_or_404(match_id)

    if match.is_bye:
        flash("Non puoi modificare una partita bye!")
        return redirect(url_for("admin.match_detail", match_id=match_id))

    try:
        player1_score = int(request.form["player1_score"])
        player2_score = int(request.form["player2_score"])

        # Validazione punteggi
        if player1_score < 0 or player2_score < 0:
            flash("I punteggi non possono essere negativi!")
            return redirect(url_for("admin.match_detail", match_id=match_id))

        # Verifica che il risultato sia valido secondo le regole della prova
        total_racks = player1_score + player2_score

        if match.prova.best_of:
            # Al meglio di: uno dei due deve aver raggiunto la soglia
            winning_score = match.prova.get_winning_score()
            if max(player1_score, player2_score) < winning_score:
                flash(
                    f'Nel "al meglio di {match.prova.distance}", uno dei '
                    f"giocatori deve raggiungere {winning_score} punti!"
                )
                return redirect(url_for("admin.match_detail", match_id=match_id))
        else:
            # Esatto numero: la somma deve essere esattamente la distanza
            if total_racks != match.prova.distance:
                flash(
                    f'Nel "{match.prova.distance} rack esatti", '
                    f"la somma deve essere esattamente {match.prova.distance}!"
                )
                return redirect(url_for("admin.match_detail", match_id=match_id))

        # Determina il vincitore
        if player1_score > player2_score:
            winner_id = match.player1_id
        elif player2_score > player1_score:
            winner_id = match.player2_id
        else:
            flash("Non può esserci un pareggio!")
            return redirect(url_for("admin.match_detail", match_id=match_id))

        # Elimina tutti i rack esistenti per questa partita
        existing_racks = Rack.query.filter_by(match_id=match_id).all()
        for rack in existing_racks:
            db.session.delete(rack)

        # Crea i nuovi rack basati sul risultato
        rack_number = 1

        # Crea rack per player1
        for i in range(player1_score):
            RackService.add_rack_result(
                match_id, rack_number, match.player1_id, 1, True
            )
            rack_number += 1

        # Crea rack per player2
        for i in range(player2_score):
            RackService.add_rack_result(
                match_id, rack_number, match.player2_id, 1, True
            )
            rack_number += 1

        # Aggiorna il match
        match.player1_score = player1_score
        match.player2_score = player2_score
        match.winner_id = winner_id
        MatchService.to_completed(match.id)

        # db.session.commit()

        flash("Risultato impostato con successo!")
        return redirect(url_for("admin.match_detail", match_id=match_id))

    except ValueError:
        flash("Errore: inserisci numeri validi per i punteggi!")
        return redirect(url_for("admin.match_detail", match_id=match_id))
    except Exception as e:
        flash(f"Errore durante l'impostazione del risultato: {str(e)}")
        return redirect(url_for("admin.match_detail", match_id=match_id))


@admin_bp.route("/match/<int:match_id>/reset", methods=["POST"])
@login_required
@match_manager_required
def reset_match(match_id):
    """Reset completo di una partita (admin)"""
    match = Match.query.get_or_404(match_id)

    if match.is_bye:
        flash("Non puoi resettare una partita bye!")
        return redirect(url_for("admin.match_detail", match_id=match_id))

    try:
        # Elimina tutti i rack
        existing_racks = Rack.query.filter_by(match_id=match_id).all()
        for rack in existing_racks:
            db.session.delete(rack)

        # Reset match
        match.player1_score = 0
        match.player2_score = 0
        match.winner_id = None
        MatchService.reset_to_pending(match.id, clear_validation=True)

        db.session.commit()

        flash("Partita resettata con successo!")
        return redirect(url_for("admin.match_detail", match_id=match_id))

    except Exception as e:
        flash(f"Errore durante il reset: {str(e)}")
        return redirect(url_for("admin.match_detail", match_id=match_id))


# ============ GESTIONE RACK ADMIN ============


@admin_bp.route("/rack/<int:rack_id>/remove", methods=["POST"])
@login_required
@rack_manager_required
def remove_rack_admin(rack_id):
    """Rimuovi un rack (admin)"""
    rack = Rack.query.get_or_404(rack_id)
    match = rack.match

    try:
        # Salva il vincitore per aggiornare il punteggio
        winner_id = rack.winner_id

        # Rimuovi il rack
        db.session.delete(rack)

        # Aggiorna il punteggio del match
        if winner_id == match.player1_id:
            match.player1_score = max(0, match.player1_score - 1)
        else:
            match.player2_score = max(0, match.player2_score - 1)

        # Se il match era completato e ora non ha più i punti per essere vinto,
        # rimettilo in playing
        if match.status == MatchStatus.COMPLETED.value:
            if match.prova.best_of:
                winning_score = match.prova.get_winning_score()
                if max(match.player1_score, match.player2_score) < winning_score:
                    MatchService.to_playing(match.id)
                    match.winner_id = None
            else:  # esatto numero
                if (match.player1_score + match.player2_score) < match.prova.distance:
                    MatchService.to_playing(match.id)
                    match.winner_id = None

        db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": "Rack rimosso (Admin)",
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "status": match.status,
            }
        )

    except Exception as e:
        return jsonify({"error": f"Errore durante la rimozione: {str(e)}"}), 500


@admin_bp.route("/rack/<int:rack_id>/validate", methods=["POST"])
@login_required
@rack_manager_required
def validate_rack_admin(rack_id):
    """Valida un rack (admin)"""
    rack = Rack.query.get_or_404(rack_id)

    try:
        # Valida il rack
        rack.validated_by_admin = True
        rack.confirmed_by_player = (
            True  # Automaticamente confermato se validato dall'admin
        )

        db.session.commit()

        return jsonify(
            {"success": True, "message": "Rack validato dall'amministratore"}
        )

    except Exception as e:
        return jsonify({"error": f"Errore durante la validazione: {str(e)}"}), 500


# ============ GESTIONE UTENTI (PUNTO 3) ============


@admin_bp.route("/users")
@admin_required
def users_list():
    """Lista di tutti gli utenti con statistiche"""

    users = (
        db.session.query(
            User,
            func.count(Inscription.id).label("total_inscriptions"),
            func.count(Match.id).label("total_matches"),
            func.sum(case((Match.winner_id == User.id, 1), else_=0)).label(
                "matches_won"
            ),
        )
        .outerjoin(Inscription, User.id == Inscription.user_id)
        .outerjoin(
            Match, db.or_(Match.player1_id == User.id, Match.player2_id == User.id)
        )
        .filter(User.role != "admin")
        .group_by(User.id)
        .order_by(desc("total_inscriptions"), User.username)
        .all()
    )

    return render_template("admin/users_list.html", users=users)


@admin_bp.route("/user/<int:user_id>")
@admin_required
def user_detail(user_id):
    """Scheda dettagliata utente"""
    user = User.query.get_or_404(user_id)

    # se l'utente è admin, ritorna alla lista utenti
    if user.role == "admin":
        return redirect(url_for("admin.users_list"))

    # Iscrizioni dell'utente
    inscriptions = (
        Inscription.query.filter_by(user_id=user_id)
        .join(Prova)
        .join(Tournament)
        .order_by(Tournament.created_at.desc(), Prova.number.desc())
        .all()
    )

    # Partite giocate
    matches = (
        Match.query.filter(
            db.or_(Match.player1_id == user_id, Match.player2_id == user_id)
        )
        .join(Prova)
        .join(Tournament)
        .order_by(
            Tournament.created_at.desc(), Prova.number.desc(), Match.round_number.desc()
        )
        .all()
    )

    # Statistiche generali
    total_matches = len([m for m in matches if m.status == MatchStatus.COMPLETED.value])
    won_matches = len(
        [
            m
            for m in matches
            if m.status == MatchStatus.COMPLETED.value and m.winner_id == user_id
        ]
    )
    win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0

    # Classifiche per torneo
    classifications = (
        Classification.query.filter_by(user_id=user_id)
        .join(Tournament)
        .order_by(Tournament.created_at.desc())
        .all()
    )

    # Partite recenti (ultime 10)
    recent_matches = [m for m in matches if m.status == MatchStatus.COMPLETED.value][
        :10
    ]

    stats = {
        "total_inscriptions": len(inscriptions),
        "total_matches": total_matches,
        "won_matches": won_matches,
        "lost_matches": total_matches - won_matches,
        "win_percentage": round(win_percentage, 1),
        "tournaments_played": len(
            set([insc.prova.tournament_id for insc in inscriptions])
        ),
    }

    return render_template(
        "admin/user_detail.html",
        user=user,
        inscriptions=inscriptions,
        matches=recent_matches,
        classifications=classifications,
        stats=stats,
    )


# ============ SISTEMA AMALFI - NUOVE ROUTE ============


@admin_bp.route("/prova/<int:prova_id>/amalfi/classification/<int:round_number>")
@login_required
@prova_manager_required
def amalfi_classification(prova_id, round_number):
    """Visualizza classifica Amalfi dopo un turno specifico"""
    prova = Prova.query.get_or_404(prova_id)

    # Verifica che il turno sia valido
    if round_number < 1 or round_number > prova.rounds_count:
        flash(f"Turno {round_number} non valido per questa prova!")
        return redirect(url_for("admin.prova_detail", prova_id=prova_id))

    # Verifica che il turno sia completato
    matches_in_round = Match.query.filter_by(
        prova_id=prova_id, round_number=round_number
    ).all()

    if not matches_in_round:
        flash(f"Il turno {round_number} non è ancora iniziato!")
        return redirect(url_for("admin.prova_detail", prova_id=prova_id))

    # Controlla se tutti i match del turno sono completati
    incomplete_matches = [
        m for m in matches_in_round if m.status != MatchStatus.COMPLETED.value
    ]
    if incomplete_matches:
        flash(
            f"Il turno {round_number} non è ancora completato! "
            f"Mancano {len(incomplete_matches)} partite."
        )
        return redirect(url_for("admin.prova_detail", prova_id=prova_id))

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


@admin_bp.route(
    "/prova/<int:prova_id>/amalfi/start_round/<int:round_number>", methods=["POST"]
)
@login_required
@prova_manager_required
def amalfi_start_round(prova_id, round_number):
    """Avvia un turno specifico con algoritmo Amalfi"""
    prova = Prova.query.get_or_404(prova_id)

    try:
        # Validazioni preliminari (invariato)
        if round_number < 1 or round_number > prova.rounds_count:
            flash(f"Turno {round_number} non valido!")
            return redirect(url_for("admin.prova_detail", prova_id=prova_id))
        if round_number <= prova.current_round:
            flash(f"Il turno {round_number} è già stato avviato!")
            return redirect(url_for("admin.prova_detail", prova_id=prova_id))
        if round_number != prova.current_round + 1:
            flash(f"Devi avviare prima il turno {prova.current_round + 1}!")
            return redirect(url_for("admin.prova_detail", prova_id=prova_id))

        validation = validate_amalfi_configuration(prova)
        if not validation["is_valid"]:
            for error in validation["errors"]:
                flash(f"Errore Amalfi: {error}", "error")
            return redirect(url_for("admin.prova_detail", prova_id=prova_id))
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
                return redirect(url_for("admin.prova_detail", prova_id=prova_id))

        # Service/Strategy (adapter al legacy engine)
        svc = get_matchmaking_service()
        pairings = svc.run("Amalfi", prova=prova, round_number=round_number)

        # Stato prova
        prova.current_round = round_number
        if prova.status != ProvaStatus.PLAYING.value:
            ProvaService.start_playing(prova.id)
        db.session.commit()

        # Messaggi basati su pairings (tuple di id: (p1,), (p1,p2), (p1,p2,p3))
        total = len(pairings)
        n_trio = sum(1 for p in pairings if len(p) == 3)
        n_bye = sum(1 for p in pairings if len(p) == 1)
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

        return redirect(url_for("admin.prova_detail", prova_id=prova_id))

    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante la creazione del turno: {str(e)}", "error")
        return redirect(url_for("admin.prova_detail", prova_id=prova_id))


@admin_bp.route("/prova/<int:prova_id>/amalfi/preview_round/<int:round_number>")
@login_required
@prova_manager_required
def amalfi_preview_round(prova_id, round_number):
    """Anteprima abbinamenti prossimo turno senza crearli"""
    prova = Prova.query.get_or_404(prova_id)

    try:
        # Validazioni
        if round_number < 1 or round_number > prova.rounds_count:
            return jsonify({"error": f"Turno {round_number} non valido"}), 400

        if round_number <= prova.current_round:
            return (
                jsonify({"error": f"Il turno {round_number} è già stato avviato"}),
                400,
            )

        # Verifica che il turno precedente sia completato (se non è il primo)
        if round_number > 1:
            prev_matches = Match.query.filter_by(
                prova_id=prova_id, round_number=round_number - 1
            ).all()

            incomplete_prev = [
                m for m in prev_matches if m.status != MatchStatus.COMPLETED.value
            ]
            if incomplete_prev:
                return (
                    jsonify(
                        {
                            "error": f"Completa prima il turno {round_number-1}",
                            "incomplete_matches": len(incomplete_prev),
                        }
                    ),
                    400,
                )

        # Genera anteprima via Strategy (no IO)
        svc = get_matchmaking_service()
        pairings = svc.preview(
            strategy_name="Amalfi", prova=prova, round_number=round_number
        )

        # Prepara dati per JSON (compat con struttura esistente)
        matches_data = []

        # Cache utenti per id
        user_ids = set()
        for p in pairings:
            for uid in p.players:
                user_ids.add(uid)
        users = {u.id: u for u in User.query.filter(User.id.in_(list(user_ids))).all()}

        def user_payload(uid: int) -> dict:
            u = users.get(uid)
            return {"id": uid, "username": (u.username if u else None)}

        for p in pairings:
            ps = list(p.players)
            if len(ps) == 1 or getattr(p, "is_bye", False):
                match_data = {
                    "player1": user_payload(ps[0]),
                    "type": "bye",
                }
            elif len(ps) == 2:
                match_data = {
                    "player1": user_payload(ps[0]),
                    "player2": user_payload(ps[1]),
                    "type": "normal",
                    # La Strategy non espone il salto; manteniamo compat con default 0
                    "salto_applied": 0,
                }
            elif len(ps) == 3:
                match_data = {
                    "player1": user_payload(ps[0]),
                    "player2": user_payload(ps[1]),
                    "player3": user_payload(ps[2]),
                    "type": "trio",
                }
            else:
                continue
            matches_data.append(match_data)

        # Calcola statistiche
        salto = prova.rounds_count - round_number if round_number > 1 else None

        return jsonify(
            {
                "success": True,
                "round_number": round_number,
                "prova_id": prova_id,
                "salto": salto,
                "matches": matches_data,
                "counts": {
                    "total": len(matches_data),
                    "normal_matches": len(
                        [m for m in matches_data if m["type"] == "normal"]
                    ),
                    "trio_matches": len(
                        [m for m in matches_data if m["type"] == "trio"]
                    ),
                    "bye_matches": len([m for m in matches_data if m["type"] == "bye"]),
                },
            }
        )

    except Exception as e:
        return jsonify({"error": f"Errore anteprima: {str(e)}"}), 500


@admin_bp.route("/prova/<int:prova_id>/amalfi/encounters")
@login_required
@prova_manager_required
def amalfi_encounters(prova_id):
    """Visualizza matrice incontri per debug anti-reincontro"""
    prova = Prova.query.get_or_404(prova_id)

    # Ottieni tutti i giocatori iscritti
    inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()
    players = [insc.user for insc in inscriptions]

    # Ottieni tutti gli incontri registrati
    encounters = PlayerEncounter.query.filter_by(prova_id=prova_id).all()

    # Crea matrice incontri
    encounter_matrix = {}
    for player1 in players:
        encounter_matrix[player1.id] = {}
        for player2 in players:
            encounter_matrix[player1.id][player2.id] = []

    # Popola matrice con i turni degli incontri
    for encounter in encounters:
        if (
            encounter.player1_id in encounter_matrix
            and encounter.player2_id in encounter_matrix[encounter.player1_id]
        ):
            encounter_matrix[encounter.player1_id][encounter.player2_id].append(
                encounter.round_number
            )
            encounter_matrix[encounter.player2_id][encounter.player1_id].append(
                encounter.round_number
            )

    return render_template(
        "admin/amalfi_encounters.html",
        prova=prova,
        players=players,
        encounter_matrix=encounter_matrix,
    )


@admin_bp.route("/prova/<int:prova_id>/amalfi/validate")
@login_required
@prova_manager_required
def amalfi_validate_configuration(prova_id):
    """Valida configurazione prova per Sistema Amalfi"""
    prova = Prova.query.get_or_404(prova_id)

    validation = validate_amalfi_configuration(prova)

    return jsonify(
        {
            "success": True,
            "validation": validation,
            "prova_info": {
                "rounds_count": prova.rounds_count,
                "inscriptions_count": len(prova.inscriptions),
                "tournament_type": prova.tournament.tournament_type,
                "without_x": prova.tournament.without_x,
            },
        }
    )


# ============ AGGIORNAMENTI ALLE ROUTE ESISTENTI ============

# Modifica la route prova_detail esistente per includere info Amalfi
@admin_bp.route("/prova/<int:prova_id>/amalfi_enhanced")
@login_required
@prova_manager_required
def prova_detail_amalfi_enhanced(prova_id):
    """Versione potenziata del dettaglio prova con funzionalità Amalfi"""
    prova = Prova.query.get_or_404(prova_id)
    inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()
    matches = (
        Match.query.filter_by(prova_id=prova_id)
        .order_by(Match.round_number, Match.id)
        .all()
    )

    # Informazioni Amalfi
    amalfi_info = {
        "validation": validate_amalfi_configuration(prova),
        "classifications": {},
        "next_round": prova.current_round + 1
        if prova.current_round < prova.rounds_count
        else None,
    }

    # Ottieni classifiche per ogni turno completato
    for round_num in range(1, prova.current_round + 1):
        round_matches = [m for m in matches if m.round_number == round_num]
        if all(m.status == MatchStatus.COMPLETED.value for m in round_matches):
            amalfi_info["classifications"][round_num] = get_amalfi_classification(
                prova_id, round_num
            )

    return render_template(
        "admin/prova_detail_amalfi.html",
        prova=prova,
        inscriptions=inscriptions,
        matches=matches,
        amalfi_info=amalfi_info,
    )


# ============ GESTIONE TRII ============


@admin_bp.route("/trio/<int:trio_id>/add_rack", methods=["POST"])
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


@admin_bp.route("/trio/<int:trio_id>/reset", methods=["POST"])
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


@admin_bp.route("/director_requests")
@admin_required
def director_requests():
    pending = DirectorRequest.query.filter_by(
        status=DirectorRequestStatus.PENDING.value
    ).all()
    return render_template("admin/director_requests.html", requests=pending)


@admin_bp.route("/director_requests/<int:req_id>/approve", methods=["POST"])
@admin_required
def approve_director_request(req_id):
    req = DirectorRequest.query.get_or_404(req_id)
    req.status = DirectorRequestStatus.APPROVED.value
    req.user.role = "director"
    db.session.commit()
    flash("Richiesta approvata.")
    return redirect(url_for("admin.director_requests"))


@admin_bp.route("/director_requests/<int:req_id>/reject", methods=["POST"])
@admin_required
def reject_director_request(req_id):
    req = DirectorRequest.query.get_or_404(req_id)
    req.status = DirectorRequestStatus.REJECTED.value
    db.session.commit()
    flash("Richiesta rifiutata.")
    return redirect(url_for("admin.director_requests"))
