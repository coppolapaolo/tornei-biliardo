"""Referto TPA di un match individuale.

Una pagina e sette azioni.

**Il gate della gamification sta sull'apertura, non sulla lettura.** Sbloccare
la funzione vuol dire poter *prendere* un referto; una volta che il referto
esiste, riguarda tutti e due i giocatori — e chi non ha sbloccato niente lo
vede comunque, in sola lettura. E' la stessa regola del TPA nel profilo
(ADR-044): il dato esiste e ti riguarda, nasconderlo sarebbe assurdo.

Tenere il gate anche sulla scrittura sarebbe peggio che inutile: se l'admin
irrigidisse le regole a partita in corso, il compilatore resterebbe chiuso
fuori da un referto a meta', con il segnapunti normale nascosto e nessun modo
di segnare i rack.

Chi puo' *scrivere* resta una cosa sola: il compilatore. Quel controllo sta nel
servizio, non qui, cosi' vale anche per una POST arrivata per conto suo.

Le azioni rispondono sempre con **lo stato completo del referto**, non con un
"ok": il tastierino cambia a ogni tocco, e farlo ricalcolare al client da un
esito parziale e' il modo piu' rapido per farlo andare fuori sincrono.
"""

from __future__ import annotations

import logging

from flask import abort, jsonify, redirect, render_template, request, url_for, flash
from flask_babel import gettext as _
from flask_login import current_user

from models import IndividualMatch
from models.base import db
from models.exceptions import DomainError, http_status_for_exception
from models.tpa.services import FEATURE_CODE, TpaRefertoService
from models.user.permissions import RoleRequirement
from utils.permissions import feature_required

from . import individual_match_bp

logger = logging.getLogger(__name__)


def _load(match_id: int):
    """Il match e il suo referto, con l'utente corrente gia' verificato."""
    match = IndividualMatch.query.get_or_404(match_id)
    if current_user.id not in (match.player1_id, match.player2_id):
        return match, None, False
    return match, TpaRefertoService.get_for_match(match_id), True


def _may_read(referto) -> bool:
    """Se l'utente corrente puo' *guardare* il referto.

    Basta che il referto esista: e' una partita sua, e chi l'ha annotata ha
    annotato anche lui. Chi non ha ancora un referto vede invece la pagina di
    presentazione, e quella si', e' riservata a chi ha sbloccato la funzione.
    """
    if referto is not None:
        return True
    return bool(current_user.is_authenticated and current_user.can_access(FEATURE_CODE))


def _state_response(referto):
    return jsonify(
        {
            "success": True,
            "state": TpaRefertoService.describe(referto, viewer_id=current_user.id),
        }
    )


def _score_of(match_id: int):
    match = db.session.get(IndividualMatch, match_id)
    return (match.player1_score, match.player2_score) if match else None


def _announce(match_id: int, referto, score_before=None) -> None:
    """Dice al canale del match che il referto e' cambiato.

    Due eventi distinti, perche' interessano due pagine diverse:

    - ``tpa_updated`` a ogni tocco. Lo ascolta la pagina del referto, che
      rilegge lo stato e si ridisegna **senza ricaricarsi**: chi guarda sta
      seguendo una partita, e una pagina che si ricarica da sola ogni pochi
      secondi perde la posizione e fa perdere il filo.
    - ``rack_updated`` solo quando il punteggio si e' mosso davvero. Lo
      ascolta la pagina del match, che invece si ricarica: mandarglielo a ogni
      tocco vorrebbe dire ricaricare la pagina dell'avversario venti volte per
      rack.

    ``score_before`` a ``None`` significa "questo gesto il punteggio non lo
    tocca" — la chiusura del referto — e allora il secondo evento non parte.
    """
    from routes.sse import emit_individual_match_event

    emit_individual_match_event(
        match_id,
        "tpa_updated",
        {"by": current_user.id, "commands": len(referto.comandi or [])},
    )

    if score_before is None:
        return
    match = db.session.get(IndividualMatch, match_id)
    if match is None or (match.player1_score, match.player2_score) == score_before:
        return
    emit_individual_match_event(
        match_id,
        "rack_updated",
        {
            "action": "tpa",
            "added_by": current_user.id,
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "is_ready_for_validation": match.is_ready_for_validation(),
        },
    )


def _domain_error(error: Exception):
    return (
        jsonify({"success": False, "message": str(error)}),
        http_status_for_exception(error),
    )


@individual_match_bp.route("/matches/<int:match_id>/tpa")
@RoleRequirement.player_or_director_required
def tpa_referto(match_id: int):
    """La pagina del referto: si compila o si guarda, secondo chi sei."""
    match, referto, is_player = _load(match_id)
    if not is_player:
        flash(_("Accesso negato a questa sfida."), "danger")
        return redirect(url_for("individual_match.match_list"))
    if not _may_read(referto):
        abort(403)

    state = None
    if referto is not None:
        state = TpaRefertoService.describe(referto, viewer_id=current_user.id)

    return render_template(
        "individual_match/tpa_referto.html",
        match=match,
        referto=referto,
        state=state,
        blocking_reason=(
            TpaRefertoService.blocking_reason(match, current_user.id)
            if referto is None
            else None
        ),
    )


