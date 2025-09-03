"""
Module: models/matchmaking/strategies/direct_elimination.py
Purpose: Direct Elimination (single knockout) pairing strategy implementation
Requirements: SPECIFICHE.md - Direct elimination campionato format
"""

from __future__ import annotations

import math
from typing import Sequence, List, Optional, TYPE_CHECKING, cast

from .base import Pairing, ValidationResult, PairingStrategy, StrategyMetrics

if TYPE_CHECKING:
    from models.competition.models import Gara


class DirectEliminationStrategy(PairingStrategy):
    """Direct Elimination (single knockout) pairing strategy."""

    # PairingStrategy metadata
    name = "direct_elimination"
    display_name = "Direct Elimination"
    description = "Single knockout campionato format"
    min_players = 4
    max_players = 128
    supports_byes = True
    requires_classification = False

    def __init__(self):
        self.strategy_name = "direct_elimination"

    def validate(self, gara: object) -> ValidationResult:
        """Validate if Direct Elimination can be used for this gara."""
        try:
            # Get active inscriptions
            inscriptions = list(gara.inscriptions)  # type: ignore[arg-type]
            active_inscriptions = [i for i in inscriptions if i.status == "confirmed"]
            player_count = len(active_inscriptions)

            if player_count < 4:
                return ValidationResult(
                    ok=False,
                    messages=("Direct Elimination requires at least 4 players",),
                )

            if player_count > 128:
                return ValidationResult(
                    ok=False,
                    messages=(
                        "Direct Elimination with more than 128 players may be impractical",
                    ),
                )

            # Calculate required rounds
            required_rounds = math.ceil(math.log2(player_count))

            if hasattr(gara, "rounds_count"):
                rounds_count = getattr(gara, "rounds_count")
                if rounds_count < required_rounds:
                    return ValidationResult(
                        ok=False,
                        messages=(
                            f"Direct Elimination requires {required_rounds} rounds, but gara has {rounds_count}",
                        ),
                    )

            return ValidationResult(ok=True)

        except Exception as e:
            return ValidationResult(ok=False, messages=(f"Validation error: {str(e)}",))

    def preview(self, gara: object, round_number: int) -> Sequence[Pairing]:
        """Preview pairings for a specific round without side effects."""
        return self._generate_round_pairings(gara, round_number)  # type: ignore[arg-type]

    def propose(self, gara: object, round_number: int) -> Sequence[Pairing]:
        """Propose actual pairings for the round."""
        return self._generate_round_pairings(gara, round_number)  # type: ignore[arg-type]

    def _generate_round_pairings(
        self, gara: object, round_number: int
    ) -> List[Pairing]:
        """Generate pairings for a specific round using Direct Elimination."""
        try:
            gara_typed = cast("Gara", gara)
            if round_number == 1:
                return self._generate_first_round_pairings(gara_typed)
            else:
                return self._generate_subsequent_round_pairings(
                    gara_typed, round_number
                )

        except Exception as e:
            print(f"Error generating Direct Elimination pairings: {e}")
            return []

    def _generate_first_round_pairings(self, gara: "Gara") -> List[Pairing]:
        """Generate first round pairings with proper seeding and byes."""
        # Get active players
        inscriptions = list(gara.inscriptions)  # type: ignore[arg-type]
        active_inscriptions = [i for i in inscriptions if i.status == "confirmed"]

        # Sort players by seeding (use classification or random)
        player_ids = self._get_seeded_players(gara, active_inscriptions)

        n = len(player_ids)

        if n < 2:
            return []

        # Find next power of 2
        next_power_of_2 = 2 ** math.ceil(math.log2(n))
        byes_needed = next_power_of_2 - n

        pairings = []

        # Distribute byes among top seeds
        players_with_byes = set()
        if byes_needed > 0:
            # Give byes to top seeds
            for i in range(byes_needed):
                if i < len(player_ids):
                    players_with_byes.add(player_ids[i])
                    pairings.append(
                        Pairing(players=(player_ids[i],), is_bye=True, round_number=1)
                    )

        # Pair remaining players
        remaining_players = [p for p in player_ids if p not in players_with_byes]

        # Standard campionato seeding: 1 vs last, 2 vs second-last, etc.
        while len(remaining_players) >= 2:
            player1 = remaining_players.pop(0)
            player2 = remaining_players.pop(-1)
            pairings.append(Pairing(players=(player1, player2), round_number=1))

        return pairings

    def _generate_subsequent_round_pairings(
        self, gara: "Gara", round_number: int
    ) -> List[Pairing]:
        """Generate pairings for subsequent rounds based on previous round winners."""
        from ...match.models import Match

        # Get winners from previous round
        previous_round = round_number - 1
        previous_matches = Match.query.filter_by(
            gara_id=gara.id, round_number=previous_round, status="completed"
        ).all()

        # Check if all previous matches are completed
        total_previous_matches = Match.query.filter_by(
            gara_id=gara.id, round_number=previous_round
        ).count()

        if len(previous_matches) != total_previous_matches:
            # Not all previous matches completed
            return []

        # Get winners
        winners = []
        for match in previous_matches:
            if match.winner_id:
                winners.append(match.winner_id)
            elif match.is_bye and match.player1_id:
                winners.append(match.player1_id)
            elif match.is_bye and match.player2_id:
                winners.append(match.player2_id)

        # Pair winners
        pairings = []
        winners = list(winners)  # Make a copy

        while len(winners) >= 2:
            player1 = winners.pop(0)
            player2 = winners.pop(0)
            pairings.append(
                Pairing(players=(player1, player2), round_number=round_number)
            )

        # Handle odd winner (shouldn't happen in proper elimination)
        if len(winners) == 1:
            pairings.append(
                Pairing(players=(winners[0],), is_bye=True, round_number=round_number)
            )

        return pairings

    def _get_seeded_players(self, gara: "Gara", inscriptions: List) -> List[int]:
        """Get players in seeded order (by classification or random)."""
        from ...classification.models import Classification

        # Try to get seeding from campionato classification
        if hasattr(gara, "campionato_id"):
            classifications = (
                Classification.query.filter_by(campionato_id=gara.campionato_id)
                .order_by(Classification.position)
                .all()
            )

            classified_players = {c.user_id: c.position for c in classifications}

            # Sort inscriptions by classification position
            inscriptions.sort(key=lambda x: classified_players.get(x.user_id, 999))
        else:
            # Random seeding if no classification available
            import random

            random.shuffle(inscriptions)

        return [i.user_id for i in inscriptions]

    def get_total_rounds_needed(self, player_count: int) -> int:
        """Calculate total rounds needed for Direct Elimination."""
        if player_count < 2:
            return 0
        return math.ceil(math.log2(player_count))

    def get_bracket_size(self, player_count: int) -> int:
        """Get the bracket size (next power of 2)."""
        if player_count < 2:
            return 0
        return 2 ** math.ceil(math.log2(player_count))

    def get_byes_needed(self, player_count: int) -> int:
        """Calculate number of byes needed."""
        bracket_size = self.get_bracket_size(player_count)
        return bracket_size - player_count

    def get_metrics(self) -> Optional[StrategyMetrics]:
        """Get performance metrics from last execution."""
        return None  # No metrics collection implemented yet


class DirectEliminationPairingStrategy(DirectEliminationStrategy):
    """Alias for compatibility with existing strategy registry."""
