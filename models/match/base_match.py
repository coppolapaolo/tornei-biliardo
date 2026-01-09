"""
Module: models/match/base_match.py
Purpose: Mixin class for all match types
Architecture: Provides shared functionality between Match and IndividualMatch

This module implements the shared behavior for:
- Match validation and confirmation workflow
- Rack scoring abstraction
- Distance configuration
- Result management
"""

from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models.match.score import RackScore


class BaseMatchMixin:
    """
    Mixin class for match entities.

    Provides shared functionality for both tournament matches (Match)
    and casual matches (IndividualMatch).

    Expected Attributes (must be defined in concrete classes):
        player1_id: ID of first player
        player2_id: ID of second player
        player1_score: Current score for player 1
        player2_score: Current score for player 2
        winner_id: ID of winning player (when completed)
        status: Match status (pending, in_progress, completed, etc.)
        distance: Number of racks/sets to win
        best_of: Whether using best-of or exact distance
        is_multi_set: Whether match has multiple sets
        player1_confirmed: Whether player 1 confirmed result
        player2_confirmed: Whether player 2 confirmed result
        player1_confirmed_at: When player 1 confirmed
        player2_confirmed_at: When player 2 confirmed

    Expected Properties (must be defined in concrete classes):
        distance_config: Distance configuration value object
        rack_score: Rack score value object
    """

    # Type hints for attributes used by this mixin
    # These must be provided by the concrete class
    player1_id: int
    player2_id: int
    player1_score: int
    player2_score: int
    winner_id: Optional[int]
    status: Any  # Can be string or enum
    player1_confirmed: bool
    player2_confirmed: bool
    player1_confirmed_at: Optional[datetime]
    player2_confirmed_at: Optional[datetime]

    # Properties that must be implemented by concrete classes
    @property
    def rack_score(self) -> "RackScore":
        """Rack score abstraction (must be implemented by concrete class)."""
        raise NotImplementedError("Concrete class must implement rack_score property")

    def can_add_rack(self) -> bool:
        """
        Check if a rack can be added to the match.

        A rack cannot be added if:
        - Match is not in progress
        - Match has reached the maximum possible racks (ready for validation)

        Returns:
            bool: True if rack can be added, False otherwise
        """
        # Match must be in progress
        if not hasattr(self, "status"):
            return False

        # Status-based validation
        from models.status_enum import MatchStatus as SharedMatchStatus

        # Extract value if it is an enum member
        status_val = self.status.value if hasattr(self.status, "value") else self.status

        # States where racks can be added:
        # - pending: first rack transitions match to playing
        # - playing/in_progress: match actively in progress
        allowed_states = [
            SharedMatchStatus.PENDING.value,
            SharedMatchStatus.PLAYING.value,
            SharedMatchStatus.IN_PROGRESS.value,
        ]

        if status_val not in allowed_states:
            return False

        # Cannot add rack if match is at validation stage
        return not self.is_ready_for_validation()

    def is_ready_for_validation(self) -> bool:
        """
        Check if match has reached the distance and is ready for validation.

        Returns:
            bool: True if match is complete and ready for player confirmation
        """
        # Match must be in progress
        if not hasattr(self, "status"):
            return False

        # Status-based validation
        from models.status_enum import MatchStatus as SharedMatchStatus

        # Extract value if it is an enum member
        status_val = self.status.value if hasattr(self.status, "value") else self.status

        # Active states
        active_states = [
            SharedMatchStatus.PLAYING.value,
            SharedMatchStatus.IN_PROGRESS.value,
        ]

        if status_val not in active_states:
            return False

        # Check using RackScore if match is complete
        return self.rack_score.is_complete()

    def confirm_result(self, user_id: int) -> bool:
        """
        Confirm match result by a player.

        Args:
            user_id: ID of player confirming the result

        Returns:
            bool: True if both players have confirmed (match completed)

        Raises:
            ValueError: If user is not part of this match
        """
        if user_id not in [self.player1_id, self.player2_id]:
            raise ValueError("User is not part of this match")

        # Set confirmation for the appropriate player
        if user_id == self.player1_id:
            self.player1_confirmed = True
            self.player1_confirmed_at = datetime.utcnow()
        elif user_id == self.player2_id:
            self.player2_confirmed = True
            self.player2_confirmed_at = datetime.utcnow()

        # If both confirmed, complete the match
        if self.player1_confirmed and self.player2_confirmed:
            self._complete_match_after_confirmation()
            return True

        return False

    def reject_result(self, user_id: int) -> None:
        """
        Reject match result - removes last rack and resets confirmations.

        Args:
            user_id: ID of player rejecting the result

        Raises:
            ValueError: If user is not part of this match
        """
        if user_id not in [self.player1_id, self.player2_id]:
            raise ValueError("User is not part of this match")

        # Remove last rack (implementation delegated to subclass)
        self._remove_last_rack(user_id)

        # Reset confirmations
        self.player1_confirmed = False
        self.player2_confirmed = False
        self.player1_confirmed_at = None
        self.player2_confirmed_at = None

    def _complete_match_after_confirmation(self) -> None:
        """
        Complete the match after both players have confirmed.

        Sets winner and status based on current scores.
        Emits MatchCompletedEvent for SSE real-time updates.
        """
        from models.status_enum import MatchStatus as TournamentMatchStatus
        from models.individual_match.models import (
            MatchStatus as IndividualMatchStatus,
        )

        # Get winner from rack_score
        winner_number = self.rack_score.get_winner()
        if winner_number is None:
            self.winner_id = None  # Tie
        else:
            self.winner_id = self.player1_id if winner_number == 1 else self.player2_id

        # Update status - use correct enum based on type
        is_tournament_match = isinstance(self.status, str)
        if is_tournament_match:
            # Match (tournament) - use string value
            self.status = TournamentMatchStatus.COMPLETED.value
        else:
            # IndividualMatch - use enum directly
            self.status = IndividualMatchStatus.COMPLETED

        if hasattr(self, "completed_at"):
            self.completed_at = datetime.utcnow()

        # Emit SSE event for tournament matches (gara matches)
        if is_tournament_match and hasattr(self, "gara_id") and self.gara_id:
            self._emit_match_completed_event()

    def _remove_last_rack(self, user_id: int) -> None:
        """
        Remove last rack from match (soft delete).

        This method must be implemented by concrete classes because
        Match and IndividualMatch have different rack models
        (Rack vs IndividualRack).

        Args:
            user_id: ID of user removing the rack

        Raises:
            NotImplementedError: If not implemented in concrete class
        """
        raise NotImplementedError("Subclasses must implement _remove_last_rack()")

    def reset_confirmations(self) -> None:
        """
        Reset confirmation flags.

        Called when score changes (rack added/removed).
        """
        self.player1_confirmed = False
        self.player2_confirmed = False
        self.player1_confirmed_at = None
        self.player2_confirmed_at = None

    def _emit_match_completed_event(self) -> None:
        """
        Emit MatchCompletedEvent for SSE real-time updates.

        Called when match completes after player confirmation.
        Only for tournament matches with gara_id.
        """
        from models.events.match_events import MatchCompletedEvent
        from models.events.base import EventBus

        # Build player names
        player1_name = self.player1.username if self.player1 else "Player 1"
        player2_name = self.player2.username if self.player2 else "Player 2"
        winner_name = None
        if self.winner_id and self.winner:
            winner_name = self.winner.username

        score = f"{self.player1_score}-{self.player2_score}"

        event = MatchCompletedEvent(
            match_id=self.id,
            player1_id=self.player1_id,
            player1_name=player1_name,
            player2_id=self.player2_id,
            player2_name=player2_name,
            winner_id=self.winner_id,
            winner_name=winner_name,
            score=score,
            gara_id=self.gara_id,
        )
        EventBus.publish(event)
