"""
MatchValidationService: Validates match results and completes with table reassignment.

Extracted from routes/admin/match/scoring.py to eliminate manual
db.session.commit()/rollback() in route handlers (Technical Debt Round 4 P1).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from models.base import db
from models.status_enum import MatchStatus
from models.transaction.manager import transactional
from .models import Match


class MatchValidationService:
    """Validates match results and orchestrates completion + table reassignment."""

    @staticmethod
    @transactional(domain="match")
    def validate_and_complete(match_id: int) -> Dict[str, Any]:
        """Validate match result and complete with table reassignment.

        Performs all 6 operations atomically:
        1. Auto-determine winner if needed
        2. Set validated_by_admin = True
        3. Transition to completed
        4. Release table assignment
        5. Reassign table to waiting match (+ transition to playing)
        6. Update round progression

        Returns:
            Dict with match data needed for SSE events.

        Raises:
            ValueError: If match not found, already completed, or not ready.
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        # Check match is not already completed
        if match.status in [MatchStatus.COMPLETED.value, MatchStatus.VALIDATED.value]:
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

        # 1. Set admin validation
        match.validated_by_admin = True

        # 2. Transition to completed (nested savepoint)
        from .match_service import MatchService

        MatchService.to_completed(match_id)

        # 3. Handle table reassignment
        waiting_match_id: Optional[int] = None
        old_table = match.table_assignment
        if old_table:
            match.table_assignment = None

            from .table_assignment_service import TableAssignmentService

            waiting_match = TableAssignmentService.release_and_reassign_table(
                match_id
            )

            if waiting_match and waiting_match.status != MatchStatus.PLAYING.value:
                try:
                    MatchService.to_playing(waiting_match.id)
                except Exception:
                    pass  # Table assignment succeeded regardless

                waiting_match_id = waiting_match.id

        # 4. Update round progression
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
