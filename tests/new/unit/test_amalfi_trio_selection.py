"""
Unit tests for the Amalfi trio selection algorithm (3-step: salto + swap + companions).

Tests cover all 12 scenarios from the I/O matrix in the spec, plus the
_swap_anchor_if_needed and _select_trio_companions pure functions.
"""

import pytest
from typing import Dict, List, Tuple

from models.matchmaking.strategies.amalfi import AmalfiStrategy


@pytest.fixture
def strategy() -> AmalfiStrategy:
    return AmalfiStrategy()


# ---------------------------------------------------------------------------
# Helper: build player_to_index from a list of player_ids
# ---------------------------------------------------------------------------
def _p2i(players: List[int]) -> Dict[int, int]:
    """Map player_id -> classification index (0-based)."""
    return {p: i for i, p in enumerate(players)}


# ===================================================================
# Tests for _swap_anchor_if_needed (pure function — no DB needed)
# ===================================================================
class TestSwapAnchorIfNeeded:
    """Step 2: swap anchor for fair trio rotation."""

    def test_swap_when_anchor_has_too_many_trios(self, strategy: AmalfiStrategy) -> None:
        """Scenario: Salto gives anchor P with trio_count=2, min=0.
        Step 2 finds Q with count=0 and swaps."""
        anchor = 10
        pairs: List[Tuple[int, int]] = [(20, 30), (40, 50)]
        trio_counts = {10: 2, 20: 1, 30: 0, 40: 1, 50: 0}
        p2i = _p2i([10, 20, 30, 40, 50])

        new_anchor, new_pairs = strategy._swap_anchor_if_needed(
            anchor, pairs, trio_counts, p2i
        )

        assert new_anchor != 10
        assert trio_counts.get(new_anchor, 0) == 0
        # Original anchor should now be in a pair
        all_in_pairs = [p for pair in new_pairs for p in pair]
        assert 10 in all_in_pairs

    def test_swap_prefers_lower_classification_at_tie(
        self, strategy: AmalfiStrategy
    ) -> None:
        """Scenario: Two candidates Q1(pos 2) and Q2(pos 5) both at count=0.
        Step 2 chooses Q2 (higher index = lower in classification = more Amalfi)."""
        anchor = 10
        pairs: List[Tuple[int, int]] = [(20, 30), (40, 50)]
        trio_counts = {10: 2, 20: 0, 30: 1, 40: 1, 50: 0}
        # 20 is at index 1 (pos 2), 50 is at index 4 (pos 5)
        p2i = _p2i([10, 20, 30, 40, 50])

        new_anchor, _ = strategy._swap_anchor_if_needed(
            anchor, pairs, trio_counts, p2i
        )

        # Should pick player 50 (index 4) over player 20 (index 1)
        assert new_anchor == 50

    def test_no_swap_when_all_same_count(self, strategy: AmalfiStrategy) -> None:
        """Scenario: All players at trio_count=2, min=2. No swap."""
        anchor = 10
        pairs: List[Tuple[int, int]] = [(20, 30), (40, 50)]
        trio_counts = {10: 2, 20: 2, 30: 2, 40: 2, 50: 2}
        p2i = _p2i([10, 20, 30, 40, 50])

        new_anchor, new_pairs = strategy._swap_anchor_if_needed(
            anchor, pairs, trio_counts, p2i
        )

        assert new_anchor == 10
        assert new_pairs == pairs

    def test_no_swap_when_anchor_already_at_min(
        self, strategy: AmalfiStrategy
    ) -> None:
        """Anchor has count=0, others have count >= 0. No swap needed."""
        anchor = 10
        pairs: List[Tuple[int, int]] = [(20, 30)]
        trio_counts = {10: 0, 20: 1, 30: 2}
        p2i = _p2i([10, 20, 30])

        new_anchor, new_pairs = strategy._swap_anchor_if_needed(
            anchor, pairs, trio_counts, p2i
        )

        assert new_anchor == 10
        assert new_pairs == pairs

    def test_swap_places_anchor_in_correct_pair_position(
        self, strategy: AmalfiStrategy
    ) -> None:
        """After swap, the old anchor takes the exact position of the new anchor."""
        anchor = 10
        pairs: List[Tuple[int, int]] = [(20, 30), (40, 50)]
        trio_counts = {10: 3, 20: 1, 30: 0, 40: 1, 50: 1}
        p2i = _p2i([10, 20, 30, 40, 50])

        new_anchor, new_pairs = strategy._swap_anchor_if_needed(
            anchor, pairs, trio_counts, p2i
        )

        assert new_anchor == 30
        # Player 10 should replace 30 in pair with 20
        assert (10, 20) in new_pairs or (20, 10) in new_pairs


