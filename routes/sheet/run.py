"""La seduta: aprirla, segnare le caselle, chiuderla (ADR-067).

Ogni gesto è **una richiesta JSON** e la risposta riporta i due pezzi che
cambiano — «come sta andando» e i comandi — già disegnati dal server. È la
stessa scelta della prova a colpi (ADR-066), e per la stessa ragione: due stati
da tenere in pari, uno qui e uno nel browser, sono due stati che prima o poi
divergono. Qui pesa il doppio, perché le caselle si segnano dieci alla volta col
telefono appoggiato alla sponda.
"""

from __future__ import annotations

from typing import Optional

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models.base import db
from models.exceptions import DomainError
from models.training_sheet import TrainingSheetService
from models.training_sheet.models import TrainingSession
from models.training_sheet.run_view import build_run
from models.training_sheet.session_service import TrainingSessionService
from models.training_sheet.summary_view import build_summary
from utils.route_helpers import http_status_for_exception

from . import sheet_bp


def _mia_o_404(sheet_id: int):
    try:
        sheet = TrainingSheetService.get_sheet(sheet_id)
    except DomainError:
        abort(404)
    if not TrainingSheetService.can_edit(sheet, current_user):
        abort(404)
    return sheet


def _seduta_o_404(session_id: int) -> TrainingSession:
    """La seduta, se è di chi sta guardando. Per **scriverci**."""
    session = db.session.get(TrainingSession, session_id)
    if session is None or session.user_id != current_user.id:
        abort(404)
    return session


def _seduta_da_leggere(session_id: int) -> TrainingSession:
    """La seduta, se la si può **guardare**: anche di un allievo (ADR-069).

    Le due porte restano separate. Una sola, con un `if` dentro ogni gesto,
    sarebbe a un refactor di distanza dal lasciar scrivere un istruttore nel
    registro di qualcun altro.
    """
    session = db.session.get(TrainingSession, session_id)
    if session is None or not TrainingSessionService.can_read(session, current_user):
        abort(404)
    return session


def _pezzi(session: TrainingSession, at: Optional[int] = None) -> dict:
    """I due pezzi ridisegnati, più i numeri che stanno in testata."""
    vista = build_run(session, at)
    return {
        "success": True,
        "progress_html": render_template("sheet/_run_progress.html", run=vista),
        "dock_html": render_template("sheet/_run_dock.html", run=vista),
        "total": vista.total,
        "max_total": vista.max_total,
    }


@sheet_bp.route("/<int:sheet_id>/seduta", methods=["POST"])
@login_required
def start_session(sheet_id):
    """Comincia — o riprende quella lasciata aperta."""
    sheet = _mia_o_404(sheet_id)
    try:
        session = TrainingSessionService.start(
            sheet.id, current_user, day=request.form.get("day")
        )
    except DomainError as errore:
        flash(str(errore), "error")
        return redirect(url_for("sheet.index"))
    return redirect(url_for("sheet.run", session_id=session.id))


@sheet_bp.route("/seduta/<int:session_id>", methods=["GET"])
@login_required
def run(session_id):
    """La seduta in corso: una voce per volta.

    A seduta chiusa non si scrive più, e questo indirizzo manda al riepilogo:
    è la stessa pagina che si riapre per rileggerla.
    """
    session = _seduta_o_404(session_id)
    if not session.is_open:
        return redirect(url_for("sheet.session_summary", session_id=session.id))

    at = request.args.get("voce", type=int)
    vista = build_run(session, at)
    return render_template("sheet/run.html", run=vista)


@sheet_bp.route("/seduta/<int:session_id>/segna", methods=["POST"])
@login_required
def record_cell(session_id):
    """Scrive una casella: il numero, o la spunta. Un tocco."""
    session = _seduta_o_404(session_id)
    dati = request.get_json(silent=True) or {}
    try:
        TrainingSessionService.record(
            session.id,
            _int(dati.get("item_id")) or 0,
            current_user,
            variant_id=_int(dati.get("variant_id")),
            value=_int(dati.get("value")),
            done=dati.get("done") if isinstance(dati.get("done"), bool) else None,
        )
    except ValueError as errore:
        db.session.rollback()
        return (
            jsonify({"success": False, "error": str(errore)}),
            http_status_for_exception(errore),
        )
    return jsonify(_pezzi(session, _int(dati.get("at"))))


@sheet_bp.route("/seduta/<int:session_id>/tiro", methods=["POST"])
@login_required
def record_shot(session_id):
    """Un tiro alla volta, sulle voci lunghe."""
    session = _seduta_o_404(session_id)
    dati = request.get_json(silent=True) or {}
    try:
        TrainingSessionService.mark(
            session.id,
            _int(dati.get("item_id")) or 0,
            current_user,
            made=bool(dati.get("made")),
            variant_id=_int(dati.get("variant_id")),
        )
    except ValueError as errore:
        db.session.rollback()
        return (
            jsonify({"success": False, "error": str(errore)}),
            http_status_for_exception(errore),
        )
    return jsonify(_pezzi(session, _int(dati.get("at"))))


