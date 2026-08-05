"""
TrioStateSerializer - Builds UI state dict for TrioMatch rendering.

Extracted from TrioMatch.get_current_state() to reduce model size.
"""

from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import TrioMatch


class TrioStateSerializer:
    """Serializer for TrioMatch UI state."""

    @staticmethod
    def serialize(trio: "TrioMatch") -> Dict[str, Any]:
        """Return current state of the trio for UI rendering.

        Args:
            trio: The TrioMatch instance

        Returns:
            Dict with players, current_matchup, progress, config,
            completion status, and winner info.
        """
        config = trio.trio_config
        next_rack = trio.total_racks_played + 1

        return {
            "players": {
                "player1": {
                    "id": trio.player1_id,
                    "user": trio.player1,
                    "racks": trio.player1_racks,
                },
                "player2": {
                    "id": trio.player2_id,
                    "user": trio.player2,
                    "racks": trio.player2_racks,
                },
                "player3": {
                    "id": trio.player3_id,
                    "user": trio.player3,
                    "racks": trio.player3_racks,
                },
            },
            "current_matchup": {
                "player1": trio.current_player1,
                "player2": trio.current_player2,
                "waiting": trio.waiting_player,
            },
            "progress": {
                "current_round": trio.current_round,
                "total_rounds": config.num_rounds,
                "rack_in_round": trio.current_rack_in_round + 1,
                "racks_per_round": config.racks_per_round,
                "total_racks_played": trio.total_racks_played,
                "total_racks_needed": config.total_played_racks,
                "next_rack": (
                    next_rack if next_rack <= config.total_played_racks else None
                ),
            },
            "config": {
                "distance": config.distance,
                "num_rounds": config.num_rounds,
                "bonus_racks": config.bonus_racks,
                "max_racks_per_player": config.max_racks_per_player,
            },
            "is_completed": trio.is_completed,
            "bonus_applied": trio.bonus_applied,
            "winner": trio.winner,
        }


__all__ = ["TrioStateSerializer"]
