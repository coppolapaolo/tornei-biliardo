"""Catalogo, dettaglio e composizione degli esami (US-P1, US-E1, US-E2, US-E8)."""

from flask import abort, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models.base import db
from models.exam.services import ExamService
from models.user.models import User
from utils import examiner_required, feature_required
from utils.route_helpers import handle_service_action

from . import exam_bp


def _actor() -> User:
    """``current_user`` come istanza attaccata alla sessione corrente."""
    user = db.session.get(User, current_user.id)
    if user is None:
        abort(403)
    return user


def _int_or_none(value):
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


# ────────────────────────────────────────────────────────────────────────────────
# Catalogo e dettaglio (US-P1)
# ────────────────────────────────────────────────────────────────────────────────
@exam_bp.route("/", methods=["GET"])
@login_required
def exam_catalog():
    """Gli esami disponibili, con i drill che li compongono.

    Il gate ``take_exam`` **non** basta da solo qui, ed è una lezione presa
    provando il percorso: un esaminatore che non ha ancora macinato i suoi drill
    non può *sostenere* un esame, ma deve poter arrivare ai propri — e questa è
    l'unica porta verso l'area di gestione. Gattando sul solo ``take_exam`` si
    ottiene un esaminatore che non raggiunge niente.

    I due gate restano ortogonali: chi entra di qui perché è esaminatore vede il
    catalogo, ma i bottoni per sostenere l'esame restano chiusi dalle loro route.
    """
    actor = _actor()
    if not (actor.can_access("take_exam") or actor.is_examiner):
        abort(403)

    return render_template(
        "exam/catalog.html",
        exams=ExamService.get_available_exams(),
        my_exams=(
            ExamService.get_exams_for_examiner(current_user.id)
            if current_user.is_examiner
            else []
        ),
    )


@exam_bp.route("/<int:exam_id>", methods=["GET"])
@login_required
@feature_required("take_exam")
def exam_detail(exam_id: int):
    """Dettaglio: drill, punteggi massimi e **chi lo somministra** (US-P1)."""
    from models.exam.request_service import ExamRequestService

    exam = ExamService.get_exam(exam_id)
    actor = _actor()

    return render_template(
        "exam/detail.html",
        exam=exam,
        can_edit=ExamService.can_edit(exam, actor),
        examiners=User.query.filter(User.id.in_(exam.examiner_ids)).all(),
        open_attempt=ExamService.get_open_self_practice(actor.id, exam_id),
        open_request=ExamRequestService.get_open_request(actor.id, exam_id),
        statistics=ExamService.get_exam_statistics(exam_id),
    )


# ────────────────────────────────────────────────────────────────────────────────
# Composizione (US-E1)
# ────────────────────────────────────────────────────────────────────────────────
@exam_bp.route("/manage", methods=["GET"])
@login_required
@examiner_required
def manage_exams():
    """Gli esami che l'esaminatore può somministrare, con le sue statistiche."""
    return render_template(
        "exam/manage.html",
        exams=ExamService.get_exams_for_examiner(current_user.id),
        statistics=ExamService.get_examiner_statistics(current_user.id),
    )


@exam_bp.route("/create", methods=["POST"])
@login_required
@examiner_required
def create_exam():
    actor = _actor()
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    time_limit = _int_or_none(request.form.get("time_limit_minutes"))

    return handle_service_action(
        action=lambda: ExamService.create_exam(
            actor, name=name, description=description, time_limit_minutes=time_limit
        ),
        redirect_url=url_for("exam.manage_exams"),
        success_message=_("Esame creato."),
        error_prefix=None,
    )


@exam_bp.route("/<int:exam_id>/update", methods=["POST"])
@login_required
@examiner_required
def update_exam(exam_id: int):
    actor = _actor()
    name = (request.form.get("name") or "").strip() or None
    description = (request.form.get("description") or "").strip() or None
    time_limit = _int_or_none(request.form.get("time_limit_minutes"))

    return handle_service_action(
        action=lambda: ExamService.update_exam(
            exam_id,
            actor,
            name=name,
            description=description,
            time_limit_minutes=time_limit,
        ),
        redirect_url=url_for("exam.exam_detail", exam_id=exam_id),
        success_message=_("Esame aggiornato."),
        error_prefix=None,
    )


@exam_bp.route("/<int:exam_id>/deactivate", methods=["POST"])
@login_required
@examiner_required
def deactivate_exam(exam_id: int):
    actor = _actor()
    return handle_service_action(
        action=lambda: ExamService.deactivate_exam(exam_id, actor),
        redirect_url=url_for("exam.manage_exams"),
        success_message=_("Esame disattivato."),
        error_prefix=None,
    )


