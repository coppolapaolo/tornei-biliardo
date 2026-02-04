"""
ScoringService - Scoring logic for Match domain.

Extracted from MatchService and RackService to follow Single Responsibility Principle.
Handles score calculation, validation, and match completion logic.

High-complexity methods have been refactored with helper functions to reduce CC.
"""

from __future__ import annotations

from typing import Optional, Tuple
from datetime import datetime

from models.base import db
from models.status_enum import MatchStatus
from models.transaction.manager import transactional
from .models import Match, Rack


class ScoringService:
    """Service for scoring operations with reduced cyclomatic complexity.

    Handles:
    - Rack-level scoring with auto-completion detection
    - Direct score setting for admin operations
    - Player rack addition/removal (simplified UX)
    - Forfeit handling
    """

    # -----------------------------
    # PLAYER UX - Simplified Scoring
    # -----------------------------

    @staticmethod
    @transactional(domain="match")
    def add_rack_for_player(
        match_id: int, user_id: int, winner_id: int
    ) -> Rack:
        """Add a rack won by specified player (simplified UX for tournament matches).

        Args:
            match_id: ID of the match
            user_id: ID of user adding the rack
            winner_id: ID of the player who won the rack

        Returns:
            The created Rack object

        Raises:
            ValueError: If winner invalid or match not found
        """
        from sqlalchemy import func

        match = db.session.get(Match, match_id)
        if match is None:
            from flask import abort
            abort(404)

        # Validate winner
        if winner_id not in (match.player1_id, match.player2_id):
            raise ValueError("Invalid winner ID")

        # Get next rack number
        max_rack = (
            db.session.query(func.max(Rack.rack_number))
            .filter_by(match_id=match_id, is_deleted=False)
            .scalar()
        )
        rack_number = (max_rack or 0) + 1

        # Create rack with audit trail
        rack = Rack(
            match_id=match_id,
            rack_number=rack_number,
            winner_id=winner_id,
            added_by_id=user_id,
            added_at=datetime.utcnow(),
        )
        db.session.add(rack)

        # Update scores
        ScoringService._update_score_on_add(match, winner_id)

        # Reset confirmations when score changes
        match.reset_confirmations()

        # Auto-confirm winner when distance is reached
        # (winner has no reason to contest, only loser needs to confirm)
        if match.is_at_distance:
            winner_number = match.rack_score.get_winner()
            if winner_number is not None:
                # There's a clear winner - auto-confirm them
                match_winner_id = (
                    match.player1_id if winner_number == 1 else match.player2_id
                )
                match.confirm_result(match_winner_id)

        # Soft transition: pending → playing
        if match.status == MatchStatus.PENDING.value:
            match.status = MatchStatus.PLAYING.value

        return rack

    @staticmethod
    @transactional(domain="match")
    def remove_rack_for_player(
        match_id: int, user_id: int, player_id: int
    ) -> None:
        """Remove last rack won by specified player (simplified UX).

        Args:
            match_id: ID of the match
            user_id: ID of user removing the rack
            player_id: ID of player whose rack to remove

        Raises:
            ValueError: If no rack to remove
        """
        match = db.session.get(Match, match_id)
        if match is None:
            from flask import abort
            abort(404)

        # Find last non-deleted rack for this player
        last_rack = (
            Rack.query.filter_by(
                match_id=match_id, winner_id=player_id, is_deleted=False
            )
            .order_by(Rack.rack_number.desc())
            .first()
        )

        if not last_rack:
            raise ValueError("No rack to remove for this player")

        # Soft delete with audit trail
        last_rack.is_deleted = True
        last_rack.removed_by_id = user_id
        last_rack.removed_at = datetime.utcnow()

        # Update scores
        ScoringService._update_score_on_remove(match, player_id)

        # Clear winner if score no longer justifies it
        if ScoringService._should_clear_winner(match):
            match.winner_id = None

        # Reset confirmations
        match.reset_confirmations()

    # -----------------------------
    # FORFEIT HANDLING
    # -----------------------------

    @staticmethod
    @transactional(domain="match")
    def forfeit_match(match_id: int, user_id: int) -> Match:
        """Forfeit match - user loses, opponent gets maximum score.

        Also handles gara-level forfait policy (FORFEIT vs EXCLUDE).

        Args:
            match_id: ID of the match
            user_id: ID of player forfeiting

        Returns:
            The updated Match object

        Raises:
            ValueError: If invalid forfeit conditions
        """
        match = db.session.get(Match, match_id)
        if match is None:
            from flask import abort
            abort(404)

        # Validate forfeit conditions
        ScoringService._validate_forfeit(match, user_id)

        # Determine winner and calculate scores
        winner_id, forfeit_player = ScoringService._determine_forfeit_outcome(
            match, user_id
        )
        winning_score = ScoringService._calculate_forfeit_score(match)

        # Apply forfeit scores
        ScoringService._apply_forfeit_scores(match, forfeit_player, winning_score)
        match.winner_id = winner_id

        # Complete the match
        from .state_service import MatchStateService
        match = MatchStateService.to_completed(match_id)

        # Handle gara-level forfait policy
        from models.competition.withdraw_policy_service import WithdrawPolicyService
        WithdrawPolicyService.handle_forfeit(gara_id=match.gara_id, user_id=user_id)

        return match

    # -----------------------------
    # ADMIN SCORING
    # -----------------------------

    @staticmethod
    @transactional(domain="match")
    def add_rack_with_score_update(
        match_id: int,
        winner_id: int,
        reported_by_id: int = 1,
        validated_by_admin: bool = True,
    ) -> dict:
        """Add rack and auto-update match score with completion detection.

        Args:
            match_id: ID of the match
            winner_id: ID of rack winner
            reported_by_id: ID of reporter
            validated_by_admin: If True, auto-complete on winning score

        Returns:
            Dict with updated match state
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        # Validate match not already complete
        if match.rack_score.is_complete():
            raise ValueError(
                "Il match è già finito, non è possibile aggiungere altri punti"
            )

        # Validate score limits before adding
        ScoringService._validate_rack_addition(match, winner_id)

        # Find next rack number and add rack
        from .services import RackService
        last_rack = (
            Rack.query.filter_by(match_id=match_id)
            .order_by(Rack.rack_number.desc())
            .first()
        )
        next_rack_number = (last_rack.rack_number + 1) if last_rack else 1

        RackService.add_rack_result(
            match_id=match.id,
            rack_number=next_rack_number,
            winner_id=winner_id,
            reported_by_id=reported_by_id,
            validated_by_admin=validated_by_admin,
        )

        # Reload match for updated scores
        db.session.refresh(match)

        # Handle completion if match is finished
        if match.rack_score.is_complete():
            ScoringService._handle_rack_completion(match, validated_by_admin)

        return {
            "success": True,
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "status": match.status,
        }

    @staticmethod
    @transactional(domain="match")
    def set_match_result_direct(
        match_id: int, player1_score: int, player2_score: int
    ) -> None:
        """Set complete match result directly (admin operation).

        Replaces all existing racks with new result.

        Args:
            match_id: ID of the match
            player1_score: Final score for player 1
            player2_score: Final score for player 2

        Raises:
            ValueError: If invalid scores
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        if match.is_bye:
            raise ValueError("Non puoi modificare una partita bye!")

        # Validate scores
        ScoringService._validate_score_limits(match, player1_score, player2_score)

        # Determine winner and completion status
        is_complete, winner_id = ScoringService._calculate_result(
            match, player1_score, player2_score
        )

        # Replace all racks
        ScoringService._replace_all_racks(match, player1_score, player2_score)

        # Update match state
        ScoringService._update_match_with_result(
            match, player1_score, player2_score, winner_id, is_complete
        )

    # -----------------------------
    # HELPER METHODS (Private)
    # -----------------------------

    @staticmethod
    def _update_score_on_add(match: Match, winner_id: int) -> None:
        """Update match score when rack is added."""
        if winner_id == match.player1_id:
            match.player1_score += 1
        else:
            match.player2_score += 1

    @staticmethod
    def _update_score_on_remove(match: Match, player_id: int) -> None:
        """Update match score when rack is removed."""
        if player_id == match.player1_id:
            match.player1_score = max(0, match.player1_score - 1)
        else:
            match.player2_score = max(0, match.player2_score - 1)

    @staticmethod
    def _should_clear_winner(match: Match) -> bool:
        """Check if winner should be cleared based on current scores."""
        if match.gara.is_race_to:
            winning_score = match.gara.distance_config.get_winning_racks()
            return max(match.player1_score, match.player2_score) < winning_score
        else:
            return (match.player1_score + match.player2_score) < match.gara.distance

    @staticmethod
    def _validate_forfeit(match: Match, user_id: int) -> None:
        """Validate that forfeit is allowed."""
        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("User is not a player in this match")
        if match.is_bye:
            raise ValueError("Cannot forfeit a bye match - it's an automatic win")
        if match.status == MatchStatus.COMPLETED.value:
            raise ValueError("Cannot forfeit a completed match")

    @staticmethod
    def _determine_forfeit_outcome(
        match: Match, user_id: int
    ) -> Tuple[Optional[int], int]:
        """Determine winner and forfeiting player number."""
        if user_id == match.player1_id:
            return match.player2_id, 1
        else:
            return match.player1_id, 2

    @staticmethod
    def _calculate_forfeit_score(match: Match) -> int:
        """Calculate winning score for forfeit."""
        distance = match.distance_config
        if match.is_multi_set:
            return distance.get_winning_sets()
        else:
            return distance.get_winning_racks()

    @staticmethod
    def _apply_forfeit_scores(
        match: Match, forfeit_player: int, winning_score: int
    ) -> None:
        """Apply forfeit scores to match.

        The forfeiting player keeps their current score (racks already won).
        The winner receives at least the winning score (distance).
        """
        if forfeit_player == 1:
            # Player 1 forfeits - keep their score, ensure player 2 has winning score
            if match.player2_score < winning_score:
                match.player2_score = winning_score
            # Keep match.player1_score as-is (racks already won)
        else:
            # Player 2 forfeits - keep their score, ensure player 1 has winning score
            if match.player1_score < winning_score:
                match.player1_score = winning_score
            # Keep match.player2_score as-is (racks already won)

    @staticmethod
    def _validate_rack_addition(match: Match, winner_id: int) -> None:
        """Validate that a rack can be added."""
        temp_p1_score = match.player1_score
        temp_p2_score = match.player2_score

        if winner_id == match.player1_id:
            temp_p1_score += 1
        else:
            temp_p2_score += 1

        distance = match.gara.distance_config
        if distance.is_race_to_racks:
            winning_racks = distance.get_winning_racks()
            if temp_p1_score > winning_racks or temp_p2_score > winning_racks:
                raise ValueError(
                    f"Match già completato - limite raggiunto per "
                    f"'{distance.to_display_string()}'"
                )
        else:
            total_racks = temp_p1_score + temp_p2_score
            if total_racks > distance.racks:
                raise ValueError(
                    f"Non è possibile superare il limite di {distance.racks} "
                    f"rack totali per questo match"
                )

    @staticmethod
    def _handle_rack_completion(match: Match, validated_by_admin: bool) -> None:
        """Handle match completion after rack addition."""
        final_winner_id = match.rack_score.get_winner()

        if final_winner_id is None:
            # True tie (exact mode) - no winner
            match.winner_id = None
            if validated_by_admin:
                from .state_service import MatchStateService
                MatchStateService.to_completed(match.id)
            else:
                match.status = MatchStatus.COMPLETED.value
                db.session.add(match)
                match.reset_confirmations()
        else:
            # Convert player number to ID
            final_winner_id = (
                match.player1_id if final_winner_id == 1 else match.player2_id
            )

            if validated_by_admin:
                from .services import MatchResultService
                MatchResultService.submit_result(match.id, final_winner_id)
            else:
                match.winner_id = final_winner_id
                db.session.add(match)
                match.reset_confirmations()

    @staticmethod
    def _validate_score_limits(
        match: Match, player1_score: int, player2_score: int
    ) -> None:
        """Validate score limits for direct result setting.

        For "race to n" matches, validates that both players cannot have
        the winning score simultaneously (logically impossible - match
        ends when first player reaches winning score).
        """
        if player1_score < 0 or player2_score < 0:
            raise ValueError("I punteggi non possono essere negativi!")

        max_score = match.gara.distance
        if player1_score > max_score or player2_score > max_score:
            raise ValueError(f"I punteggi non possono superare {max_score}!")

        # In "race to n" matches, both players cannot have winning score
        # (match ends when first player reaches it)
        if match.gara.is_race_to:
            winning_score = match.gara.distance_config.get_winning_racks()
            if player1_score >= winning_score and player2_score >= winning_score:
                raise ValueError(
                    f"In un match 'al {winning_score}', entrambi i giocatori "
                    f"non possono avere {winning_score} o più punti!"
                )
        else:
            # In "exact number" mode, total racks must equal distance
            total_racks = player1_score + player2_score
            if total_racks != match.gara.distance:
                raise ValueError(
                    f"In modalità 'esatto numero', il totale dei rack ({total_racks}) "
                    f"deve essere esattamente {match.gara.distance}!"
                )

    @staticmethod
    def _calculate_result(
        match: Match, player1_score: int, player2_score: int
    ) -> Tuple[bool, Optional[int]]:
        """Calculate if result is complete and who won."""
        winning_score = match.gara.distance_config.get_winning_racks()

        if match.gara.is_race_to:
            if player1_score >= winning_score:
                return True, match.player1_id
            elif player2_score >= winning_score:
                return True, match.player2_id
            return False, None
        else:
            total_racks = player1_score + player2_score
            if total_racks == match.gara.distance:
                if player1_score > player2_score:
                    return True, match.player1_id
                elif player2_score > player1_score:
                    return True, match.player2_id
                return True, None  # Tie
            return False, None

    @staticmethod
    def _replace_all_racks(
        match: Match, player1_score: int, player2_score: int
    ) -> None:
        """Replace all existing racks with new result."""
        from .services import RackService
        from .state_service import MatchStateService

        # Delete existing racks
        existing_racks = Rack.query.filter_by(match_id=match.id).all()
        for rack in existing_racks:
            db.session.delete(rack)

        # Ensure match is in playing state
        if match.status != MatchStatus.PLAYING.value:
            MatchStateService.to_playing(match.id)

        # Create new racks
        rack_number = 1
        for _ in range(player1_score):
            RackService.add_rack_result(
                match.id, rack_number, match.player1_id, 1,
                validated_by_admin=True, bypass_validation=True
            )
            rack_number += 1

        for _ in range(player2_score):
            RackService.add_rack_result(
                match.id, rack_number, match.player2_id, 1,
                validated_by_admin=True, bypass_validation=True
            )
            rack_number += 1

    @staticmethod
    def _update_match_with_result(
        match: Match,
        player1_score: int,
        player2_score: int,
        winner_id: Optional[int],
        is_complete: bool,
    ) -> None:
        """Update match with final result."""
        from .state_service import MatchStateService

        match.player1_score = player1_score
        match.player2_score = player2_score
        match.winner_id = winner_id

        if is_complete:
            match.validated_by_admin = True
            if match.status != MatchStatus.COMPLETED.value:
                MatchStateService.to_completed(match.id)

            # Release table
            if match.table_assignment:
                from .table_assignment_service import TableAssignmentService
                TableAssignmentService.release_and_reassign_table(match.id)
                match.table_assignment = None
        else:
            match.validated_by_admin = False
            if match.status == MatchStatus.COMPLETED.value:
                match.status = MatchStatus.PLAYING.value


__all__ = ["ScoringService"]
