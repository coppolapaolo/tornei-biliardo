"""
Module: models/matchmaking/strategies/random_anti_rematch.py
Purpose: Random pairing strategy with anti-rematch logic
Spec: _bmad-output/implementation-artifacts/spec-random-anti-rematch.md
"""

from __future__ import annotations

import logging
import random
from itertools import combinations
from typing import Sequence, List, Tuple, Set, Dict, Any, TYPE_CHECKING
import networkx as nx

from .base import Pairing, BaseStrategy

if TYPE_CHECKING:
    from models.competition.models import Gara
    from models.matchmaking.registry import PairingContext


logger = logging.getLogger(__name__)


class RandomAntiRematchStrategy(BaseStrategy):
    """Random pairing strategy that prevents rematches and ensures fair trio distribution.

    Features:
    - Weighted NetworkX matching: non-rematch edges (weight=100) beat rematch edges
      (weight=1), so `max_weight_matching(G, maxcardinality=True)` picks a perfect
      matching that minimizes forced rematches.
    - Trio selection (odd players) with multi-objective optimization:
        1. Minimize max(trio_count) — protect the most-exposed player
        2. Minimize internal rematches within trio
        3. Minimize sum(trio_count) — secondary fairness
    - Audit trail: logger.warning when any rematch is forced.
    - Deterministic seeding via PairingContext (set_context): tests/replay use
      an isolated `random.Random` instance, no global state contamination.
    - Data source: PlayerEncounterService.get_encounter_matrix + get_trio_counts
      (cached, invalidated on match completion, coherent with ADR-002 cleanup).
    """

    name = "random_anti_rematch"
    display_name = "Random Anti-Rematch"
    description = "Random pairing strategy with anti-rematch logic"
    min_players = 2
    max_players = None
    supports_byes = True
    requires_classification = False

    # NetworkX edge weights. Ratio 100:1 guarantees that any non-rematch pair
    # outweighs up to 99 rematch pairs combined — safe for realistic tournaments.
    _WEIGHT_NON_REMATCH = 100
    _WEIGHT_REMATCH = 1

    def __init__(self):
        super().__init__()
        self.strategy_name = "random_anti_rematch"
        self._rng: random.Random = random.Random()

    def set_context(self, context: "PairingContext") -> None:
        """Inject deterministic RNG from PairingContext (see registry.py)."""
        self._rng = context.get_rng()

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
        inscriptions = list(gara.inscriptions)  # type: ignore[arg-type]
        active_inscriptions = [
            i
            for i in inscriptions
            if not getattr(i, "is_withdrawn", False)
            and not getattr(i, "is_waitlist", False)
        ]
        player_ids = [i.user_id for i in active_inscriptions]

        return self._generate_valid_random_pairings(
            player_ids, set(), round_number, gara
        )

    def _generate_valid_random_pairings(
        self,
        player_ids: List[int],
        previous_pairings: Set[Tuple[int, int]],
        round_number: int,
        gara: object = None,
    ) -> List[Pairing]:
        """Generate pairings via weighted maximum cardinality matching.

        Args:
            player_ids: Active player IDs to pair.
            previous_pairings: Legacy fallback when no gara is provided (tests only).
                When gara is provided, encounter history is loaded via
                PlayerEncounterService (cached, ADR-002 compliant).
            round_number: 1-based round number.
            gara: Optional Gara instance; enables real encounter-history lookup.
        """
        if len(player_ids) < self.min_players:
            raise ValueError(
                f"{self.__class__.__name__} requires at least {self.min_players} "
                f"players, got {len(player_ids)}."
            )

        if gara:
            all_previous_pairs, trio_count = self._get_encounter_history(
                gara, round_number  # type: ignore[arg-type]
            )
        else:
            # Legacy path for unit tests that provide encounter history inline.
            all_previous_pairs, trio_count = previous_pairings, {}

        remaining_players = player_ids.copy()
        pairings: List[Pairing] = []

        # Odd-number handling: trio or bye sentinel
        if len(remaining_players) % 2 == 1:
            if self._should_use_trio(remaining_players, gara):
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

        if len(remaining_players) >= 2:
            selected_pairs = self._apply_weighted_matching(
                remaining_players, all_previous_pairs, gara, round_number
            )

            for pair in selected_pairs:
                if self.BYE_PLAYER_ID in pair:
                    real_player = pair[0] if pair[1] == self.BYE_PLAYER_ID else pair[1]
                    pairings.append(
                        Pairing(
                            players=(real_player,),
                            is_bye=True,
                            round_number=round_number,
                        )
                    )
                else:
                    pairings.append(Pairing(players=pair, round_number=round_number))

        return pairings

    def _should_use_trio(self, player_ids: List[int], gara: object = None) -> bool:
        """Determine if trio should be used for odd number of players.

        Priority order:
        1. Even player count → False (trio impossible).
        2. gara.odd_number_policy explicitly set → use that value.
        3. No explicit policy → delegate to StrategyBehaviorConfig.get_default_odd_policy
           (considers gara.distance and ADR-005 constraints).
        4. No gara or distance available → False (safe default).
        """
        if len(player_ids) % 2 == 0:
            return False

        if gara is not None and hasattr(gara, "odd_number_policy"):
            odd_policy = getattr(gara, "odd_number_policy", None)
            if odd_policy == "trio":
                return True
            if odd_policy in ("bye", "bye_with_challenge", "no"):
                return False

        # No explicit policy: delegate to config defaults (ADR-005 aware).
        distance = getattr(gara, "distance", None) if gara is not None else None
        if distance is None:
            return False  # Without distance we can't validate ADR-005; default to bye.

        from models.matchmaking.configuration import (
            MatchmakingStrategy,
            OddNumberPolicy,
            get_strategy_behavior,
        )

        default_policy = get_strategy_behavior(
            MatchmakingStrategy.RANDOM
        ).get_default_odd_policy(distance)
        return default_policy == OddNumberPolicy.TRIO

    def _get_encounter_history(
        self, gara: "Gara", current_round: int
    ) -> Tuple[Set[Tuple[int, int]], Dict[int, int]]:
        """Load encounter history: pair set + trio counts.

        Hybrid data source (see spec-random-anti-rematch §Design Notes):
        - **trio_counts**: via `PlayerEncounterService.get_trio_counts(gara_id)`
          — cached with walkover filter. Coherent with Amalfi post-refactor
          (2026-04-19): walkover trios (total_racks_played == 0) don't penalize
          survivors in rotation.
        - **previous_pairs**: read directly from `Match.query` for previous
          rounds. Reason: Random creates all rounds at startup in a single
          transaction (`RoundService.start_first_round`, for round N the service
          calls `db.session.flush()` so the Match rows of rounds < N are visible
          but no `PlayerEncounter` exists yet — those are populated only on
          match completion. Using the service here would return an empty
          encounter_matrix for pre-created rounds, breaking anti-rematch.

        Known limitation: `RackService.reset_match_complete` deletes the
        `PlayerEncounter` (ADR-002) but keeps the Match row, so the pair stays
        in the history for Random. Documented in spec §7 as out-of-scope
        (requires UX decision on reset semantics for Random).
        """
        from models.classification.encounter_service import PlayerEncounterService

        trio_count = PlayerEncounterService.get_trio_counts(gara.id)
        previous_pairs = self._get_pair_history_from_matches(gara.id, current_round)

        return previous_pairs, trio_count

    def _get_pair_history_from_matches(
        self, gara_id: int, current_round: int
    ) -> Set[Tuple[int, int]]:
        """Build previous_pairs from Match rows of rounds < current_round.

        Includes:
        - 1v1 matches: `(p1, p2)` canonical pair
        - Bye matches: `(player, BYE_PLAYER_ID)` sentinel pair
        - Trio matches: 3 internal pairs `(p1,p2), (p1,p3), (p2,p3)`
        """
        from ...match.models import Match, TrioMatch

        previous_matches = (
            Match.query.filter_by(gara_id=gara_id)
            .filter(Match.round_number < current_round)  # type: ignore[attr-defined]
            .all()
        )

        previous_pairs: Set[Tuple[int, int]] = set()
        for match in previous_matches:
            if match.is_trio:
                trio_match = TrioMatch.query.filter_by(match_id=match.id).first()
                if trio_match:
                    players = [
                        trio_match.player1_id,
                        trio_match.player2_id,
                        trio_match.player3_id,
                    ]
                    for i in range(len(players)):
                        for j in range(i + 1, len(players)):
                            pair = tuple(sorted([players[i], players[j]]))
                            previous_pairs.add(pair)
            elif match.is_bye and match.player1_id:
                pair = tuple(sorted([match.player1_id, self.BYE_PLAYER_ID]))
                previous_pairs.add(pair)
            elif match.player1_id and match.player2_id and not match.is_bye:
                pair = tuple(sorted([match.player1_id, match.player2_id]))
                previous_pairs.add(pair)

        return previous_pairs

    def _select_optimal_trio(
        self,
        players: List[int],
        trio_count: Dict[int, int],
        previous_pairs: Set[Tuple[int, int]],
    ) -> List[int]:
        """Select optimal trio balancing fair distribution and anti-rematch.

        Multi-objective score (lower is better):
            (max(trio_count), rematch_penalty, sum(trio_count))
        Random tiebreak via pre-shuffle.
        """
        shuffled_players = players.copy()
        self._rng.shuffle(shuffled_players)

        best_trio: Tuple[int, ...] | None = None
        best_score: Tuple[float, float, float] = (
            float("inf"),
            float("inf"),
            float("inf"),
        )

        for trio in combinations(shuffled_players, 3):
            max_count = max(trio_count.get(p, 0) for p in trio)
            sum_count = sum(trio_count.get(p, 0) for p in trio)
            rematch_penalty = self._count_internal_rematches(trio, previous_pairs)
            score: Tuple[float, float, float] = (
                max_count,
                rematch_penalty,
                sum_count,
            )
            if score < best_score:
                best_trio = trio
                best_score = score

        if best_trio:
            return list(best_trio)
        return list(shuffled_players[:3])

    def _count_internal_rematches(
        self, trio: Tuple[int, ...], previous_pairs: Set[Tuple[int, int]]
    ) -> int:
        """Count rematches among the 3 internal pairs of a trio (0-3)."""
        count = 0
        players = list(trio)
        for i in range(len(players)):
            for j in range(i + 1, len(players)):
                pair = tuple(sorted([players[i], players[j]]))
                if pair in previous_pairs:
                    count += 1
        return count

    def _apply_weighted_matching(
        self,
        players: List[int],
        previous_pairs: Set[Tuple[int, int]],
        gara: object,
        round_number: int,
    ) -> List[Tuple[int, int]]:
        """Weighted maximum-cardinality matching.

        Non-rematch edges get weight=100, rematch edges get weight=1.
        `nx.max_weight_matching(G, maxcardinality=True)` prioritizes coverage
        (primary) then total weight (secondary), so it always picks the
        minimum-rematch perfect matching when one exists.

        Emits a logger.warning if any selected pair is a rematch — audit trail
        for tournament directors when anti-rematch is forced to degrade.
        """
        if len(players) < 2:
            return []

        all_pairs = list(combinations(players, 2))
        canonical_pairs = [tuple(sorted(pair)) for pair in all_pairs]

        # Shuffle for randomness among equivalent-weight options.
        shuffled_pairs = canonical_pairs.copy()
        self._rng.shuffle(shuffled_pairs)

        G = nx.Graph()
        G.add_nodes_from(players)
        for p1, p2 in shuffled_pairs:
            pair = (p1, p2)
            weight = (
                self._WEIGHT_REMATCH
                if pair in previous_pairs
                else self._WEIGHT_NON_REMATCH
            )
            G.add_edge(p1, p2, weight=weight)

        matching = nx.max_weight_matching(G, maxcardinality=True)
        selected_pairs = [tuple(sorted(pair)) for pair in matching]

        rematches = [p for p in selected_pairs if p in previous_pairs]
        if rematches:
            gara_id = getattr(gara, "id", None) if gara is not None else None
            logger.warning(
                "Random: rematch forzato in gara %s, turno %s: %d/%d pair "
                "erano già incontrati",
                gara_id,
                round_number,
                len(rematches),
                len(selected_pairs),
            )

        return selected_pairs
