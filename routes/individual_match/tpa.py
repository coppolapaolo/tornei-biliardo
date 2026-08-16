"""Referto TPA di un match individuale.

Una pagina e cinque azioni.

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
        flash(_("Accesso negato a questo match."), "danger")
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
    return _state_response(referto)


@individual_match_bp.route("/matches/<int:match_id>/tpa/undo", methods=["POST"])
@RoleRequirement.player_or_director_required
def tpa_undo(match_id: int):
    """Annulla l'ultimo tocco."""
    match, referto, is_player = _load(match_id)
    if not is_player or referto is None:
        return jsonify({"success": False, "message": _("Referto non trovato")}), 404

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
        flash(_("Referto chiuso."), "success")
    except DomainError as error:
        flash(str(error), "warning")
    except Exception:
        logger.error("Chiusura referto TPA fallita", exc_info=True)
        flash(_("Errore interno del server"), "danger")
    return redirect(url_for("individual_match.tpa_referto", match_id=match_id))
