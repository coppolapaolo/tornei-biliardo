"""
Module: models/classification/strategies/round_strategies.py
Purpose: Classification strategies for round-by-round ranking
Data Structures: AmalfiRoundClassificationStrategy, RandomRoundClassificationStrategy
Dependencies: typing, .base
"""

from typing import Sequence, Dict, Any, Optional, Tuple

from .base import (
    ClassificationStrategy,
    ClassificationScope,
    ClassificationResult,
    PlayerScore,
)


class AmalfiRoundClassificationStrategy(ClassificationStrategy):
    """Amalfi round classification strategy.

    Ranking criteria (in priority order):
    1. Matches won (descending) - more wins = higher rank
    2. Rack difference (descending) - better differential = higher rank
    3. Previous round position (ascending) - advantage to leader in ties

    Used for Amalfi-style tournaments where classification drives next round pairings.
    The Amalfi algorithm pairs players by proximity in the classification.
    """

    name = "amalfi_round"
    display_name = "Amalfi Round"
    description = "Matches won, then rack difference, then previous position"
    scope = ClassificationScope.ROUND

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """Get sort key: matches_won DESC, rack_diff DESC, prev_pos ASC."""
        return (
            -score.matches_won,  # Primary: matches won DESC
            -score.rack_difference,  # Secondary: rack diff DESC
            score.previous_position or 999,  # Tertiary: previous position ASC
            score.player_id,  # Stability: player ID
        )

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Calculate Amalfi round classification.

        Args:
            scores: Player scores for this round (cumulative up to round)
            previous_classification: Classification from previous round (for tiebreaking)
            context: Optional context with round_number, gara_id

        Returns:
            ClassificationResult with ordered entries
        """
        # Enrich scores with previous positions for tie-breaking
        enriched_scores = self._enrich_with_previous(scores, previous_classification)

        # Sort by Amalfi criteria
        sorted_scores = sorted(enriched_scores, key=self.get_sort_key)

        # Build entries with tie detection
        entries, has_ties = self._build_entries_with_ties(sorted_scores)

        return ClassificationResult(
            entries=tuple(entries),
            scope=self.scope,
            has_ties=has_ties,
            requires_tiebreaker=has_ties,
            metadata={
                "round_number": context.get("round_number") if context else None,
                "strategy": self.name,
            },
        )


class RandomRoundClassificationStrategy(ClassificationStrategy):
    """Random gara round classification strategy.

    Ranking criteria (in priority order):
    1. Total racks won (descending) - more racks = higher rank
    2. Rack difference (descending) - better differential = higher rank

    Different from Amalfi: prioritizes total scoring over wins.
    A player with more racks but fewer match wins ranks higher.
    """

    name = "random_round"
    display_name = "Random Round"
    description = "Total racks won, then rack difference"
    scope = ClassificationScope.ROUND

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """Get sort key: racks_won DESC, rack_diff DESC."""
        return (
            -score.racks_won,  # Primary: racks won DESC
            -score.rack_difference,  # Secondary: rack diff DESC
            score.player_id,  # Stability
        )

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Calculate Random round classification.

        Args:
            scores: Player scores for this round
            previous_classification: Not used for Random strategy
            context: Optional context with round_number, gara_id

        Returns:
            ClassificationResult with ordered entries
        """
        # Sort by Random criteria
        sorted_scores = sorted(scores, key=self.get_sort_key)

        # Build entries with tie detection
        entries, has_ties = self._build_entries_with_ties(sorted_scores)

        return ClassificationResult(
            entries=tuple(entries),
            scope=self.scope,
            has_ties=has_ties,
            requires_tiebreaker=has_ties,
            metadata={
                "round_number": context.get("round_number") if context else None,
                "strategy": self.name,
            },
        )


class RoundRobinRoundClassificationStrategy(ClassificationStrategy):
    """Round-robin classification strategy.

    Same as Amalfi: matches won, then rack difference.
    May incorporate head-to-head tiebreaker in future.
    """

    name = "round_robin_round"
    display_name = "Round Robin Round"
    description = "Matches won, then rack difference"
    scope = ClassificationScope.ROUND

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """Get sort key: matches_won DESC, rack_diff DESC."""
        return (
            -score.matches_won,
            -score.rack_difference,
            score.player_id,
        )

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Calculate Round Robin classification."""
        sorted_scores = sorted(scores, key=self.get_sort_key)
        entries, has_ties = self._build_entries_with_ties(sorted_scores)

        return ClassificationResult(
            entries=tuple(entries),
            scope=self.scope,
            has_ties=has_ties,
            requires_tiebreaker=has_ties,
            metadata={
                "round_number": context.get("round_number") if context else None,
                "strategy": self.name,
            },
        )


__all__ = [
    "AmalfiRoundClassificationStrategy",
    "RandomRoundClassificationStrategy",
    "RoundRobinRoundClassificationStrategy",
]
