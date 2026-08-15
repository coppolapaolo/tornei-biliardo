"""L'appuntamento d'esame: richiesta a più esaminatori e negoziazione.

Copre US-P4 (chiedo a chi voglio), US-P5 (ci accordiamo su ora e luogo),
US-E4/E5 (accetto o contropropongo).

Gli invarianti della trattativa — può accettare solo chi non ha fatto l'ultima
proposta, e la prima controproposta fissa l'interlocutore — vivono nel servizio.
Qui si legge il form e si lascia parlare il dominio.
"""

from flask import abort, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models.base import db
from models.exam.request_service import ExamRequestService
from models.exam.services import ExamService
from models.user.models import User
from utils import feature_required
from utils.local_time import parse_local_datetime
from utils.route_helpers import handle_service_action

from . import exam_bp


def _actor() -> User:
    user = db.session.get(User, current_user.id)
    if user is None:
        abort(403)
    return user


def _int_or_none(value):
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


# ────────────────────────────────────────────────────────────────────────────────
# Elenco e dettaglio
# ────────────────────────────────────────────────────────────────────────────────
@exam_bp.route("/requests", methods=["GET"])
@login_required
def request_list():
    """Le mie richieste: quelle inviate e, se sono esaminatore, quelle ricevute."""
    actor = _actor()
    return render_template(
        "exam/requests.html",
        sent=ExamRequestService.get_requests_for_requester(actor.id),
        received=(
            ExamRequestService.get_requests_for_examiner(actor.id)
            if actor.is_examiner
            else []
        ),
    )


@exam_bp.route("/requests/<int:request_id>", methods=["GET"])
@login_required
def request_detail(request_id: int):
    """La trattativa, con lo storico delle proposte e chi tocca adesso."""
    exam_request = ExamRequestService.get_request(request_id)
    actor = _actor()

    involved = {exam_request.requester_id} | set(exam_request.recipient_ids())
    if actor.id not in involved and not actor.is_admin:
        abort(403)

    recipient = exam_request.recipient_for(actor.id)
    is_recipient = recipient is not None
    # Chi ha fatto l'ultima proposta aspetta: è l'invariante 1, e la UI deve
    # dirlo invece di offrire un bottone che il servizio rifiuterebbe.
    waiting_for_the_other = exam_request.last_proposed_by_id == actor.id
    # Invariante 2: fissato l'interlocutore, gli altri possono solo accettare.
    locked_out = (
        is_recipient
        and exam_request.negotiating_with_id is not None
        and exam_request.negotiating_with_id != actor.id
    )

    return render_template(
        "exam/request_detail.html",
        exam_request=exam_request,
        is_requester=(actor.id == exam_request.requester_id),
        is_recipient=is_recipient,
        recipient=recipient,
        can_act=exam_request.is_open and not exam_request.is_expired(),
        waiting_for_the_other=waiting_for_the_other,
        locked_out=locked_out,
        attempt=exam_request.attempt,
    )


# ────────────────────────────────────────────────────────────────────────────────
# Richiesta (US-P4)
# ────────────────────────────────────────────────────────────────────────────────
@exam_bp.route("/<int:exam_id>/request", methods=["GET"])
@login_required
@feature_required("take_exam")
def request_form(exam_id: int):
    """A chi chiedere, e quando: gli esaminatori con le loro disponibilità."""
    from models.location.models import BilliardHall

    exam = ExamService.get_exam(exam_id)
    actor = _actor()

    return render_template(
        "exam/request_form.html",
        exam=exam,
        examiners=ExamRequestService.eligible_examiners(exam_id, actor.id),
        halls=BilliardHall.query.order_by(BilliardHall.name.asc()).all(),
        open_request=ExamRequestService.get_open_request(actor.id, exam_id),
    )


@exam_bp.route("/<int:exam_id>/request", methods=["POST"])
@login_required
@feature_required("take_exam")
def create_request(exam_id: int):
    """Invia la richiesta. Nessun destinatario scelto = a tutti gli esaminatori."""
    actor = _actor()
    recipient_ids = [
        int(value)
        for value in request.form.getlist("recipient_ids")
        if value.strip().isdigit()
    ]
    notes = (request.form.get("notes") or "").strip() or None

    return handle_service_action(
        action=lambda: ExamRequestService.create_request(
            actor,
            exam_id,
            scheduled_at=parse_local_datetime(request.form.get("scheduled_at")),
            billiard_hall_id=_int_or_none(request.form.get("billiard_hall_id")),
            recipient_ids=recipient_ids,
            notes=notes,
        ),
        redirect_url=url_for("exam.request_list"),
        success_message=_("Richiesta inviata."),
        error_prefix=None,
    )


# ────────────────────────────────────────────────────────────────────────────────
# Negoziazione (US-E5, US-P5)
# ────────────────────────────────────────────────────────────────────────────────
@exam_bp.route("/requests/<int:request_id>/counter", methods=["POST"])
@login_required
def counter_propose(request_id: int):
    """Contropropone un altro slot. La sala si eredita se non se ne indica una."""
    actor = _actor()
    return handle_service_action(
        action=lambda: ExamRequestService.counter_propose(
            request_id,
            actor,
            scheduled_at=parse_local_datetime(request.form.get("scheduled_at")),
            billiard_hall_id=_int_or_none(request.form.get("billiard_hall_id")),
        ),
        redirect_url=url_for("exam.request_detail", request_id=request_id),
        success_message=_("Controproposta inviata."),
        error_prefix=None,
    )


@exam_bp.route("/requests/<int:request_id>/accept", methods=["POST"])
@login_required
def accept_request(request_id: int):
    """Accetta la proposta sul tavolo: il primo che accetta chiude gli altri."""
    actor = _actor()
    return handle_service_action(
        action=lambda: ExamRequestService.accept(request_id, actor),
        redirect_url=url_for("exam.request_detail", request_id=request_id),
        success_message=_("Appuntamento fissato."),
        error_prefix=None,
    )


@exam_bp.route("/requests/<int:request_id>/decline", methods=["POST"])
@login_required
def decline_request(request_id: int):
    """Un esaminatore si sfila. Gli altri possono ancora accettare."""
    actor = _actor()
    return handle_service_action(
        action=lambda: ExamRequestService.decline(request_id, actor),
        redirect_url=url_for("exam.request_list"),
        success_message=_("Richiesta rifiutata."),
        error_prefix=None,
    )


@exam_bp.route("/requests/<int:request_id>/cancel", methods=["POST"])
@login_required
def cancel_request(request_id: int):
    """Il candidato ritira la richiesta."""
    actor = _actor()
    return handle_service_action(
        action=lambda: ExamRequestService.cancel(request_id, actor),
        redirect_url=url_for("exam.request_list"),
        success_message=_("Richiesta ritirata."),
        error_prefix=None,
    )
