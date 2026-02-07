"""
Module: models/matchmaking/strategies/round_robin.py
Purpose: Round Robin pairing strategy implementation
Requirements: SPECIFICHE.md - Round Robin campionato format
"""

from __future__ import annotations

from typing import Sequence, List, Tuple, Dict, Any, TYPE_CHECKING

from .base import Pairing, BaseStrategy

if TYPE_CHECKING:
    pass


class RoundRobinStrategy(BaseStrategy):
    """Round Robin pairing strategy where everyone plays everyone else."""

    # PairingStrategy metadata
    name = "round_robin"
    display_name = "Round Robin"
    description = "Round Robin campionato where everyone plays everyone else"
    min_players = 3
    max_players = 16
    supports_byes = True
    requires_classification = False

    def __init__(self):
        super().__init__()
        self.strategy_name = "round_robin"

    def _validate_strategy_specific(self, gara: object) -> Dict[str, List[str]]:
        """Validate Round Robin specific requirements."""
        errors = []
        warnings = []

        try:
            # Get active inscriptions
            inscriptions = getattr(gara, "inscriptions", [])
            active_inscriptions = [
                i for i in inscriptions if not getattr(i, "is_withdrawn", False)
            ]
            player_count = len(active_inscriptions)

            # Calculate required rounds
            required_rounds = (
                player_count - 1 if player_count % 2 == 0 else player_count
            ) if player_count > 0 else 0

            # Check if gara has rounds_count and validate
            if hasattr(gara, "rounds_count"):
                rounds_count = getattr(gara, "rounds_count", 0)
                if rounds_count and rounds_count < required_rounds:
                    errors.append(
                        f"Round Robin requires {required_rounds} rounds, "
                        f"but gara has {rounds_count}"
                    )

        except Exception as e:
            warnings.append(f"Round Robin validation warning: {str(e)}")

        return {"errors": errors, "warnings": warnings}

    def preview(self, gara: object, round_number: int) -> Sequence[Pairing]:
        """Preview pairings for a specific round without side effects."""
        return self._generate_round_pairings(gara, round_number)

    def _generate_pairings(
        self, processed_data: Dict[str, Any], round_number: int
    ) -> Sequence[Pairing]:
        """Generate Round Robin pairings for the round."""
        gara = processed_data["gara"]
        return self._generate_round_pairings(gara, round_number)

    def _generate_round_pairings(
        self, gara: object, round_number: int
    ) -> List[Pairing]:
        """Generate pairings for a specific round using Round Robin algorithm."""
        try:
            # Get active players
            inscriptions = getattr(gara, "inscriptions", [])
            active_inscriptions = [i for i in inscriptions if not i.is_withdrawn]
            player_ids = [i.user_id for i in active_inscriptions]

            if len(player_ids) < 2:
                return []

            # Generate complete round robin schedule
            schedule = self._generate_round_robin_schedule(player_ids)

            # Return pairings for the specific round
            if round_number <= len(schedule):
                round_pairings = schedule[round_number - 1]  # 0-indexed
                return [
                    Pairing(
                        players=pairing,
                        round_number=round_number,
                        is_bye=(len(pairing) == 1),
                    )
                    for pairing in round_pairings
                ]

            return []

        except Exception as e:
            print(f"Error generating Round Robin pairings: {e}")
            return []

    def _generate_round_robin_schedule(
        self, player_ids: List[int]
    ) -> List[List[Tuple[int, ...]]]:
        """Generate complete Round Robin schedule using the classic polygon method."""
        n = len(player_ids)

        if n < 2:
            return []

        # For odd players, we need a modified approach to ensure all players get exactly one bye
        if n % 2 == 1:
            schedule = []

            # Each player gets exactly one bye - rotate which player sits out
            for round_num in range(n):
                round_pairings = []

                # Player who sits out this round
                bye_player = player_ids[round_num]
                round_pairings.append((bye_player,))

                # Remaining players for this round
                active_players = [p for p in player_ids if p != bye_player]

                # Pair the remaining 4 players (which is even)
                for i in range(len(active_players) // 2):
                    p1 = active_players[i]
                    p2 = active_players[-(i + 1)]  # From the end
                    round_pairings.append((p1, p2))

                schedule.append(round_pairings)

        else:
            # For even players, use standard polygon method
            players = player_ids[:]
            schedule = []

            # Classic polygon method: fix one player, rotate others
            for round_num in range(n - 1):
                round_pairings = []

                # Pair players symmetrically
                for i in range(n // 2):
                    p1_idx = i
                    p2_idx = n - 1 - i

                    player1 = players[p1_idx]
                    player2 = players[p2_idx]
                    round_pairings.append((player1, player2))

                schedule.append(round_pairings)

                # Rotate: keep first player fixed, rotate all others
                if n > 2:
                    first = players[0]
                    rest = players[1:]
                    # Standard rotation: last becomes second, others shift right
                    players = [first] + [rest[-1]] + rest[:-1]

        return schedule

    def get_total_rounds_needed(self, player_count: int) -> int:
        """Calculate total rounds needed for Round Robin."""
        if player_count < 2:
            return 0
        return player_count - 1 if player_count % 2 == 0 else player_count

    def get_matches_per_player(self, player_count: int) -> int:
        """Calculate matches per player in Round Robin."""
        return max(0, player_count - 1)



class RoundRobinPairingStrategy(RoundRobinStrategy):
    """Alias for compatibility with existing strategy registry."""
