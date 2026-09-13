# utils/card_partita.py
"""I rifiuti e l'evento live comuni agli stepper della card del direttore.

Tre endpoint segnano dalla card — la partita a due (`punteggio_partita`), il
trio (`trio_punteggio`) e il set in corso di una partita a set
(`set_punteggio`) — e devono rifiutare le stesse cose con gli stessi codici:
una partita chiusa si cambia solo con la correzione o dal segnapunti (409),
un turno bloccato non si tocca (409). Nascondere gli stepper non basta: e' la
route che rifiuta (rilievo della revisione automatica sulla PR #349).
"""

from __future__ import annotations

from typing import Optional

from flask import jsonify
from flask_babel import gettext as _

from models.status_enum import MatchStatus


def rifiuto_punteggio_card(match, messaggio_chiusa: Optional[str] = None):
    """La risposta JSON di rifiuto, o `None` se la card puo' segnare."""
    from models.competition.round_manager import AdvancedRoundManager

    if MatchStatus.is_finished(match.status):
        errore = messaggio_chiusa or _(
            "La partita è chiusa: si cambia con «Correggi il risultato»."
        )
        return jsonify({"success": False, "error": str(errore)}), 409
    consentito, motivo = AdvancedRoundManager.can_modify_match(match.id)
    if not consentito:
        return jsonify({"success": False, "error": str(motivo)}), 409
    return None


def rifiuto_del_dominio(errore: Exception):
    """Un rifiuto del servizio in JSON: 409 per un conflitto, 400 altrimenti.

    Le card distinguono solo due casi — «non si puo' piu'» e «punteggio non
    valido» — come `punteggio_partita`: un `ValidationError` qui e' un 400, non
    il 422 della tassonomia generale.
    """
    from models.exceptions import ConflictError

    stato = 409 if isinstance(errore, ConflictError) else 400
    return jsonify({"success": False, "error": str(errore)}), stato


def annuncia_punteggio(match, autore_id: int, **extra) -> None:
    """L'evento live del punteggio, con `autore`.

    La pagina di chi ha toccato lo riceve come tutte, e grazie ad `autore` non
    si ricarica per un fatto che la card ha gia' mostrato. Alla chiusura
    l'evento e' `match_completed`, e li' la pagina si ricarica comunque: il
    tavolo passa a un'altra partita.
    """
    from routes.sse import emit_gara_event

    if not match.gara_id:
        return
    emit_gara_event(
        match.gara_id,
        (
            "match_completed"
            if MatchStatus.is_finished(match.status)
            else "match_updated"
        ),
        {
            "match_id": match.id,
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "winner_id": match.winner_id,
            "autore": autore_id,
            **extra,
        },
    )


__all__ = ["annuncia_punteggio", "rifiuto_del_dominio", "rifiuto_punteggio_card"]
