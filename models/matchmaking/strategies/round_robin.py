"""
Module: models/matchmaking/strategies/round_robin.py
Purpose: Round Robin pairing strategy implementation
Requirements: SPECIFICHE.md - Round Robin tournament format
"""

from __future__ import annotations

from typing import Sequence, List, Tuple, Optional, TYPE_CHECKING

from .base import Pairing, ValidationResult, PairingStrategy, StrategyMetrics

if TYPE_CHECKING:
    pass


class RoundRobinStrategy(PairingStrategy):
    """Round Robin pairing strategy where everyone plays everyone else."""

    # PairingStrategy metadata
    name = "round_robin"
    display_name = "Round Robin"
    description = "Round Robin tournament where everyone plays everyone else"
    min_players = 3
    max_players = 16
    supports_byes = True
    requires_classification = False

    def __init__(self):
        self.strategy_name = "round_robin"

    def validate(self, prova: object) -> ValidationResult:
        """Validate if Round Robin can be used for this prova."""
        try:
            # Get active inscriptions
            inscriptions = getattr(prova, "inscriptions", [])
            active_inscriptions = [i for i in inscriptions if i.status == "confirmed"]
            player_count = len(active_inscriptions)

            if player_count < 3:
                return ValidationResult(
                    ok=False, messages=("Round Robin requires at least 3 players",)
                )

            if player_count > 16:
                return ValidationResult(
                    ok=False,
                    messages=(
                        "Round Robin with more than 16 players may be impractical",
                    ),
                )

            # Calculate required rounds
            required_rounds = (
                player_count - 1 if player_count % 2 == 0 else player_count
            )

            # Check if prova has rounds_count and validate
            if (
                hasattr(prova, "rounds_count")
                and getattr(prova, "rounds_count", 0) < required_rounds
            ):
                return ValidationResult(
                    ok=False,
                    messages=(
                        f"Round Robin requires {required_rounds} rounds, but prova has {getattr(prova, 'rounds_count', 0)}",
                    ),
                )

            return ValidationResult(ok=True)

        except Exception as e:
            return ValidationResult(ok=False, messages=(f"Validation error: {str(e)}",))

    def preview(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Preview pairings for a specific round without side effects."""
        return self._generate_round_pairings(prova, round_number)

    def propose(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Propose actual pairings for the round."""
        return self._generate_round_pairings(prova, round_number)

    def _generate_round_pairings(
        self, prova: object, round_number: int
    ) -> List[Pairing]:
        """Generate pairings for a specific round using Round Robin algorithm."""
        try:
            # Get active players
            inscriptions = getattr(prova, "inscriptions", [])
            active_inscriptions = [i for i in inscriptions if i.status == "confirmed"]
            player_ids = [i.user_id for i in active_inscriptions]

            if len(player_ids) < 2:
                return []

            # Generate complete round robin schedule
            schedule = self._generate_round_robin_schedule(player_ids)

            # Return pairings for the specific round
            if round_number <= len(schedule):
                round_pairings = schedule[round_number - 1]  # 0-indexed
                return [
                    Pairing(players=pairing, round_number=round_number)
                    for pairing in round_pairings
                ]

            return []

        except Exception as e:
            print(f"Error generating Round Robin pairings: {e}")
            return []

    def _generate_round_robin_schedule(
        self, player_ids: List[int]
    ) -> List[List[Tuple[int, ...]]]:
        """Generate complete Round Robin schedule using standard algorithm."""
        n = len(player_ids)

        if n < 2:
            return []

        # Handle odd number of players by adding a dummy "bye" player
        if n % 2 == 1:
            player_ids = player_ids + [-1]  # -1 represents bye
            n += 1

        schedule = []

        # Standard Round Robin algorithm
        for round_num in range(n - 1):
            round_pairings = []

            for i in range(n // 2):
                player1_idx = i
                player2_idx = n - 1 - i

                player1 = player_ids[player1_idx]
                player2 = player_ids[player2_idx]

                # Handle bye
                if player1 == -1:
                    round_pairings.append((player2,))  # Bye for player2
                elif player2 == -1:
                    round_pairings.append((player1,))  # Bye for player1
                else:
                    round_pairings.append((player1, player2))

            schedule.append(round_pairings)

            # Rotate players (except the first one)
            player_ids = [player_ids[0]] + [player_ids[-1]] + player_ids[1:-1]

        return schedule

    def get_total_rounds_needed(self, player_count: int) -> int:
        """Calculate total rounds needed for Round Robin."""
        if player_count < 2:
            return 0
        return player_count - 1 if player_count % 2 == 0 else player_count

    def get_matches_per_player(self, player_count: int) -> int:
        """Calculate matches per player in Round Robin."""
        return max(0, player_count - 1)

    def get_metrics(self) -> Optional[StrategyMetrics]:
        """Get performance metrics from last execution."""
        return None  # No metrics collection implemented yet


class RoundRobinPairingStrategy(RoundRobinStrategy):
    """Alias for compatibility with existing strategy registry."""
