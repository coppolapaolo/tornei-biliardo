"""Sessioni d'esame: allenamento in autonomia e sessione certificata.

Copre US-P3 (prova da solo), US-P6 (il candidato accetta l'inizio), US-E6
(l'esaminatore registra i punteggi) e US-E7 (certifica l'esito).

**I divieti stanno nel servizio, non qui.** Una POST diretta aggira la UI ma non
`ExamService`: registrare un punteggio prima che il candidato abbia accettato
l'inizio è rifiutato dal dominio, e queste route si limitano a lasciar passare
l'eccezione. Le guardie che restano qui sono di sola *visibilità*.
"""

from flask import abort, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models.base import db
from models.exam.models import ExamAttempt
from models.exam.services import ExamService
from models.user.models import User
from utils import feature_required
from utils.route_helpers import handle_service_action

from . import exam_bp


def _actor() -> User:
    user = db.session.get(User, current_user.id)
    if user is None:
        abort(403)
    return user


def _attempt_or_404(attempt_id: int) -> ExamAttempt:
    attempt = db.session.get(ExamAttempt, attempt_id)
    if attempt is None:
        abort(404)
    return attempt


def _int_or_none(value):
    value = (value or "").strip()
    if value.startswith("-") and value[1:].isdigit():
        return int(value)
    return int(value) if value.isdigit() else None


# ────────────────────────────────────────────────────────────────────────────────
# Vista della sessione
# ────────────────────────────────────────────────────────────────────────────────
@exam_bp.route("/sessions/<int:attempt_id>", methods=["GET"])
@login_required
@feature_required("take_exam")
def session_detail(attempt_id: int):
    """La sessione, vista dal candidato o dall'esaminatore.

    La stessa schermata per entrambi: cambia chi può agire, non cosa si vede —
    il candidato deve poter seguire i punteggi mentre gli vengono registrati.
    """
    attempt = _attempt_or_404(attempt_id)
    actor = _actor()

    allowed = {attempt.user_id}
    if attempt.examiner_id is not None:
        allowed.add(attempt.examiner_id)
    if actor.id not in allowed and not actor.is_admin:
        abort(403)

    return render_template(
        "exam/session.html",
        attempt=attempt,
        is_candidate=(actor.id == attempt.user_id),
        is_examiner=(actor.id == attempt.examiner_id),
        progress=attempt.get_progress(),
    )


# ────────────────────────────────────────────────────────────────────────────────
# Allenamento in autonomia (US-P3)
# ────────────────────────────────────────────────────────────────────────────────
@exam_bp.route("/<int:exam_id>/practice", methods=["POST"])
@login_required
@feature_required("take_exam")
def start_self_practice(exam_id: int):
    """Apre (o riprende) un tentativo di allenamento. Non certifica mai."""
    actor = _actor()
    return handle_service_action(
        action=lambda: ExamService.start_self_practice(actor, exam_id),
        redirect_url=url_for("exam.exam_detail", exam_id=exam_id),
        success_message=_("Tentativo aperto: buon allenamento."),
        error_prefix=None,
    )


# ────────────────────────────────────────────────────────────────────────────────
# Sessione certificata (US-E6, US-P6)
# ────────────────────────────────────────────────────────────────────────────────
@exam_bp.route("/requests/<int:request_id>/open-session", methods=["POST"])
@login_required
def open_certified_session(request_id: int):
    """L'esaminatore apre la sessione dall'appuntamento accettato."""
    actor = _actor()
    return handle_service_action(
        action=lambda: ExamService.open_certified_session(actor, request_id),
        redirect_url=url_for("exam.request_detail", request_id=request_id),
        success_message=_("Sessione aperta: attendi che il candidato accetti."),
        error_prefix=None,
    )


@exam_bp.route("/sessions/<int:attempt_id>/accept-start", methods=["POST"])
@login_required
def accept_session_start(attempt_id: int):
    """Il candidato accetta l'inizio: nessuno lo valuta a sua insaputa (US-P6)."""
    actor = _actor()
    return handle_service_action(
        action=lambda: ExamService.accept_session_start(attempt_id, actor),
        redirect_url=url_for("exam.session_detail", attempt_id=attempt_id),
        success_message=_("Esame iniziato."),
        error_prefix=None,
    )


# ────────────────────────────────────────────────────────────────────────────────
# Punteggi ed esito (US-E6, US-E7)
# ────────────────────────────────────────────────────────────────────────────────
@exam_bp.route("/sessions/<int:attempt_id>/results", methods=["POST"])
@login_required
def record_result(attempt_id: int):
    """Registra il risultato di un drill dentro la sessione.

    ``passed`` arriva solo per i drill pass/fail, ``score`` solo per i numerici:
    quale dei due valga lo decide il servizio sul tipo di drill, non questa
    route sul nome del campo ricevuto.
    """
    actor = _actor()
    exam_challenge_id = _int_or_none(request.form.get("exam_challenge_id"))
    if exam_challenge_id is None:
        abort(400)

    score = _int_or_none(request.form.get("score"))
    raw_passed = request.form.get("passed")
    passed = None if raw_passed is None else raw_passed in ("1", "true", "True", "on")

    return handle_service_action(
        action=lambda: ExamService.record_challenge_result(
            attempt_id, exam_challenge_id, actor, score=score, passed=passed
        ),
        redirect_url=url_for("exam.session_detail", attempt_id=attempt_id),
        success_message=_("Risultato registrato."),
        error_prefix=None,
    )


@exam_bp.route("/sessions/<int:attempt_id>/complete", methods=["POST"])
@login_required
def complete_attempt(attempt_id: int):
    """Chiude la sessione. In autonomia senza esito, certificata con esito."""
    actor = _actor()
    raw_passed = request.form.get("passed")
    passed = None if raw_passed is None else raw_passed in ("1", "true", "True", "on")

    return handle_service_action(
        action=lambda: ExamService.complete_attempt(attempt_id, actor, passed=passed),
        redirect_url=url_for("exam.session_detail", attempt_id=attempt_id),
        success_message=_("Esame concluso."),
        error_prefix=None,
    )


@exam_bp.route("/sessions/<int:attempt_id>/abandon", methods=["POST"])
@login_required
def abandon_attempt(attempt_id: int):
    """Interrompe senza esito: il candidato non si è presentato, o si lascia."""
    actor = _actor()
    return handle_service_action(
        action=lambda: ExamService.abandon_attempt(attempt_id, actor),
        redirect_url=url_for("exam.exam_catalog"),
        success_message=_("Sessione interrotta."),
        error_prefix=None,
    )
