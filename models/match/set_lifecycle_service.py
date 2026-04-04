"""
SetLifecycleService - Multi-set match lifecycle operations.

Extracted from Match model to reduce god class size.
Handles start_next_set, get_current_set, complete_set operations.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from models.base import db

if TYPE_CHECKING:
    from .models import Match
    from .set_models import Set


class SetLifecycleService:
    """Service for multi-set match lifecycle operations."""

    @staticmethod
    def start_next_set(match: "Match") -> "Set":
        """Start the next set in a multi-set match.

        Args:
            match: The Match instance

        Returns:
            The newly created Set

        Raises:
            ValueError: If match is not multi-set, current set not complete,
                       or match already completed
        """
        if not match.is_multi_set:
            raise ValueError("This is not a multi-set match")

        current_set = SetLifecycleService.get_current_set(match)
        if current_set and not current_set.is_completed():
            raise ValueError("Current set must be completed before starting next set")

        if match.is_completed():
            raise ValueError("Match is already completed")

        from .set_models import Set

        distance = getattr(current_set, "distance", 5) if current_set else 5

        new_set = Set(
            match_id=match.id,
            set_number=match.current_set_number,
            distance=distance,
            is_race_to=True,
        )

        db.session.add(new_set)
        return new_set

    @staticmethod
    def get_current_set(match: "Match") -> Optional["Set"]:
        """Get the current set being played.

        Args:
            match: The Match instance

        Returns:
            The current Set, or None if not a multi-set match or no set exists
        """
        if not match.is_multi_set:
            return None

        from .set_models import Set

        return Set.query.filter_by(
            match_id=match.id, set_number=match.current_set_number
        ).first()

    @staticmethod
    def complete_set(match: "Match", set_number: int, winner_id: int) -> None:  # pyright: ignore[reportUnusedParameter]
        """Complete a set and check if match is finished.

        Updates match scores (sets won) and either completes the match
        or advances to the next set.

        Args:
            match: The Match instance
            set_number: Number of the completed set (unused, kept for API compat)
            winner_id: ID of the player who won the set

        Raises:
            ValueError: If match is not multi-set or winner is invalid
        """
        if not match.is_multi_set:
            raise ValueError("This is not a multi-set match")

        if winner_id == match.player1_id:
            match.player1_score += 1
        elif winner_id == match.player2_id:
            match.player2_score += 1
        else:
            raise ValueError("Winner must be one of the match players")

        if match.player1_score >= match.match_distance:
            match.winner_id = match.player1_id
            from .state_service import MatchStateService
            MatchStateService.to_completed(match.id)
        elif match.player2_score >= match.match_distance:
            match.winner_id = match.player2_id
            from .state_service import MatchStateService
            MatchStateService.to_completed(match.id)
        else:
            match.current_set_number += 1


__all__ = ["SetLifecycleService"]
