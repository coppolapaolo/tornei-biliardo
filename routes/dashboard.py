from __future__ import annotations
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from models.dashboard.services import DashboardService
from models.base import db

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard() -> str:
    """Rotta unica che instrada al wrapper corretto in base al ruolo più alto.
    Priorità: Admin > Director > Player. Supporta ?tournament_id=..."""
    tournament_id = request.args.get("tournament_id", type=int)
    prova_id = request.args.get("prova_id", type=int)

    # Regola difensiva se arrivano entrambi:
    # - se prova è standalone, consideriamo quella e ignoriamo il torneo
    # - se prova NON è standalone, usiamo il suo tournament_id (se non presente)
    if tournament_id and prova_id:
        from models.competition.models import Prova
        p = db.session.get(Prova, prova_id)
        if p is not None:
            if p.tournament_id is None:
                tournament_id = None  # standalone: mostra come prova
            else:
                # prova di torneo: ignora prova, forza tournament_id se manca
                prova_id = None
                tournament_id = tournament_id or p.tournament_id

    if getattr(current_user, "is_admin", False):
        vm = DashboardService.for_admin()
        return render_template("dashboard/admin.html", vm=vm)

    if getattr(current_user, "is_director", False):
        vm = DashboardService.for_director(
            current_user.id,
            selected_tournament_id=tournament_id,
            selected_prova_id=prova_id,
        )
        return render_template("dashboard/director.html", vm=vm)

    vm = DashboardService.for_player(
        current_user.id,
        selected_tournament_id=tournament_id,
        selected_prova_id=prova_id,
    )
    return render_template("dashboard/player.html", vm=vm)
