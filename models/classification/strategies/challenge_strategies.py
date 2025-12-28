"""
Module: models/classification/strategies/challenge_strategies.py
Purpose: Classification strategies for challenges within gare
Data Structures: ChallengeClassificationStrategy
Dependencies: typing, .base
"""

from typing import Sequence, Dict, Any, Optional, Tuple

from .base import (
    ClassificationStrategy,
    ClassificationScope,
    ClassificationResult,
    PlayerScore,
)


class ChallengeClassificationStrategy(ClassificationStrategy):
    """Classification strategy for challenges within a gara.

    Challenges are side competitions that occur during a gara, such as:
    - Spot shot rally (used for tiebreaking)
    - Longest run challenge
    - Break and run challenge

    Ranking is based on challenge_score (higher is better).
    """

    name = "challenge"
    display_name = "Challenge Classification"
    description = "Ranks players by challenge performance"
    scope = ClassificationScope.CHALLENGE

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """Sort key: challenge_score DESC."""
        return (
            -score.challenge_score,
            score.player_id,
        )

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Calculate challenge classification.

        Args:
            scores: Player scores with challenge_score populated
            previous_classification: Not used for challenges
            context: Optional challenge metadata (challenge_id, challenge_type)

        Returns:
            ClassificationResult with challenge ranking
        """
        sorted_scores = sorted(scores, key=self.get_sort_key)
        entries, has_ties = self._build_entries_with_ties(sorted_scores)

        return ClassificationResult(
            entries=tuple(entries),
            scope=self.scope,
            has_ties=has_ties,
            requires_tiebreaker=False,  # Challenges don't have tiebreakers
            metadata={
                "strategy": self.name,
                "challenge_id": context.get("challenge_id") if context else None,
                "challenge_type": context.get("challenge_type") if context else None,
            },
        )


class SpotShotRallyClassificationStrategy(ClassificationStrategy):
    """Specific strategy for spot shot rally challenges.

    Spot shot rally is the primary tiebreaker mechanism in pool tournaments.
    Players compete in a series of spot shots, and wins determine ranking.
    """

    name = "spot_shot_rally"
    display_name = "Spot Shot Rally"
    description = "Ranks by spot shot rally wins"
    scope = ClassificationScope.CHALLENGE

    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """Sort key: spot_shot_wins DESC."""
        return (
            -score.spot_shot_wins,
            score.player_id,
        )

    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Calculate spot shot rally classification."""
        sorted_scores = sorted(scores, key=self.get_sort_key)
        entries, has_ties = self._build_entries_with_ties(sorted_scores)

        return ClassificationResult(
            entries=tuple(entries),
            scope=self.scope,
            has_ties=has_ties,
            requires_tiebreaker=False,
            metadata={
                "strategy": self.name,
                "gara_id": context.get("gara_id") if context else None,
            },
        )


__all__ = [
    "ChallengeClassificationStrategy",
    "SpotShotRallyClassificationStrategy",
]
