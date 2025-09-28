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
    """Random pairing strategy that prevents rematches."""

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
        """Select optimal trio minimizing trio history and avoiding rematches."""

        # Priority 1: Players who have never been in a trio
        never_trio = [p for p in players if trio_count.get(p, 0) == 0]

        if len(never_trio) >= 3:
            # Try combinations from players who never did trio
            for trio in combinations(never_trio, 3):
                if self._trio_has_no_internal_rematches(trio, previous_pairs):
                    return list(trio)

            # If no trio without rematches found, apply cascading fallback logic:
            # Get players with trio_count = 1
            trio_count_1 = [p for p in players if trio_count.get(p, 0) == 1]
            random.shuffle(trio_count_1)

            # 1. Try to find 2 players from never_trio who haven't played together
            #    + 1 from trio_count=1 who hasn't played with either
            valid_pairs_never_trio = []
            for p1, p2 in combinations(never_trio, 2):
                if tuple(sorted([p1, p2])) not in previous_pairs:
                    valid_pairs_never_trio.append((p1, p2))

            if valid_pairs_never_trio:
                random.shuffle(valid_pairs_never_trio)  # randomize order
                for p1, p2 in valid_pairs_never_trio:
                    for candidate in trio_count_1:
                        if (
                            tuple(sorted([p1, candidate])) not in previous_pairs
                            and tuple(sorted([p2, candidate])) not in previous_pairs
                        ):
                            return [p1, p2, candidate]

            # 2. If that fails, take 1 random from never_trio + 2 from trio_count=1
            #    (ensuring anti-rematch)
            if len(trio_count_1) >= 2:
                chosen_never = random.choice(never_trio)
                remaining_trio_count_1 = [p for p in trio_count_1]
                random.shuffle(remaining_trio_count_1)

                for i, p1 in enumerate(remaining_trio_count_1):
                    if tuple(sorted([chosen_never, p1])) not in previous_pairs:
                        for p2 in remaining_trio_count_1[i + 1 :]:
                            if (
                                tuple(sorted([chosen_never, p2])) not in previous_pairs
                                and tuple(sorted([p1, p2])) not in previous_pairs
                            ):
                                return [chosen_never, p1, p2]

            # 3. Ultimate fallback: pick first combination from never_trio anyway
            return list(list(combinations(never_trio, 3))[0])

        # Priority 2: Minimize total trio count and avoid internal rematches
        best_trio = None
        min_trio_count = float("inf")

        for trio in combinations(players, 3):
            total_trio_count = sum(trio_count.get(p, 0) for p in trio)

            if (
                total_trio_count < min_trio_count
                and self._trio_has_no_internal_rematches(trio, previous_pairs)
            ):
                best_trio = trio
                min_trio_count = total_trio_count

        # Fallback: return any trio if no optimal found
        if best_trio:
            return list(best_trio)
        else:
            return list(list(combinations(players, 3))[0])

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
