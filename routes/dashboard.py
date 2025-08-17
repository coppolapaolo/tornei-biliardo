from __future__ import annotations
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from models.dashboard.services import DashboardService

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard() -> str:
    """Rotta unica che instrada al wrapper corretto in base al ruolo più alto.
    Priorità: Admin > Director > Player. Supporta ?tournament_id=..."""
    tournament_id = request.args.get("tournament_id", type=int)

    if (
        hasattr(current_user, "is_admin")
        and callable(current_user.is_admin)
        and current_user.is_admin()
    ):
        vm = DashboardService.for_admin()
        return render_template("dashboard/admin.html", vm=vm)

    if (
        hasattr(current_user, "is_director")
        and callable(current_user.is_director)
        and current_user.is_director()
    ):
        vm = DashboardService.for_director(
            current_user.id, selected_tournament_id=tournament_id
        )
        return render_template("dashboard/director.html", vm=vm)

    vm = DashboardService.for_player(
        current_user.id, selected_tournament_id=tournament_id
    )
    return render_template("dashboard/player.html", vm=vm)
