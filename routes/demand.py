"""Route del segnale-domanda → director (ADR-036).

Un giocatore esprime "vorrei una gara nella mia zona". La posizione viene da
GPS effimero (``near_lat``/``near_lng``) o, come fallback, dal centroide della
``home_city`` (ADR-034). Visibilità maturity-gated (ADR-028): in prod
raggiungibile da admin/director nel beta.
"""

from flask import Blueprint, request, redirect, url_for, flash
from flask_babel import gettext as _
from flask_login import login_required, current_user

from models.demand.service import DemandSignalService
from utils.route_helpers import ajax_success, ajax_error, is_ajax_request

demand_bp = Blueprint("demand", __name__)


def _wants_json() -> bool:
    return is_ajax_request() or request.is_json


@demand_bp.route("/signal", methods=["POST"])
@login_required
def create_signal():
    """Crea un segnale di domanda per l'utente corrente."""
    data = request.get_json(silent=True) if request.is_json else request.form
    data = data or {}

    near_lat = data.get("near_lat")
    near_lng = data.get("near_lng")
    city = (data.get("city") or "").strip() or None

    try:
        DemandSignalService.create_signal(
            user_id=current_user.id,
            near_lat=near_lat,
            near_lng=near_lng,
            city=city,
        )
    except ValueError as e:
        if _wants_json():
            return ajax_error(str(e))
        flash(str(e), "warning")
        return redirect(url_for("dashboard.dashboard"))

    msg = _("Fatto! Ti avviseremo se apre una gara nella tua zona.")
    if _wants_json():
        return ajax_success(message=msg)
    flash(msg, "success")
    return redirect(url_for("dashboard.dashboard"))
