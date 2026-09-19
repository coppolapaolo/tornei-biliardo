"""Catalogo, dettaglio e composizione degli esami (US-P1, US-E1, US-E2, US-E8)."""

from flask import abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models.base import db
from models.challenge.models import Challenge
from models.challenge.services import ChallengeService
from models.exam.services import (
    MAX_ATTEMPTS_PER_CHALLENGE,
    CompositionItem,
    ExamService,
)
from models.exceptions import http_status_for_exception
from models.user.models import User
from utils import examiner_required
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


def require_exam_reader() -> User:
    """Chi può **guardare** gli esami: chi li sostiene, o chi li somministra.

    Il gate ``take_exam`` da solo non basta, ed è una lezione presa provando il
    percorso a mano: un esaminatore che non ha ancora macinato i suoi drill non
    può *sostenere* un esame, ma deve arrivare ai propri — e le pagine di
    lettura sono l'unica strada verso l'area di gestione. Gattando sul solo
    ``take_exam`` si ottiene un esaminatore che non raggiunge niente.

    Sta qui, in un posto solo, perché la prima volta l'avevo scritta inline nel
    catalogo e dimenticata su dettaglio e sessione — che è il modo in cui una
    regola ripetuta smette di valere.

    I due gate restano ortogonali: chi entra perché è esaminatore *vede*, ma i
    bottoni per sostenere l'esame restano chiusi dalle loro route.
    """
    actor = _actor()
    if not (actor.can_access("take_exam") or actor.is_examiner):
        abort(403)
    return actor


# ────────────────────────────────────────────────────────────────────────────────
# Catalogo e dettaglio (US-P1)
# ────────────────────────────────────────────────────────────────────────────────
@exam_bp.route("/", methods=["GET"])
@login_required
def exam_catalog():
    """Gli esami disponibili, con i drill che li compongono."""
    require_exam_reader()

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
def exam_detail(exam_id: int):
    """Dettaglio: drill, punteggi massimi e **chi lo somministra** (US-P1)."""
    from models.exam.request_service import ExamRequestService

    actor = require_exam_reader()
    exam = ExamService.get_exam(exam_id)

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
    """Crea l'esame e porta **dritto a comporlo**: un esame senza esercizi non
    è sostenibile, e rimandare all'elenco voleva dire andarselo a ricercare."""
    actor = _actor()
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    time_limit = _int_or_none(request.form.get("time_limit_minutes"))

    try:
        exam = ExamService.create_exam(
            actor, name=name, description=description, time_limit_minutes=time_limit
        )
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("exam.manage_exams"))

    flash(_("Esame creato: ora scegli gli esercizi."), "success")
    return redirect(url_for("exam.compose_exam", exam_id=exam.id))


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
# Comporre l'esame (US-E1)
# ────────────────────────────────────────────────────────────────────────────────
# Una pagina e un salvataggio. Fino al 19/09/2026 c'erano cinque route — una per
# mossa: aggiungi, togli, cambia, riordina, rinomina — e tre di loro non avevano
# nessun comando nell'interfaccia; per aggiungere un esercizio si scriveva il
# suo ID a mano. Le regole di ogni mossa restano nel servizio, che ora le
# compone in una transazione sola (``ExamService.save_composition``).


def _items_of(exam) -> list[dict]:
    """Le voci della sequenza come le disegna la pagina."""
    return [
        {
            "challenge": ec.challenge,
            "max_score": ec.max_score,
            "max_attempts": ec.max_attempts,
        }
        for ec in exam.challenges.all()
    ]


def _items_from_form() -> list[CompositionItem]:
    """La sequenza inviata dal modulo: tre liste parallele, lette per posizione.

    Ogni voce manda sempre tutti e tre i campi — anche ``max_score`` vuoto per
    un esercizio riuscito o no — proprio perché le liste restino allineate. Se
    non lo sono il modulo è stato manomesso o è rotto: si rifiuta, non si
    indovina a quale voce appartenga un punteggio.
    """
    challenge_ids = request.form.getlist("challenge_id")
    max_scores = request.form.getlist("max_score")
    max_attempts = request.form.getlist("max_attempts")
    if not (len(challenge_ids) == len(max_scores) == len(max_attempts)):
        abort(400)

    items = []
    for raw_id, raw_score, raw_attempts in zip(challenge_ids, max_scores, max_attempts):
        challenge_id = _int_or_none(raw_id)
        if challenge_id is None:
            abort(400)
        items.append(
            CompositionItem(
                challenge_id=challenge_id,
                max_score=_int_or_none(raw_score),
                max_attempts=_int_or_none(raw_attempts) or 1,
            )
        )
    return items


def _render_compose(exam, items, *, form=None, status=200):
    return (
        render_template(
            "exam/compose.html",
            exam=exam,
            items=items,
            form=form or {},
            available=ChallengeService.get_active_challenges(),
            examiners=User.query.filter(User.id.in_(exam.examiner_ids)).all(),
            max_attempts_cap=MAX_ATTEMPTS_PER_CHALLENGE,
            locked=ExamService.has_open_certified_session(exam),
        ),
        status,
    )


@exam_bp.route("/<int:exam_id>/compose", methods=["GET"])
@login_required
@examiner_required
def compose_exam(exam_id: int):
    """La pagina «Componi l'esame»: nome, sequenza, chi lo somministra."""
    exam = ExamService.get_exam(exam_id)
    if not ExamService.can_edit(exam, _actor()):
        abort(403)
    return _render_compose(exam, _items_of(exam))


@exam_bp.route("/<int:exam_id>/compose", methods=["POST"])
@login_required
@examiner_required
def save_composition(exam_id: int):
    """Salva tutto insieme. Se qualcosa non va, la pagina torna **com'era
    stata lasciata**: un redirect butterebbe via il lavoro di chi ha appena
    riordinato dieci voci per un punteggio scritto male."""
    actor = _actor()
    exam = ExamService.get_exam(exam_id)
    if not ExamService.can_edit(exam, actor):
        abort(403)

    items = _items_from_form()
    form = {
        "name": (request.form.get("name") or "").strip(),
        "description": (request.form.get("description") or "").strip(),
        "time_limit_minutes": (request.form.get("time_limit_minutes") or "").strip(),
    }

    try:
        ExamService.save_composition(
            exam_id,
            actor,
            name=form["name"],
            description=form["description"] or None,
            time_limit_minutes=_int_or_none(form["time_limit_minutes"]),
            items=items,
        )
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")
        exam = ExamService.get_exam(exam_id)
        challenges = {
            c.id: c
            for c in Challenge.query.filter(
                Challenge.id.in_([item.challenge_id for item in items])
            ).all()
        }
        submitted = [
            {
                "challenge": challenges[item.challenge_id],
                "max_score": item.max_score,
                "max_attempts": item.max_attempts,
            }
            for item in items
            if item.challenge_id in challenges
        ]
        return _render_compose(
            exam, submitted, form=form, status=http_status_for_exception(error)
        )

    flash(_("Esame salvato."), "success")
    return redirect(url_for("exam.exam_detail", exam_id=exam_id))


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
