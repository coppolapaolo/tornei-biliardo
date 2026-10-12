# routes/admin/preset.py
"""I preset dei direttori: salvarli dai moduli, e rileggerli per precompilare.

Tre route, tutte in JSON per il JavaScript del modulo (`preset_modulo.js`):

* «Salva come preset» da un modulo della gara, così com'è sullo schermo;
* «Salva come preset» da una gara che esiste già;
* i valori di un preset, da scrivere nei campi («Parti da un preset»).

Il modulo passa dal parser di sempre (`GaraFormParser`): il preset conserva
ciò che la gara riceverebbe salvando, non ciò che c'è scritto nei campi.
Applicarlo, invece, non salva niente: scrive nei campi, e al salvataggio
della gara valgono le validazioni di sempre (ADR-082).
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, current_app, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models import Campionato, Gara, db
from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
    http_status_for_exception,
)
from models.preset import payload as formato
from models.preset.models import TipoPreset
from models.preset.service import ConfigPresetService
from utils import director_or_admin_required
from utils.route_helpers import ajax_error, ajax_success

preset_bp = Blueprint("preset", __name__)


def _risposta_di_errore(errore: Exception):
    """Un rifiuto del dominio diventa il suo codice; il conflitto lo dice."""
    if isinstance(errore, ConflictError):
        return jsonify({"success": False, "error": str(errore), "conflitto": True}), 409
    return ajax_error(str(errore), http_status_for_exception(errore))


def _contesto():
    """Il campionato o la gara del modulo da cui si salva, se ci sono.

    Servono a leggere il modulo come lo leggerebbe la route di quel modulo:
    dentro un campionato i valori ereditati diventano espliciti.
    """
    from models.user.permissions import PermissionChecker

    gara = campionato = None
    gara_id = request.form.get("preset_gara_id", type=int)
    campionato_id = request.form.get("preset_campionato_id", type=int)
    if gara_id:
        gara = db.session.get(Gara, gara_id)
        if gara is None or not PermissionChecker.can_manage_competition(
            current_user, gara_id
        ):
            raise NotFoundError(_("Questa gara non esiste."))
        campionato = gara.campionato
    elif campionato_id:
        campionato = db.session.get(Campionato, campionato_id)
        if campionato is None or not PermissionChecker.can_manage_campionato(
            current_user, campionato_id
        ):
            raise NotFoundError(_("Questo campionato non esiste."))
    return campionato, gara


def _campi_dal_modulo_della_gara(campionato, gara) -> dict:
    """Il modulo letto dal parser della gara, senza ciò che il preset non tiene.

    Data e ora non entrano nel preset, ma il parser le pretende: al loro posto
    se ne mettono due qualsiasi, così un modulo con la data ancora vuota si
    salva lo stesso.
    """
    from routes.admin.competition.form_parser import GaraFormParser

    modulo = request.form.copy()
    modulo["date"] = date.today().isoformat()
    modulo["time"] = "20:00"
    modulo.setdefault("discipline", "")
    try:
        with current_app.test_request_context(method="POST", data=modulo):
            dati = GaraFormParser(campionato=campionato, gara=gara).parse()
    except KeyError:
        raise ValidationError(
            _("Scegli almeno disciplina e distanza prima di salvare il preset.")
        )
    return formato.esplicita(dati, campionato)


@preset_bp.route("/gara/dal-modulo", methods=["POST"])
@login_required
@director_or_admin_required
def salva_dal_modulo_gara():
    """«Salva come preset» dal modulo della gara: singola, nuova gara, modifica."""
    from models.categoria.listino import leggi_dal_modulo

    try:
        campionato, gara = _contesto()
        campi = _campi_dal_modulo_della_gara(campionato, gara)
        # Il listino è della gara singola; dentro un campionato è del campionato.
        listino = None if campionato is not None else leggi_dal_modulo(request.form)
        preset = ConfigPresetService.salva(
            current_user,
            request.form.get("preset_nome"),
            TipoPreset.GARA,
            campi,
            listino,
            sostituisci=request.form.get("preset_sostituisci") == "1",
        )
    except (ConflictError, NotFoundError, PermissionDeniedError) as errore:
        return _risposta_di_errore(errore)
    except ValueError as errore:
        return ajax_error(str(errore), 422)
    return ajax_success(
        _("Preset «%(nome)s» salvato.", nome=preset.name),
        {"preset": {"id": preset.id, "nome": preset.name}},
    )


@preset_bp.route("/gara/da/<int:gara_id>", methods=["POST"])
@login_required
@director_or_admin_required
def salva_dalla_gara(gara_id: int):
    """«Salva come preset» dalla pagina di una gara che esiste già."""
    from models.user.permissions import PermissionChecker

    gara = db.session.get(Gara, gara_id)
    if gara is None or not PermissionChecker.can_manage_competition(
        current_user, gara_id
    ):
        return ajax_error(_("Questa gara non esiste."), 404)
    try:
        preset = ConfigPresetService.salva_dalla_gara(
            current_user,
            request.form.get("preset_nome"),
            gara,
            sostituisci=request.form.get("preset_sostituisci") == "1",
        )
    except (ConflictError, NotFoundError, PermissionDeniedError) as errore:
        return _risposta_di_errore(errore)
    except ValueError as errore:
        return ajax_error(str(errore), 422)
    return ajax_success(
        _("Preset «%(nome)s» salvato.", nome=preset.name),
        {"preset": {"id": preset.id, "nome": preset.name}},
    )


@preset_bp.route("/<int:preset_id>/valori")
@login_required
@director_or_admin_required
def valori_per_il_modulo(preset_id: int):
    """I valori di un preset, da scrivere nei campi del modulo."""
    try:
        dati = ConfigPresetService.per_il_modulo(preset_id, current_user)
    except (NotFoundError, PermissionDeniedError) as errore:
        return _risposta_di_errore(errore)
    return ajax_success(data=dati)
