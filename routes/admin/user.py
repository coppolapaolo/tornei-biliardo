# routes/admin/user.py
"""User management blueprint for admin interface."""

from flask import Blueprint, render_template, redirect, url_for, flash, request

from models import (
    User,
    DirectorRequest,
    db,
)
from utils import admin_required
from models.status_enum import DirectorRequestStatus
from models.user.services import UserService

# Initialize the UserService
user_service = UserService()

# User management blueprint
user_bp = Blueprint("user", __name__)


@user_bp.route("/users")
@admin_required
def users_list():
    """Lista di tutti gli utenti con statistiche"""
    # Use the service layer instead of direct database access
    users = user_service.get_users_with_stats()

    return render_template("admin/users_list.html", users=users)


@user_bp.route("/user/<int:user_id>")
@admin_required
def user_detail(user_id):
    """Scheda dettagliata utente"""
    try:
        # Use the service layer instead of direct database access
        user_data = user_service.get_user_detail_data(user_id)
        user = user_data["user"]

        # se l'utente è admin, ritorna alla lista utenti
        if user.role == "admin":
            return redirect(url_for("admin.user.users_list"))

        # Get additional data through service methods
        inscriptions = user_data["inscriptions"]
        matches = user_service.get_user_matches(user_id)
        classifications = user_service.get_user_classifications(user_id)
        stats = user_service.get_user_statistics(user_id)

    except ValueError:
        from flask import abort

        abort(404)

    return render_template(
        "admin/user_detail.html",
        user=user,
        inscriptions=inscriptions,
        matches=matches,
        classifications=classifications,
        stats=stats,
    )


@user_bp.route("/director_requests")
@admin_required
def director_requests():
    """Lista richieste di promozione a direttore"""
    pending = DirectorRequest.query.filter_by(
        status=DirectorRequestStatus.PENDING.value
    ).all()
    return render_template("admin/director_requests.html", requests=pending)


@user_bp.route("/director_requests/<int:req_id>/approve", methods=["POST"])
@admin_required
def approve_director_request(req_id):
    """Approva richiesta di promozione a direttore"""
    from models.user.services import DirectorRequestService
    from flask_login import current_user

    try:
        # Usa il service layer invece del direct database access
        # Cast current_user to User type since @admin_required ensures it's a valid admin User
        from models.base import db

        admin_user = db.session.get(User, current_user.id)
        DirectorRequestService.process_request(req_id, admin_user, approve=True)
        flash("Richiesta approvata.")
    except (PermissionError, ValueError) as e:
        flash(str(e), "error")

    return redirect(url_for("admin.user.director_requests"))


@user_bp.route("/director_requests/<int:req_id>/reject", methods=["POST"])
@admin_required
def reject_director_request(req_id):
    """Rifiuta richiesta di promozione a direttore"""
    from models.user.services import DirectorRequestService
    from flask_login import current_user

    try:
        # Usa il service layer invece del direct database access
        # Cast current_user to User type since @admin_required ensures it's a valid admin User
        from models.base import db

        admin_user = db.session.get(User, current_user.id)
        DirectorRequestService.process_request(req_id, admin_user, approve=False)
        flash("Richiesta rifiutata.")
    except (PermissionError, ValueError) as e:
        flash(str(e), "error")

    return redirect(url_for("admin.user.director_requests"))


@user_bp.route("/director_requests/<int:req_id>/process", methods=["POST"])
@admin_required
def process_director_request(req_id):
    """Process director request (approve or reject based on status parameter)"""
    from models.user.services import DirectorRequestService
    from flask_login import current_user

    try:
        status = request.form.get("status")
        admin_notes = request.form.get("admin_notes", "")

        approve = status == "approved"

        admin_user = db.session.get(User, current_user.id)
        processed_request = DirectorRequestService.process_request(
            req_id, admin_user, approve=approve
        )

        # Update admin notes if provided
        if admin_notes:
            processed_request.notes = admin_notes
            db.session.commit()

        flash("Richiesta processata con successo.")
    except (PermissionError, ValueError) as e:
        db.session.rollback()
        flash(str(e), "error")

    return redirect(url_for("admin.user.director_requests"))


@user_bp.route("/user/<int:user_id>/demote_director", methods=["POST"])
@admin_required
def demote_director(user_id):
    """Rimuove il ruolo director da un utente"""
    from models.user.services import UserService
    from flask_login import current_user

    try:
        UserService.demote_director_to_player(user_id, current_user.id)
        flash("Utente degradato da direttore a giocatore.")
    except (PermissionError, ValueError) as e:
        flash(str(e), "error")

    return redirect(url_for("admin.user.user_detail", user_id=user_id))


@user_bp.route("/user/<int:user_id>/promote_director", methods=["POST"])
@admin_required
def promote_director(user_id):
    """Promuove un utente a direttore di gara (senza richiesta)"""
    from models.user.permission_service import UserPermissionService
    from flask_login import current_user

    try:
        UserPermissionService.promote_to_director(user_id, current_user.id)
        flash("Utente promosso a direttore di gara.")
    except ValueError as e:
        flash(str(e), "error")

    return redirect(url_for("admin.user.user_detail", user_id=user_id))
