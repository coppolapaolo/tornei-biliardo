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
from models.individual_match.pending_confirmation import PendingConfirmationError
from models.individual_match.quick_match_service import QuickMatchService
from models.status_enum import MatchStatus
from models.tpa.engine import GAME_TYPE_BY_DISCIPLINE
from models.tpa.services import FEATURE_CODE as TPA_FEATURE
from models.user.permissions import RoleRequirement

from . import individual_match_bp
from .pending import pending_confirmation_response
from .tpa_choice import open_tpa_referto, wants_referto

logger = logging.getLogger(__name__)


@individual_match_bp.route("/quick", methods=["GET", "POST"])
@RoleRequirement.player_or_director_required
def quick_match():
    """Apri una partita adesso, contro chi hai davanti."""
    if request.method == "GET":
        return _quick_match_form()

    data = request.get_json() if request.is_json else request.form

    opponent_id = _scelta_avversario(data)

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
        "start_rule": data.get("start_rule") or None,
        "description": data.get("description") or None,
    }
    if data.get("is_race_to") is not None:
        config["is_race_to"] = str(data.get("is_race_to")).lower() == "true"

    try:
        match = QuickMatchService.start(current_user.id, opponent_id, config)
    except PendingConfirmationError as exc:
        # Non un errore secco: la proposta di chiudere le partite che aspettano
        # la sua firma, e poi il ritorno qui con lo stesso avversario.
        # Un avversario ancora da creare non ha un id da riportare: si torna
        # al modulo vuoto.
        ritorno = (
            url_for("individual_match.quick_match", opponent_id=opponent_id)
            if isinstance(opponent_id, int)
            else url_for("individual_match.quick_match")
        )
        return pending_confirmation_response(exc, ritorno)
    except DomainError as exc:
        if request.is_json:
            return (
                jsonify({"success": False, "error": str(exc)}),
                http_status_for_exception(exc),
            )
        flash(str(exc), "danger")
        return redirect(url_for("individual_match.quick_match"))

    col_referto = open_tpa_referto(match, wants_referto(data))
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


def _scelta_avversario(data):
    """L'id scelto, oppure nome e cognome di un avversario da creare.

    Sotto la ricerca c'è «Non ha un account? Aggiungilo» (ADR-085,
    emendamento del 2026-10-18): se c'è un id vince l'id, come nel modulo
    della partita di altri due — i due campi restano nel modulo anche quando
    si è cambiato idea e si è cercato. ``0`` se non c'è né l'uno né l'altro.
    """
    from models.individual_match.scored_match_service import NuovoGiocatore

    try:
        opponent_id = int(data.get("opponent_id") or 0)
    except (TypeError, ValueError):
        opponent_id = 0
    if opponent_id:
        return opponent_id
    nome = (data.get("opponent_new_first_name") or "").strip()
    cognome = (data.get("opponent_new_last_name") or "").strip()
    if nome or cognome:
        return NuovoGiocatore(nome, cognome)
    return 0


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
        if QuickMatchService.can_be_opponent(candidate):
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
        if QuickMatchService.can_be_opponent(player)
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
        # Chi può aggiungere un avversario non registrato (ADR-085): direttori
        # e istruttori. Gli altri lo trovano nella ricerca, se c'è già.
        puo_creare_avversario=QuickMatchService.can_create_opponent(current_user),
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
            # La partita di altri due la segna un terzo: non c'è un segnapunti
            # a cui tornare (ADR-084).
            IndividualMatch.scorer_id.is_(None),
            db.or_(
                IndividualMatch.player1_id == current_user.id,
                IndividualMatch.player2_id == current_user.id,
            ),
        )
        .order_by(IndividualMatch.created_at.desc())
        .all()
    )
