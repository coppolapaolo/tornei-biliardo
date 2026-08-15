"""Unit tests per la separazione dei compagni di squadra (Step 1).

Copre:
1. Bande di seeding (`band_of_seed`) e vincolo di seeding preservato
2. Non-regressione: senza squadre l'output e' l'ordine canonico
3. Vincolo bye: i buchi restano nei blocchi-foglia dei top seed
4. Determinismo a parita' di `rng`
5. Limite teorico `R*` e sua achievability (`R <= R*`, `R == R*` senza bye)
6. Ottimalita' verificata per brute force esaustivo su S in {4, 8, 16}
7. Purezza del modulo (solo stdlib + il modulo `bracket`)

Tutti i test sono puri: nessuna app fixture, nessun DB.
"""

import ast
import math
import random
from itertools import permutations, product
from pathlib import Path

import pytest

from models.matchmaking import team_separation as team_separation_module
from models.matchmaking.bracket import (
    bracket_size,
    meet_round,
    standard_bracket_order,
)
from models.matchmaking.team_separation import (
    assign_slots,
    band_of_seed,
    derby_counts_by_round,
    first_derby_round,
    theoretical_first_derby_round,
)

# --------------------------------------------------------------------------
# Helper indipendenti dal modulo sotto test
# --------------------------------------------------------------------------


def seeded(n):
    """Giocatori 1..n in ordine di seeding (id = seed, per leggibilita')."""
    return list(range(1, n + 1))


def canonical_assignment(seeded_players, size):
    """L'assegnazione canonica: slot -> giocatore, buchi a None."""
    n = len(seeded_players)
    return [
        seeded_players[seed - 1] if seed <= n else None
        for seed in standard_bracket_order(size)
    ]


def bands_layout(seeded_players, size):
    """(membri, slot) per ciascuna banda, ricostruito senza il modulo."""
    order = standard_bracket_order(size)
    slot_of = {seed: slot for slot, seed in enumerate(order)}
    n = len(seeded_players)
    levels = int(math.log2(size))
    layout = []
    for band in range(levels + 1):
        seeds = [1] if band == 0 else list(range(2 ** (band - 1) + 1, 2**band + 1))
        members = [seeded_players[s - 1] for s in seeds if s <= n]
        slots = [slot_of[s] for s in seeds if s <= n]
        layout.append((members, slots))
    return layout


