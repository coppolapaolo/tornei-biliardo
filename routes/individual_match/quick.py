"""Avvio rapido di una sfida individuale (issue #176).

Due sole schermate: scegli chi hai davanti, e sei al segnapunti. Tutto quello
che il modulo della proposta chiede — quando, dove, come — qui arriva
precompilato da ``QuickMatchService.get_defaults`` e si può cambiare solo se si
vuole davvero.
"""

import logging

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user

from models.exceptions import DomainError, http_status_for_exception
from models.individual_match.quick_match_service import QuickMatchService
from models.status_enum import MatchStatus
from models.tpa.engine import GAME_TYPE_BY_DISCIPLINE
from models.tpa.services import FEATURE_CODE as TPA_FEATURE, TpaRefertoService
from models.user.permissions import RoleRequirement

from . import individual_match_bp

logger = logging.getLogger(__name__)


@individual_match_bp.route("/quick", methods=["GET", "POST"])
@RoleRequirement.player_or_director_required
def quick_match():
    """Apri una partita adesso, contro chi hai davanti."""
    if request.method == "GET":
        return _quick_match_form()

    data = request.get_json() if request.is_json else request.form

    try:
        opponent_id = int(data.get("opponent_id") or 0)
    except (TypeError, ValueError):
        opponent_id = 0

    if not opponent_id:
        message = _("Scegli l'avversario per iniziare.")
        if request.is_json:
            return jsonify({"success": False, "error": message}), 400
        flash(message, "warning")
        return redirect(url_for("individual_match.quick_match"))

    # `None` = «tienti il default»: il servizio riempie i buchi con le
    # abitudini del giocatore. Il modulo manda tutti i campi, ma una chiamata
    # col solo avversario deve restare legittima.
    config = {
        "billiard_hall_id": data.get("billiard_hall_id") or None,
        "location": data.get("location"),
        "discipline": data.get("discipline") or None,
        "match_format": data.get("match_format") or None,
        "distance": data.get("distance") or None,
        "match_distance": data.get("match_distance") or None,
        "break_rule": data.get("break_rule") or None,
    }
    if data.get("is_race_to") is not None:
        config["is_race_to"] = str(data.get("is_race_to")).lower() == "true"

    try:
        match = QuickMatchService.start(current_user.id, opponent_id, config)
    except DomainError as exc:
        if request.is_json:
            return (
                jsonify({"success": False, "error": str(exc)}),
                http_status_for_exception(exc),
            )
        flash(str(exc), "danger")
        return redirect(url_for("individual_match.quick_match"))

    col_referto = _open_tpa_referto(match, _flag(data.get("tpa_referto")))
    destinazione = (
        url_for("individual_match.tpa_referto", match_id=match.id)
        if col_referto
        else url_for("individual_match.match_detail", match_id=match.id)
    )

    if request.is_json:
        return jsonify({"success": True, "match_id": match.id, "url": destinazione})

    flash(
        (
            _("Partita aperta: il referto è tuo.")
            if col_referto
            else _("Partita aperta: segnate pure.")
        ),
        "success",
    )
    return redirect(destinazione)


def _flag(value) -> bool:
    """Una spunta del modulo. Presente e affermativa, o niente."""
    return str(value).lower() in ("1", "true", "on", "yes")


def _open_tpa_referto(match, wanted: bool) -> bool:
    """Il referto scelto nel modulo, aperto subito dopo la partita.

    **Perché qui e non dentro `QuickMatchService.start`**: sono due
    `@transactional` diversi, e annidarli è il modo noto per far tornare
    indietro anche quello esterno (`models/transaction/CLAUDE.md`). La partita
    è già salvata quando arriviamo qui, quindi le due scritture restano
    separate — e separate devono restare anche nell'esito.

    **Perché il rifiuto non ferma la partita**: la disciplina si sceglie nello
    stesso modulo, e a One Pocket il TPA non vuol dire niente. Chi ha spuntato
    la casella su una disciplina che il referto non copre voleva comunque
    giocare: si gioca, senza referto, e il perché sta scritto per esteso sulla
    pagina del referto (`blocking_reason`).

    Lo sblocco lo si controlla qui e non nel servizio perché il gate della
    gamification, per il referto, sta sull'*apertura*: è la stessa regola di
    `@feature_required` su `tpa_open`.
    """
    if not wanted or not current_user.can_access(TPA_FEATURE):
        return False
    try:
        TpaRefertoService.open_referto(match.id, current_user.id)
        return True
    except DomainError as exc:
        logger.info("Referto TPA non aperto all'avvio rapido: %s", exc)
        return False


def _quick_match_form():
    """La schermata di avvio, con i valori già scritti dentro."""
    from models.base import db
    from models.individual_match.statistics_service import (
        IndividualMatchStatisticsService,
    )
    from models.location.models import BilliardHall

    defaults = QuickMatchService.get_defaults(current_user.id)

    # `?opponent_id=`: chi arriva dalla partita appena finita ha gia' risposto
    # alla sola domanda che l'avvio rapido pone.
    preselected = None
    requested_id = request.args.get("opponent_id", type=int)
    if requested_id and requested_id != current_user.id:
        from models.user.models import User

        candidate = db.session.get(User, requested_id)
        if (
            candidate is not None
            and candidate.deleted_at is None
            and candidate.can_access("create_match_direct")
        ):
            preselected = candidate

    # Gli avversari abituali sono la scorciatoia vera: in sala si rigioca quasi
    # sempre con le stesse persone. La ricerca completa resta per gli altri.
    # `can_access` come nell'elenco avversari e nella ricerca: proporre qualcuno
    # che poi il servizio rifiuta sarebbe una porta dipinta sul muro.
    frequent = [
        player
        for player in IndividualMatchStatisticsService.get_frequent_opponents(
            current_user.id, limit=8
        )
        if player.can_access("create_match_direct")
    ][:6]

    verified_venues = (
        BilliardHall.query.filter_by(is_active=True, verified=True)
        .order_by(BilliardHall.name)
        .all()
    )

    # Il preselezionato apre l'elenco, e non ci compare due volte.
    if preselected is not None:
        frequent = [preselected] + [p for p in frequent if p.id != preselected.id]

    # Il referto TPA si chiede **qui** o non si chiede: va aperto prima del
    # primo triangolo, e l'avvio rapido porta dritti al segnapunti. Le
    # discipline che il TPA copre servono alla pagina per far sparire la
    # domanda quando la risposta non vorrebbe dire niente.
    return render_template(
        "individual_match/quick_match.html",
        defaults=defaults,
        preselected_id=preselected.id if preselected else None,
        frequent_opponents=frequent,
        verified_venues=verified_venues,
        in_progress=_own_matches_in_progress(),
        tpa_disponibile=current_user.can_access(TPA_FEATURE),
        tpa_discipline=sorted(GAME_TYPE_BY_DISCIPLINE),
    )


def _own_matches_in_progress():
    """Le partite che questo giocatore sta già giocando.

    Non è un dettaglio decorativo: chi apre l'avvio rapido per la seconda volta
    di solito voleva tornare al segnapunti di prima, non aprirne un altro.
    """
    from models.base import db
    from models.individual_match.models import IndividualMatch

    return (
        IndividualMatch.query.filter(
            IndividualMatch.status == MatchStatus.IN_PROGRESS,
            db.or_(
                IndividualMatch.player1_id == current_user.id,
                IndividualMatch.player2_id == current_user.id,
            ),
        )
        .order_by(IndividualMatch.created_at.desc())
        .all()
    )