# ────────────────────────────────────────────────────────────────────────────────
# Drill dell'esame (US-E1)
# ────────────────────────────────────────────────────────────────────────────────
@exam_bp.route("/<int:exam_id>/challenges/add", methods=["POST"])
@login_required
@examiner_required
def add_challenge(exam_id: int):
    actor = _actor()
    challenge_id = _int_or_none(request.form.get("challenge_id"))
    max_score = _int_or_none(request.form.get("max_score"))

    if challenge_id is None:
        abort(400)

    return handle_service_action(
        action=lambda: ExamService.add_challenge_to_exam(
            exam_id, challenge_id, actor, max_score=max_score
        ),
        redirect_url=url_for("exam.exam_detail", exam_id=exam_id),
        success_message=_("Drill aggiunto all'esame."),
        error_prefix=None,
    )


@exam_bp.route("/<int:exam_id>/challenges/<int:challenge_id>/update", methods=["POST"])
@login_required
@examiner_required
def update_challenge(exam_id: int, challenge_id: int):
    actor = _actor()
    max_score = _int_or_none(request.form.get("max_score"))

    return handle_service_action(
        action=lambda: ExamService.update_exam_challenge(
            exam_id, challenge_id, actor, max_score=max_score
        ),
        redirect_url=url_for("exam.exam_detail", exam_id=exam_id),
        success_message=_("Punteggio massimo aggiornato."),
        error_prefix=None,
    )


@exam_bp.route("/<int:exam_id>/challenges/<int:challenge_id>/remove", methods=["POST"])
@login_required
@examiner_required
def remove_challenge(exam_id: int, challenge_id: int):
    actor = _actor()
    return handle_service_action(
        action=lambda: ExamService.remove_challenge_from_exam(
            exam_id, challenge_id, actor
        ),
        redirect_url=url_for("exam.exam_detail", exam_id=exam_id),
        success_message=_("Drill rimosso dall'esame."),
        error_prefix=None,
    )


@exam_bp.route("/<int:exam_id>/challenges/reorder", methods=["POST"])
@login_required
@examiner_required
def reorder_challenges(exam_id: int):
    """Riordina i drill. L'ordine arriva come lista di ``challenge_id``."""
    actor = _actor()
    order = [
        int(value)
        for value in request.form.getlist("challenge_ids")
        if value.strip().isdigit()
    ]

    return handle_service_action(
        action=lambda: ExamService.reorder_exam_challenges(exam_id, actor, order),
        redirect_url=url_for("exam.exam_detail", exam_id=exam_id),
        success_message=_("Ordine aggiornato."),
        error_prefix=None,
    )


# ────────────────────────────────────────────────────────────────────────────────
# Co-esaminatori (US-E2)
# ────────────────────────────────────────────────────────────────────────────────
@exam_bp.route("/<int:exam_id>/examiners", methods=["GET"])
@login_required
@examiner_required
def manage_examiners(exam_id: int):
    """Chi altro può somministrare questo esame.

    La lista dei candidati può essere **vuota**: all'inizio esiste un solo
    titolare del ruolo, e la schermata deve reggerlo (UJ-1) invece di mostrare
    un menu a tendina senza voci.
    """
    exam = ExamService.get_exam(exam_id)
    actor = _actor()
    if not ExamService.can_edit(exam, actor):
        abort(403)

    return render_template(
        "exam/examiners.html",
        exam=exam,
        current=User.query.filter(User.id.in_(exam.examiner_ids)).all(),
        candidates=ExamService.eligible_examiners(exam_id),
    )


@exam_bp.route("/<int:exam_id>/examiners/add", methods=["POST"])
@login_required
@examiner_required
def add_examiner(exam_id: int):
    actor = _actor()
    user_id = _int_or_none(request.form.get("user_id"))
    if user_id is None:
        abort(400)

    return handle_service_action(
        action=lambda: ExamService.add_examiner(exam_id, user_id, actor),
        redirect_url=url_for("exam.manage_examiners", exam_id=exam_id),
        success_message=_("Esaminatore aggiunto."),
        error_prefix=None,
    )


@exam_bp.route("/<int:exam_id>/examiners/<int:user_id>/remove", methods=["POST"])
@login_required
@examiner_required
def remove_examiner(exam_id: int, user_id: int):
    actor = _actor()
    return handle_service_action(
        action=lambda: ExamService.remove_examiner(exam_id, user_id, actor),
        redirect_url=url_for("exam.manage_examiners", exam_id=exam_id),
        success_message=_("Esaminatore rimosso."),
        error_prefix=None,
    )
