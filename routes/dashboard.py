from __future__ import annotations
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from models.dashboard.services import DashboardService
from models.competition.services import GaraService

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard() -> str:
    """Rotta unica che instrada al wrapper corretto in base al ruolo più alto.
    Priorità: Admin > Director > Player. Supporta ?campionato_id=..."""
    campionato_id = request.args.get("campionato_id", type=int)
    gara_id = request.args.get("gara_id", type=int)

    # Regola difensiva se arrivano entrambi:
    # - se gara è standalone, consideriamo quella e ignoriamo il campionato
    # - se gara NON è standalone, usiamo il suo campionato_id (se non presente)
    if campionato_id and gara_id:
        # Use service layer instead of direct database access
        p = GaraService.get_gara_by_id(gara_id)
        if p is not None:
            if p.campionato_id is None:
                campionato_id = None  # standalone: mostra come gara
            else:
                # gara di campionato: ignora gara, forza campionato_id se manca
                gara_id = None
                campionato_id = campionato_id or p.campionato_id

    if getattr(current_user, "is_admin", False):
        vm = DashboardService.for_admin()
        return render_template("dashboard/admin.html", vm=vm)

    if getattr(current_user, "is_director", False):
        vm = DashboardService.for_director(
            current_user.id,
            selected_campionato_id=campionato_id,
            selected_gara_id=gara_id,
        )
        return render_template("dashboard/director.html", vm=vm)

    vm = DashboardService.for_player(
        current_user.id,
        selected_campionato_id=campionato_id,
        selected_gara_id=gara_id,
    )
    return render_template("dashboard/player.html", vm=vm)
