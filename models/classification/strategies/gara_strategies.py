"""
Module: models/classification/strategies/gara_strategies.py
Purpose: Classification strategies for final gara ranking
Data Structures: AmalfiGaraClassificationStrategy, RandomGaraClassificationStrategy
Dependencies: typing, .base
"""

from typing import Sequence, Dict, Any, Optional, Tuple

from .base import (
    ClassificationStrategy,
    ClassificationScope,
    ClassificationResult,
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
        """Sort key includes spot shot wins for tiebreaking.

        player_id intenzionalmente escluso: due giocatori altrimenti parimerito
        DEVONO ricevere la stessa chiave perché `_build_entries_with_ties`
        rilevi `has_ties=True` e SpareggioService possa attivare lo spareggio.
        """
        return (
            -score.matches_won,
            -score.rack_difference,
            -score.spot_shot_wins,  # Tiebreaker
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
        until_position = context.get("tiebreaker_until_position") if context else None

        # Ricostruisci entries usando il sort key di GARA (senza player_id, vedi
        # `get_sort_key`) per rilevare ties che il round strategy ha nascosto
        # includendo player_id. Bug 4 produzione 2026-05-20: senza questo, due
        # giocatori parimerito ricevono position diverse e SSR non scatta.
        rebuilt_scores = sorted(
            (e.score for e in previous_classification.entries),
            key=self.get_sort_key,
        )
        rebuilt_entries, rebuilt_has_ties = self._build_entries_with_ties(
            rebuilt_scores
        )

        if not rebuilt_has_ties or not spot_shot_results:
            return ClassificationResult(
                entries=tuple(rebuilt_entries),
                scope=self.scope,
                has_ties=rebuilt_has_ties,
                requires_tiebreaker=rebuilt_has_ties and not spot_shot_results,
                metadata={
                    "strategy": self.name,
                    "tiebreaker_applied": False,
                },
            )

        # Resolve ties using spot shot results
        resolved_entries = self._resolve_ties_with_spot_shot(
            tuple(rebuilt_entries), spot_shot_results, until_position
        )

        # Non tutti i pari merito sono spariti: oltre la soglia restano, e a
        # SSR uguale pure. Dichiarare `has_ties=False` mentirebbe a chi legge.
        pari_rimasti = any(e.tied_with for e in resolved_entries)

        return ClassificationResult(
            entries=tuple(resolved_entries),
            scope=self.scope,
            has_ties=pari_rimasti,
            requires_tiebreaker=False,
            metadata={
                "strategy": self.name,
                "tiebreaker_applied": True,
            },
        )


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
        """Sort key: racks_won DESC, spot_shot DESC.

        player_id intenzionalmente escluso: vedi nota in AmalfiGara.
        """
        return (
            -score.racks_won,
            -score.spot_shot_wins,
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
        until_position = context.get("tiebreaker_until_position") if context else None

        # Vedi nota in AmalfiGara.calculate: ricostruisci entries usando il
        # sort key di gara per rilevare i parimerito che il round strategy
        # nasconde tramite player_id nel sort key.
        rebuilt_scores = sorted(
            (e.score for e in previous_classification.entries),
            key=self.get_sort_key,
        )
        rebuilt_entries, rebuilt_has_ties = self._build_entries_with_ties(
            rebuilt_scores
        )

        if not rebuilt_has_ties or not spot_shot_results:
            return ClassificationResult(
                entries=tuple(rebuilt_entries),
                scope=self.scope,
                has_ties=rebuilt_has_ties,
                requires_tiebreaker=rebuilt_has_ties and not spot_shot_results,
                metadata={
                    "strategy": self.name,
                    "tiebreaker_applied": False,
                },
            )

        # Use parent class resolve method reapplied
        resolved_entries = self._resolve_ties_with_spot_shot(
            tuple(rebuilt_entries), spot_shot_results, until_position
        )

        # Non tutti i pari merito sono spariti: oltre la soglia restano, e a
        # SSR uguale pure. Dichiarare `has_ties=False` mentirebbe a chi legge.
        pari_rimasti = any(e.tied_with for e in resolved_entries)

        return ClassificationResult(
            entries=tuple(resolved_entries),
            scope=self.scope,
            has_ties=pari_rimasti,
            requires_tiebreaker=False,
            metadata={
                "strategy": self.name,
                "tiebreaker_applied": True,
            },
        )
