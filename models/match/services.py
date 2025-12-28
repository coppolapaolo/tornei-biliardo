"""
Module: models/match/services
Purpose: Service layer per il dominio Match (Match, Rack, MatchResult, TrioMatch)
         + state machine centralizzata per gli stati del Match.
Data Structures: MatchService, RackService, MatchResultService
Dependencies: models.base.db, models.match.models, models.status_enum

Nota sprint 4: aggiunte API di transizione di stato; preservati nomi/classi esistenti
per compatibilità con i test di separazione.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from models.orchestration.service import OperationResult

from models.base import db
from models.status_enum import MatchStatus
from .models import Match, Rack, TrioMatch
from models.transaction.manager import transactional

from models.exceptions import InvalidTransitionError


class MatchService:
    """Operazioni di business sui Match + state machine facade."""

    # -----------------------------
    # CREAZIONE / QUERY DI SUPPORTO
    # -----------------------------
    @staticmethod
    @transactional(domain="match")
    def create_match(
        gara_id: int,
        round_number: int,
        player1_id: int,
        player2_id: Optional[int] = None,
        is_bye: bool = False,
    ) -> Match:
        """Crea un match. Imposta lo stato iniziale a 'pending'."""
        # Get gara to fetch the distance
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        match = Match(
            gara_id=gara_id,
            round_number=round_number,
            player1_id=player1_id,
            player2_id=player2_id,
            is_bye=is_bye,
            status=MatchStatus.PENDING.value,
            match_distance=gara.distance,
        )
        db.session.add(match)
        return match

    @staticmethod
    def get_matches_by_gara(gara_id: int) -> List[Match]:
        return Match.query.filter_by(gara_id=gara_id).all()

    @staticmethod
    @transactional(domain="match")
    def create_trio_match(match_id: int, player3_id: int) -> TrioMatch:
        """Crea l'entità TrioMatch e marca il match come trio (compat)."""
        trio = TrioMatch(match_id=match_id, waiting_player_id=player3_id)
        db.session.add(trio)
        match = db.session.get(Match, match_id)
        if match is not None:
            match.is_trio = True  # compat con modello esistente
            db.session.add(match)
        return trio

    # -----------------------------
    # STATE MACHINE FACADE
    # Delegates to MatchStateService
    # -----------------------------
    @staticmethod
    @transactional(domain="match")
    def to_playing(match_id: int) -> Match:
        """pending/completed → playing (delegates to MatchStateService)."""
        from .state_service import MatchStateService

        return MatchStateService.to_playing(match_id)

    @staticmethod
    @transactional(domain="match")
    def to_completed(match_id: int) -> Match:
        """playing → completed (delegates to MatchStateService)."""
        from .state_service import MatchStateService

        return MatchStateService.to_completed(match_id)

    @staticmethod
    def reset_to_pending(
        match_id: int, clear_validation: bool = True
    ) -> "OperationResult":
        """DEPRECATED: Use RackService.reset_match_complete() instead."""
        from .state_service import MatchStateService

        return MatchStateService.reset_to_pending(match_id, clear_validation)

    @staticmethod
    def add_rack_to_completed_match(
        match_id: int,
        rack_number: int,
        winner_id: int,
        modifier_id: int,
    ) -> "OperationResult":
        """
        Add a rack to a completed match (admin function).

        Args:
            match_id: ID of the match
            rack_number: Rack number to add
            winner_id: ID of the winner of this rack
            modifier_id: ID of the admin making the modification

        Returns:
            OperationResult indicating success or failure
        """
        from models.orchestration.service import OperationResult, OperationType

        match = db.session.get(Match, match_id)
        if not match:
            return OperationResult(
                success=False,
                operation_type=OperationType.RESULT_PROCESSING,
                data={},
                errors=["Match not found"],
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["match"],
            )

        # Check if match is locked
        if match.is_locked or match.round_locked:
            return OperationResult(
                success=False,
                operation_type=OperationType.RESULT_PROCESSING,
                data={},
                errors=["Match is locked and cannot be modified"],
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["match"],
            )

        # Add the rack
        try:
            RackService.add_rack_result(
                match_id=match_id,
                rack_number=rack_number,
                winner_id=winner_id,
                reported_by_id=modifier_id,
                validated_by_admin=True,
                admin_note=f"Added by admin {modifier_id}",
            )

            return OperationResult.success_result(
                operation_type=OperationType.RESULT_PROCESSING,
                data={
                    "match_id": match_id,
                    "rack_number": rack_number,
                    "winner_id": winner_id,
                    "modifier_id": modifier_id,
                },
                execution_time_ms=0.0,
                affected_domains=["match"],
            )

        except Exception as e:
            return OperationResult(
                success=False,
                operation_type=OperationType.RESULT_PROCESSING,
                data={},
                errors=[str(e)],
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["match"],
            )

    @staticmethod
    @transactional(domain="match")
    def admin_unlock_match(
        match_id: int,
        admin_id: int,
        unlock_reason: str,
    ) -> "OperationResult":
        """
        Admin override to unlock a match for modifications.

        Args:
            match_id: ID of the match to unlock
            admin_id: ID of the admin performing the unlock
            unlock_reason: Reason for unlocking

        Returns:
            OperationResult indicating success or failure
        """
        from models.orchestration.service import OperationResult, OperationType

        match = db.session.get(Match, match_id)
        if not match:
            return OperationResult(
                success=False,
                operation_type=OperationType.RESULT_PROCESSING,
                data={},
                errors=["Match not found"],
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["match"],
            )

        # Unlock the match
        match.is_locked = False
        match.round_locked = False
        db.session.add(match)

        return OperationResult.success_result(
            operation_type=OperationType.RESULT_PROCESSING,
            data={
                "match_id": match_id,
                "admin_id": admin_id,
                "unlock_reason": unlock_reason,
                "was_locked": True,
            },
            execution_time_ms=0.0,
            affected_domains=["match"],
        )

    @staticmethod
    def apply_batch_corrections(
        gara_id: int,
        corrections: List[Dict[str, Any]],
        admin_id: int,
    ) -> "OperationResult":
        """
        Apply batch corrections to multiple matches.

        Args:
            gara_id: ID of the tournament
            corrections: List of correction dictionaries
            admin_id: ID of the admin performing corrections

        Returns:
            OperationResult with batch correction results
        """
        from models.orchestration.service import OperationResult, OperationType

        results = []
        errors = []

        for correction in corrections:
            try:
                match_id = correction["match_id"]
                correction_type = correction["correction_type"]
                new_winner_score = correction["new_winner_score"]
                new_loser_score = correction["new_loser_score"]
                reason = correction.get("reason", "Batch correction")

                match = db.session.get(Match, match_id)
                if not match:
                    error_msg = f"Match {match_id} not found"
                    errors.append(error_msg)
                    results.append(
                        {
                            "match_id": match_id,
                            "success": False,
                            "error": error_msg,
                        }
                    )
                    continue

                if match.gara_id != gara_id:
                    error_msg = (
                        f"Match {match_id} does not belong to specified tournament"
                    )
                    errors.append(error_msg)
                    results.append(
                        {
                            "match_id": match_id,
                            "success": False,
                            "error": error_msg,
                        }
                    )
                    continue

                # Apply score correction
                if correction_type == "score_adjustment":
                    # Use existing method to set the result
                    RackService.set_match_result_direct(
                        match_id=match_id,
                        player1_score=new_winner_score,
                        player2_score=new_loser_score,
                    )

                    results.append(
                        {
                            "match_id": match_id,
                            "success": True,
                            "correction_type": correction_type,
                            "new_scores": {
                                "winner": new_winner_score,
                                "loser": new_loser_score,
                            },
                            "reason": reason,
                            "admin_id": admin_id,
                        }
                    )

            except Exception as e:
                error_msg = str(e)
                errors.append(error_msg)
                results.append(
                    {
                        "match_id": correction.get("match_id", "unknown"),
                        "success": False,
                        "error": error_msg,
                    }
                )

        # Determine overall success
        overall_success = len(errors) == 0

        if overall_success:
            return OperationResult.success_result(
                operation_type=OperationType.RESULT_PROCESSING,
                data={
                    "corrections_applied": len(results),
                    "results": results,
                    "admin_id": admin_id,
                },
                execution_time_ms=0.0,
                affected_domains=["match", "competition"],
            )
        else:
            return OperationResult(
                success=False,
                operation_type=OperationType.RESULT_PROCESSING,
                data={"results": results},
                errors=errors,
                warnings=[],
                execution_time_ms=0.0,
                affected_domains=["match", "competition"],
            )

    # ---------------------------------------
    # SIMPLIFIED UX - Delegates to ScoringService
    # ---------------------------------------
    @staticmethod
    @transactional(domain="match")
    def add_rack_for_player(
        match_id: int, user_id: int, winner_id: int
    ) -> Rack:
        """Add a rack won by specified player (delegates to ScoringService)."""
        from .scoring_service import ScoringService

        return ScoringService.add_rack_for_player(match_id, user_id, winner_id)

    @staticmethod
    @transactional(domain="match")
    def remove_rack_for_player(
        match_id: int, user_id: int, player_id: int
    ) -> None:
        """Remove last rack won by specified player (delegates to ScoringService)."""
        from .scoring_service import ScoringService

        return ScoringService.remove_rack_for_player(match_id, user_id, player_id)

    @staticmethod
    @transactional(domain="match")
    def confirm_match_result(match_id: int, user_id: int) -> Match:
        """
        Confirm match result by a player (new UX).

        Uses BaseMatchMixin.confirm_result() method.
        When both players confirm, the match is completed and table is reassigned.

        Args:
            match_id: ID of the match
            user_id: ID of player confirming

        Returns:
            The updated Match object

        Raises:
            ValueError: If user not in match or match not ready
        """
        match = db.session.get(Match, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if not match.is_ready_for_validation():
            raise ValueError("Match is not ready for validation")

        # confirm_result returns True if match is now completed (both confirmed)
        is_completed = match.confirm_result(user_id)

        # Se il match è completato, libera e riassegna il tavolo
        if is_completed and match.table_assignment:
            from models.match.table_assignment_service import TableAssignmentService
            TableAssignmentService.release_and_reassign_table(match.id)
            # Sincronizza l'oggetto match locale
            match.table_assignment = None

        return match

    @staticmethod
    @transactional(domain="match")
    def reject_match_result(match_id: int, user_id: int) -> Match:
        """
        Reject match result - removes last rack (new UX).

        Uses BaseMatchMixin.reject_result() method.

        Args:
            match_id: ID of the match
            user_id: ID of player rejecting

        Returns:
            The updated Match object

        Raises:
            ValueError: If user not in match or match not ready
        """
        match = db.session.get(Match, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if not match.is_ready_for_validation():
            raise ValueError("Match is not ready for validation")

        match.reject_result(user_id)
        return match

    @staticmethod
    @transactional(domain="match")
    def forfeit_match(match_id: int, user_id: int) -> Match:
        """Forfeit match (delegates to ScoringService)."""
        from .scoring_service import ScoringService

        return ScoringService.forfeit_match(match_id, user_id)


class RackService:
    """Service per gestione rack con business logic completa."""

    @staticmethod
    @transactional(domain="match")
    def add_rack_result(
        match_id: int,
        rack_number: int,
        winner_id: int,
        reported_by_id: int,
        *,
        confirmed_by_player: bool = False,
        validated_by_admin: bool = False,
        admin_note: Optional[str] = None,
        bypass_validation: bool = False,
    ) -> Rack:
        # Check if rack can be added (match not at max)
        match = db.session.get(Match, match_id)
        if match and not bypass_validation and not match.can_add_rack():
            raise ValueError(
                "Cannot add rack: match has reached maximum and needs validation"
            )

        rack = Rack(
            match_id=match_id,
            rack_number=rack_number,
            winner_id=winner_id,
            reported_by_id=reported_by_id,
            confirmed_by_player=confirmed_by_player,
            validated_by_admin=validated_by_admin,
            admin_note=admin_note,
        )
        db.session.add(rack)

        # Update match scores when rack is added
        if match:
            # Update match scores based on winner
            if winner_id == match.player1_id:
                match.player1_score = (match.player1_score or 0) + 1
            elif winner_id == match.player2_id:
                match.player2_score = (match.player2_score or 0) + 1

            # Transizione soft: se il match è pending, portalo a playing
            if (match.status or MatchStatus.PENDING.value) == MatchStatus.PENDING.value:
                match.status = MatchStatus.PLAYING.value

            db.session.add(match)

        return rack

    @staticmethod
    @transactional(domain="match")
    def add_rack_with_score_update(
        match_id: int,
        winner_id: int,
        reported_by_id: int = 1,
        validated_by_admin: bool = True,
    ) -> dict:
        """Add rack with score update (delegates to ScoringService)."""
        from .scoring_service import ScoringService

        return ScoringService.add_rack_with_score_update(
            match_id, winner_id, reported_by_id, validated_by_admin
        )

    @staticmethod
    @transactional(domain="match")
    def set_match_result_direct(
        match_id: int, player1_score: int, player2_score: int
    ) -> None:
        """Set match result directly (delegates to ScoringService)."""
        from .scoring_service import ScoringService

        return ScoringService.set_match_result_direct(
            match_id, player1_score, player2_score
        )

    @staticmethod
    @transactional(domain="match")
    def reset_match_complete(match_id: int) -> None:
        """Reset completo di una partita eliminando tutti i rack.

        Il match viene riportato allo stato appropriato in base all'assegnazione
        del tavolo: PLAYING se ha un tavolo, PENDING altrimenti.

        IMPORTANT: Also deletes the PlayerEncounter record to maintain
        anti-rematch consistency. This ensures that when a match is reset,
        the players can be paired again in future rounds.
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        if match.is_bye:
            raise ValueError("Non puoi resettare una partita bye!")

        # Elimina tutti i rack
        existing_racks = Rack.query.filter_by(match_id=match_id).all()
        for rack in existing_racks:
            db.session.delete(rack)

        # Delete PlayerEncounter to maintain anti-rematch consistency
        # This ensures players can be paired again after match reset
        if match.player2_id:  # Only for non-bye matches
            from models.classification.models import PlayerEncounter
            PlayerEncounter.delete_encounter(
                gara_id=match.gara_id,
                player1_id=match.player1_id,
                player2_id=match.player2_id
            )

        # Reset match scores
        match.player1_score = 0
        match.player2_score = 0
        match.winner_id = None

        # Stato intelligente basato su table_assignment:
        # - Se ha tavolo assegnato → PLAYING (pronto per essere giocato)
        # - Se non ha tavolo → PENDING (in attesa di assegnazione)
        if match.table_assignment:
            match.status = MatchStatus.PLAYING.value
        else:
            match.status = MatchStatus.PENDING.value

        # Clear validation flags se presenti
        if hasattr(match, "validated_by_admin"):
            match.validated_by_admin = False

        db.session.add(match)

    @staticmethod
    @transactional(domain="match")
    def remove_rack_admin(rack_id: int) -> dict:
        """Rimuove un rack e aggiorna il punteggio del match (admin).

        Returns:
            Dict con stato aggiornato del match
        """
        rack = db.session.get(Rack, rack_id)
        if rack is None:
            from flask import abort

            abort(404)
        match = rack.match

        # Salva il vincitore per aggiornare il punteggio
        winner_id = rack.winner_id

        # Rimuovi il rack
        db.session.delete(rack)

        # Aggiorna il punteggio del match
        if winner_id == match.player1_id:
            match.player1_score = max(0, match.player1_score - 1)
        else:
            match.player2_score = max(0, match.player2_score - 1)

        # Controlla sempre se il punteggio giustifica ancora il winner_id
        should_clear_winner = False
        if match.gara.is_race_to:
            winning_score = match.gara.get_winning_score()
            if max(match.player1_score, match.player2_score) < winning_score:
                should_clear_winner = True
        else:  # esatto numero
            if (match.player1_score + match.player2_score) < match.gara.distance:
                should_clear_winner = True

        if should_clear_winner:
            match.winner_id = None
            match.reset_confirmations()
            # Se era completed, rimettilo in playing
            if match.status == MatchStatus.COMPLETED.value:
                MatchService.to_playing(match.id)

        return {
            "success": True,
            "message": "Rack rimosso (Admin)",
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "status": match.status,
        }

    @staticmethod
    @transactional(domain="match")
    def validate_rack_admin(rack_id: int) -> None:
        """Valida un rack (admin)."""
        rack = db.session.get(Rack, rack_id)
        if rack is None:
            from flask import abort

            abort(404)

        # Valida il rack
        rack.validated_by_admin = True
        rack.confirmed_by_player = (
            True  # Automaticamente confermato se validato dall'admin
        )

    @staticmethod
    @transactional(domain="match")
    def remove_last_rack(match_id: int) -> Optional[Rack]:
        last = (
            Rack.query.filter_by(match_id=match_id)
            .order_by(Rack.rack_number.desc())
            .first()
        )
        if last:
            db.session.delete(last)
        return last


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
        # import locale per evitare cicli
        from models.match.services import MatchService

        MatchService.to_completed(match.id)

        # ricarica o restituisci l'oggetto aggiornato
        return match


# Helper function for simplified rack addition
def add_rack(match_id: int, winner_id: int, added_by_id: int) -> Rack:
    """
    Simplified helper to add a rack to a match.

    Args:
        match_id: ID of the match
        winner_id: ID of the player who won the rack
        added_by_id: ID of the user adding the rack

    Returns:
        The created Rack instance

    Raises:
        ValueError: If match not found or rack cannot be added
    """
    match = db.session.get(Match, match_id)
    if not match:
        raise ValueError(f"Match {match_id} not found")

    # Determine next rack number
    from sqlalchemy import func

    max_rack = (
        db.session.query(func.max(Rack.rack_number))
        .filter_by(match_id=match_id)
        .scalar()
    )
    rack_number = (max_rack or 0) + 1

    # Use RackService to add the rack with validation
    return RackService.add_rack_result(
        match_id=match_id,
        rack_number=rack_number,
        winner_id=winner_id,
        reported_by_id=added_by_id,
        confirmed_by_player=False,
        validated_by_admin=False,
    )


__all__ = [
    "MatchService",
    "RackService",
    "MatchResultService",
    "InvalidTransitionError",
    "add_rack",
]
