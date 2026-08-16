# routes/admin/user.py
"""User management blueprint for admin interface."""

from flask import Blueprint, render_template, redirect, url_for, flash, request

from models import (
    User,
    DirectorRequest,
    db,
)
from utils import admin_required
from utils.route_helpers import handle_service_action
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
    from models.user.role_enum import GrantableRole
    from models.user.role_grant_service import RoleGrantService

    # Use the service layer instead of direct database access
    users = user_service.get_users_with_stats()

    # Una query sola per tutta la colonna «Esaminatore»: `user.is_examiner`
    # nel template ne farebbe una per riga.
    examiner_ids = RoleGrantService.holder_ids(GrantableRole.EXAMINER)

    return render_template(
        "admin/users_list.html", users=users, examiner_ids=examiner_ids
    )


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

    def action():
        admin_user = db.session.get(User, current_user.id)
        DirectorRequestService.process_request(req_id, admin_user, approve=True)

    return handle_service_action(
        action=action,
        redirect_url=url_for("admin.user.director_requests"),
        success_message="Richiesta approvata.",
        error_prefix=None,
    )


@user_bp.route("/director_requests/<int:req_id>/reject", methods=["POST"])
@admin_required
def reject_director_request(req_id):
    """Rifiuta richiesta di promozione a direttore"""
    from models.user.services import DirectorRequestService
    from flask_login import current_user

    def action():
        admin_user = db.session.get(User, current_user.id)
        DirectorRequestService.process_request(req_id, admin_user, approve=False)

    return handle_service_action(
        action=action,
        redirect_url=url_for("admin.user.director_requests"),
        success_message="Richiesta rifiutata.",
        error_prefix=None,
    )


@user_bp.route("/director_requests/<int:req_id>/process", methods=["POST"])
@admin_required
def process_director_request(req_id):
    """Process director request (approve or reject based on status parameter)"""
    from models.user.permission_service import UserPermissionService
    from flask_login import current_user

    status = request.form.get("status")
    admin_notes = request.form.get("admin_notes", "") or None
    approve = status == "approved"

    def action():
        admin_user = db.session.get(User, current_user.id)
        UserPermissionService.process_director_request(
            req_id, admin_user, approve=approve, notes=admin_notes
        )

    return handle_service_action(
        action=action,
        redirect_url=url_for("admin.user.director_requests"),
        success_message="Richiesta processata con successo.",
        error_prefix=None,
    )


@user_bp.route("/user/<int:user_id>/demote_director", methods=["POST"])
@admin_required
def demote_director(user_id):
    """Rimuove il ruolo director da un utente"""
    from models.user.services import UserService
    from flask_login import current_user

    return handle_service_action(
        action=lambda: UserService.demote_director_to_player(user_id, current_user.id),
        redirect_url=url_for("admin.user.user_detail", user_id=user_id),
        success_message="Utente degradato da direttore a giocatore.",
        error_prefix=None,
    )


@user_bp.route("/user/<int:user_id>/promote_director", methods=["POST"])
@admin_required
def promote_director(user_id):
    """Promuove un utente a direttore di gara (senza richiesta)"""
    from models.user.permission_service import UserPermissionService
    from flask_login import current_user

    return handle_service_action(
        action=lambda: UserPermissionService.promote_to_director(
            user_id, current_user.id
        ),
        redirect_url=url_for("admin.user.user_detail", user_id=user_id),
        success_message="Utente promosso a direttore di gara.",
        error_prefix=None,
    )


@user_bp.route("/user/<int:user_id>/toggle_gamification_override", methods=["POST"])
@admin_required
def toggle_gamification_override(user_id):
    """Toggle gamification_override for a user (admin bypass)"""
    return handle_service_action(
        action=lambda: UserService.toggle_gamification_override(user_id),
        redirect_url=url_for("admin.user.user_detail", user_id=user_id),
        success_message="Gamification Override aggiornato.",
    )


@user_bp.route("/user/<int:user_id>/anonymize", methods=["POST"])
@admin_required
def anonymize_user(user_id: int):
    """Anonimizza (soft-delete GDPR con scrub PII) un utente."""
    from flask_login import current_user
    from flask_babel import _

    return handle_service_action(
        action=lambda: UserService.anonymize_user(user_id, current_user.id),
        redirect_url=url_for("admin.user.users_list"),
        success_message=_("Utente eliminato (anonimizzato) con successo."),
        error_prefix=None,
    )


@user_bp.route("/users/merge", methods=["POST"])
@admin_required
def merge_users():
    """Unisce l'account sorgente nell'account destinazione (admin-only)."""
    from flask_login import current_user
    from flask_babel import _

    try:
        source_id = int(request.form.get("source_id", ""))
        target_id = int(request.form.get("target_id", ""))
    except (TypeError, ValueError):
        flash(_("Seleziona sia l'account sorgente sia quello destinazione."), "error")
        return redirect(url_for("admin.user.users_list"))

    return handle_service_action(
        action=lambda: UserService.merge_users(source_id, target_id, current_user.id),
        redirect_url=url_for("admin.user.users_list"),
        success_message=_("Account uniti con successo."),
        error_prefix=None,
    )


@user_bp.route("/user/<int:user_id>/verify-email", methods=["POST"])
@admin_required
def verify_user_email(user_id: int):
    """Segna manualmente come verificata l'email di un utente."""
    from flask_babel import _

    return handle_service_action(
        action=lambda: UserService.set_email_verified(user_id),
        redirect_url=url_for("admin.user.users_list"),
        success_message=_("Email verificata manualmente."),
        error_prefix=None,
    )


@user_bp.route("/user/<int:user_id>/resend-verification", methods=["POST"])
@admin_required
def resend_verification(user_id: int):
    """Reinvia l'email di verifica a un utente non verificato."""
    from flask_babel import _

    def action():
        sent = UserService.resend_verification_email(user_id)
        if not sent:
            raise ValueError(
                _("Impossibile reinviare: utente già verificato o invio fallito.")
            )

    return handle_service_action(
        action=action,
        redirect_url=url_for("admin.user.users_list"),
        success_message=_("Email di verifica reinviata."),
        error_prefix=None,
    )


@user_bp.route("/user/<int:user_id>/set-password", methods=["POST"])
@admin_required
def set_user_password(user_id: int):
    """Admin sets a new password for a user"""
    from flask_login import current_user
    from flask_babel import _
    from models.user.profile_service import UserProfileService

    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if new_password != confirm_password:
        flash(_("Le password non corrispondono"), "danger")
        return redirect(url_for("admin.user.user_detail", user_id=user_id))

    return handle_service_action(
        action=lambda: UserProfileService.set_password_as_admin(
            user_id=user_id,
            new_password=new_password,
            admin_id=current_user.id,
        ),
        redirect_url=url_for("admin.user.user_detail", user_id=user_id),
        success_message=_("Password impostata con successo"),
        error_prefix=None,
    )
