"""
MatchValidationService: Validates match results and completes with table reassignment.

Extracted from routes/admin/match/scoring.py to eliminate manual
db.session.commit()/rollback() in route handlers (Technical Debt Round 4 P1).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from models.base import db
from models.status_enum import MatchStatus
from models.transaction.manager import transactional
from .models import Match

logger = logging.getLogger(__name__)


class MatchValidationService:
    """Validates match results and orchestrates completion + table reassignment."""

    @staticmethod
    @transactional(domain="match")
    def validate_and_complete(match_id: int) -> Dict[str, Any]:
        """Validate match result and complete with table reassignment.

        Performs all 5 operations atomically:
        1. Auto-determine winner if needed
        2. Transition to completed — *è* la registrazione della validazione
        3. Release table assignment
        4. Reassign table to waiting match (+ transition to playing)
        5. Update round progression

        Returns:
            Dict with match data needed for SSE events.

        Raises:
            ValueError: If match not found, already completed, or not ready.
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        # Check match is not already completed (predicato typo-safe, CLAUDE.md)
        if MatchStatus.is_finished(match.status):
            raise ValueError("Il match è già stato completato")

        # Check distance is reached (works for both 1v1 and trio)
        if not match.is_at_distance:
            raise ValueError("Il match non ha ancora raggiunto la distanza")

        # Auto-determine winner if not set
        if not match.winner_id:

            if match.player1_score > match.player2_score:
                match.winner_id = match.player1_id
            elif match.player2_score > match.player1_score:
                match.winner_id = match.player2_id
            # else: Draw — winner_id remains NULL (allowed)

        # 1. Transitare a COMPLETED **è** la validazione del direttore: è lo
        #    stato a distinguere una partita chiusa da lui (non più
        #    annullabile dai giocatori) da una chiusa dalla doppia conferma,
        #    ed è già così che ragiona
        #    `ScoringService.remove_rack_for_player`.
        #
        #    Qui c'era anche `match.validated_by_admin = True`, un attributo
        #    che su `Match` non esiste — vive su `Rack` — e che serviva solo a
        #    farsi rileggere da `to_completed` col `getattr`. Ora quel
        #    permesso è un parametro dichiarato: la partita potrebbe non
        #    essere mai partita (nessun tavolo → PENDING) e chiuderla resta
        #    una facoltà del direttore.
        from .match_service import MatchService

        MatchService.to_completed(match_id, closed_by_director=True)

        # 2. Handle table reassignment
        waiting_match_id: Optional[int] = None
        old_table = match.table_assignment
        if old_table:
            match.table_assignment = None

            from .table_assignment_service import TableAssignmentService

            waiting_match = TableAssignmentService.release_and_reassign_table(match_id)

            if waiting_match:
                # L'id si riporta sempre, anche se la partita era già PLAYING:
                # serve al chiamante per l'evento SSE che fa aggiornare la
                # pagina della gara. Stava dentro il ramo qui sotto, quindi
                # nel caso "aveva già lo stato giusto" il tavolo cambiava
                # senza che nessuno schermo se ne accorgesse.
                waiting_match_id = waiting_match.id

                if waiting_match.status != MatchStatus.PLAYING.value:
                    try:
                        MatchService.to_playing(waiting_match.id)
                    except Exception:
                        # L'assegnazione del tavolo è comunque riuscita e non
                        # va annullata: la partita successiva ha dove
                        # giocarsi. Ma un `pass` muto qui lascerebbe una
                        # partita con un tavolo e lo stato sbagliato senza
                        # traccia da nessuna parte — a livello ERROR l'evento
                        # arriva a GlitchTip (decisione 2026-06-10).
                        logger.error(
                            "Transizione a PLAYING fallita per il match %s dopo "
                            "il riassegnamento del tavolo: resta con lo stato "
                            "precedente",
                            waiting_match.id,
                            exc_info=True,
                        )

        # 3. Update round progression
        if match.gara_id:
            from models.competition.round_service import RoundService

            RoundService.update_round_progression(match.gara_id)

        return {
            "match_id": match_id,
            "winner_id": match.winner_id,
            "gara_id": match.gara_id,
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "waiting_match_id": waiting_match_id,
        }
