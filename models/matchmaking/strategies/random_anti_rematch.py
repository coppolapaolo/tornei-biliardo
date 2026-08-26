"""
Module: models/matchmaking/strategies/random_anti_rematch.py
Purpose: Random pairing strategy with anti-rematch logic
Spec: _bmad-output/implementation-artifacts/spec-random-anti-rematch.md
"""

from __future__ import annotations

import logging
import math
import random
import time
from itertools import combinations
from typing import Optional, Sequence, List, Tuple, Set, Dict, Any, TYPE_CHECKING
import networkx as nx

from .base import Pairing, BaseStrategy

if TYPE_CHECKING:
    from models.competition.models import Gara
    from models.matchmaking.registry import PairingContext


logger = logging.getLogger(__name__)

# Trio-search deadline (ramo C). Per N ≤ 9 e rounds ≤ 8 (scenari pratici) la
# ricerca completa termina largamente sotto questa soglia. Oltre il deadline
# si ricade sul path incrementale (`_apply_weighted_matching` per round).
_TRIO_SEARCH_DEADLINE_MS = 8000


class RandomAntiRematchStrategy(BaseStrategy):
    """Random pairing strategy preventing rematches, with fair trio distribution.

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
    # L'ordine di partenza è il sorteggio stesso: si legge dagli accoppiamenti
    # del primo turno, senza consumare l'RNG deterministico dello schedule.
    persists_seeding = True

    # NetworkX edge weights. Ratio 100:1 guarantees that any non-rematch pair
    # outweighs up to 99 rematch pairs combined — safe for realistic tournaments.
    _WEIGHT_NON_REMATCH = 100
    _WEIGHT_REMATCH = 1

    def __init__(self):
        super().__init__()
        self.strategy_name = "random_anti_rematch"
        self._rng: random.Random = random.Random()
        # Cache della pre-generazione completa dello schedule, condivisa tra
        # le `create_round` consecutive di `start_first_round`. Vedi
        # `_get_or_build_schedule`. Una signature non-matching la invalida.
        self._precomputed_schedule: Optional[List[List[Pairing]]] = None
        self._schedule_signature: Optional[Tuple[Any, ...]] = None

    def set_context(self, context: "PairingContext") -> None:
        """Inject deterministic RNG from PairingContext (see registry.py)."""
        self._rng = context.get_rng()
        # Nuovo context = potenzialmente nuovi seed/RNG: scarta la cache.
        self._precomputed_schedule = None
        self._schedule_signature = None

    def _generate_pairings(
        self, processed_data: Dict[str, Any], round_number: int
    ) -> Sequence[Pairing]:
        """Generate random pairings while avoiding rematches."""
        gara = processed_data["gara"]
        return self._generate_round_pairings(
            gara, round_number  # type: ignore[arg-type]
        )

    def _generate_round_pairings(self, gara: Gara, round_number: int) -> List[Pairing]:
        """Generate random pairings while avoiding rematches.

        Path preferito: pre-generazione globale dello schedule (vedi
        `_get_or_build_schedule`) — circle method per N pari / dispari+BYE,
        branch-and-bound search per N dispari+TRIO. Fallback automatico al
        path incrementale (`_apply_weighted_matching` per round) se la
        pre-generazione non è applicabile o supera il deadline.
        """
        inscriptions = list(gara.inscriptions)  # type: ignore[arg-type]
        active_inscriptions = [
            i
            for i in inscriptions
            if not getattr(i, "is_withdrawn", False)
            and not getattr(i, "is_waitlist", False)
        ]
        player_ids = [i.user_id for i in active_inscriptions]

        schedule = self._get_or_build_schedule(gara, player_ids)
        if schedule is not None and 1 <= round_number <= len(schedule):
            return list(schedule[round_number - 1])

        pairings = self._generate_valid_random_pairings(
            player_ids, set(), round_number, gara
        )
        if round_number == 1:
            # Path incrementale: qui i turni nascono uno alla volta leggendo
            # gli incontri già giocati, quindi lo scambio sul primo turno non
            # può contraddire i successivi — sono ancora da generare.
            from models.matchmaking import bye_preference

            pairings = bye_preference.apply_to_round(
                pairings, bye_preference.preferred_bye_player(gara)
            )
        return pairings

    def _get_or_build_schedule(
        self, gara: Gara, player_ids: List[int]
    ) -> Optional[List[List[Pairing]]]:
        """Return cached schedule if signature matches, else build at first call.

        Restituisce `None` se la pre-generazione non è applicabile (es. troppi
        round per round-robin, search trio fallita entro il deadline). In quel
        caso il caller cade nel path incrementale. La signature è cached anche
        quando il risultato è None, per evitare di ritentare la search a ogni
        round.
        """
        n_rounds = getattr(gara, "rounds_count", None)
        if not isinstance(n_rounds, int) or n_rounds < 1:
            return None

        from models.matchmaking import bye_preference

        preferred_bye = bye_preference.preferred_bye_player(gara)

        signature = (
            getattr(gara, "id", None),
            tuple(sorted(player_ids)),
            n_rounds,
            getattr(gara, "odd_number_policy", None),
            preferred_bye,
        )
        if self._schedule_signature == signature:
            return self._precomputed_schedule

        schedule = self._pre_generate_full_schedule(gara, player_ids, n_rounds)
        if schedule is not None:
            schedule = self._relabel_for_preferred_bye(schedule, preferred_bye)
        self._precomputed_schedule = schedule
        self._schedule_signature = signature
        return schedule

    def _relabel_for_preferred_bye(
        self, schedule: List[List[Pairing]], preferred_bye: Optional[int]
    ) -> List[List[Pairing]]:
        """Porta la X del primo turno al giocatore scelto dal direttore.

        Lo scambio è su **tutto** lo schedule, non sul solo primo turno. Qui i
        turni sono già tutti generati e ogni giocatore ha una X sola: spostare
        la X del turno 1 senza toccare il resto ne regalerebbe due al
        destinatario e introdurrebbe un reincontro. Scambiare le identità
        ovunque è invece una pura rietichettatura — la struttura dipende dalle
        posizioni, non dai nomi — e conserva tutte le garanzie del sorteggio.
        """
        from models.matchmaking import bye_preference

        if preferred_bye is None or not schedule:
            return schedule

        drawn = bye_preference.bye_player_in(schedule[0])
        if drawn is None or drawn == preferred_bye:
            return schedule

        return [
            bye_preference.swap_players(round_pairings, drawn, preferred_bye)
            for round_pairings in schedule
        ]

    def _pre_generate_full_schedule(
        self, gara: Gara, player_ids: List[int], n_rounds: int
    ) -> Optional[List[List[Pairing]]]:
        """Dispatch fra i tre rami (A: pari, B: dispari+BYE, C: dispari+TRIO).

        Ritorna `None` quando il caso non ammette pre-generazione (rounds
        oltre la capacità round-robin, o search trio fallita).
        """
        n = len(player_ids)
        if n < 2:
            return None

        odd_policy = getattr(gara, "odd_number_policy", None)
        is_odd = n % 2 == 1

        # Ramo C — N dispari + TRIO: branch-and-bound search globale.
        if is_odd and odd_policy == "trio":
            return self._search_trio_schedule(player_ids, n_rounds)

        # Ramo B — N dispari + BYE: circle method su N+1 con sentinella.
        if is_odd:
            if n_rounds > n:
                return None  # oltre N round servono reincontri
            return self._circle_method(
                list(player_ids) + [self.BYE_PLAYER_ID], n_rounds
            )

        # Ramo A — N pari: circle method puro.
        if n_rounds > n - 1:
            return None  # oltre N-1 round servono reincontri
        return self._circle_method(list(player_ids), n_rounds)

    def _circle_method(self, players: List[int], n_rounds: int) -> List[List[Pairing]]:
        """Berger tables / circle method. Richiede `len(players)` pari.

        Shuffle iniziale via `self._rng` per casualità deterministica (stesso
        seed → stesso schedule). Fissa il primo giocatore, ruota gli altri
        di una posizione per ogni turno. Genera `n_rounds` turni di `len/2`
        coppie ciascuno. Le coppie contenenti `BYE_PLAYER_ID` (ramo B)
        diventano `Pairing(is_bye=True, players=(real_player,))`.
        """
        ordered = list(players)
        self._rng.shuffle(ordered)
        n = len(ordered)
        assert n % 2 == 0, "circle method requires even player count"

        schedule: List[List[Pairing]] = []
        fixed = ordered[0]
        rotating = ordered[1:]

        for round_idx in range(n_rounds):
            round_players = [fixed] + rotating
            round_pairings: List[Pairing] = []
            for i in range(n // 2):
                p1 = round_players[i]
                p2 = round_players[n - 1 - i]
                round_pairings.append(self._pair_to_pairing(p1, p2, round_idx + 1))
            schedule.append(round_pairings)
            # rotate: last element goes to front
            rotating = [rotating[-1]] + rotating[:-1]

        return schedule

    def _pair_to_pairing(self, p1: int, p2: int, round_number: int) -> Pairing:
        """Convert raw pair to `Pairing`, mapping `BYE_PLAYER_ID` to is_bye."""
        if p1 == self.BYE_PLAYER_ID:
            return Pairing(players=(p2,), is_bye=True, round_number=round_number)
        if p2 == self.BYE_PLAYER_ID:
            return Pairing(players=(p1,), is_bye=True, round_number=round_number)
        return Pairing(players=(p1, p2), round_number=round_number)

    def _search_trio_schedule(
        self,
        player_ids: List[int],
        n_rounds: int,
        deadline_ms: int = _TRIO_SEARCH_DEADLINE_MS,
    ) -> Optional[List[List[Pairing]]]:
        """Branch-and-bound search globale per schedule trio (Ramo C).

        Obiettivo lessicografico (minimize):
          1. `max_player(trio_count)` (fairness)
          2. somma totale di reincontri (incluso quelli interni al trio)
          3. `sum_player(trio_count)` (tie-break secondario)

        Determinismo: ordine di enumerazione dei trii guidato da
        `self._rng.shuffle(player_ids)`. Stesso seed → stesso schedule.

        Pruning:
          - relax progressiva del max trio_count consentito (target, +1, +2);
          - lower bound dal partial score (max/rematches/sum sono monotone
            non-decrescenti durante il branch).

        Deadline `deadline_ms`: oltre questa soglia ritorna `None`
        (caller usa il fallback incrementale).
        """
        n = len(player_ids)
        if n < 3 or n_rounds < 1:
            return None
        if (n - 3) % 2 != 0:
            # Resto dopo il trio deve essere accoppiabile a coppie. Per N
            # dispari (n-3) è sempre pari, quindi questo non scatta in pratica.
            return None

        deadline = time.monotonic() + deadline_ms / 1000.0

        ordered_players = list(player_ids)
        self._rng.shuffle(ordered_players)
        ordered_set = set(ordered_players)
        target_max = math.ceil(n_rounds * 3 / n)

        best_schedule: Optional[List[List[Pairing]]] = None
        best_score: Tuple[int, int, int] = (10**9, 10**9, 10**9)

        def partial_score(
            trio_counts: Dict[int, int], rematches: int
        ) -> Tuple[int, int, int]:
            max_t = max(trio_counts.values()) if trio_counts else 0
            sum_t = sum(trio_counts.values())
            return (max_t, rematches, sum_t)

        def recurse(
            round_idx: int,
            schedule: List[List[Pairing]],
            trio_counts: Dict[int, int],
            pair_counts: Dict[Tuple[int, int], int],
            rematches: int,
        ) -> None:
            nonlocal best_schedule, best_score
            if time.monotonic() > deadline:
                return
            current_score = partial_score(trio_counts, rematches)
            # Tutti e tre i campi sono monotoni non-decrescenti durante il
            # branch → current_score è LB sul final score.
            if current_score >= best_score:
                return
            if round_idx == n_rounds:
                best_schedule = [list(r) for r in schedule]
                best_score = current_score
                return

            for relaxation in (target_max, target_max + 1, target_max + 2):
                candidates: List[
                    Tuple[
                        int,
                        Tuple[int, ...],
                        List[Tuple[int, int]],
                        List[Tuple[int, int]],
                    ]
                ] = []
                for trio in combinations(ordered_players, 3):
                    if any(trio_counts.get(p, 0) + 1 > relaxation for p in trio):
                        continue
                    trio_pairs = [
                        tuple(sorted([trio[i], trio[j]]))
                        for i, j in ((0, 1), (0, 2), (1, 2))
                    ]
                    trio_rematches = sum(
                        1 for tp in trio_pairs if pair_counts.get(tp, 0) >= 1
                    )
                    remaining = [p for p in ordered_players if p not in trio]
                    matched = self._matching_for_round(remaining, pair_counts)
                    if matched is None:
                        continue
                    pairs, pair_rematches = matched
                    candidates.append(
                        (trio_rematches + pair_rematches, trio, trio_pairs, pairs)
                    )

                if not candidates:
                    continue  # try a more relaxed level

                # Esplora prima i trii a minor incremento di reincontri.
                candidates.sort(key=lambda c: c[0])

                for delta_rematches, trio, trio_pairs, pairs in candidates:
                    if time.monotonic() > deadline:
                        return
                    round_pairings: List[Pairing] = [
                        Pairing(players=tuple(trio), round_number=round_idx + 1)
                    ]
                    for p1, p2 in pairs:
                        round_pairings.append(
                            self._pair_to_pairing(p1, p2, round_idx + 1)
                        )

                    for p in trio:
                        trio_counts[p] = trio_counts.get(p, 0) + 1
                    for tp in trio_pairs:
                        pair_counts[tp] = pair_counts.get(tp, 0) + 1
                    for pp in pairs:
                        cp = tuple(sorted(pp))
                        pair_counts[cp] = pair_counts.get(cp, 0) + 1
                    schedule.append(round_pairings)

                    recurse(
                        round_idx + 1,
                        schedule,
                        trio_counts,
                        pair_counts,
                        rematches + delta_rematches,
                    )

                    schedule.pop()
                    for p in trio:
                        trio_counts[p] -= 1
                        if trio_counts[p] == 0:
                            del trio_counts[p]
                    for tp in trio_pairs:
                        pair_counts[tp] -= 1
                        if pair_counts[tp] == 0:
                            del pair_counts[tp]
                    for pp in pairs:
                        cp = tuple(sorted(pp))
                        pair_counts[cp] -= 1
                        if pair_counts[cp] == 0:
                            del pair_counts[cp]

                # Fermarsi al primo livello di relax che ha candidati. Se la
                # search non trova mai una soluzione completa con relax stretto
                # ma backtracking ha già esplorato tutti i candidati, la
                # ricorsione ritorna e l'iterazione esterna passa al livello
                # successivo.
                return

        # Sanity check: il sub-problem (remaining = ordered_set - trio) deve
        # essere consistente. `ordered_set` usato solo per assertion futura.
        _ = ordered_set

        recurse(0, [], {}, {}, 0)
        return best_schedule

    def _matching_for_round(
        self,
        players: List[int],
        pair_counts: Dict[Tuple[int, int], int],
    ) -> Optional[Tuple[List[Tuple[int, int]], int]]:
        """Max-weight matching su `players` (pari, no sentinella).

        Riusa la logica weighted di `_apply_weighted_matching` ma su un
        `pair_counts` dict (consumato dalla search trio) invece di un set di
        coppie. Pesi: `_WEIGHT_NON_REMATCH` per coppie mai incontrate,
        `_WEIGHT_REMATCH` per quelle già viste almeno una volta.

        Ritorna `(pairs, n_rematches)` o `None` se non esiste perfect matching.
        """
        if len(players) == 0:
            return [], 0
        if len(players) % 2 != 0:
            return None
        if len(players) == 2:
            cp = tuple(sorted(players))
            n_rem = 1 if pair_counts.get(cp, 0) >= 1 else 0
            return [(players[0], players[1])], n_rem

        G = nx.Graph()
        G.add_nodes_from(players)
        for p1, p2 in combinations(players, 2):
            cp = tuple(sorted([p1, p2]))
            weight = (
                self._WEIGHT_REMATCH
                if pair_counts.get(cp, 0) >= 1
                else self._WEIGHT_NON_REMATCH
            )
            G.add_edge(p1, p2, weight=weight)

        matching = nx.max_weight_matching(G, maxcardinality=True)
        if len(matching) * 2 != len(players):
            return None
        pairs = [tuple(sorted(pair)) for pair in matching]
        n_rem = sum(1 for p in pairs if pair_counts.get(p, 0) >= 1)
        return pairs, n_rem

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
        3. No explicit policy → delegate to
           StrategyBehaviorConfig.get_default_odd_policy
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
