# routes/admin/tournament.py
"""Tournament management blueprint for admin interface."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import not_
from sqlalchemy.exc import IntegrityError

from models import (
    db,
    Tournament,
    Prova,
    User,
)
from utils import (
    tournament_manager_required,
)
from models.tournament.services import TournamentService

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
    return redirect(url_for("dashboard.dashboard"))


@tournament_bp.route("/<int:tournament_id>")
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


@tournament_bp.route("/<int:tournament_id>/edit", methods=["GET", "POST"])
@tournament_manager_required(lambda tournament_id: tournament_id)
def edit_tournament(tournament_id):
    """Modifica torneo - AGGIORNATO per nuovo model"""
    tournament = Tournament.query.get_or_404(tournament_id)

    if not tournament.can_be_modified():
        flash(
            "Impossibile modificare il torneo: alcune prove hanno già delle iscrizioni!"
        )
        return redirect(url_for("admin.tournament.tournament_detail", tournament_id=tournament_id))

    if request.method == "POST":
        tournament.name = request.form["name"]
        tournament.tournament_type = request.form.get("tournament_type", "Amalfi")
        tournament.without_x = "without_x" in request.form
        tournament.final_playoffs = "final_playoffs" in request.form
        tournament.challenge_mode = "challenge_mode" in request.form
        tournament.updated_at = datetime.utcnow()

        db.session.commit()
        flash("Torneo aggiornato con successo!")
        return redirect(url_for("admin.tournament.tournament_detail", tournament_id=tournament_id))

    return render_template("admin/tournament_edit.html", tournament=tournament)


@tournament_bp.route("/<int:tournament_id>/delete", methods=["POST"])
@tournament_manager_required(lambda tournament_id: tournament_id)
def delete_tournament(tournament_id):
    """Elimina torneo (service layer, gestione errori user-friendly)"""
    try:
        TournamentService.delete_tournament(tournament_id)
        flash("Torneo cancellato con successo!")
        return redirect(url_for("dashboard.dashboard"))
    except ValueError as ve:
        flash(str(ve))
        return redirect(url_for("admin.tournament.tournament_detail", tournament_id=tournament_id))
    except IntegrityError:
        flash("Cancellazione bloccata da vincoli di integrità.")
        return redirect(url_for("admin.tournament.tournament_detail", tournament_id=tournament_id))


@tournament_bp.route("/<int:tournament_id>/toggle_active", methods=["POST"])
@tournament_manager_required(lambda tournament_id: tournament_id)
def toggle_tournament_active(tournament_id):
    """Attiva/disattiva torneo"""
    tournament = Tournament.query.get_or_404(tournament_id)
    tournament.is_active = not tournament.is_active
    tournament.updated_at = datetime.utcnow()
    db.session.commit()

    status = "attivato" if tournament.is_active else "disattivato"
    flash(f'Torneo "{tournament.name}" {status}!')
    return redirect(url_for("dashboard.dashboard"))


@tournament_bp.route("/<int:tournament_id>/add_director", methods=["POST"])
@login_required
@tournament_manager_required(lambda tournament_id: tournament_id)
def add_director(tournament_id):
    """Aggiunge un co‑direttore"""
    new_director_id = int(request.form["user_id"])
    user = User.query.get_or_404(new_director_id)

    if user.role == "admin":
        flash("Gli admin non vanno assegnati come direttori.", "warning")
        return redirect(url_for("admin.tournament.tournament_detail", tournament_id=tournament_id))

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
    return redirect(url_for("admin.tournament.tournament_detail", tournament_id=tournament_id))


@tournament_bp.route("/<int:tournament_id>/remove_director", methods=["POST"])
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
    return redirect(url_for("admin.tournament.tournament_detail", tournament_id=tournament_id))