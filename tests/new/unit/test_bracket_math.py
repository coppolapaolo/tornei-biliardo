"""Unit tests per l'aritmetica pura del tabellone (Step 0).

Copre:
1. Dimensionamento del tabellone (`bracket_size`)
2. Ordine canonico "snake" dei seed (`standard_bracket_order`)
3. Turno d'incontro e alimentazione del winners bracket
   (`meet_round`, `wb_feed`)
4. Permutazione di alimentazione del losers bracket
   (`losers_feed_permutation`)
5. Schedule turno-di-gara -> round di bracket (`bracket_schedule`)
6. Purezza del modulo (niente Flask/SQLAlchemy/DB)

Tutti i test sono puri: nessuna app fixture, nessun DB.
"""

import ast
import math
from pathlib import Path

import pytest

from models.matchmaking import bracket as bracket_module
from models.matchmaking.bracket import (
    BRACKET_GRAND_FINAL,
    BRACKET_GRAND_FINAL_RESET,
    BRACKET_LOSERS,
    BRACKET_WINNERS,
    MIN_BRACKET_SIZE_DIRECT_ELIMINATION,
    MIN_BRACKET_SIZE_DOUBLE_KNOCKOUT,
    BracketRound,
    bracket_schedule,
    bracket_size,
    losers_feed_permutation,
    meet_round,
    standard_bracket_order,
    total_rounds,
    wb_feed,
)

POWER_SIZES = [2, 4, 8, 16, 32, 64, 128]


class TestBracketSize:
    """S = 2**ceil(log2(n))."""

    @pytest.mark.parametrize(
        "player_count,expected",
        [
            (1, 1),
            (2, 2),
            (3, 4),
            (4, 4),
            (5, 8),
            (6, 8),
            (8, 8),
            (9, 16),
            (12, 16),
            (16, 16),
            (17, 32),
            (64, 64),
            (65, 128),
        ],
    )
    def test_bracket_size(self, player_count, expected):
        assert bracket_size(player_count) == expected

    def test_matches_log2_formula(self):
        """Coincide con 2**ceil(log2(n)) senza errori di floating point."""
        for n in range(1, 300):
            assert bracket_size(n) == 2 ** math.ceil(math.log2(n))

    def test_bracket_size_is_never_smaller_than_players(self):
        for n in range(1, 300):
            size = bracket_size(n)
            assert size >= n
            assert size < 2 * n  # potenza di 2 immediatamente superiore

    def test_holes_are_always_less_than_half(self):
        """Invariante chiave del piano: b = S - n < S/2.

        Ne discende che non esistono due buchi nella stessa coppia, quindi
        nessun bye oltre il primo turno del winners bracket.
        """
        for n in range(2, 300):
            size = bracket_size(n)
            assert size - n < size / 2

    @pytest.mark.parametrize("bad", [0, -1, -8])
    def test_invalid_player_count(self, bad):
        with pytest.raises(ValueError):
            bracket_size(bad)

    def test_format_floors(self):
        """I pavimenti di formato dichiarati dal piano (US-4)."""
        assert MIN_BRACKET_SIZE_DIRECT_ELIMINATION == 4
        assert MIN_BRACKET_SIZE_DOUBLE_KNOCKOUT == 8


