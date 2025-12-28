"""
Module: models/classification/strategies/campionato_strategies.py
Purpose: Classification strategies for overall campionato ranking
Data Structures: AmalfiCampionatoClassificationStrategy, RandomCampionatoClassificationStrategy,
                 PointBasedCampionatoClassificationStrategy
Dependencies: typing, .base
"""

from typing import Sequence, Dict, Any, Optional, Tuple, List

from .base import (
    ClassificationStrategy,
    ClassificationScope,
    ClassificationResult,
    ClassificationEntry,
    PlayerScore,
)


class AmalfiCampionatoClassificationStrategy(ClassificationStrategy):
    """Amalfi campionato overall classification strategy.

    Aggregates results across all gare in a campionato.

    Ranking criteria (in priority order):
    1. Matches won (descending) - total wins across all gare
    2. Rack difference (descending) - total rack differential
    3. Spot shot rally wins (for ties)
    """

    name = "amalfi_campionato"
    display_name = "Amalfi Campionato"
    description = "Matches won, rack difference, spot shot wins"
    scope = ClassificationScope.CAMPIONATO

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """Sort key: matches_won DESC, rack_diff DESC, spot_shot DESC."""
        return (
            -score.matches_won,
            -score.rack_difference,
            -score.spot_shot_wins,
            score.player_id,
        )

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Calculate Amalfi campionato classification.

        Args:
            scores: Aggregated scores across all gare
            previous_classification: Not typically used for campionato
            context: Optional metadata

        Returns:
            ClassificationResult with overall campionato ranking
        """
        sorted_scores = sorted(scores, key=self.get_sort_key)
        entries, has_ties = self._build_entries_with_ties(sorted_scores)

        return ClassificationResult(
            entries=tuple(entries),
            scope=self.scope,
            has_ties=has_ties,
            requires_tiebreaker=has_ties,
            metadata={
                "strategy": self.name,
                "campionato_id": context.get("campionato_id") if context else None,
            },
        )


class RandomCampionatoClassificationStrategy(ClassificationStrategy):
    """Random campionato overall classification strategy.

    Ranking criteria (in priority order):
    1. Total racks won (descending)
    2. Spot shot rally wins (for ties)

    Different from Amalfi: prioritizes total scoring over wins.
    """

    name = "random_campionato"
    display_name = "Random Campionato"
    description = "Total racks won, spot shot wins"
    scope = ClassificationScope.CAMPIONATO

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """Sort key: racks_won DESC, spot_shot DESC."""
        return (
            -score.racks_won,
            -score.spot_shot_wins,
            score.player_id,
        )

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Calculate Random campionato classification."""
        sorted_scores = sorted(scores, key=self.get_sort_key)
        entries, has_ties = self._build_entries_with_ties(sorted_scores)

        return ClassificationResult(
            entries=tuple(entries),
            scope=self.scope,
            has_ties=has_ties,
            requires_tiebreaker=has_ties,
            metadata={
                "strategy": self.name,
                "campionato_id": context.get("campionato_id") if context else None,
            },
        )


class PointBasedCampionatoClassificationStrategy(ClassificationStrategy):
    """Point-based campionato classification strategy.

    Each gara position awards fixed points (configurable).
    Final ranking is sum of points from best n-1 gare (drop worst).

    Example point table:
    - 1st place: 1000 points
    - 2nd place: 800 points
    - 3rd-4th place: 500 points
    - 5th-6th place: 300 points
    - 7th-8th place: 200 points
    - 9th+ place: 100 points
    """

    name = "point_based_campionato"
    display_name = "Point-Based Campionato"
    description = "Position points summed, drop worst gara"
    scope = ClassificationScope.CAMPIONATO

    # Default point allocation
    DEFAULT_POINTS = {
        1: 1000,
        2: 800,
        3: 500,
        4: 500,
        5: 300,
        6: 300,
        7: 200,
        8: 200,
    }
    DEFAULT_OTHER = 100  # Points for positions not in table

    def __init__(
        self,
        points_table: Optional[Dict[int, int]] = None,
        drop_worst: int = 1,
    ):
        """Initialize point-based strategy.

        Args:
            points_table: Dict mapping position -> points (default: standard table)
            drop_worst: Number of worst results to drop (default: 1)
        """
        super().__init__()
        self.points_table = points_table or self.DEFAULT_POINTS
        self.drop_worst = drop_worst

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """Sort key: points DESC."""
        return (
            -score.points,
            score.player_id,
        )

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Calculate point-based campionato classification.

        Args:
            scores: Basic player scores (points will be calculated)
            previous_classification: Not used
            context: Must contain 'gara_results': Dict[player_id, List[position]]

        Returns:
            ClassificationResult with point-based ranking
        """
        gara_results = context.get("gara_results", {}) if context else {}

        # Calculate points for each player
        enriched_scores = []
        for score in scores:
            positions = gara_results.get(score.player_id, [])
            total_points = self._calculate_total_points(positions)

            enriched_scores.append(
                PlayerScore(
                    player_id=score.player_id,
                    matches_won=score.matches_won,
                    matches_lost=score.matches_lost,
                    racks_won=score.racks_won,
                    racks_lost=score.racks_lost,
                    rack_difference=score.rack_difference,
                    points=total_points,
                )
            )

        sorted_scores = sorted(enriched_scores, key=self.get_sort_key)
        entries, has_ties = self._build_entries_with_ties(sorted_scores)

        return ClassificationResult(
            entries=tuple(entries),
            scope=self.scope,
            has_ties=has_ties,
            requires_tiebreaker=has_ties,
            metadata={
                "strategy": self.name,
                "campionato_id": context.get("campionato_id") if context else None,
                "points_table": self.points_table,
                "drop_worst": self.drop_worst,
            },
        )

    def _calculate_total_points(self, positions: List[int]) -> int:
        """Calculate total points from positions, dropping worst.

        Args:
            positions: List of positions achieved in each gara

        Returns:
            Total points after dropping worst results
        """
        if not positions:
            return 0

        # Convert positions to points
        gara_points = [
            self.points_table.get(pos, self.DEFAULT_OTHER) for pos in positions
        ]

        # Sort descending to keep best results
        gara_points.sort(reverse=True)

        # Drop worst results
        if self.drop_worst > 0 and len(gara_points) > self.drop_worst:
            counted_points = gara_points[: -self.drop_worst]
        else:
            counted_points = gara_points

        return sum(counted_points)

    def get_points_for_position(self, position: int) -> int:
        """Get points awarded for a specific position.

        Args:
            position: Finishing position (1-based)

        Returns:
            Points awarded for that position
        """
        return self.points_table.get(position, self.DEFAULT_OTHER)


__all__ = [
    "AmalfiCampionatoClassificationStrategy",
    "RandomCampionatoClassificationStrategy",
    "PointBasedCampionatoClassificationStrategy",
]