@individual_match_bp.route("/matches/<int:match_id>/tpa/open", methods=["POST"])
@RoleRequirement.player_or_director_required
@feature_required(FEATURE_CODE)
def tpa_open(match_id: int):
    """Apre il referto e ne fa compilatore chi ha premuto."""
    try:
        TpaRefertoService.open_referto(match_id, current_user.id)
    except DomainError as error:
        flash(str(error), "warning")
    except Exception:
        logger.error("Apertura referto TPA fallita", exc_info=True)
        flash(_("Errore interno del server"), "danger")
    return redirect(url_for("individual_match.tpa_referto", match_id=match_id))


@individual_match_bp.route("/matches/<int:match_id>/tpa/press", methods=["POST"])
@RoleRequirement.player_or_director_required
def tpa_press(match_id: int):
    """Registra un tocco sul tastierino."""
    match, referto, is_player = _load(match_id)
    if not is_player or referto is None:
        return jsonify({"success": False, "message": _("Referto non trovato")}), 404

    command = (request.get_json(silent=True) or {}).get("command", "")
    score_before = _score_of(match_id)
    try:
        TpaRefertoService.press(referto.id, current_user.id, str(command))
    except DomainError as error:
        return _domain_error(error)
    except Exception:
        logger.error("Annotazione referto TPA fallita", exc_info=True)
        return (
            jsonify({"success": False, "message": _("Errore interno del server")}),
            500,
        )
    _announce(match_id, referto, score_before)
    return _state_response(referto)


@individual_match_bp.route("/matches/<int:match_id>/tpa/undo", methods=["POST"])
@RoleRequirement.player_or_director_required
def tpa_undo(match_id: int):
    """Annulla l'ultimo tocco."""
    match, referto, is_player = _load(match_id)
    if not is_player or referto is None:
        return jsonify({"success": False, "message": _("Referto non trovato")}), 404

    score_before = _score_of(match_id)
    try:
        TpaRefertoService.undo(referto.id, current_user.id)
    except DomainError as error:
        return _domain_error(error)
    except Exception:
        logger.error("Annulla referto TPA fallito", exc_info=True)
        return (
            jsonify({"success": False, "message": _("Errore interno del server")}),
            500,
        )
    _announce(match_id, referto, score_before)
    return _state_response(referto)


@individual_match_bp.route("/matches/<int:match_id>/tpa/clear", methods=["POST"])
@RoleRequirement.player_or_director_required
def tpa_clear(match_id: int):
    """«Cancella»: via l'annotazione del turno in corso."""
    match, referto, is_player = _load(match_id)
    if not is_player or referto is None:
        return jsonify({"success": False, "message": _("Referto non trovato")}), 404

    score_before = _score_of(match_id)
    try:
        TpaRefertoService.clear_turn(referto.id, current_user.id)
    except DomainError as error:
        return _domain_error(error)
    except Exception:
        logger.error("Cancella turno del referto TPA fallito", exc_info=True)
        return (
            jsonify({"success": False, "message": _("Errore interno del server")}),
            500,
        )
    _announce(match_id, referto, score_before)
    return _state_response(referto)


@individual_match_bp.route("/matches/<int:match_id>/tpa/restart", methods=["POST"])
@RoleRequirement.player_or_director_required
def tpa_restart(match_id: int):
    """«Riparti da questo turno…»: il registro si tronca a un turno del passato."""
    match, referto, is_player = _load(match_id)
    if not is_player or referto is None:
        return jsonify({"success": False, "message": _("Referto non trovato")}), 404

    body = request.get_json(silent=True) or {}
    try:
        rack_number, turn_number = int(body["rack"]), int(body["turn"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"success": False, "message": _("Turno non valido.")}), 400

    score_before = _score_of(match_id)
    try:
        TpaRefertoService.restart_from_turn(
            referto.id, current_user.id, rack_number, turn_number
        )
    except DomainError as error:
        return _domain_error(error)
    except Exception:
        logger.error("Ripartenza del referto TPA fallita", exc_info=True)
        return (
            jsonify({"success": False, "message": _("Errore interno del server")}),
            500,
        )
    _announce(match_id, referto, score_before)
    return _state_response(referto)


@individual_match_bp.route("/matches/<int:match_id>/tpa/state")
@RoleRequirement.player_or_director_required
def tpa_state(match_id: int):
    """Lo stato del referto, per chi lo sta guardando in sola lettura."""
    match, referto, is_player = _load(match_id)
    if not is_player or referto is None:
        return jsonify({"success": False, "message": _("Referto non trovato")}), 404
    return _state_response(referto)


@individual_match_bp.route("/matches/<int:match_id>/tpa/close", methods=["POST"])
@RoleRequirement.player_or_director_required
def tpa_close(match_id: int):
    """Chiude il referto: da qui in poi si legge e basta."""
    match, referto, is_player = _load(match_id)
    if not is_player or referto is None:
        flash(_("Referto non trovato"), "warning")
        return redirect(url_for("individual_match.match_detail", match_id=match_id))

    try:
        TpaRefertoService.close(referto.id, current_user.id)
        _announce(match_id, referto)
        flash(_("Referto chiuso."), "success")
    except DomainError as error:
        flash(str(error), "warning")
    except Exception:
        logger.error("Chiusura referto TPA fallita", exc_info=True)
        flash(_("Errore interno del server"), "danger")
    return redirect(url_for("individual_match.tpa_referto", match_id=match_id))
