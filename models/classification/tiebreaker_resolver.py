"""
Module: models/classification/tiebreaker_resolver.py
Purpose: Resolves ties in classifications using tiebreaker results
Data Structures: TiebreakerContext, TiebreakerResolver
Dependencies: typing, dataclasses, .strategies.base
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List, Sequence

from .strategies.base import ClassificationEntry, PlayerScore


@dataclass
class TiebreakerContext:
    """Context for tiebreaker resolution.

    Contains information about a tie that needs resolution,
    including which players are tied and at what position.
    """

    tied_player_ids: List[int]
    position_at_stake: int
    scope: str  # "round", "gara", "campionato"
    gara_id: Optional[int] = None
    campionato_id: Optional[int] = None
    original_scores: Dict[int, PlayerScore] = field(default_factory=dict)

    def __post_init__(self):
        """Validate tied_player_ids has at least 2 players."""
        if len(self.tied_player_ids) < 2:
            raise ValueError("Tiebreaker requires at least 2 tied players")


class TiebreakerResolver:
    """Resolves ties in classifications using tiebreaker results.

    Primary tiebreaker mechanism is spot shot rally, where tied players
    compete in a series of spot shots. The player with more wins ranks higher.

    This resolver takes classification entries with ties and applies
    tiebreaker results to produce a resolved ordering.
    """

    def resolve(
        self,
        entries: Sequence[ClassificationEntry],
        tiebreaker_results: Dict[int, int],
    ) -> List[ClassificationEntry]:
        """Resolve ties in classification using tiebreaker results.

        Args:
            entries: Classification entries (may contain ties)
            tiebreaker_results: Dict mapping player_id -> tiebreaker score/wins

        Returns:
            List of entries with ties resolved to unique positions
        """
        if not entries:
            return []

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
                # No tie - update position and mark resolved
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
                # Resolve tie using tiebreaker results
                sorted_group = sorted(
                    group,
                    key=lambda e: (
                        -tiebreaker_results.get(e.player_id, 0),
                        e.player_id,  # Stability for equal tiebreaker scores
                    ),
                )

                # Check if tiebreaker actually resolved the tie
                tiebreaker_scores = [
                    tiebreaker_results.get(e.player_id, 0) for e in sorted_group
                ]
                fully_resolved = len(set(tiebreaker_scores)) == len(tiebreaker_scores)

                for entry in sorted_group:
                    resolved_entries.append(
                        ClassificationEntry(
                            player_id=entry.player_id,
                            position=current_position,
                            score=entry.score,
                            tied_with=(),  # Clear tied_with after resolution
                            tiebreaker_resolved=fully_resolved,
                        )
                    )
                    current_position += 1

        return resolved_entries

    def detect_ties(
        self,
        entries: Sequence[ClassificationEntry],
        until_position: int = 0,
    ) -> List[TiebreakerContext]:
        """Detect ties that need tiebreaker resolution.

        Args:
            entries: Classification entries to check
            until_position: Only check ties up to this position (0 = all)

        Returns:
            List of TiebreakerContext objects for each tie group
        """
        ties: List[TiebreakerContext] = []
        position_groups: Dict[int, List[int]] = {}

        for entry in entries:
            # Skip if beyond position limit
            if until_position > 0 and entry.position > until_position:
                continue

            if entry.position not in position_groups:
                position_groups[entry.position] = []
            position_groups[entry.position].append(entry.player_id)

        for pos, player_ids in position_groups.items():
            if len(player_ids) > 1:
                # Create original scores dict from entries
                original_scores = {
                    entry.player_id: entry.score
                    for entry in entries
                    if entry.player_id in player_ids
                }

                ties.append(
                    TiebreakerContext(
                        tied_player_ids=player_ids,
                        position_at_stake=pos,
                        scope="gara",  # Default, caller should update
                        original_scores=original_scores,
                    )
                )

        return ties

    def detect_ties_for_podium(
        self,
        entries: Sequence[ClassificationEntry],
    ) -> List[TiebreakerContext]:
        """Detect ties for podium positions (1st, 2nd, 3rd).

        Convenience method for common use case of resolving
        ties only for prize positions.

        Args:
            entries: Classification entries to check

        Returns:
            List of TiebreakerContext for podium ties
        """
        return self.detect_ties(entries, until_position=3)

    def needs_resolution(
        self,
        entries: Sequence[ClassificationEntry],
    ) -> bool:
        """Check if any ties exist in the classification.

        Args:
            entries: Classification entries to check

        Returns:
            True if any entry has tied_with populated
        """
        return any(entry.is_tied() for entry in entries)

    def get_tied_groups(
        self,
        entries: Sequence[ClassificationEntry],
    ) -> Dict[int, List[int]]:
        """Get mapping of position -> tied player IDs.

        Args:
            entries: Classification entries to analyze

        Returns:
            Dict with positions as keys and list of tied player IDs as values
        """
        groups: Dict[int, List[int]] = {}

        for entry in entries:
            if entry.position not in groups:
                groups[entry.position] = []
            groups[entry.position].append(entry.player_id)

        # Filter to only tied positions
        return {pos: pids for pos, pids in groups.items() if len(pids) > 1}

    def create_placeholder_tiebreaker(
        self,
        tied_player_ids: List[int],
    ) -> Dict[int, int]:
        """Create placeholder tiebreaker results using player ID order.

        Used when no spot shot rally has been performed yet.
        Lower player ID wins tie (arbitrary but consistent).

        Args:
            tied_player_ids: List of tied player IDs

        Returns:
            Dict mapping player_id -> artificial score
        """
        sorted_ids = sorted(tied_player_ids)
        return {pid: len(sorted_ids) - i for i, pid in enumerate(sorted_ids)}


__all__ = [
    "TiebreakerContext",
    "TiebreakerResolver",
]
