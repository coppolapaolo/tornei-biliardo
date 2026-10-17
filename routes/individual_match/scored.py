"""La partita di altri due, segnata da un istruttore o da un direttore (ADR-084).

Una schermata, sul modello dell'avvio rapido: chi sono i due giocatori, che
partita è, come si gioca. La partita nasce in corso, col referto aperto, e si
arriva dritti al referto.

**L'admin.** Le sfide individuali sono chiuse all'admin
(`RoleRequirement.player_or_director_required`): l'admin non gioca. Segnare la
partita di altri due però non è giocare, e l'admin ha i poteri del direttore.
`player_director_or_scorer` apre a lui **solo** le route della partita che sta
segnando, e quelle per crearne una.
"""

from __future__ import annotations

import logging
from functools import wraps

from flask import abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user

from models.base import db
from models.exceptions import DomainError
from models.individual_match.scored_match_service import ScoredMatchService
from models.tpa.engine import GAME_TYPE_BY_DISCIPLINE

from . import individual_match_bp

logger = logging.getLogger(__name__)


def player_director_or_scorer(f):
    """Come `player_or_director_required`, più l'admin che segna (ADR-084).

    Con ``match_id`` nella route l'admin passa se è lo scorer di quella
    partita; senza, se può segnare (cioè sempre: è admin). Gli altri controlli
    — chi è giocatore, chi tiene il referto — restano dove sono, nelle route e
    nei servizi.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(403)
        if not current_user.is_admin:
            if not (current_user.is_player or current_user.is_director):
                abort(403)
            return f(*args, **kwargs)

        match_id = kwargs.get("match_id")
        if match_id is None:
            if ScoredMatchService.can_score(current_user):
                return f(*args, **kwargs)
            abort(403)

        from models import IndividualMatch

        match = db.session.get(IndividualMatch, match_id)
        if match is not None and match.scorer_id == current_user.id:
            return f(*args, **kwargs)
        abort(403)

    return decorated_function


@individual_match_bp.route("/scored", methods=["GET", "POST"])
@player_director_or_scorer
def scored_match():
    """Segna la partita di altri due: il modulo, e la partita che nasce."""
    if not ScoredMatchService.can_score(current_user):
        flash(
            _("La partita di altri due la segnano istruttori e direttori."),
            "warning",
        )
        return redirect(url_for("individual_match.dashboard"))

    if request.method == "GET":
        return _form()

    data = request.form
    config = {
        "location": data.get("location"),
        "discipline": data.get("discipline") or None,
        "match_format": data.get("match_format") or None,
        "distance": data.get("distance") or None,
        "break_rule": data.get("break_rule") or None,
        "start_rule": data.get("start_rule") or None,
        "description": data.get("description") or None,
    }
    if data.get("is_race_to") is not None:
        config["is_race_to"] = str(data.get("is_race_to")).lower() == "true"

    try:
        match = ScoredMatchService.start(
            current_user,
            data.get("player1_id"),
            data.get("player2_id"),
            config,
        )
    except DomainError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("individual_match.scored_match"))

    flash(_("Partita aperta: il referto è tuo."), "success")
    return redirect(url_for("individual_match.tpa_referto", match_id=match.id))


def _form():
    from models.individual_match.quick_match_service import QuickMatchService

    defaults = dict(QuickMatchService.SYSTEM_DEFAULTS)
    from models.status_enum import Discipline

    discipline_tpa = [
        (value, label)
        for value, label in Discipline.get_choices()
        if value in GAME_TYPE_BY_DISCIPLINE
    ]
    return render_template(
        "individual_match/scored_match.html",
        defaults=defaults,
        discipline_tpa=discipline_tpa,
    )
