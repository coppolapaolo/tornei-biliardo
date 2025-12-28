"""
Module: models/classification/strategies/gara_strategies.py
Purpose: Classification strategies for final gara ranking
Data Structures: AmalfiGaraClassificationStrategy, RandomGaraClassificationStrategy
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


class AmalfiGaraClassificationStrategy(ClassificationStrategy):
    """Final Amalfi gara classification strategy.

    Takes the final round classification and resolves any ties using
    spot shot rally results. The final gara classification determines:
    - Prize positions
    - Campionato points (if part of a campionato)

    Composition: final_round_classification + spot_shot_results → final_ranking
    """

    name = "amalfi_gara"
    display_name = "Amalfi Gara Final"
    description = "Final round classification with spot shot tiebreaker"
    scope = ClassificationScope.GARA

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """Sort key includes spot shot wins for tiebreaking."""
        return (
            -score.matches_won,
            -score.rack_difference,
            -score.spot_shot_wins,  # Tiebreaker
            score.player_id,
        )

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Calculate final Amalfi gara classification.

        For Amalfi, the final gara classification is typically the last round's
        classification, with ties resolved by spot shot rally.

        Args:
            scores: Final scores (can be empty if using previous_classification)
            previous_classification: Final round classification (required)
            context: Should contain 'spot_shot_results' dict if ties need resolution

        Returns:
            ClassificationResult with resolved positions
        """
        if previous_classification is None:
            raise ValueError("Amalfi gara requires final round classification")

        # Get spot shot results for tiebreaking
        spot_shot_results = context.get("spot_shot_results") if context else None

        if not previous_classification.has_ties or not spot_shot_results:
            # No ties or no tiebreaker data - use previous classification as-is
            return ClassificationResult(
                entries=previous_classification.entries,
                scope=self.scope,
                has_ties=previous_classification.has_ties,
                requires_tiebreaker=previous_classification.has_ties
                and not spot_shot_results,
                metadata={
                    "strategy": self.name,
                    "tiebreaker_applied": False,
                },
            )

        # Resolve ties using spot shot results
        resolved_entries = self._resolve_ties_with_spot_shot(
            previous_classification.entries, spot_shot_results
        )

        return ClassificationResult(
            entries=tuple(resolved_entries),
            scope=self.scope,
            has_ties=False,  # Ties resolved
            requires_tiebreaker=False,
            metadata={
                "strategy": self.name,
                "tiebreaker_applied": True,
            },
        )

    def _resolve_ties_with_spot_shot(
        self,
        entries: Tuple[ClassificationEntry, ...],
        spot_shot_results: Dict[int, int],
    ) -> List[ClassificationEntry]:
        """Resolve tied entries using spot shot rally results.

        Args:
            entries: Classification entries with potential ties
            spot_shot_results: Dict mapping player_id -> spot shot wins

        Returns:
            List of entries with ties resolved
        """
        # Group entries by position (find ties)
        position_groups: Dict[int, List[ClassificationEntry]] = {}
        for entry in entries:
            if entry.position not in position_groups:
                position_groups[entry.position] = []
            position_groups[entry.position].append(entry)

        resolved_entries: List[ClassificationEntry] = []
        current_position = 1

        for pos in sorted(position_groups.keys()):
            group = position_groups[pos]

            if len(group) == 1:
                # No tie - keep entry with updated position
                entry = group[0]
                resolved_entries.append(
                    ClassificationEntry(
                        player_id=entry.player_id,
                        position=current_position,
                        score=entry.score,
                        tied_with=(),
                        tiebreaker_resolved=True,
                    )
                )
                current_position += 1
            else:
                # Resolve tie using spot shot results
                sorted_group = sorted(
                    group,
                    key=lambda e: (
                        -spot_shot_results.get(e.player_id, 0),
                        e.player_id,
                    ),
                )

                for entry in sorted_group:
                    resolved_entries.append(
                        ClassificationEntry(
                            player_id=entry.player_id,
                            position=current_position,
                            score=entry.score,
                            tied_with=(),
                            tiebreaker_resolved=True,
                        )
                    )
                    current_position += 1

        return resolved_entries


class RandomGaraClassificationStrategy(ClassificationStrategy):
    """Final Random gara classification strategy.

    Similar to Amalfi but with Random-specific ranking criteria.
    Total racks won is primary, with spot shot for ties.
    """

    name = "random_gara"
    display_name = "Random Gara Final"
    description = "Total racks with spot shot tiebreaker"
    scope = ClassificationScope.GARA

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
        """Calculate final Random gara classification.

        Args:
            scores: Final scores with spot_shot_wins populated
            previous_classification: Final round classification
            context: Should contain 'spot_shot_results' if needed

        Returns:
            ClassificationResult with resolved positions
        """
        if previous_classification is None:
            raise ValueError("Random gara requires final round classification")

        spot_shot_results = context.get("spot_shot_results") if context else None

        if not previous_classification.has_ties or not spot_shot_results:
            return ClassificationResult(
                entries=previous_classification.entries,
                scope=self.scope,
                has_ties=previous_classification.has_ties,
                requires_tiebreaker=previous_classification.has_ties
                and not spot_shot_results,
                metadata={
                    "strategy": self.name,
                    "tiebreaker_applied": False,
                },
            )

        # Use parent class resolve method reapplied
        resolved_entries = self._resolve_ties_with_spot_shot(
            previous_classification.entries, spot_shot_results
        )

        return ClassificationResult(
            entries=tuple(resolved_entries),
            scope=self.scope,
            has_ties=False,
            requires_tiebreaker=False,
            metadata={
                "strategy": self.name,
                "tiebreaker_applied": True,
            },
        )

    def _resolve_ties_with_spot_shot(
        self,
        entries: Tuple[ClassificationEntry, ...],
        spot_shot_results: Dict[int, int],
    ) -> List[ClassificationEntry]:
        """Resolve tied entries using spot shot rally results."""
        position_groups: Dict[int, List[ClassificationEntry]] = {}
        for entry in entries:
            if entry.position not in position_groups:
                position_groups[entry.position] = []
            position_groups[entry.position].append(entry)

        resolved_entries: List[ClassificationEntry] = []
        current_position = 1

        for pos in sorted(position_groups.keys()):
            group = position_groups[pos]

            if len(group) == 1:
                entry = group[0]
                resolved_entries.append(
                    ClassificationEntry(
                        player_id=entry.player_id,
                        position=current_position,
                        score=entry.score,
                        tied_with=(),
                        tiebreaker_resolved=True,
                    )
                )
                current_position += 1
            else:
                sorted_group = sorted(
                    group,
                    key=lambda e: (
                        -spot_shot_results.get(e.player_id, 0),
                        e.player_id,
                    ),
                )

                for entry in sorted_group:
                    resolved_entries.append(
                        ClassificationEntry(
                            player_id=entry.player_id,
                            position=current_position,
                            score=entry.score,
                            tied_with=(),
                            tiebreaker_resolved=True,
                        )
                    )
                    current_position += 1

        return resolved_entries


__all__ = [
    "AmalfiGaraClassificationStrategy",
    "RandomGaraClassificationStrategy",
]