# ===================================================================
# Tests for _select_trio_companions (pure function — no DB needed)
# ===================================================================
class TestSelectTrioCompanions:
    """Step 3: select 2 companions for the anchor."""

    def test_rotation_beats_classification(self, strategy: AmalfiStrategy) -> None:
        """Scenario: Low-classification pair has companion_sum=2, high pair has sum=0.
        Step 3 picks the high pair (lower sum wins)."""
        anchor = 10
        # Pair 0: (20, 30) high in classification but sum=0
        # Pair 1: (40, 50) low in classification but sum=2
        pairs: List[Tuple[int, int]] = [(20, 30), (40, 50)]
        trio_counts = {10: 0, 20: 0, 30: 0, 40: 1, 50: 1}
        encounter_matrix: Dict[Tuple[int, int], bool] = {}
        p2i = _p2i([10, 20, 30, 40, 50])

        c1, c2 = strategy._select_trio_companions(
            anchor, pairs, trio_counts, encounter_matrix, p2i
        )

        assert {c1, c2} == {20, 30}  # sum=0 wins over sum=2

    def test_anti_rematch_beats_classification(self, strategy: AmalfiStrategy) -> None:
        """Scenario: Two pairs at same sum, one with rematch in trio.
        Step 3 picks the one without rematch."""
        anchor = 10
        pairs: List[Tuple[int, int]] = [(20, 30), (40, 50)]
        trio_counts = {10: 0, 20: 0, 30: 0, 40: 0, 50: 0}
        # 10-20 already played (rematch in trio if 20 chosen)
        encounter_matrix: Dict[Tuple[int, int], bool] = {
            (10, 20): True, (20, 10): True,
            (10, 30): True, (30, 10): True,
        }
        p2i = _p2i([10, 20, 30, 40, 50])

        c1, c2 = strategy._select_trio_companions(
            anchor, pairs, trio_counts, encounter_matrix, p2i
        )

        # Pair (40, 50) has 0 rematches vs pair (20, 30) which has 2
        assert {c1, c2} == {40, 50}

    def test_rotation_beats_anti_rematch(self, strategy: AmalfiStrategy) -> None:
        """Scenario: Combo with sum=0 has rematch, combo with sum=1 has no rematch.
        Step 3 picks sum=0 (rotation beats anti-rematch).
        We must ensure the sum=0 combo has no lower-sum cross-pair alternatives."""
        anchor = 10
        # 3 pairs so we can isolate combos
        pairs: List[Tuple[int, int]] = [(20, 30), (40, 50), (60, 70)]
        # Only (20, 30) has sum=0, all cross-pair combos including 40 have sum>=1
        trio_counts = {10: 0, 20: 0, 30: 0, 40: 1, 50: 1, 60: 1, 70: 1}
        # 10-20 and 10-30 already played (full rematch if (20,30) chosen)
        # But no rematches for any other combos
        encounter_matrix: Dict[Tuple[int, int], bool] = {
            (10, 20): True, (20, 10): True,
            (10, 30): True, (30, 10): True,
            (20, 30): True, (30, 20): True,
        }
        p2i = _p2i([10, 20, 30, 40, 50, 60, 70])

        c1, c2 = strategy._select_trio_companions(
            anchor, pairs, trio_counts, encounter_matrix, p2i
        )

        # sum=0 (20, 30) wins despite having 3 rematches, because sum is lower
        assert {c1, c2} == {20, 30}

    def test_companions_from_different_pairs_orphan_rematch(
        self, strategy: AmalfiStrategy
    ) -> None:
        """Scenario: Step 3 picks 2 from 2 different pairs.
        Orphan rematch penalizes but doesn't block."""
        anchor = 10
        pairs: List[Tuple[int, int]] = [(20, 30), (40, 50)]
        trio_counts = {10: 0, 20: 0, 30: 1, 40: 0, 50: 1}
        # 30 and 50 (the orphans if 20 and 40 chosen) already played
        encounter_matrix: Dict[Tuple[int, int], bool] = {
            (30, 50): True, (50, 30): True,
        }
        p2i = _p2i([10, 20, 30, 40, 50])

        c1, c2 = strategy._select_trio_companions(
            anchor, pairs, trio_counts, encounter_matrix, p2i
        )

        # (20, 40) has sum=0 but orphan_rematch=1
        # (20, 30) has sum=1, same-pair so orphan_rematch=0
        # sum=0 < sum=1, so (20, 40) wins despite orphan_rematch
        assert {c1, c2} == {20, 40}

    def test_n3_degenerate_case(self, strategy: AmalfiStrategy) -> None:
        """Scenario: N=3 players. Only 1 pair in pool, C(2,2)=1 combination."""
        anchor = 10
        pairs: List[Tuple[int, int]] = [(20, 30)]
        trio_counts: dict[int, int] = {}
        encounter_matrix: Dict[Tuple[int, int], bool] = {}
        p2i = _p2i([10, 20, 30])

        c1, c2 = strategy._select_trio_companions(
            anchor, pairs, trio_counts, encounter_matrix, p2i
        )

        assert {c1, c2} == {20, 30}

    def test_n5_six_combinations(self, strategy: AmalfiStrategy) -> None:
        """Scenario: N=5 players. 2 pairs, C(4,2)=6 combinations.
        All sums are 0, no rematches. Tiebreaker is -position_sum.
        (40,50) has position_sum=3+4=7, highest among all combos."""
        anchor = 10
        pairs: List[Tuple[int, int]] = [(20, 30), (40, 50)]
        trio_counts: dict[int, int] = {}
        encounter_matrix: Dict[Tuple[int, int], bool] = {}
        p2i = _p2i([10, 20, 30, 40, 50])

        c1, c2 = strategy._select_trio_companions(
            anchor, pairs, trio_counts, encounter_matrix, p2i
        )

        # (40,50) has position_sum=7, (30,50)=6, (20,50)=5, (30,40)=5, etc.
        # -7 is the most negative → wins
        assert {c1, c2} == {40, 50}

    def test_prefers_low_classification_companions_over_top_ranked(
        self, strategy: AmalfiStrategy
    ) -> None:
        """Regression: player1 (1st in classification) was chosen as companion
        because -max_position only compared the MAX index, ignoring the
        other companion's position. Using -position_sum fixes this.

        Scenario: anchor=Paolo(1), all at count=1.
        (player1=0, EGLE=6) has sum=6, (CRISTIAN=5, EGLE=6) has sum=11.
        Should pick CRISTIAN+EGLE (sum=11 > sum=6)."""
        anchor = 100  # Paolo, index 1
        # Pairs from salto (after swap)
        pairs: List[Tuple[int, int]] = [(10, 40), (30, 60), (50, 70)]
        # player1=10(idx0), MAX_P=40(idx3), BRUNO=30(idx2), CRISTIAN=60(idx5), PICCHIO=50(idx4), EGLE=70(idx6)
        trio_counts = {100: 0, 10: 1, 40: 1, 30: 1, 60: 1, 50: 1, 70: 1}
        encounter_matrix: Dict[Tuple[int, int], bool] = {}  # No rematches
        p2i = {10: 0, 100: 1, 30: 2, 40: 3, 50: 4, 60: 5, 70: 6}

        c1, c2 = strategy._select_trio_companions(
            anchor, pairs, trio_counts, encounter_matrix, p2i
        )

        # Should pick the 2 lowest-classified: CRISTIAN(5) + EGLE(6) = sum 11
        # NOT player1(0) + EGLE(6) = sum 6
        assert {c1, c2} == {60, 70}
        assert 10 not in {c1, c2}, "Top-ranked player1 should not be in trio"

    def test_worst_case_all_high_all_rematch(self, strategy: AmalfiStrategy) -> None:
        """Scenario: All high trio counts, all pairs already encountered.
        Best effort: picks the combo with min score."""
        anchor = 10
        pairs: List[Tuple[int, int]] = [(20, 30), (40, 50)]
        trio_counts = {10: 3, 20: 3, 30: 3, 40: 3, 50: 3}
        # All pairs already played
        all_players = [10, 20, 30, 40, 50]
        encounter_matrix: Dict[Tuple[int, int], bool] = {}
        for i, a in enumerate(all_players):
            for b in all_players[i + 1:]:
                encounter_matrix[(a, b)] = True
                encounter_matrix[(b, a)] = True
        p2i = _p2i(all_players)

        # Should not raise — returns best effort
        c1, c2 = strategy._select_trio_companions(
            anchor, pairs, trio_counts, encounter_matrix, p2i
        )

        assert c1 != c2
        assert c1 in [20, 30, 40, 50]
        assert c2 in [20, 30, 40, 50]


