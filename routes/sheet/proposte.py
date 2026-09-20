"""
Module: routes/sheet/proposte.py
Purpose: le schede che un istruttore ti propone — guardarle, prenderle, dire di no.
Requirements: ADR-071, fase 8d del redesign «TPA ed esercizi», issue #173.

Stanno sotto `/schede` e non sotto `/istruttore` perché sono una cosa che
succede **alle tue schede**: la proposta arriva, e se la prendi diventa una
scheda tua come le altre. L'altro lato — chi propone — sta in
`routes/istruttore.py`.
"""

from flask import abort, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models.exceptions import DomainError
from models.istruttore import AssegnazioneService
from models.training_sheet import amount_label
from utils.route_helpers import handle_service_action

from . import sheet_bp


def _mia_o_404(assignment_id: int):
    """La proposta, se è indirizzata a chi guarda. Altrimenti non esiste."""
    try:
        proposta = AssegnazioneService.get_proposta(assignment_id)
    except DomainError:
        abort(404)
    if proposta.user_id != current_user.id:
        abort(404)
    return proposta


@sheet_bp.route("/proposte/<int:assignment_id>", methods=["GET"])
@login_required
def proposta(assignment_id):
    """La scheda proposta, per esteso: si vede prima di prenderla.

    Una proposta a cui si è già risposto non sparisce in un 404: porta alla
    scheda nata, se è nata. Chi arriva dalla notifica di ieri sera deve
    ritrovarsi dove si aspetta.
    """
    proposta = _mia_o_404(assignment_id)
    if not proposta.is_pending:
        if proposta.sheet_id:
            return redirect(url_for("sheet.detail", sheet_id=proposta.sheet_id))
        return redirect(url_for("sheet.index"))

    return render_template(
        "sheet/proposta.html",
        proposta=proposta,
        modello=proposta.source_sheet,
        # La funzione, e non una property nuova sul modello: «5 tiri» si scrive
        # già in un posto solo (`run_view`), e due copie direbbero la stessa
        # cosa in due modi il giorno che una cambia.
        quanto=amount_label,
    )


@sheet_bp.route("/proposte/<int:assignment_id>/prendi", methods=["POST"])
@login_required
def accetta_proposta(assignment_id):
    """La scheda nasce qui, e nasce tua. Il permesso di lettura è la casella."""
    _mia_o_404(assignment_id)
    apri = request.form.get("apri_lettura") == "1"
    archivia = request.form.get("archivia_promossa") == "1"

    def _accetta():
        return AssegnazioneService.accetta(
            assignment_id,
            current_user,
            apri_lettura=apri,
            archivia_promossa=archivia,
        )

    return handle_service_action(
        _accetta,
        success_message=_("La scheda è tua: componila come vuoi."),
        redirect_url=url_for("sheet.index"),
    )


@sheet_bp.route("/proposte/<int:assignment_id>/rifiuta", methods=["POST"])
@login_required
def rifiuta_proposta(assignment_id):
    """«No, grazie». Non nasce niente, e nessuno legge niente."""
    _mia_o_404(assignment_id)

    return handle_service_action(
        lambda: AssegnazioneService.rifiuta(assignment_id, current_user),
        success_message=_("Proposta rifiutata."),
        redirect_url=url_for("sheet.index"),
    )
