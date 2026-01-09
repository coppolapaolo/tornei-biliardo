"""
Module: models/matchmaking/strategies/random_anti_rematch.py
Purpose: Random pairing strategy with anti-rematch logic
Requirements: SPECIFICHE.md - Random pairing with rematch prevention
"""

from __future__ import annotations

import random
from itertools import combinations
from typing import Sequence, List, Tuple, Set, Dict, Any, TYPE_CHECKING
import networkx as nx

from .base import Pairing, BaseStrategy

if TYPE_CHECKING:
    from models.competition.models import Gara


class RandomAntiRematchStrategy(BaseStrategy):
    """Random pairing strategy that prevents rematches and ensures fair trio distribution.

    Features:
    - Random pairings with anti-rematch logic using NetworkX maximum matching
    - Trio selection (odd players) with multi-objective optimization:
        1. Fairness: minimize max(trio_count) for equal participation
        2. Anti-rematch: minimize internal rematches within trio
        3. Efficiency: minimize sum(trio_count) as tiebreaker
    - Automatic fallback to rematches when anti-rematch constraints prevent complete matching
    """

    # PairingStrategy metadata
    name = "random_anti_rematch"
    display_name = "Random Anti-Rematch"
    description = "Random pairing strategy with anti-rematch logic"
    min_players = 2
    max_players = None
    supports_byes = True
    requires_classification = False

    def __init__(self):
        super().__init__()
        self.strategy_name = "random_anti_rematch"

    def _generate_pairings(
        self, processed_data: Dict[str, Any], round_number: int
    ) -> Sequence[Pairing]:
        """Generate random pairings while avoiding rematches."""
        gara = processed_data["gara"]
        return self._generate_round_pairings(
            gara, round_number  # type: ignore[arg-type]
        )

    def _generate_round_pairings(self, gara: Gara, round_number: int) -> List[Pairing]:
        """Generate random pairings while avoiding rematches."""
        # Get active players
        inscriptions = list(gara.inscriptions)  # type: ignore[arg-type]
        active_inscriptions = [
            i for i in inscriptions if not getattr(i, "is_withdrawn", False)
        ]
        player_ids = [i.user_id for i in active_inscriptions]

        # Generate valid random pairings (encounter history handled internally)
        pairings = self._generate_valid_random_pairings(
            player_ids, set(), round_number, gara
        )

        return pairings

    def _generate_valid_random_pairings(
        self,
        player_ids: List[int],
        previous_pairings: Set[Tuple[int, int]],
        round_number: int,
        gara: object = None,
    ) -> List[Pairing]:
        """Generate random pairings using graph-based maximum matching approach."""

        if len(player_ids) < self.min_players:
            raise ValueError(
                f"{self.__class__.__name__} requires at least {self.min_players} "
                f"players, got {len(player_ids)}."
            )

        # Get complete encounter history (pairs + trio counts) if gara available
        if gara:
            all_previous_pairs, trio_count = self._get_encounter_history(
                gara, round_number  # type: ignore[arg-type]
            )
        else:
            # Fallback to legacy behavior for compatibility
            all_previous_pairs, trio_count = previous_pairings, {}

        remaining_players = player_ids.copy()
        pairings = []

        # Handle trio if odd number and trio is allowed
        if (len(remaining_players) % 2 == 1):
            if (self._should_use_trio(remaining_players, gara)):
                # Select optimal trio minimizing trio history and avoiding rematches
                trio_players = self._select_optimal_trio(
                    remaining_players, trio_count, all_previous_pairs
                )
                remaining_players = [
                    p for p in remaining_players if p not in trio_players
                ]
                pairings.append(
                    Pairing(players=tuple(trio_players), round_number=round_number)
                )
            else:
                remaining_players.append(self.BYE_PLAYER_ID)

        # Generate pairings for all players (now even number including potential BYE)
        if len(remaining_players) >= 2:
            # Generate all possible pairs (includes pairs with BYE_PLAYER_ID)
            all_pairs = list(combinations(remaining_players, 2))

            # Convert to canonical form (smaller ID first) to match
            # all_previous_pairs format
            canonical_pairs = [tuple(sorted(pair)) for pair in all_pairs]

            # Filter out rematches (pairs that have already been played)
            valid_pairs = [
                pair for pair in canonical_pairs if pair not in all_previous_pairs
            ]

            # If no valid pairs available, fall back to allowing rematches
            if not valid_pairs and len(remaining_players) >= 2:
                valid_pairs = canonical_pairs

            # Shuffle valid pairs to introduce randomness
            random.shuffle(valid_pairs)

            # Apply maximum matching algorithm
            selected_pairs = self._apply_maximum_matching(
                valid_pairs,
                remaining_players
            )

            # Check if matching is complete (covers all players)
            # If not, we need to retry with all pairs (allowing rematches)
            matched_players = set()
            for pair in selected_pairs:
                matched_players.update(pair)

            expected_pairs = len(remaining_players) // 2
            if len(selected_pairs) < expected_pairs:
                # Incomplete matching - retry with all pairs (including rematches)
                # but prioritize non-rematch pairs by putting them first
                all_pairs_shuffled = canonical_pairs.copy()
                random.shuffle(all_pairs_shuffled)
                # Put valid (non-rematch) pairs first to prefer them
                prioritized_pairs = valid_pairs + [
                    p for p in all_pairs_shuffled if p not in valid_pairs
                ]
                selected_pairs = self._apply_maximum_matching(
                    prioritized_pairs,
                    remaining_players
                )

            # Convert selected pairs to Pairing objects
            for pair in selected_pairs:
                if self.BYE_PLAYER_ID in pair:
                    # Convert algorithmic bye back to real bye
                    real_player = pair[0] if pair[1] == self.BYE_PLAYER_ID else pair[1]
                    pairings.append(
                        Pairing(
                            players=(real_player,),
                            is_bye=True,
                            round_number=round_number,
                        )
                    )
                else:
                    # Regular 1v1 match
                    pairings.append(
                        Pairing(players=pair, round_number=round_number)
                    )

        return pairings

    def _should_use_trio(self, player_ids: List[int], gara: object = None) -> bool:
        """Determine if trio should be used for odd number of players."""
        # Only consider trio for odd number of players
        if len(player_ids) % 2 == 0:
            return False

        # Check gara configuration first
        if gara is not None and hasattr(gara, "odd_number_policy"):
            odd_policy = getattr(gara, "odd_number_policy", "bye")
            if odd_policy == "bye" or odd_policy == "bye_with_challenge":
                return False  # Use bye when configured
            elif odd_policy == "trio":
                return True  # Use trio when configured for odd numbers

        # Fallback to original hardcoded logic if no configuration available
        # Use trio if we have 3, 5, or 7 players (as per specifications)
        # For larger odd numbers, use bye instead
        return len(player_ids) in [3, 5, 7]

    # New helper methods for graph-based algorithm (backward compatible)

    def _get_encounter_history(
        self, gara: "Gara", current_round: int
    ) -> Tuple[Set[Tuple[int, int]], Dict[int, int]]:
        """Get complete encounter history: all pairs + trio count per player.

        Returns:
            Tuple of (all_previous_pairs, trio_count_per_player)
        """
        from ...match.models import Match, TrioMatch

        previous_matches = (
            Match.query.filter_by(gara_id=gara.id)
            .filter(Match.round_number < current_round)  # type: ignore[attr-defined]
            .all()
        )

        previous_pairs = set()
        trio_count = {}

        for match in previous_matches:
            if match.is_trio:
                # Handle trio matches - get all combinations of 3 players
                trio_match = TrioMatch.query.filter_by(match_id=match.id).first()
                if trio_match:
                    players = [
                        trio_match.player1_id,
                        trio_match.player2_id,
                        trio_match.player3_id,
                    ]

                    # Update trio count for each player
                    for player_id in players:
                        trio_count[player_id] = trio_count.get(player_id, 0) + 1

                    # Add all possible pairs from the trio
                    for i in range(len(players)):
                        for j in range(i + 1, len(players)):
                            pair = tuple(sorted([players[i], players[j]]))
                            previous_pairs.add(pair)

            elif match.is_bye and match.player1_id:
                # Convert DB bye to algorithmic pair: (player, BYE_PLAYER_ID)
                pair = tuple(sorted([match.player1_id, self.BYE_PLAYER_ID]))
                previous_pairs.add(pair)

            elif match.player1_id and match.player2_id and not match.is_bye:
                # Standard 1v1 match
                pair = tuple(sorted([match.player1_id, match.player2_id]))
                previous_pairs.add(pair)

        return previous_pairs, trio_count

    def _select_optimal_trio(
        self,
        players: List[int],
        trio_count: Dict[int, int],
        previous_pairs: Set[Tuple[int, int]],
    ) -> List[int]:
        """Select optimal trio balancing fair distribution and anti-rematch.

        Multi-objective optimization with priority order:
        1. Minimize max(trio_count) in the trio (fairness - most important)
        2. Minimize internal rematches (anti-rematch)
        3. Minimize sum(trio_count) (secondary fairness)
        4. Random among equivalent options
        """
        # Shuffle players to add randomness among equivalent options
        shuffled_players = players.copy()
        random.shuffle(shuffled_players)

        # Evaluate all possible trios
        best_trio = None
        best_score = (float("inf"), float("inf"), float("inf"))

        for trio in combinations(shuffled_players, 3):
            # Calculate fairness score (lower is better)
            max_count = max(trio_count.get(p, 0) for p in trio)
            sum_count = sum(trio_count.get(p, 0) for p in trio)

            # Calculate rematch penalty (number of internal rematches, 0-3)
            rematch_penalty = self._count_internal_rematches(trio, previous_pairs)

            # Score tuple: (max_count, rematch_penalty, sum_count)
            # Prioritizes: fairness > anti-rematch > efficiency
            score = (max_count, rematch_penalty, sum_count)

            if score < best_score:
                best_trio = trio
                best_score = score

        if best_trio:
            return list(best_trio)

        # Fallback (should never reach here with valid players)
        return list(shuffled_players[:3])

    def _count_internal_rematches(
        self, trio: Tuple[int, ...], previous_pairs: Set[Tuple[int, int]]
    ) -> int:
        """Count number of internal rematches in a trio (0-3)."""
        count = 0
        players = list(trio)
        for i in range(len(players)):
            for j in range(i + 1, len(players)):
                pair = tuple(sorted([players[i], players[j]]))
                if pair in previous_pairs:
                    count += 1
        return count

    def _trio_has_no_internal_rematches(
        self, trio: Tuple[int, int, int], previous_pairs: Set[Tuple[int, int]]
    ) -> bool:
        """Check if trio players haven't played against each other before."""

        # Check all 3 pairs within the trio
        for i in range(len(trio)):
            for j in range(i + 1, len(trio)):
                pair = tuple(sorted([trio[i], trio[j]]))
                if pair in previous_pairs:
                    return False
        return True

    def _apply_maximum_matching(
        self, valid_pairs: List[Tuple[int, ...]], all_players: List[int]
    ) -> List[Tuple[int, int]]:
        """Apply maximum matching algorithm using NetworkX.

        Returns:
            List of selected pairs (maximum cardinality matching)
        """
        if not valid_pairs:
            return []

        # Filter to ensure all pairs have exactly 2 elements (for NetworkX)
        valid_edges = [(p1, p2) for p1, p2 in valid_pairs if len((p1, p2)) == 2]

        if not valid_edges:
            return []

        # Create graph with players as nodes and valid pairs as edges
        G = nx.Graph()
        G.add_nodes_from(all_players)
        G.add_edges_from(valid_edges)

        # Find maximum cardinality matching
        matching = nx.max_weight_matching(G, maxcardinality=True)

        # Convert to sorted tuples for consistency
        selected_pairs = [tuple(sorted(pair)) for pair in matching]
        return selected_pairs
