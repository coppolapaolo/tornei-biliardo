# routes/admin/tournament.py
"""Tournament management blueprint for admin interface."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from models import (
    db,
    Tournament,
)
from utils import (
    tournament_manager_required,
)
from models.tournament.services import TournamentService

# Initialize the TournamentService
tournament_service = TournamentService()

# Tournament management blueprint
tournament_bp = Blueprint("tournament", __name__)


@tournament_bp.route("/create", methods=["POST"])
@login_required
def create_tournament():
    """Crea nuovo torneo: accessibile ad admin e direttori"""
    if not (current_user.is_admin or current_user.is_director):
        flash("Non hai i permessi per creare un torneo.", "error")
        return redirect(url_for("dashboard.dashboard"))

    name = request.form["name"]
    tournament_type = request.form.get("tournament_type", "Amalfi")
    without_x = "without_x" in request.form
    final_playoffs = "final_playoffs" in request.form
    challenge_mode = "challenge_mode" in request.form

    # Usa il service layer invece del direct database access
    tournament = tournament_service.create_tournament_with_director(
        name=name,
        creator_user_id=current_user.id,
        tournament_type=tournament_type,
        without_x=without_x,
        final_playoffs=final_playoffs,
        challenge_mode=challenge_mode,
        is_active=True,
    )

    flash(f'Torneo "{name}" creato con successo!')
    return redirect(url_for("dashboard.dashboard"))


@tournament_bp.route("/<int:tournament_id>")
@login_required
@tournament_manager_required(lambda tournament_id: tournament_id)
def tournament_detail(tournament_id):
    """Dettaglio torneo con prove"""
    # Use the service layer instead of direct database access
    tournament_data = tournament_service.get_tournament_detail_data(tournament_id)
    tournament = tournament_data["tournament"]
    provas = tournament_data["provas"]
    candidate_directors = tournament_data["candidate_directors"]

    can_manage_directors = current_user.is_admin or any(
        td.user_id == current_user.id for td in tournament.directors_association
    )

    # Calcola statistiche avanzate del torneo  
    tournament_stats = tournament_service.calculate_tournament_statistics(tournament_id)
    
    # Calcola classifica generale se ci sono prove completate o prove in corso con tutti i round completati
    general_classification = None
    last_completed_prova_number = None
    
    # Trova prove completate o prove "playing" ma con tutti i round completati
    eligible_provas = []
    for p in provas:
        if p.status == 'completed':
            eligible_provas.append(p)
        elif p.status == 'playing' and p.current_round > p.rounds_count:
            # Prova tecnicamente completata ma non ancora marcata come tale
            eligible_provas.append(p)
    
    if eligible_provas:
        last_completed_prova_number = max(p.number for p in eligible_provas)
        general_classification = tournament_service.calculate_general_classification(tournament_id)

    return render_template(
        "admin/tournament_detail.html",
        tournament=tournament,
        provas=provas,
        users=candidate_directors,
        can_manage_directors=can_manage_directors,
        tournament_stats=tournament_stats,
        general_classification=general_classification,
        last_completed_prova_number=last_completed_prova_number,
    )


@tournament_bp.route("/<int:tournament_id>/edit", methods=["GET", "POST"])
@tournament_manager_required(lambda tournament_id: tournament_id)
def edit_tournament(tournament_id):
    """Modifica torneo - AGGIORNATO per nuovo model"""
    tournament = db.session.get(Tournament, tournament_id)
    if tournament is None:
        abort(404)

    if not tournament.can_be_modified():
        flash(
            "Impossibile modificare il torneo: alcune prove hanno già delle iscrizioni!"
        )
        return redirect(
            url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
        )

    if request.method == "POST":
        # Usa il service layer invece del direct database access
        try:
            tournament_service.update_tournament(
                tournament_id=tournament_id,
                name=request.form["name"],
                tournament_type=request.form.get("tournament_type", "Amalfi"),
                without_x="without_x" in request.form,
                final_playoffs="final_playoffs" in request.form,
                challenge_mode="challenge_mode" in request.form,
            )
            flash("Torneo aggiornato con successo!")
        except ValueError as ve:
            flash(str(ve), "error")

        return redirect(
            url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
        )

    return render_template("admin/tournament_edit.html", tournament=tournament)


@tournament_bp.route("/<int:tournament_id>/delete", methods=["POST"])
@tournament_manager_required(lambda tournament_id: tournament_id)
def delete_tournament(tournament_id):
    """Elimina torneo (service layer, gestione errori user-friendly)"""
    try:
        tournament_service.delete_tournament(tournament_id)
        flash("Torneo cancellato con successo!")
        return redirect(url_for("dashboard.dashboard"))
    except ValueError as ve:
        flash(str(ve))
        return redirect(
            url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
        )
    except IntegrityError:
        flash("Cancellazione bloccata da vincoli di integrità.")
        return redirect(
            url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
        )


@tournament_bp.route("/<int:tournament_id>/toggle_active", methods=["POST"])
@tournament_manager_required(lambda tournament_id: tournament_id)
def toggle_tournament_active(tournament_id):
    """Attiva/disattiva torneo"""
    # Usa il service layer invece del direct database access
    tournament = tournament_service.toggle_active_status(tournament_id)

    status = "attivato" if tournament.is_active else "disattivato"
    flash(f'Torneo "{tournament.name}" {status}!')
    return redirect(url_for("dashboard.dashboard"))


@tournament_bp.route("/<int:tournament_id>/add_director", methods=["POST"])
@login_required
@tournament_manager_required(lambda tournament_id: tournament_id)
def add_director(tournament_id):
    """Aggiunge un co‑direttore"""
    new_director_id = int(request.form["user_id"])

    # Usa il service layer invece del direct database access
    try:
        success = tournament_service.add_director(
            tournament_id=tournament_id,
            user_id=new_director_id,
            assigned_by_id=current_user.id,
        )

        if success:
            flash("Direttore aggiunto con successo.")
        else:
            flash("Questo utente è già un direttore.", "warning")

    except ValueError as ve:
        flash(str(ve), "warning")

    return redirect(
        url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
    )


@tournament_bp.route("/<int:tournament_id>/remove_director", methods=["POST"])
@login_required
@tournament_manager_required(lambda tournament_id: tournament_id)
def remove_director(tournament_id):
    """Rimuove un co‑direttore"""
    director_id = int(request.form["user_id"])

    # Usa il service layer invece del direct database access
    success = tournament_service.remove_director(
        tournament_id=tournament_id, user_id=director_id
    )

    if success:
        flash("Direttore rimosso con successo.")
    else:
        flash("Direttore non trovato.", "warning")

    return redirect(
        url_for("admin.tournament.tournament_detail", tournament_id=tournament_id)
    )