def cost_vector(placement, team_of, levels):
    """(c_1, ..., c_k) da una mappa giocatore -> slot."""
    counts = [0] * (levels + 1)
    items = list(placement.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            player_a, slot_a = items[i]
            player_b, slot_b = items[j]
            team_a = team_of.get(player_a)
            if team_a is not None and team_a == team_of.get(player_b):
                counts[meet_round(slot_a, slot_b)] += 1
    return tuple(counts[1:])


def brute_force_best(seeded_players, team_of, size, limit=400_000):
    """Miglior vettore lessicografico su tutte le assegnazioni ammissibili.

    Enumera solo le posizioni dei giocatori *con squadra*: i teamless non
    contribuiscono al costo, quindi permutarli e' inutile e farebbe
    esplodere lo spazio.
    """
    per_band = []
    space = 1
    for members, slots in bands_layout(seeded_players, size):
        teamed = [m for m in members if team_of.get(m) is not None]
        options = list(permutations(slots, len(teamed)))
        space *= len(options)
        per_band.append((teamed, options))

    assert space <= limit, f"spazio di ricerca troppo grande: {space}"

    levels = int(math.log2(size))
    best = None
    for combo in product(*[options for _, options in per_band]):
        placement = {}
        for (teamed, _), chosen in zip(per_band, combo):
            placement.update(zip(teamed, chosen))
        vector = cost_vector(placement, team_of, levels)
        if best is None or vector < best:
            best = vector
    return best


def teams_by_size(seeded_players, sizes, rng):
    """Assegna squadre di taglia data a giocatori estratti a caso."""
    pool = list(seeded_players)
    assert sum(sizes) <= len(pool), "profilo piu' grande del campo"
    rng.shuffle(pool)
    team_of = {}
    index = 0
    for team_id, size in enumerate(sizes):
        for _ in range(size):
            team_of[pool[index]] = team_id
            index += 1
    return team_of


def profile_for(n):
    """Due squadre proporzionate al campo, sempre capienti."""
    return [max(2, n // 3), max(2, n // 4)]


def achieved(assignment, team_of, size):
    """(vettore dei derby, turno del primo derby)."""
    counts = derby_counts_by_round(assignment, team_of, size)
    return counts, first_derby_round(counts)


# --------------------------------------------------------------------------


class TestBands:
    """Bande di seeding: banda 0 = {1}, banda j = {2^(j-1)+1 .. 2^j}."""

    @pytest.mark.parametrize(
        "seed,expected",
        [
            (1, 0),
            (2, 1),
            (3, 2),
            (4, 2),
            (5, 3),
            (8, 3),
            (9, 4),
            (16, 4),
            (17, 5),
        ],
    )
    def test_band_of_seed(self, seed, expected):
        assert band_of_seed(seed) == expected

    @pytest.mark.parametrize("size", [2, 4, 8, 16, 32, 64])
    def test_bands_partition_the_seeds(self, size):
        levels = int(math.log2(size))
        buckets = {band: [] for band in range(levels + 1)}
        for seed in range(1, size + 1):
            buckets[band_of_seed(seed)].append(seed)
        assert buckets[0] == [1]
        for band in range(1, levels + 1):
            assert len(buckets[band]) == 2 ** (band - 1)
        assert sorted(s for v in buckets.values() for s in v) == list(
            range(1, size + 1)
        )

    def test_invalid_seed(self):
        with pytest.raises(ValueError):
            band_of_seed(0)


class TestNoTeamsIsCanonical:
    """Rete di non-regressione: senza squadre nulla deve cambiare."""

    @pytest.mark.parametrize("n", [4, 5, 6, 7, 8, 9, 12, 16, 20, 32])
    @pytest.mark.parametrize("rng_seed", [0, 7, 12345])
    def test_matches_standard_bracket_order(self, n, rng_seed):
        players = seeded(n)
        size = bracket_size(n)
        result = assign_slots(players, {}, size, random.Random(rng_seed), size - n)
        assert result == canonical_assignment(players, size)

    @pytest.mark.parametrize("n", [8, 12, 16])
    def test_explicit_none_team_is_the_same_as_no_team(self, n):
        players = seeded(n)
        size = bracket_size(n)
        team_of = {player: None for player in players}
        result = assign_slots(players, team_of, size, random.Random(3), size - n)
        assert result == canonical_assignment(players, size)

    def test_singleton_teams_do_not_move_anyone(self):
        """Squadre da un giocatore: nessun compagno, nessun vincolo."""
        players = seeded(16)
        team_of = {player: player for player in players}
        result = assign_slots(players, team_of, 16, random.Random(1), 0)
        assert result == canonical_assignment(players, 16)


class TestSeedingConstraint:
    """La liberta' e' *quale* membro della banda, non *quale* banda."""

    @pytest.mark.parametrize("n", [8, 12, 16, 24, 32])
    def test_players_stay_inside_their_band_slots(self, n):
        players = seeded(n)
        size = bracket_size(n)
        rng = random.Random(n)
        team_of = teams_by_size(players, profile_for(n), rng)
        result = assign_slots(players, team_of, size, rng, size - n)

        slot_of_player = {p: s for s, p in enumerate(result) if p is not None}
        for members, slots in bands_layout(players, size):
            assert {slot_of_player[m] for m in members} == set(slots)

    @pytest.mark.parametrize("n", [8, 12, 16])
    def test_every_player_appears_exactly_once(self, n):
        players = seeded(n)
        size = bracket_size(n)
        rng = random.Random(n * 3)
        team_of = teams_by_size(players, profile_for(n), rng)
        result = assign_slots(players, team_of, size, rng, size - n)

        assert len(result) == size
        assert sorted(p for p in result if p is not None) == players
        assert result.count(None) == size - n


class TestByeConstraint:
    """I buchi restano nei blocchi-foglia dei seed 1..b."""

    @pytest.mark.parametrize("n", [5, 6, 7, 9, 11, 13, 20, 30])
    def test_hole_slots_are_the_partners_of_the_top_seeds(self, n):
        players = seeded(n)
        size = bracket_size(n)
        rng = random.Random(n)
        team_of = teams_by_size(players, profile_for(n), rng)
        result = assign_slots(players, team_of, size, rng, size - n)

        order = standard_bracket_order(size)
        slot_of_seed = {seed: slot for slot, seed in enumerate(order)}
        expected_holes = {slot_of_seed[s] for s in range(n + 1, size + 1)}
        actual_holes = {slot for slot, p in enumerate(result) if p is None}
        assert actual_holes == expected_holes

        # Il compagno di coppia di ogni buco e' lo slot canonico di un top seed
        partner_seeds = {order[slot ^ 1] for slot in expected_holes}  # 2j <-> 2j+1
        assert partner_seeds == set(range(1, size - n + 1))

    @pytest.mark.parametrize("n", [5, 6, 7, 11, 13])
    def test_without_teams_byes_go_to_the_exact_top_seeds(self, n):
        players = seeded(n)
        size = bracket_size(n)
        result = assign_slots(players, {}, size, random.Random(0), size - n)

        bye_players = {result[slot ^ 1] for slot, p in enumerate(result) if p is None}
        assert bye_players == set(range(1, size - n + 1))

    @pytest.mark.parametrize("n", [5, 6, 7, 11, 13])
    def test_with_teams_byes_stay_in_the_top_bands(self, n):
        """Con le squadre il *posto* del bye non cambia, l'occupante si'.

        Le bande 0 e 1 sono singoletti, quindi i seed 1 e 2 tengono
        sempre il proprio bye; dalla banda 2 in su l'occupante puo'
        essere un altro membro della stessa banda.
        """
        players = seeded(n)
        size = bracket_size(n)
        holes = size - n
        rng = random.Random(n + 100)
        team_of = teams_by_size(players, profile_for(n), rng)
        result = assign_slots(players, team_of, size, rng, holes)

        bye_players = [result[slot ^ 1] for slot, p in enumerate(result) if p is None]
        allowed_bands = {band_of_seed(seed) for seed in range(1, holes + 1)}
        for player in bye_players:
            assert player is not None
            assert band_of_seed(player) in allowed_bands


class TestDeterminism:
    """Stesso rng -> stesso tabellone."""

    def test_hundred_repetitions_are_identical(self):
        players = seeded(12)
        team_of = teams_by_size(players, [5, 4, 3], random.Random(99))
        reference = assign_slots(players, team_of, 16, random.Random(42), 4)
        for _ in range(100):
            assert assign_slots(players, team_of, 16, random.Random(42), 4) == reference

    def test_different_rng_may_differ_but_stays_valid(self):
        players = seeded(16)
        team_of = teams_by_size(players, [8, 8], random.Random(5))
        results = [
            assign_slots(players, team_of, 16, random.Random(s), 0) for s in range(6)
        ]
        for result in results:
            assert sorted(p for p in result if p is not None) == players


class TestTheoreticalLimit:
    """R* = floor(log2(S/m)) + 1."""

    @pytest.mark.parametrize(
        "size,largest,expected",
        [
            (8, 1, 4),  # nessuna squadra -> nessun derby possibile
            (8, 2, 3),  # due compagni: al piu' in finale
            (8, 3, 2),
            (8, 4, 2),
            (8, 5, 1),
            (16, 4, 3),
            (16, 5, 2),
            (16, 8, 2),
            (16, 9, 1),
            (32, 4, 4),
        ],
    )
    def test_known_values(self, size, largest, expected):
        assert theoretical_first_derby_round(size, largest) == expected

    def test_first_derby_round_of_an_empty_vector(self):
        assert first_derby_round((0, 0, 0)) == 4
        assert first_derby_round((0, 2, 1)) == 2
        assert first_derby_round((1, 0, 0)) == 1


class TestSeparationQuality:
    """Quanto e' buono il tabellone prodotto."""

    @pytest.mark.parametrize("n", list(range(4, 65)))
    def test_first_derby_never_beats_the_theoretical_limit(self, n):
        """R <= R*: R* e' un maggiorante, non un obiettivo raggiungibile."""
        players = seeded(n)
        size = bracket_size(n)
        rng = random.Random(n)
        team_of = teams_by_size(players, profile_for(n), rng)
        result = assign_slots(players, team_of, size, rng, size - n)

        largest = max(
            sum(1 for p in players if team_of.get(p) == t)
            for t in set(team_of.values())
        )
        _, achieved_round = achieved(result, team_of, size)
        assert achieved_round <= theoretical_first_derby_round(size, largest)

    @pytest.mark.parametrize("n", [4, 8, 16, 32, 64])
    @pytest.mark.parametrize(
        "profile",
        [
            (2,),
            (3,),
            (4,),
            (5,),
            (7,),
            (8,),
            (2, 2),
            (3, 3),
            (4, 4),
            (5, 5),
            (8, 8),
            (2, 2, 2),
            (4, 4, 4),
            (6, 5, 4),
        ],
    )
    @pytest.mark.parametrize("rng_seed", [0, 11, 2026])
    def test_reaches_the_limit_without_byes(self, n, profile, rng_seed):
        """Senza bye il limite R* e' raggiungibile e va raggiunto."""
        if sum(profile) > n:
            pytest.skip("profilo piu' grande del campo")
        players = seeded(n)
        rng = random.Random(rng_seed)
        team_of = teams_by_size(players, profile, rng)
        result = assign_slots(players, team_of, n, rng, 0)

        _, achieved_round = achieved(result, team_of, n)
        assert achieved_round == theoretical_first_derby_round(n, max(profile))

    def test_journey_case_twelve_players_three_teams_of_four(self):
        """12 iscritti, tre squadre da 4, tabellone da 16: R* = 3."""
        players = seeded(12)
        rng = random.Random(2026)
        team_of = teams_by_size(players, [4, 4, 4], rng)
        result = assign_slots(players, team_of, 16, rng, 4)

        counts, achieved_round = achieved(result, team_of, 16)
        assert theoretical_first_derby_round(16, 4) == 3
        assert achieved_round == 3
        assert counts[0] == 0  # nessun derby al primo turno
        assert counts[1] == 0  # nessun derby ai quarti

    def test_journey_case_oversized_team_only_minimises(self):
        """Squadra da 9 su 16: R* = 1, i derby al turno 1 sono inevitabili.

        Con 9 compagni e 8 match di primo turno il principio dei cassetti
        ne impone almeno uno: il sorteggio non fallisce, minimizza.
        """
        players = seeded(16)
        team_of = {player: "big" for player in players[:9]}
        result = assign_slots(players, team_of, 16, random.Random(7), 0)

        counts, achieved_round = achieved(result, team_of, 16)
        assert theoretical_first_derby_round(16, 9) == 1
        assert achieved_round == 1
        assert counts[0] == 1  # esattamente il minimo imposto dai cassetti


class TestOptimalityAgainstBruteForce:
    """Confronto lessicografico con l'ottimo enumerato."""

    @pytest.mark.parametrize("rng_seed", [0, 1, 2, 3, 4])
    @pytest.mark.parametrize("profile", [(2,), (2, 2), (3,), (4,)])
    def test_size_four_and_eight(self, rng_seed, profile):
        for n in (4, 8):
            if sum(profile) > n:
                continue
            players = seeded(n)
            rng = random.Random(rng_seed)
            team_of = teams_by_size(players, profile, rng)
            result = assign_slots(players, team_of, n, rng, 0)

            counts = derby_counts_by_round(result, team_of, n)
            assert counts == brute_force_best(players, team_of, n)

    @pytest.mark.parametrize("rng_seed", [0, 5, 9])
    @pytest.mark.parametrize("profile", [(3,), (4,), (5,), (3, 3)])
    def test_size_sixteen_with_few_teamed_players(self, rng_seed, profile):
        players = seeded(16)
        rng = random.Random(rng_seed)
        team_of = teams_by_size(players, profile, rng)
        result = assign_slots(players, team_of, 16, rng, 0)

        counts = derby_counts_by_round(result, team_of, 16)
        assert counts == brute_force_best(players, team_of, 16)

    @pytest.mark.parametrize("n", [5, 6, 7])
    @pytest.mark.parametrize("profile", [(2,), (3,), (2, 2)])
    def test_with_byes(self, n, profile):
        players = seeded(n)
        size = bracket_size(n)
        rng = random.Random(n * 10 + sum(profile))
        team_of = teams_by_size(players, profile, rng)
        result = assign_slots(players, team_of, size, rng, size - n)

        counts = derby_counts_by_round(result, team_of, size)
        assert counts == brute_force_best(players, team_of, size)


class TestValidation:
    """Il contratto ai bordi (Step 4/6 passano dati calcolati)."""

    def test_holes_must_match_the_bracket_size(self):
        with pytest.raises(ValueError):
            assign_slots(seeded(6), {}, 8, random.Random(0), 1)

    def test_size_must_be_a_power_of_two(self):
        with pytest.raises(ValueError):
            assign_slots(seeded(6), {}, 12, random.Random(0), 6)

    def test_too_many_players_for_the_bracket(self):
        with pytest.raises(ValueError):
            assign_slots(seeded(9), {}, 8, random.Random(0), -1)

    def test_holes_cannot_reach_half_the_bracket(self):
        """b < S/2 e' l'invariante che vieta due buchi nella stessa coppia."""
        with pytest.raises(ValueError):
            assign_slots(seeded(4), {}, 8, random.Random(0), 4)

    def test_duplicate_players_are_rejected(self):
        with pytest.raises(ValueError):
            assign_slots([1, 2, 3, 3], {}, 4, random.Random(0), 0)


class TestModulePurity:
    """Il modulo e' puro: stdlib piu' il solo `bracket`."""

    ALLOWED_ROOTS = {"__future__", "collections", "math", "random", "typing"}
    ALLOWED_RELATIVE = {".bracket"}

    def test_imports_only_stdlib_and_bracket(self):
        source = Path(team_separation_module.__file__).read_text(encoding="utf-8")
        roots = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    roots.add("." * node.level + (node.module or ""))
                elif node.module:
                    roots.add(node.module.split(".")[0])

        allowed = self.ALLOWED_ROOTS | self.ALLOWED_RELATIVE
        assert roots <= allowed, f"import estranei: {sorted(roots - allowed)}"