# ===================================================================
# Integration-style tests using mock classification objects
# ===================================================================
class TestAmalfiPairingTrioIntegration:
    """End-to-end tests of _amalfi_pairing with use_trio=True.

    These tests mock the DB-dependent methods to isolate the algorithm logic.
    """

    @pytest.fixture
    def mock_classifica(self):
        """Create mock RoundClassification objects."""
        from unittest.mock import Mock

        def _make(player_ids: List[int], gara_id: int = 1):
            result = []
            for i, pid in enumerate(player_ids):
                rc = Mock()
                rc.user_id = pid
                rc.gara_id = gara_id
                rc.position = i + 1
                result.append(rc)
            return result

        return _make

    @pytest.fixture
    def mock_gara(self):
        """Create a mock gara with trio policy."""
        from unittest.mock import Mock

        gara = Mock()
        gara.odd_number_policy = "trio"
        gara.rounds_count = 5
        return gara

    def _patch_db_methods(
        self,
        strategy: AmalfiStrategy,
        monkeypatch: pytest.MonkeyPatch,
        trio_counts: dict[int, int] | None = None,
        encounter_matrix: Dict[Tuple[int, int], bool] | None = None,
        players_with_bye: set[int] | None = None,
    ) -> None:
        """Patch DB-dependent methods on the strategy instance."""
        monkeypatch.setattr(
            strategy, "_get_trio_counts", lambda gara_id: trio_counts or {}
        )
        monkeypatch.setattr(
            strategy, "_get_players_with_bye", lambda gara_id: players_with_bye or set()
        )
        monkeypatch.setattr(
            strategy,
            "_have_already_played",
            lambda p1, p2, gid: (encounter_matrix or {}).get((p1, p2), False),
        )
        # Patch PlayerEncounterService.get_encounter_matrix
        monkeypatch.setattr(
            "models.classification.encounter_service.PlayerEncounterService"
            ".get_encounter_matrix",
            lambda gara_id: encounter_matrix or {},
        )

    def test_first_trio_no_history(
        self,
        strategy: AmalfiStrategy,
        mock_classifica,
        mock_gara,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario: 7 players, round 1, no history. Produces 1 trio + 2 pairs."""
        classifica = mock_classifica([1, 2, 3, 4, 5, 6, 7])
        self._patch_db_methods(strategy, monkeypatch)

        result = strategy._amalfi_pairing(classifica, 1, 5, mock_gara)

        trios = [p for p in result if p.is_trio]
        pairs = [p for p in result if not p.is_trio and not p.is_bye]
        assert len(trios) == 1
        assert len(trios[0].players) == 3
        assert len(pairs) == 2
        # No BYE in output
        assert all(
            strategy.BYE_PLAYER_ID not in p.players for p in result
        )
        # All 7 players accounted for
        all_players = set()
        for p in result:
            all_players.update(p.players)
        assert all_players == {1, 2, 3, 4, 5, 6, 7}

    def test_trio_players_sorted_by_classification(
        self,
        strategy: AmalfiStrategy,
        mock_classifica,
        mock_gara,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Trio Pairing players must be sorted by classification position."""
        classifica = mock_classifica([1, 2, 3, 4, 5, 6, 7])
        self._patch_db_methods(strategy, monkeypatch)

        result = strategy._amalfi_pairing(classifica, 1, 5, mock_gara)

        trio = [p for p in result if p.is_trio][0]
        trio_list = list(trio.players)
        # Should be sorted by classification position (index order)
        positions = [classifica[0].gara_id for _ in trio_list]  # dummy
        player_positions = {c.user_id: c.position for c in classifica}
        sorted_by_pos = sorted(trio_list, key=lambda p: player_positions[p])
        assert trio_list == sorted_by_pos

    def test_no_bye_player_in_output(
        self,
        strategy: AmalfiStrategy,
        mock_classifica,
        mock_gara,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """BYE_PLAYER_ID (-1) must never appear in any output Pairing."""
        classifica = mock_classifica([1, 2, 3, 4, 5])
        self._patch_db_methods(strategy, monkeypatch)

        result = strategy._amalfi_pairing(classifica, 1, 5, mock_gara)

        for pairing in result:
            assert strategy.BYE_PLAYER_ID not in pairing.players

    def test_n3_produces_single_trio(
        self,
        strategy: AmalfiStrategy,
        mock_classifica,
        mock_gara,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario: N=3 players. Must produce exactly 1 trio, 0 regular pairs."""
        classifica = mock_classifica([1, 2, 3])
        self._patch_db_methods(strategy, monkeypatch)

        result = strategy._amalfi_pairing(classifica, 1, 3, mock_gara)

        assert len(result) == 1
        assert result[0].is_trio
        assert set(result[0].players) == {1, 2, 3}

    def test_n5_produces_one_trio_one_pair(
        self,
        strategy: AmalfiStrategy,
        mock_classifica,
        mock_gara,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario: N=5 players. 1 trio + 1 pair."""
        classifica = mock_classifica([1, 2, 3, 4, 5])
        self._patch_db_methods(strategy, monkeypatch)

        result = strategy._amalfi_pairing(classifica, 1, 5, mock_gara)

        trios = [p for p in result if p.is_trio]
        pairs = [p for p in result if not p.is_trio and not p.is_bye]
        assert len(trios) == 1
        assert len(pairs) == 1
        all_players = set()
        for p in result:
            all_players.update(p.players)
        assert all_players == {1, 2, 3, 4, 5}

    def test_even_players_no_trio(
        self,
        strategy: AmalfiStrategy,
        mock_classifica,
        mock_gara,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Even number of players with trio policy: no trio produced."""
        classifica = mock_classifica([1, 2, 3, 4, 5, 6])
        self._patch_db_methods(strategy, monkeypatch)

        result = strategy._amalfi_pairing(classifica, 1, 5, mock_gara)

        trios = [p for p in result if p.is_trio]
        assert len(trios) == 0
        assert len(result) == 3  # 3 pairs

    def test_long_tournament_graceful_degradation(
        self,
        strategy: AmalfiStrategy,
        mock_classifica,
        mock_gara,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario: Very long tournament (round 25), all encountered.
        Should still produce valid output without errors."""
        players = list(range(1, 8))  # 7 players
        classifica = mock_classifica(players)

        # All pairs have played each other
        enc: Dict[Tuple[int, int], bool] = {}
        for i, a in enumerate(players):
            for b in players[i + 1:]:
                enc[(a, b)] = True
                enc[(b, a)] = True

        # All players have high trio counts
        tc = {p: 3 for p in players}

        self._patch_db_methods(
            strategy, monkeypatch, trio_counts=tc, encounter_matrix=enc
        )

        result = strategy._amalfi_pairing(classifica, 25, 25, mock_gara)

        trios = [p for p in result if p.is_trio]
        assert len(trios) == 1
        all_players = set()
        for p in result:
            all_players.update(p.players)
        assert all_players == set(players)

    def test_multi_round_fairness_trio_count(
        self,
        strategy: AmalfiStrategy,
        mock_classifica,
        mock_gara,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC1: Given 7 players and 5 rounds, max - min trio_count <= 1.

        Simulates 5 consecutive rounds, tracking trio_counts and
        updating them between rounds (as the real system would).
        """
        players = list(range(1, 8))  # 7 players
        trio_counts: dict[int, int] = {}
        encounter_matrix: Dict[Tuple[int, int], bool] = {}

        for round_num in range(1, 6):
            classifica = mock_classifica(players)

            self._patch_db_methods(
                strategy,
                monkeypatch,
                trio_counts=dict(trio_counts),
                encounter_matrix=dict(encounter_matrix),
            )

            result = strategy._amalfi_pairing(
                classifica, round_num, 5, mock_gara
            )

            # Extract trio and update counts + encounters
            for pairing in result:
                if pairing.is_trio:
                    for p in pairing.players:
                        trio_counts[p] = trio_counts.get(p, 0) + 1
                    # Record encounters for all 3 pairs
                    ps = list(pairing.players)
                    for i in range(len(ps)):
                        for j in range(i + 1, len(ps)):
                            encounter_matrix[(ps[i], ps[j])] = True
                            encounter_matrix[(ps[j], ps[i])] = True
                elif not pairing.is_bye and len(pairing.players) == 2:
                    a, b = pairing.players
                    encounter_matrix[(a, b)] = True
                    encounter_matrix[(b, a)] = True

        # Verify fairness: max - min trio_count <= 1
        counts = [trio_counts.get(p, 0) for p in players]
        assert max(counts) - min(counts) <= 1, (
            f"Trio count unfair: {dict(sorted(trio_counts.items()))} "
            f"(max-min={max(counts) - min(counts)})"
        )

    def test_orphan_recomposition_end_to_end(
        self,
        strategy: AmalfiStrategy,
        mock_classifica,
        mock_gara,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC6: When Step 3 picks companions from different pairs,
        orphans form a valid pair and no BYE_PLAYER_ID in output.

        Force this by giving 2 players in different salto pairs
        a trio_count of 0, while all others have count=1.
        """
        players = [1, 2, 3, 4, 5, 6, 7]
        classifica = mock_classifica(players)

        # Player who lands on BYE (anchor) will have count=0.
        # Two players in DIFFERENT salto pairs also have count=0.
        # This forces Step 3 to pick from different pairs.
        # We set counts so that only players 2 and 4 have count=0,
        # and they should end up in different salto pairs.
        trio_counts = {1: 1, 2: 0, 3: 1, 4: 0, 5: 1, 6: 1, 7: 1}

        self._patch_db_methods(
            strategy, monkeypatch, trio_counts=trio_counts
        )

        result = strategy._amalfi_pairing(classifica, 1, 5, mock_gara)

        # Verify structure
        trios = [p for p in result if p.is_trio]
        pairs = [p for p in result if not p.is_trio and not p.is_bye]
        assert len(trios) == 1
        assert len(trios[0].players) == 3

        # All 7 players accounted for
        all_players_out = set()
        for p in result:
            all_players_out.update(p.players)
        assert all_players_out == set(players)

        # No BYE_PLAYER_ID anywhere
        for pairing in result:
            assert strategy.BYE_PLAYER_ID not in pairing.players

        # All pairs have exactly 2 players
        for p in pairs:
            assert len(p.players) == 2
