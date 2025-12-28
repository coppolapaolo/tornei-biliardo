"""
Module: models/competition/round_manager.py
Purpose: Advanced round management with locking and state control
"""

from __future__ import annotations

from typing import Dict, Any, Tuple
from enum import Enum

from models.base import db
from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.classification.models import RoundClassification
from models.classification.services import RoundClassificationService
from models.transaction.manager import transactional


class RoundLockStatus(Enum):
    """Round lock status for advanced management."""

    UNLOCKED = "unlocked"
    LOCKED = "locked"


class AdvancedRoundManager:
    """Advanced round management with locking and modification control."""

    @staticmethod
    def get_round_lock_status(gara_id: int, round_number: int) -> RoundLockStatus:
        """Determine the lock status of a specific round.

        Business Rule: Match modification is allowed ONLY for the current active round
        and only if the tournament is in 'playing' state.

        Definition of "current active round":
        - The HIGHEST round number that has matches created
        - NOT the last fully completed round (that's a different concept)

        This ensures that:
        1. Past rounds (< current) are locked to maintain historical integrity.
        2. Future rounds (> current, pre-generated in Random strategy) are locked.
        3. Match results can only be entered when the tournament is active.
        """
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        if gara.status != GaraStatus.PLAYING.value:
            return RoundLockStatus.LOCKED

        # Find the highest round that has matches (the actual active round)
        highest_round_with_matches = (
            db.session.query(db.func.max(Match.round_number))
            .filter(Match.gara_id == gara_id)
            .scalar()
        ) or 0

        # The active round is the highest round with matches
        # This is what should be unlocked
        active_round = highest_round_with_matches

        # Fallback: if gara.current_round is higher (shouldn't happen normally),
        # use it instead
        if gara.current_round > active_round:
            active_round = gara.current_round

        # Unlock only the active round
        if round_number == active_round:
            return RoundLockStatus.UNLOCKED

        return RoundLockStatus.LOCKED

    @staticmethod
    def can_modify_match(match_id: int) -> Tuple[bool, str]:
        """Check if a match can be modified based on round locking rules."""
        match = db.session.get(Match, match_id)
        if not match:
            return False, "Match non trovato"

        lock_status = AdvancedRoundManager.get_round_lock_status(
            match.gara_id, match.round_number
        )

        if lock_status == RoundLockStatus.LOCKED:
            return (
                False,
                "Il turno è bloccato perché un turno successivo è già iniziato",
            )

        return True, ""

    @staticmethod
    @transactional(domain="competition")
    def reset_match_with_validation(match_id: int) -> Tuple[bool, str]:
        """Reset a match with validation, classification updates and round progression.

        Business Rules:
        - Validates round locking: blocked if subsequent rounds exist
        - Recalculates all classifications for affected rounds
        - Updates round progression (may decrement current_round)
        - Respects table_assignment for match state

        Returns:
            Tuple[bool, str]: (success, message)
                success=False if round is locked or error occurs
                message contains reason for failure or success confirmation

        Use Case 8 Requirement:
            Match modification blocked when subsequent rounds exist
            to maintain tournament integrity.
        """
        from models.match.services import RackService

        match = db.session.get(Match, match_id)
        if not match:
            return False, "Match non trovato"

        # Always validate modification permission (no override)
        can_modify, reason = AdvancedRoundManager.can_modify_match(match_id)
        if not can_modify:
            return False, reason

        # Store original match state for rollback
        original_status = match.status
        original_winner = match.winner_id
        original_p1_score = match.player1_score
        original_p2_score = match.player2_score

        try:
            # Reset the match
            RackService.reset_match_complete(match_id)

            # Recalculate classifications for affected rounds
            AdvancedRoundManager._recalculate_affected_classifications(
                match.gara_id, match.round_number
            )

            # Update round progression if needed
            AdvancedRoundManager._update_round_progression_after_reset(
                match.gara_id, match.round_number
            )

            # Transaction managed by @transactional decorator
            return True, "Match resettato con successo"

        except Exception as e:
            # Rollback match state
            match.status = original_status
            match.winner_id = original_winner
            match.player1_score = original_p1_score
            match.player2_score = original_p2_score
            db.session.rollback()
            return False, f"Errore nel reset del match: {str(e)}"

    @staticmethod
    @transactional(domain="competition")
    def cancel_round(gara_id: int, round_number: int) -> Tuple[bool, str]:
        """Cancel an entire round with proper validation.

        Business Rules:
        - Can only cancel current round or future rounds
        - Cannot cancel if matches have partial results
        - Deletes all matches and racks in the round
        - Recalculates classifications for previous rounds

        Returns:
            Tuple[bool, str]: (success, message)
        """
        gara = db.session.get(Gara, gara_id)
        if not gara:
            return False, "Gara non trovata"

        # Only allow canceling the current round or higher
        if round_number < gara.current_round:
            return False, "Non puoi cancellare un turno precedente a quello corrente"

        # Get all matches in the round
        round_matches = Match.query.filter_by(
            gara_id=gara_id, round_number=round_number
        ).all()

        if not round_matches:
            return False, f"Nessun match trovato per il turno {round_number}"

        # Check if any matches have partial results
        matches_with_results = [
            m
            for m in round_matches
            if m.player1_score is not None or m.player2_score is not None
        ]
        if matches_with_results:
            return (
                False,
                "Alcuni match hanno già risultati parziali. "
                "Reset i match prima di cancellare il turno.",
            )

        try:
            # Delete all matches in the round
            for match in round_matches:
                # Delete associated racks first (bulk delete via query)
                from models.match.models import Rack

                Rack.query.filter_by(match_id=match.id).delete()
                # Delete match instance (requires explicit session delete)
                # Note: Rack.query.delete() is bulk delete on query result
                # while db.session.delete(match) deletes specific instance
                db.session.delete(match)

            # Delete classifications for this round
            RoundClassification.query.filter_by(
                gara_id=gara_id, round_number=round_number
            ).delete()

            # Delete PlayerEncounters for this round to maintain anti-rematch consistency
            # This ensures players can be paired again after round cancellation
            from models.classification.models import PlayerEncounter
            PlayerEncounter.delete_round_encounters(gara_id, round_number)

            # Update gara current round if we cancelled the current round
            if round_number == gara.current_round:
                gara.current_round = max(0, round_number - 1)

                # Update gara status if going back to round 0
                if gara.current_round == 0:
                    gara.status = GaraStatus.INSCRIPTION.value

            # Transaction managed by @transactional decorator
            return True, f"Turno {round_number} cancellato con successo"

        except Exception as e:
            db.session.rollback()
            return False, f"Errore nella cancellazione del turno: {str(e)}"

    @staticmethod
    @transactional(domain="competition")
    def bulk_reset_round_matches(
        gara_id: int, round_number: int
    ) -> Tuple[bool, str, Dict[str, int]]:
        """Reset all matches in a round with statistics."""
        gara = db.session.get(Gara, gara_id)
        if not gara:
            return False, "Gara non trovata", {}

        # Get all completed matches in the round
        completed_matches = Match.query.filter_by(
            gara_id=gara_id,
            round_number=round_number,
            status=MatchStatus.COMPLETED.value,
        ).all()

        if not completed_matches:
            return (
                False,
                f"Nessun match completato trovato nel turno {round_number}",
                {},
            )

        reset_count = 0
        error_count = 0
        errors = []

        try:
            for match in completed_matches:
                success, message = AdvancedRoundManager.reset_match_with_validation(
                    match.id
                )
                if success:
                    reset_count += 1
                else:
                    error_count += 1
                    errors.append(f"Match {match.id}: {message}")

            # Update gara status if all matches were reset
            if reset_count > 0:
                # Recalculate round progression
                AdvancedRoundManager._update_round_progression_after_reset(
                    gara_id, round_number
                )

            # Transaction managed by @transactional decorator

            stats = {
                "reset_count": reset_count,
                "error_count": error_count,
                "total_matches": len(completed_matches),
            }

            if error_count == 0:
                return True, f"Tutti i {reset_count} match sono stati resettati", stats
            else:
                message = f"{reset_count} match resettati, {error_count} errori"
                return False, message, stats

        except Exception as e:
            db.session.rollback()
            return False, f"Errore nel reset bulk: {str(e)}", {"error_count": 1}

    @staticmethod
    def get_round_modification_summary(gara_id: int) -> Dict[int, Dict[str, Any]]:
        """Get a summary of which rounds can be modified and their status."""
        gara = db.session.get(Gara, gara_id)
        if not gara:
            return {}

        rounds_summary = {}

        # Get all rounds with matches
        rounds_with_matches = (
            db.session.query(Match.round_number)
            .filter_by(gara_id=gara_id)
            .distinct()
            .all()
        )

        for (round_number,) in rounds_with_matches:
            lock_status = AdvancedRoundManager.get_round_lock_status(
                gara_id, round_number
            )

            # Get round matches
            round_matches = Match.query.filter_by(
                gara_id=gara_id, round_number=round_number
            ).all()

            completed_matches = [
                m for m in round_matches if m.status == MatchStatus.COMPLETED.value
            ]
            pending_matches = [
                m for m in round_matches if m.status == MatchStatus.PENDING.value
            ]

            # Check if matches can be modified
            modifiable_matches = []
            for match in round_matches:
                can_modify, _ = AdvancedRoundManager.can_modify_match(match.id)
                if can_modify:
                    modifiable_matches.append(match.id)

            rounds_summary[round_number] = {
                "lock_status": lock_status.value,
                "total_matches": len(round_matches),
                "completed_matches": len(completed_matches),
                "pending_matches": len(pending_matches),
                "modifiable_matches": len(modifiable_matches),
                "can_cancel_round": lock_status != RoundLockStatus.LOCKED,
                "can_bulk_reset": len(completed_matches) > 0
                and lock_status != RoundLockStatus.LOCKED,
            }

        return rounds_summary

    @staticmethod
    def _recalculate_affected_classifications(
        gara_id: int, affected_round: int
    ) -> None:
        """Recalculate classifications for affected rounds after match modification."""

        # Recalculate classification for the affected round and all subsequent rounds
        max_round = (
            db.session.query(db.func.max(Match.round_number))
            .filter_by(gara_id=gara_id)
            .scalar()
            or 0
        )

        for round_num in range(affected_round, max_round + 1):
            try:
                # Delete existing classification for this round
                RoundClassification.query.filter_by(
                    gara_id=gara_id, round_number=round_num
                ).delete()

                # Recalculate classification
                classification = RoundClassificationService.get_round_standings(
                    gara_id, round_num
                )

                # Save new classification
                for i, player_data in enumerate(classification, 1):
                    new_classification = RoundClassification(
                        gara_id=gara_id,
                        round_number=round_num,
                        user_id=player_data["user_id"],
                        position=i,
                        matches_won=player_data.get("matches_won", 0),
                        rack_difference=player_data.get("rack_difference", 0),
                        points=player_data.get("points", 0),
                    )
                    db.session.add(new_classification)

            except Exception as e:
                print(f"Error recalculating classification for round {round_num}: {e}")

    @staticmethod
    def _update_round_progression_after_reset(
        gara_id: int, affected_round: int
    ) -> None:
        """Update round progression after match resets.

        Important: current_round should represent the HIGHEST round with matches
        (the active round), NOT the last fully completed round.

        This function:
        1. Does NOT delete subsequent rounds (they may have been started intentionally)
        2. Sets current_round to the highest round that has matches
        """
        gara = db.session.get(Gara, gara_id)
        if not gara:
            return

        # Find the highest round that has matches
        # This is the "active round" - the one being played
        highest_round_with_matches = (
            db.session.query(db.func.max(Match.round_number))
            .filter(Match.gara_id == gara_id)
            .scalar()
        ) or 0

        # Set current_round to the highest round with matches
        # This ensures the active round stays unlocked for modifications
        if highest_round_with_matches > 0:
            gara.current_round = highest_round_with_matches
        # Note: We do NOT automatically delete subsequent rounds.
        # If a director started round 2, it should stay even if round 1 is modified.
