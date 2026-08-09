# routes/role_grant.py
"""Blueprint per i ruoli concedibili e la loro delega (ADR-038).

Prefix ``/roles`` e **non** ``/admin``: le richieste le processano gli
esaminatori, che admin non sono. L'autorizzazione non vive qui — ogni
decisione su chi può cosa è delegata a ``RoleGrantService.can_grant`` /
``can_revoke``, punto unico di verità per tutti i ruoli concedibili.
"""

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import _
from flask_login import current_user, login_required

from models.base import db
from models.exceptions import ValidationError
from models.user.models import User
from models.user.role_enum import GrantableRole
from models.user.role_grant_service import GRANT_POLICY, RoleGrantService
from utils.route_helpers import handle_service_action

role_grant_bp = Blueprint("roles", __name__, url_prefix="/roles")


def _parse_role_or_404(role: str) -> GrantableRole:
    """Traduce il path param in ``GrantableRole``; 404 se non è un ruolo noto."""
    try:
        return RoleGrantService.parse_role(role)
    except ValidationError:
        abort(404)


def _current_user_obj() -> User:
    """``current_user`` come istanza ``User`` attaccata alla sessione corrente."""
    user = db.session.get(User, current_user.id)
    if user is None:
        abort(403)
    return user


# ────────────────────────────────────────────────────────────────────────────────
# Richiesta del ruolo (US-P8)
# ────────────────────────────────────────────────────────────────────────────────
@role_grant_bp.route("/request/<role>", methods=["GET"])
@login_required
def request_role_form(role: str):
    """Form di richiesta: scegli a chi indirizzarla fra i titolari del ruolo."""
    grantable = _parse_role_or_404(role)
    user = _current_user_obj()

    if RoleGrantService.has_role(user.id, grantable):
        flash(_("Hai già questo ruolo."), "info")
        return redirect(url_for("challenge.challenge_catalog"))

    policy = RoleGrantService.get_policy(grantable)
    if not user.can_access(policy.request_feature_code):
        abort(403)

    return render_template(
        "roles/request_form.html",
        role=grantable,
        recipients=RoleGrantService.eligible_recipients(grantable, user.id),
        pending_request=RoleGrantService.get_pending_request(user.id, grantable),
    )


@role_grant_bp.route("/request/<role>", methods=["POST"])
@login_required
def request_role(role: str):
    """Invia la richiesta ai destinatari selezionati (vuoto = a tutti)."""
    grantable = _parse_role_or_404(role)
    user = _current_user_obj()

    recipient_ids = [
        int(value)
        for value in request.form.getlist("recipient_ids")
        if value.strip().isdigit()
    ]
    notes = (request.form.get("notes") or "").strip() or None

    return handle_service_action(
        action=lambda: RoleGrantService.create_request(
            user.id, grantable, recipient_ids=recipient_ids, notes=notes
        ),
        redirect_url=url_for("challenge.challenge_catalog"),
        success_message=_("Richiesta inviata."),
        error_prefix=None,
    )


# ────────────────────────────────────────────────────────────────────────────────
# Coda delle richieste (US-A2)
# ────────────────────────────────────────────────────────────────────────────────
@role_grant_bp.route("/requests", methods=["GET"])
@login_required
def role_requests():
    """Richieste che l'utente corrente può processare."""
    user = _current_user_obj()

    if not any(RoleGrantService.can_grant(user, r) for r in GRANT_POLICY):
        abort(403)

    return render_template(
        "roles/requests.html",
        requests=RoleGrantService.get_pending_requests_for(user),
    )


@role_grant_bp.route("/requests/<int:request_id>/process", methods=["POST"])
@login_required
def process_role_request(request_id: int):
    """Approva (concedendo il ruolo) o rifiuta una richiesta."""
    user = _current_user_obj()
    approve = request.form.get("decision") == "approve"
    notes = (request.form.get("decision_notes") or "").strip() or None

    return handle_service_action(
        action=lambda: RoleGrantService.process_request(
            request_id, user, approve=approve, decision_notes=notes
        ),
        redirect_url=url_for("roles.role_requests"),
        success_message=(
            _("Richiesta approvata: il ruolo è stato concesso.")
            if approve
            else _("Richiesta rifiutata.")
        ),
        error_prefix=None,
    )


# ────────────────────────────────────────────────────────────────────────────────
# Titolari e audit della catena (US-A3)
# ────────────────────────────────────────────────────────────────────────────────
@role_grant_bp.route("/holders/<role>", methods=["GET"])
@login_required
def role_holders(role: str):
    """Elenco dei titolari con la catena delle deleghe (chi ha concesso a chi)."""
    grantable = _parse_role_or_404(role)
    user = _current_user_obj()

    if not user.is_admin:
        abort(403)

    return render_template(
        "roles/holders.html",
        role=grantable,
        grants=RoleGrantService.list_grants_history(grantable),
    )


# ────────────────────────────────────────────────────────────────────────────────
# Concessione diretta e revoca (US-A1, US-A3)
# ────────────────────────────────────────────────────────────────────────────────
@role_grant_bp.route("/grant/<role>/<int:user_id>", methods=["POST"])
@login_required
def grant_role(role: str, user_id: int):
    """Concessione diretta, senza passare da una richiesta (bootstrap incluso)."""
    grantable = _parse_role_or_404(role)
    actor = _current_user_obj()
    redirect_url = request.form.get("next") or url_for(
        "admin.user.user_detail", user_id=user_id
    )

    return handle_service_action(
        action=lambda: RoleGrantService.grant(user_id, grantable, actor),
        redirect_url=redirect_url,
        success_message=_("Ruolo concesso."),
        error_prefix=None,
    )


@role_grant_bp.route("/revoke/<role>/<int:user_id>", methods=["POST"])
@login_required
def revoke_role(role: str, user_id: int):
    """Revoca del ruolo. Il lavoro già svolto dal titolare resta valido."""
    grantable = _parse_role_or_404(role)
    actor = _current_user_obj()
    redirect_url = request.form.get("next") or url_for(
        "admin.user.user_detail", user_id=user_id
    )

    return handle_service_action(
        action=lambda: RoleGrantService.revoke(user_id, grantable, actor),
        redirect_url=redirect_url,
        success_message=_("Ruolo revocato."),
        error_prefix=None,
    )