@sheet_bp.route("/seduta/<int:session_id>/prova", methods=["POST"])
@login_required
def record_score_cell(session_id):
    """Una prova a punteggio in più sulla voce (ADR-072)."""
    session = _seduta_o_404(session_id)
    dati = request.get_json(silent=True) or {}
    try:
        TrainingSessionService.record_score(
            session.id,
            _int(dati.get("item_id")) or 0,
            current_user,
            score=_int(dati.get("score")),
            variant_id=_int(dati.get("variant_id")),
        )
    except ValueError as errore:
        db.session.rollback()
        return (
            jsonify({"success": False, "error": str(errore)}),
            http_status_for_exception(errore),
        )
    return jsonify(_pezzi(session, _int(dati.get("at"))))


@sheet_bp.route("/seduta/<int:session_id>/prova/annulla", methods=["POST"])
@login_required
def undo_score_cell(session_id):
    """Toglie l'ultima prova a punteggio della voce."""
    session = _seduta_o_404(session_id)
    dati = request.get_json(silent=True) or {}
    try:
        TrainingSessionService.undo_score(
            session.id,
            _int(dati.get("item_id")) or 0,
            current_user,
            variant_id=_int(dati.get("variant_id")),
        )
    except ValueError as errore:
        db.session.rollback()
        return (
            jsonify({"success": False, "error": str(errore)}),
            http_status_for_exception(errore),
        )
    return jsonify(_pezzi(session, _int(dati.get("at"))))


@sheet_bp.route("/seduta/<int:session_id>/annulla", methods=["POST"])
@login_required
def undo_shot(session_id):
    """Toglie l'ultimo tiro segnato, o svuota la casella."""
    session = _seduta_o_404(session_id)
    dati = request.get_json(silent=True) or {}
    item_id = _int(dati.get("item_id")) or 0
    variant_id = _int(dati.get("variant_id"))
    try:
        if dati.get("clear"):
            TrainingSessionService.clear(
                session.id, item_id, current_user, variant_id=variant_id
            )
        else:
            TrainingSessionService.undo_mark(
                session.id, item_id, current_user, variant_id=variant_id
            )
    except ValueError as errore:
        db.session.rollback()
        return (
            jsonify({"success": False, "error": str(errore)}),
            http_status_for_exception(errore),
        )
    return jsonify(_pezzi(session, _int(dati.get("at"))))


@sheet_bp.route("/seduta/<int:session_id>/chiudi", methods=["POST"])
@login_required
def close_session(session_id):
    """Chiude la seduta e porta al riepilogo. Se è vuota, la butta."""
    session = _seduta_o_404(session_id)
    vuota = not any(entry.is_filled for entry in session.entries)
    try:
        if vuota:
            TrainingSessionService.discard(session.id, current_user)
            flash(_("Seduta chiusa senza segnare niente."), "info")
            return redirect(url_for("sheet.index"))
        TrainingSessionService.close(session.id, current_user)
    except DomainError as errore:
        flash(str(errore), "error")
        return redirect(url_for("sheet.run", session_id=session.id))
    return redirect(url_for("sheet.session_summary", session_id=session.id))


@sheet_bp.route("/seduta/<int:session_id>/fine", methods=["GET"])
@login_required
def session_summary(session_id):
    """Fine seduta: com'è andata, e com'era andata la volta prima.

    È anche la pagina che apre l'istruttore dal registro dell'allievo: gli
    stessi numeri, senza i comandi e — se l'allievo non le ha aperte — senza
    le note (ADR-069).
    """
    session = _seduta_da_leggere(session_id)
    mia = session.user_id == current_user.id
    return render_template(
        "sheet/summary.html",
        summary=build_summary(session),
        session=session,
        mia=mia,
        vedo_le_note=TrainingSheetService.can_read_notes(session.sheet, current_user),
    )


@sheet_bp.route("/seduta/<int:session_id>/note", methods=["POST"])
@login_required
def session_notes(session_id):
    """Le note della seduta: si scrivono anche dopo averla chiusa."""
    session = _seduta_o_404(session_id)
    try:
        TrainingSessionService.set_notes(
            session.id, current_user, request.form.get("notes")
        )
    except DomainError as errore:
        flash(str(errore), "error")
    else:
        flash(_("Note salvate."), "success")
    return redirect(url_for("sheet.session_summary", session_id=session.id))


def _int(grezzo) -> Optional[int]:
    try:
        return int(str(grezzo).strip())
    except (TypeError, ValueError):
        return None
