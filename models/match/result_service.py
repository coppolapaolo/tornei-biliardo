"""
MatchResultService: Match result validation and submission.

Split from services.py for maintainability (Round 3 P4).
"""

from __future__ import annotations

from typing import Optional

from models.base import db
from .models import Match
from models.transaction.manager import transactional


class MatchResultService:
    """Placeholder per gestione risultati/validazioni match."""

    @staticmethod
    @transactional(domain="match")
    def validate_by_admin(match_id: int) -> Match:
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")
        if hasattr(match, "validated_by_admin"):
            match.validated_by_admin = True
            db.session.add(match)
        return match

    @staticmethod
    @transactional(domain="match")
    def submit_result(match_id: int, winner_id: int) -> Match:
        """
        Imposta il vincitore del match e porta lo stato a 'completed'
        tramite la state machine.
        Non tocca Trio né logiche rack: è il percorso 'set result' da form.
        """
        match: Optional[Match] = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        # winner deve appartenere al match (2-players match)
        if winner_id not in (match.player1_id, match.player2_id):
            raise ValueError("winner_id non appartiene ai giocatori del match")

        # set vincitore
        match.winner_id = winner_id
        db.session.add(match)

        # transizione centralizzata
        from .match_service import MatchService

        MatchService.to_completed(match.id)

        # ricarica o restituisci l'oggetto aggiornato
        return match