class TestStandardBracketOrder:
    """Ordine canonico snake: slot -> seed (1-based)."""

    @pytest.mark.parametrize(
        "size,expected",
        [
            (1, [1]),
            (2, [1, 2]),
            (4, [1, 4, 3, 2]),
            (8, [1, 8, 5, 4, 3, 6, 7, 2]),
            (
                16,
                # fmt: off
                [
                    1, 16, 9, 8, 5, 12, 13, 4,
                    3, 14, 11, 6, 7, 10, 15, 2,
                ],
                # fmt: on
            ),
        ],
    )
    def test_known_orders(self, size, expected):
        assert standard_bracket_order(size) == expected

    @pytest.mark.parametrize("size", [1] + POWER_SIZES)
    def test_is_a_bijection(self, size):
        order = standard_bracket_order(size)
        assert len(order) == size
        assert sorted(order) == list(range(1, size + 1))

    @pytest.mark.parametrize("size", POWER_SIZES)
    def test_first_round_pairs_sum_to_size_plus_one(self, size):
        """Il match j accoppia gli slot 2j e 2j+1: seed complementari."""
        order = standard_bracket_order(size)
        for j in range(size // 2):
            assert order[2 * j] + order[2 * j + 1] == size + 1

    @pytest.mark.parametrize("size", POWER_SIZES)
    def test_top_seeds_are_spread_across_blocks(self, size):
        """A ogni livello j i primi 2^j seed stanno in blocchi distinti.

        E' la regola federale di distribuzione: 1 e 2 in meta' opposte,
        3 e 4 nei quarti rimasti liberi, 5-8 negli ottavi, ecc.
        """
        order = standard_bracket_order(size)
        slot_of = {seed: slot for slot, seed in enumerate(order)}
        levels = int(math.log2(size))
        for level in range(1, levels + 1):
            n_blocks = 2**level
            block_size = size // n_blocks
            blocks = [slot_of[seed] // block_size for seed in range(1, n_blocks + 1)]
            assert sorted(blocks) == list(range(n_blocks))

    @pytest.mark.parametrize("size", POWER_SIZES)
    def test_seed_1_and_2_meet_only_in_the_final(self, size):
        order = standard_bracket_order(size)
        slot_of = {seed: slot for slot, seed in enumerate(order)}
        assert meet_round(slot_of[1], slot_of[2]) == int(math.log2(size))

    def test_seeds_3_and_4_meet_after_the_top_two(self):
        """3 e 4 finiscono in meta' opposte (uno per ciascun favorito)."""
        for size in [8, 16, 32]:
            order = standard_bracket_order(size)
            slot_of = {seed: slot for slot, seed in enumerate(order)}
            k = int(math.log2(size))
            # 1 incontra 4 in semifinale, 2 incontra 3 in semifinale
            assert meet_round(slot_of[1], slot_of[4]) == k - 1
            assert meet_round(slot_of[2], slot_of[3]) == k - 1

    @pytest.mark.parametrize("bad", [0, 3, 6, 12, -4])
    def test_size_must_be_a_power_of_two(self, bad):
        with pytest.raises(ValueError):
            standard_bracket_order(bad)


class TestMeetRound:
    """meet_round(i, j) = minimo r con i >> r == j >> r."""

    @pytest.mark.parametrize(
        "slot_a,slot_b,expected",
        [
            (0, 1, 1),
            (1, 0, 1),
            (2, 3, 1),
            (0, 2, 2),
            (0, 3, 2),
            (3, 4, 3),
            (0, 7, 3),
            (0, 15, 4),
        ],
    )
    def test_known_values(self, slot_a, slot_b, expected):
        assert meet_round(slot_a, slot_b) == expected

    def test_is_symmetric(self):
        for a in range(16):
            for b in range(16):
                if a == b:
                    continue
                assert meet_round(a, b) == meet_round(b, a)

    def test_same_slot_is_an_error(self):
        with pytest.raises(ValueError):
            meet_round(3, 3)

    @pytest.mark.parametrize("bad", [(-1, 2), (2, -1)])
    def test_negative_slots_rejected(self, bad):
        with pytest.raises(ValueError):
            meet_round(*bad)


class TestWbFeed:
    """Il vincitore del match (r, s) sale a (r+1, s // 2) nel seat s % 2."""

    def test_known_values(self):
        assert wb_feed(1, 0) == (2, 0, 0)
        assert wb_feed(1, 1) == (2, 0, 1)
        assert wb_feed(1, 2) == (2, 1, 0)
        assert wb_feed(2, 5) == (3, 2, 1)

    def test_sibling_matches_share_the_destination(self):
        """2j e 2j+1 alimentano lo stesso match con seat distinti."""
        for j in range(8):
            r_a, m_a, seat_a = wb_feed(3, 2 * j)
            r_b, m_b, seat_b = wb_feed(3, 2 * j + 1)
            assert (r_a, m_a) == (r_b, m_b)
            assert {seat_a, seat_b} == {0, 1}

    def test_consistent_with_meet_round(self):
        """Due slot che si incontrano al turno r convergono sullo stesso match."""
        size = 16
        for a in range(size):
            for b in range(size):
                if a == b:
                    continue
                r = meet_round(a, b)
                # Dopo r-1 avanzamenti i due sono nei match a >> (r-1) e
                # b >> (r-1) del round r, che il feed manda sullo stesso nodo.
                slot_a, slot_b = a >> (r - 1), b >> (r - 1)
                assert wb_feed(r, slot_a)[:2] == wb_feed(r, slot_b)[:2]

    @pytest.mark.parametrize("bad", [(0, 0), (1, -1)])
    def test_invalid_coordinates(self, bad):
        with pytest.raises(ValueError):
            wb_feed(*bad)


class TestLosersFeedPermutation:
    """Baseline: sigma(s) = n_matches - 1 - s (inversione)."""

    def test_baseline_inversion(self):
        assert losers_feed_permutation(1, 4) == [3, 2, 1, 0]
        assert losers_feed_permutation(2, 2) == [1, 0]
        assert losers_feed_permutation(3, 1) == [0]

    @pytest.mark.parametrize("n", [1, 2, 4, 8, 16])
    def test_is_a_permutation(self, n):
        for wb_round in range(1, 6):
            sigma = losers_feed_permutation(wb_round, n)
            assert sorted(sigma) == list(range(n))

    @pytest.mark.parametrize("n", [1, 2, 4, 8])
    def test_is_an_involution(self, n):
        sigma = losers_feed_permutation(1, n)
        assert [sigma[sigma[s]] for s in range(n)] == list(range(n))

    def test_invalid_arguments(self):
        with pytest.raises(ValueError):
            losers_feed_permutation(1, 0)
        with pytest.raises(ValueError):
            losers_feed_permutation(0, 4)


class TestSingleEliminationSchedule:
    """bracket_schedule per l'eliminazione diretta."""

    def test_schedule_for_eight(self):
        schedule = bracket_schedule(8)
        assert schedule == {
            1: [BracketRound(BRACKET_WINNERS, 1, 4)],
            2: [BracketRound(BRACKET_WINNERS, 2, 2)],
            3: [BracketRound(BRACKET_WINNERS, 3, 1)],
        }

    @pytest.mark.parametrize("size", POWER_SIZES)
    def test_round_count_and_match_counts(self, size):
        schedule = bracket_schedule(size)
        k = int(math.log2(size))
        assert sorted(schedule) == list(range(1, k + 1))
        assert total_rounds(size) == k
        for gara_round, entries in schedule.items():
            assert len(entries) == 1
            entry = entries[0]
            assert entry.bracket_type == BRACKET_WINNERS
            assert entry.bracket_round == gara_round
            assert entry.n_matches == size // (2**gara_round)

    @pytest.mark.parametrize("size", POWER_SIZES)
    def test_total_matches_is_size_minus_one(self, size):
        schedule = bracket_schedule(size)
        total = sum(e.n_matches for entries in schedule.values() for e in entries)
        assert total == size - 1


class TestDoubleKnockoutSchedule:
    """bracket_schedule(..., double_elimination=True)."""

    def test_schedule_for_eight_matches_the_plan(self):
        """S=8: R1=W1, R2=W2+L1, R3=W3+L2, R4=L3, R5=L4, R6=GF, R7=GFR."""
        schedule = bracket_schedule(8, double_elimination=True)
        assert schedule == {
            1: [BracketRound(BRACKET_WINNERS, 1, 4)],
            2: [
                BracketRound(BRACKET_WINNERS, 2, 2),
                BracketRound(BRACKET_LOSERS, 1, 2),
            ],
            3: [
                BracketRound(BRACKET_WINNERS, 3, 1),
                BracketRound(BRACKET_LOSERS, 2, 2),
            ],
            4: [BracketRound(BRACKET_LOSERS, 3, 1)],
            5: [BracketRound(BRACKET_LOSERS, 4, 1)],
            6: [BracketRound(BRACKET_GRAND_FINAL, 1, 1)],
            7: [BracketRound(BRACKET_GRAND_FINAL_RESET, 1, 1)],
        }

    @pytest.mark.parametrize("size", POWER_SIZES)
    def test_i_turni_programmati_sono_due_k(self, size):
        """`total_rounds` conta i turni certi: la bella non e' fra questi.

        Diceva `2k + 1`, contando anche il grand final reset — che pero' si
        gioca solo se la finale la vince chi arriva dal losers bracket. La
        gara si ritrovava un turno dichiarato e mai popolato (issue #239).
        L'induzione che fissa il numero sta in
        `test_doppio_ko_conteggio_turni.py`.
        """
        k = int(math.log2(size))
        assert total_rounds(size, double_elimination=True) == 2 * k

    @pytest.mark.parametrize("size", POWER_SIZES)
    def test_lo_schedule_arriva_fino_alla_bella(self, size):
        """La *struttura*, al contrario, la bella ce l'ha: e' un nodo vero.

        Sono due domande diverse — quanti turni si giocano, e quanto e' alto
        il tabellone — e prima un solo numero rispondeva a entrambe.
        """
        k = int(math.log2(size))
        schedule = bracket_schedule(size, double_elimination=True)
        assert sorted(schedule) == list(range(1, 2 * k + 2))

    @pytest.mark.parametrize("size", POWER_SIZES)
    def test_losers_bracket_has_size_minus_two_matches(self, size):
        schedule = bracket_schedule(size, double_elimination=True)
        losers = [
            e
            for entries in schedule.values()
            for e in entries
            if e.bracket_type == BRACKET_LOSERS
        ]
        assert sum(e.n_matches for e in losers) == size - 2
        k = int(math.log2(size))
        assert len(losers) == max(0, 2 * k - 2)

    @pytest.mark.parametrize("size", POWER_SIZES)
    def test_grand_final_and_reset_are_single_matches(self, size):
        schedule = bracket_schedule(size, double_elimination=True)
        k = int(math.log2(size))
        assert schedule[2 * k] == [BracketRound(BRACKET_GRAND_FINAL, 1, 1)]
        assert schedule[2 * k + 1] == [BracketRound(BRACKET_GRAND_FINAL_RESET, 1, 1)]

    @pytest.mark.parametrize("size", POWER_SIZES)
    def test_winners_bracket_is_unchanged_by_the_format(self, size):
        single = bracket_schedule(size)
        double = bracket_schedule(size, double_elimination=True)
        for gara_round, entries in single.items():
            assert entries[0] in double[gara_round]

    @pytest.mark.parametrize("size", [8, 16, 32, 64])
    def test_feeder_dependencies_are_satisfied(self, size):
        """Ogni round di bracket cade dopo i suoi alimentatori, con il
        numero di match che i suoi alimentatori possono produrre.

        - L_{2j-1} (minore): alimentato da W1 (j=1) o da L_{2j-2} (j>1),
          e ne dimezza i match.
        - L_{2j} (maggiore): alimentato da L_{2j-1} piu' i perdenti di
          W_{j+1}, quindi ha lo stesso numero di match di entrambi.
        - GF: alimentata da W_k e da L_{2k-2}.
        """
        schedule = bracket_schedule(size, double_elimination=True)
        k = int(math.log2(size))
        where = {
            (e.bracket_type, e.bracket_round): (gara_round, e.n_matches)
            for gara_round, entries in schedule.items()
            for e in entries
        }

        for j in range(1, k):
            minor_round, minor_n = where[(BRACKET_LOSERS, 2 * j - 1)]
            major_round, major_n = where[(BRACKET_LOSERS, 2 * j)]

            # Alimentatori del round minore
            if j == 1:
                feeder_round, feeder_n = where[(BRACKET_WINNERS, 1)]
            else:
                feeder_round, feeder_n = where[(BRACKET_LOSERS, 2 * j - 2)]
            assert feeder_round < minor_round
            assert minor_n == feeder_n // 2

            # Alimentatori del round maggiore
            wb_round, wb_n = where[(BRACKET_WINNERS, j + 1)]
            assert minor_round < major_round
            assert wb_round < major_round
            assert major_n == minor_n == wb_n

        gf_round, gf_n = where[(BRACKET_GRAND_FINAL, 1)]
        wb_final_round, wb_final_n = where[(BRACKET_WINNERS, k)]
        lb_final_round, lb_final_n = where[(BRACKET_LOSERS, 2 * k - 2)]
        assert wb_final_round < gf_round
        assert lb_final_round < gf_round
        assert wb_final_n == lb_final_n == gf_n == 1

        reset_round, _ = where[(BRACKET_GRAND_FINAL_RESET, 1)]
        assert gf_round < reset_round

    @pytest.mark.parametrize("size", POWER_SIZES)
    def test_losers_permutation_matches_the_wb_feeder_size(self, size):
        """La permutazione dei perdenti WB ha la taglia del round maggiore."""
        schedule = bracket_schedule(size, double_elimination=True)
        k = int(math.log2(size))
        counts = {
            (e.bracket_type, e.bracket_round): e.n_matches
            for entries in schedule.values()
            for e in entries
        }
        for j in range(1, k):
            n = counts[(BRACKET_LOSERS, 2 * j)]
            sigma = losers_feed_permutation(j + 1, n)
            assert sorted(sigma) == list(range(n))
            assert n == counts[(BRACKET_WINNERS, j + 1)]

    @pytest.mark.parametrize("bad", [0, 1, 3, 10])
    def test_invalid_sizes(self, bad):
        with pytest.raises(ValueError):
            bracket_schedule(bad)
        with pytest.raises(ValueError):
            bracket_schedule(bad, double_elimination=True)


class TestModulePurity:
    """Il modulo e' puro: niente Flask, niente SQLAlchemy, niente DB.

    Si ispezionano gli import *del modulo* via AST (non il testo del
    sorgente, che nei commenti nomina i framework proprio per dire che non
    li usa). Il package `models.matchmaking` importa Flask nel suo
    `__init__`, quindi la purezza qui asserita e' quella del modulo, non
    dell'intera catena di import.
    """

    ALLOWED_ROOTS = {"__future__", "dataclasses", "typing", "math"}

    def test_imports_only_the_standard_library(self):
        source = Path(bracket_module.__file__).read_text(encoding="utf-8")
        imported_roots = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # import relativo -> dipende dal dominio
                    imported_roots.add(f".{node.module or ''}")
                elif node.module:
                    imported_roots.add(node.module.split(".")[0])

        assert imported_roots <= self.ALLOWED_ROOTS, (
            f"bracket.py deve restare puro, import estranei: "
            f"{sorted(imported_roots - self.ALLOWED_ROOTS)}"
        )
