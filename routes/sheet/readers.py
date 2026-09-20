"""
Module: routes/sheet/readers.py
Purpose: chi legge una scheda, e chi legge le mie schede (ADR-069, issue #173).

Due pagine, che sono la stessa tabella guardata dai due lati: «Chi la legge»
sta su una scheda, «I miei istruttori» su tutte. Nessun elenco a parte da
tenere in pari — un istruttore compare perché gli è stata aperta una scheda.
"""

from flask import abort, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models.exceptions import DomainError
from models.istruttore import cerca_istruttori, istruttori_di
from models.training_sheet import TrainingSheetService
from utils.route_helpers import handle_service_action

from . import sheet_bp


def _scheda_da_comporre(sheet_id: int):
    """La scheda, se è di chi sta guardando. Altrimenti 404.

    404 e non 403: chi non la possiede non deve nemmeno sapere che esiste una
    pagina dei lettori per quella scheda.
    """
    try:
        sheet = TrainingSheetService.get_sheet(sheet_id)
    except DomainError:
        abort(404)
    if not TrainingSheetService.can_edit(sheet, current_user):
        abort(404)
    return sheet


@sheet_bp.route("/<int:sheet_id>/lettori", methods=["GET"])
@login_required
def readers(sheet_id):
    """«Chi la legge»: i lettori di questa scheda, e come aggiungerne uno."""
    sheet = _scheda_da_comporre(sheet_id)
    lettori = TrainingSheetService.readers_of(sheet)

    # La ricerca vive dentro la pagina e non dietro una chiamata JS: un foglio
    # che si apre già con i risultati dentro è una cosa in meno che può non
    # rispondere, e qui non c'è niente da aggiornare sotto le dita.
    cercato = request.args.get("cerca")
    trovati = (
        cerca_istruttori(
            cercato, escludi={r.user_id for r in lettori} | {sheet.owner_id}
        )
        if cercato is not None
        else []
    )

    return render_template(
        "sheet/readers.html",
        sheet=sheet,
        lettori=lettori,
        cercato=cercato,
        trovati=trovati,
    )


@sheet_bp.route("/<int:sheet_id>/lettori/aggiungi", methods=["POST"])
@login_required
def add_reader(sheet_id):
    """Apre la scheda a un istruttore. Vale subito (D18)."""
    _scheda_da_comporre(sheet_id)
    user_id = request.form.get("user_id", type=int) or 0

    return handle_service_action(
        lambda: TrainingSheetService.add_reader(sheet_id, user_id, current_user),
        success_message=_("Adesso legge questa scheda."),
        redirect_url=url_for("sheet.readers", sheet_id=sheet_id),
    )


@sheet_bp.route("/<int:sheet_id>/lettori/togli", methods=["POST"])
@login_required
def remove_reader(sheet_id):
    """Toglie il permesso. Le altre schede non cambiano."""
    _scheda_da_comporre(sheet_id)
    user_id = request.form.get("user_id", type=int) or 0

    return handle_service_action(
        lambda: TrainingSheetService.remove_reader(sheet_id, user_id, current_user),
        success_message=_("Non legge più questa scheda."),
        redirect_url=url_for("sheet.readers", sheet_id=sheet_id),
    )


@sheet_bp.route("/<int:sheet_id>/note-condivise", methods=["POST"])
@login_required
def toggle_notes_shared(sheet_id):
    """Apre o richiude le note delle sedute a chi legge la scheda."""
    sheet = _scheda_da_comporre(sheet_id)
    aperte = request.form.get("shared") == "1"

    return handle_service_action(
        lambda: TrainingSheetService.set_notes_shared(sheet.id, current_user, aperte),
        success_message=(
            _("Adesso chi legge vede anche le note.")
            if aperte
            else _("Le note tornano tue.")
        ),
        redirect_url=url_for("sheet.readers", sheet_id=sheet_id),
    )


@sheet_bp.route("/<int:sheet_id>/lettori/esci", methods=["POST"])
@login_required
def leave_sheet(sheet_id):
    """L'istruttore smette di seguire questa scheda."""
    return handle_service_action(
        lambda: TrainingSheetService.leave_sheet(sheet_id, current_user),
        success_message=_("Non leggi più questa scheda."),
        redirect_url=url_for("sheet.my_instructors"),
    )


@sheet_bp.route("/istruttori", methods=["GET"])
@login_required
def my_instructors():
    """«I miei istruttori»: chi legge cosa, in un colpo solo.

    Non è un elenco a parte: si ricava dalle schede, e per questo mostra anche
    quelle che non legge nessuno — è lì che si va per cambiare idea.
    """
    schede = TrainingSheetService.sheets_of(current_user.id)
    legami = istruttori_di(current_user.id)
    lette = {s.id for legame in legami for s in legame.schede}

    return render_template(
        "sheet/instructors.html",
        legami=legami,
        sole=[s for s in schede if s.id not in lette],
    )
