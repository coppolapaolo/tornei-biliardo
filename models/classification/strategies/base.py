"""
Module: models/classification/strategies/base.py
Purpose: Base classes and value objects for classification strategies
Data Structures: ClassificationScope, PlayerScore, ClassificationEntry,
                 ClassificationResult, ClassificationStrategy
Dependencies: abc, dataclasses, typing, enum
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Sequence, Dict, Any, Optional, List, Tuple
from enum import Enum


class ClassificationScope(Enum):
    """Scope at which classification operates."""

    ROUND = "round"  # After each round within a gara
    GARA = "gara"  # Final gara classification
    CAMPIONATO = "campionato"  # Overall campionato classification
    CHALLENGE = "challenge"  # Challenge-specific classification


@dataclass(frozen=True)
class PlayerScore:
    """Immutable value object representing a player's score data.

    This is the input to classification strategies - aggregated stats
    from matches that will be ranked according to strategy-specific criteria.
    """

    player_id: int
    matches_won: int = 0
    matches_lost: int = 0
    racks_won: int = 0
    racks_lost: int = 0
    rack_difference: int = 0
    sets_won: int = 0  # For multi-set matches
    sets_lost: int = 0
    points: int = 0  # For point-based systems
    spot_shot_wins: int = 0  # For tiebreakers
    challenge_score: int = 0  # For challenge classifications
    previous_position: Optional[int] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)

    def with_previous_position(self, position: int) -> "PlayerScore":
        """Return new PlayerScore with previous_position set."""
        return PlayerScore(
            player_id=self.player_id,
            matches_won=self.matches_won,
            matches_lost=self.matches_lost,
            racks_won=self.racks_won,
            racks_lost=self.racks_lost,
            rack_difference=self.rack_difference,
            sets_won=self.sets_won,
            sets_lost=self.sets_lost,
            points=self.points,
            spot_shot_wins=self.spot_shot_wins,
            challenge_score=self.challenge_score,
            previous_position=position,
            extra_data=self.extra_data,
        )


@dataclass(frozen=True)
class ClassificationEntry:
    """Immutable value object representing a classification position.

    This is a single row in the classification table - a player with
    their position and the score data that determined it.
    """

    player_id: int
    position: int
    score: PlayerScore
    tied_with: Tuple[int, ...] = ()  # Player IDs of tied players
    tiebreaker_resolved: bool = True

    def is_tied(self) -> bool:
        """Check if this entry is tied with other players."""
        return len(self.tied_with) > 0


@dataclass(frozen=True)
class ClassificationResult:
    """Immutable result of classification calculation.

    Contains the full ordered ranking plus metadata about ties
    and whether tiebreaker resolution is needed.
    """

    entries: Tuple[ClassificationEntry, ...]
    scope: ClassificationScope
    has_ties: bool = False
    requires_tiebreaker: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_position(self, player_id: int) -> Optional[int]:
        """Get position for a specific player."""
        for entry in self.entries:
            if entry.player_id == player_id:
                return entry.position
        return None

    def get_entry(self, player_id: int) -> Optional[ClassificationEntry]:
        """Get classification entry for a specific player."""
        for entry in self.entries:
            if entry.player_id == player_id:
                return entry
        return None

    def get_tied_groups(self) -> List[List[int]]:
        """Get groups of tied players."""
        groups: Dict[int, List[int]] = {}
        for entry in self.entries:
            if entry.is_tied():
                # Use first tied player ID as group key
                key = min(entry.player_id, *entry.tied_with)
                if key not in groups:
                    groups[key] = []
                if entry.player_id not in groups[key]:
                    groups[key].append(entry.player_id)
        return list(groups.values())


class ClassificationStrategy(ABC):
    """Abstract base class for classification strategies.

    Defines the contract for calculating player rankings at various scopes
    (round, gara, campionato, challenge). Strategies implement different
    ranking criteria (e.g., matches won vs racks won) and tiebreaker rules.

    The core composable design allows building classifications iteratively:
    - First round: calculate(scores) with no previous
    - Later rounds: calculate(new_scores, previous_classification)
    - Final gara: calculate([], final_round_classification, spot_shot_results)
    """

    # Strategy metadata - subclasses should override
    name: str = "base"
    display_name: str = "Base Strategy"
    description: str = "Abstract classification strategy"
    scope: ClassificationScope = ClassificationScope.ROUND

    @abstractmethod
    def calculate(
        self,
        scores: Sequence[PlayerScore],
        previous_classification: Optional[ClassificationResult] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Calculate classification from scores.

        Core composable method: takes scores OR previous classification + new scores.

        Args:
            scores: Current round/gara scores to incorporate
            previous_classification: Optional previous classification to compose with
            context: Additional context (gara_id, round_number, spot_shot_results, etc.)

        Returns:
            ClassificationResult with ordered entries
        """
        ...

    @abstractmethod
    def get_sort_key(self, score: PlayerScore) -> Tuple[Any, ...]:
        """Get the sort key tuple for ordering players.

        Returns a tuple of values used for sorting (most important first).
        Use negative values for descending sort, positive for ascending.

        Example for Amalfi:
            return (-score.matches_won, -score.rack_difference, score.previous_position or 999)
        """
        ...

    def resolve_ties(
        self,
        tied_players: Sequence[PlayerScore],
        tiebreaker_results: Optional[Dict[int, int]] = None,
    ) -> Sequence[PlayerScore]:
        """Resolve ties between players using tiebreaker data.

        Default implementation uses tiebreaker_results if provided.
        Subclasses can override for custom tie resolution.

        Args:
            tied_players: Players who are tied by the main sort key
            tiebreaker_results: Optional mapping of player_id -> tiebreaker score

        Returns:
            Players reordered by tiebreaker
        """
        if not tiebreaker_results:
            return tied_players

        # Sort by tiebreaker results (higher is better)
        return sorted(
            tied_players, key=lambda s: -tiebreaker_results.get(s.player_id, 0)
        )

    def _enrich_with_previous(
        self,
        scores: Sequence[PlayerScore],
        previous: Optional[ClassificationResult],
    ) -> List[PlayerScore]:
        """Enrich scores with previous positions from prior classification."""
        if not previous:
            return list(scores)

        enriched = []
        for score in scores:
            prev_position = previous.get_position(score.player_id)
            if prev_position is not None:
                enriched.append(score.with_previous_position(prev_position))
            else:
                enriched.append(score)
        return enriched

    def _build_entries_with_ties(
        self,
        sorted_scores: Sequence[PlayerScore],
    ) -> Tuple[List[ClassificationEntry], bool]:
        """Build classification entries detecting ties based on sort key.

        Args:
            sorted_scores: Already sorted list of player scores

        Returns:
            Tuple of (entries list, has_ties boolean)
        """
        if not sorted_scores:
            return [], False

        entries: List[ClassificationEntry] = []
        has_ties = False
        current_position = 1

        i = 0
        while i < len(sorted_scores):
            score = sorted_scores[i]
            current_key = self.get_sort_key(score)

            # Find all players with same sort key (tied)
            tied_indices = [i]
            j = i + 1
            while j < len(sorted_scores):
                next_key = self.get_sort_key(sorted_scores[j])
                if next_key == current_key:
                    tied_indices.append(j)
                    j += 1
                else:
                    break

            if len(tied_indices) > 1:
                # Multiple players tied
                has_ties = True
                tied_player_ids = tuple(
                    sorted_scores[idx].player_id for idx in tied_indices
                )

                for idx in tied_indices:
                    tied_score = sorted_scores[idx]
                    # Exclude self from tied_with
                    others = tuple(
                        pid for pid in tied_player_ids if pid != tied_score.player_id
                    )
                    entries.append(
                        ClassificationEntry(
                            player_id=tied_score.player_id,
                            position=current_position,  # All tied get same position
                            score=tied_score,
                            tied_with=others,
                            tiebreaker_resolved=False,
                        )
                    )
            else:
                # Single player at this position
                entries.append(
                    ClassificationEntry(
                        player_id=score.player_id,
                        position=current_position,
                        score=score,
                        tied_with=(),
                        tiebreaker_resolved=True,
                    )
                )

            # Move position forward by number of players at this position
            current_position += len(tied_indices)
            i = j

        return entries, has_ties


__all__ = [
    "ClassificationScope",
    "PlayerScore",
    "ClassificationEntry",
    "ClassificationResult",
    "ClassificationStrategy",
]
