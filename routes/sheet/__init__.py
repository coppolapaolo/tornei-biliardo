"""
Module: routes/sheet/__init__.py
Purpose: Le schede di allenamento — elenco, composizione, sedute, registro.
Requirements: ADR-067 (scheda di allenamento), issue #172

Un blueprint suo, sotto `/schede`, e non una stanza del catalogo esercizi: una
scheda ha un ciclo di vita, delle sedute e dei lettori che il catalogo non ha —
la stessa ragione per cui gli esami stanno per conto loro.
"""

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models.exceptions import DomainError
from models.training_sheet import TrainingSheetService
from models.training_sheet.session_service import TrainingSessionService
from utils.route_helpers import handle_service_action

sheet_bp = Blueprint("sheet", __name__, url_prefix="/schede")


@sheet_bp.route("/")
@login_required
def index():
    """«Le tue schede»: quella che stai facendo, e le altre.

    L'amministratore non si allena (come per «Oggi»): la pagina esiste per lui
    ma non avrà mai niente dentro, e va bene — non è una schermata di gestione.
    """
    schede = TrainingSheetService.sheets_of(current_user.id)
    aperte = {
        scheda.id: TrainingSessionService.open_session(scheda.id, current_user.id)
        for scheda in schede
    }
    ultime = {
        scheda.id: TrainingSessionService.closed_sessions(
            scheda.id, current_user.id, limit=1
        )
        for scheda in schede
    }
    return render_template(
        "sheet/index.html",
        schede=schede,
        aperte=aperte,
        ultime={k: (v[0] if v else None) for k, v in ultime.items()},
    )


@sheet_bp.route("/nuova", methods=["POST"])
@login_required
def create_sheet():
    """Crea una scheda vuota e porta dritti a comporla.

    Il nome si scrive lì dentro, insieme al resto: una pagina intera per
    chiedere solo «come si chiama» è un passo in più fra chi ha deciso di
    cominciare e la prima voce.
    """
    nome = (request.form.get("name") or "").strip() or _("La mia scheda")
    try:
        scheda = TrainingSheetService.create_sheet(current_user, nome)
    except DomainError as errore:
        flash(str(errore), "error")
        return redirect(url_for("sheet.index"))
    return redirect(url_for("sheet.compose", sheet_id=scheda.id))


@sheet_bp.route("/<int:sheet_id>", methods=["GET"])
@login_required
def detail(sheet_id):
    """Il registro: le sedute fatte, voce per voce, e i tre numeri in cima.

    Lo aprono il proprietario e chi ha il permesso di leggere la scheda (D11):
    per l'istruttore **questa** è la pagina — vede come procede, e non può
    toccare niente.
    """
    from models.training_sheet.register_view import build_register

    try:
        sheet = TrainingSheetService.get_sheet(sheet_id)
    except DomainError:
        abort(404)
    if not TrainingSheetService.can_read(sheet, current_user):
        abort(404)

    return render_template(
        "sheet/detail.html",
        sheet=sheet,
        registro=build_register(sheet, sheet.owner_id),
        aperta=TrainingSessionService.open_session(sheet.id, current_user.id),
        can_edit=TrainingSheetService.can_edit(sheet, current_user),
        lettori=TrainingSheetService.readers_of(sheet),
    )


@sheet_bp.route("/<int:sheet_id>/archivia", methods=["POST"])
@login_required
def archive(sheet_id):
    """Toglie la scheda dall'elenco. Le sedute fatte restano."""

    def _archivia():
        return TrainingSheetService.archive_sheet(sheet_id, current_user)

    return handle_service_action(
        _archivia,
        success_message=_("Scheda archiviata."),
        redirect_url=url_for("sheet.index"),
    )


from . import compose, readers, run  # noqa: E402,F401  (registra le route)

__all__ = ["sheet_bp"]
