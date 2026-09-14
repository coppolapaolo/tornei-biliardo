"""Le partite che aspettano la conferma del giocatore (richiesta del 2026-09-14).

Chi ha partite che aspettano la sua firma non può lanciare né accettare altre
sfide individuali (``PendingConfirmationService``). Invece di un errore secco,
le route che lo scoprono lo portano qui: una pagina con le partite da chiudere,
ognuna con «Confermo» e «Rifiuto», e — chiusa l'ultima — il ritorno a quello
che stava facendo (``next``).
"""

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from models.individual_match.pending_confirmation import (
    PendingConfirmationError,
    PendingConfirmationService,
)
from models.user.permissions import RoleRequirement
from utils.route_helpers import is_ajax_request
from utils.safe_redirect import safe_next_url

from . import individual_match_bp

PENDING_ENDPOINT = "individual_match.pending_confirmations"


def pending_confirmation_response(exc: PendingConfirmationError, next_url: str):
    """Risposta a un tentativo bloccato: la proposta di chiudere le pendenti.

    In JSON è un 409 con le partite e l'indirizzo della pagina; altrimenti un
    avviso e il redirect alla pagina, che ricorda dove tornare.
    """
    target = url_for(PENDING_ENDPOINT, next=safe_next_url(next_url))
    if request.is_json or is_ajax_request():
        return (
            jsonify(
                {
                    "success": False,
                    "error": str(exc),
                    "pending_match_ids": exc.match_ids,
                    "redirect": target,
                }
            ),
            409,
        )
    flash(str(exc), "warning")
    return redirect(target)


@individual_match_bp.route("/matches/da_confermare")
@RoleRequirement.player_or_director_required
def pending_confirmations():
    """Le partite che aspettano la firma del giocatore corrente."""
    next_url = safe_next_url(request.args.get("next"))
    matches = PendingConfirmationService.pending_for(current_user.id)
    return render_template(
        "individual_match/pending_confirmations.html",
        matches=matches,
        next_url=next_url,
        # Dove tornano conferma e rifiuto: qui, con lo stesso `next`.
        return_url=url_for(PENDING_ENDPOINT, next=next_url),
    )
