# routes/admin/campionato.py
"""Campionato management blueprint for admin interface."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from models import (
    db,
    Campionato,
)
from utils import (
    campionato_manager_required,
)
from models.campionato.services import TournamentService

# Initialize the TournamentService
campionato_service = TournamentService()

# Campionato management blueprint
campionato_bp = Blueprint("campionato", __name__)


@campionato_bp.route("/create", methods=["POST"])
@login_required
def create_campionato():
    """Crea nuovo campionato: accessibile ad admin e direttori"""
    if not (current_user.is_admin or current_user.is_director):
        flash("Non hai i permessi per creare un campionato.", "error")
        return redirect(url_for("dashboard.dashboard"))

    name = request.form["name"]
    campionato_type = request.form.get("campionato_type", "Amalfi")
    without_x = "without_x" in request.form
    final_playoffs = "final_playoffs" in request.form
    challenge_mode = "challenge_mode" in request.form

    # Usa il service layer invece del direct database access
    campionato = campionato_service.create_campionato_with_director(
        name=name,
        creator_user_id=current_user.id,
        campionato_type=campionato_type,
        without_x=without_x,
        final_playoffs=final_playoffs,
        challenge_mode=challenge_mode,
        is_active=True,
    )

    flash(f'Campionato "{name}" creato con successo!')
    return redirect(url_for("dashboard.dashboard"))


@campionato_bp.route("/<int:campionato_id>")
@login_required
@campionato_manager_required(lambda campionato_id: campionato_id)
def campionato_detail(campionato_id):
    """Dettaglio campionato con gare"""
    # Use the service layer instead of direct database access
    campionato_data = campionato_service.get_campionato_detail_data(campionato_id)
    campionato = campionato_data["campionato"]
    gare = campionato_data["gare"]
    candidate_directors = campionato_data["candidate_directors"]

    # Controlla se l'utente può gestire director per questo campionato
    from models.user.models import DirectorAssignment
    can_manage_directors = current_user.is_admin or (
        db.session.query(DirectorAssignment)
        .filter(
            DirectorAssignment.entity_type == 'campionato',
            DirectorAssignment.entity_id == campionato.id,
            DirectorAssignment.user_id == current_user.id
        )
        .first() is not None
    )

    # Calcola statistiche avanzate del campionato  
    campionato_stats = campionato_service.calculate_campionato_statistics(campionato_id)
    
    # Calcola classifica generale se ci sono gare completate o gare in corso con tutti i round completati
    general_classification = None
    last_completed_gara_number = None
    
    # Trova gare completate o gare "playing" ma con tutti i round completati
    eligible_garas = []
    for p in gare:
        if p.status == 'completed':
            eligible_garas.append(p)
        elif p.status == 'playing' and p.current_round > p.rounds_count:
            # Gara tecnicamente completata ma non ancora marcata come tale
            eligible_garas.append(p)
    
    if eligible_garas:
        last_completed_gara_number = max(p.number for p in eligible_garas)
        general_classification = campionato_service.calculate_general_classification(campionato_id)

    return render_template(
        "admin/campionato_detail.html",
        campionato=campionato,
        gare=gare,
        provas=gare,  # Alias per compatibilità con il template
        users=candidate_directors,
        can_manage_directors=can_manage_directors,
        campionato_stats=campionato_stats,
        general_classification=general_classification,
        last_completed_gara_number=last_completed_gara_number,
    )


@campionato_bp.route("/<int:campionato_id>/edit", methods=["GET", "POST"])
@campionato_manager_required(lambda campionato_id: campionato_id)
def edit_campionato(campionato_id):
    """Modifica campionato - AGGIORNATO per nuovo model"""
    campionato = db.session.get(Campionato, campionato_id)
    if campionato is None:
        abort(404)

    if not campionato.can_be_modified():
        flash(
            "Impossibile modificare il campionato: alcune gare hanno già delle iscrizioni!"
        )
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    if request.method == "POST":
        # Usa il service layer invece del direct database access
        try:
            campionato_service.update_campionato(
                campionato_id=campionato_id,
                name=request.form["name"],
                campionato_type=request.form.get("campionato_type", "Amalfi"),
                without_x="without_x" in request.form,
                final_playoffs="final_playoffs" in request.form,
                challenge_mode="challenge_mode" in request.form,
            )
            flash("Campionato aggiornato con successo!")
        except ValueError as ve:
            flash(str(ve), "error")

        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )

    return render_template("admin/campionato_edit.html", campionato=campionato)


@campionato_bp.route("/<int:campionato_id>/delete", methods=["POST"])
@campionato_manager_required(lambda campionato_id: campionato_id)
def delete_campionato(campionato_id):
    """Elimina campionato (service layer, gestione errori user-friendly)"""
    try:
        campionato_service.delete_campionato(campionato_id)
        flash("Campionato cancellato con successo!")
        return redirect(url_for("dashboard.dashboard"))
    except ValueError as ve:
        flash(str(ve))
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )
    except IntegrityError:
        flash("Cancellazione bloccata da vincoli di integrità.")
        return redirect(
            url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
        )


@campionato_bp.route("/<int:campionato_id>/toggle_active", methods=["POST"])
@campionato_manager_required(lambda campionato_id: campionato_id)
def toggle_campionato_active(campionato_id):
    """Attiva/disattiva campionato"""
    # Usa il service layer invece del direct database access
    campionato = campionato_service.toggle_active_status(campionato_id)

    status = "attivato" if campionato.is_active else "disattivato"
    flash(f'Campionato "{campionato.name}" {status}!')
    return redirect(url_for("dashboard.dashboard"))


@campionato_bp.route("/<int:campionato_id>/add_director", methods=["POST"])
@login_required
@campionato_manager_required(lambda campionato_id: campionato_id)
def add_director(campionato_id):
    """Aggiunge un co‑direttore"""
    new_director_id = int(request.form["user_id"])

    # Usa il service layer invece del direct database access
    try:
        success = campionato_service.add_director(
            campionato_id=campionato_id,
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
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )


@campionato_bp.route("/<int:campionato_id>/remove_director", methods=["POST"])
@login_required
@campionato_manager_required(lambda campionato_id: campionato_id)
def remove_director(campionato_id):
    """Rimuove un co‑direttore"""
    director_id = int(request.form["user_id"])

    # Usa il service layer invece del direct database access
    success = campionato_service.remove_director(
        campionato_id=campionato_id, user_id=director_id
    )

    if success:
        flash("Direttore rimosso con successo.")
    else:
        flash("Direttore non trovato.", "warning")

    return redirect(
        url_for("admin.campionato.campionato_detail", campionato_id=campionato_id)
    )
