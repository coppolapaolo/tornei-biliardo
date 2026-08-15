"""Unit tests per la fase a gironi della formula FISBB (Step 12).

Copre:
1. Aritmetica del girone (`group_size_for`, `group_phase_rounds`,
   `group_schedule`, `group_count`, `group_player_counts`)
2. Fattibilita' della divisione in gironi (`group_phase_is_feasible`)
3. Tabellone finale (`final_bracket_size`, `group_format_total_rounds`)
4. Composizione dei gironi (`assign_groups`): serpentina, ripartizione,
   determinismo, separazione delle squadre fra gironi
5. Semina del tabellone finale (`qualifier_seeding`)

Tutti i test sono puri: nessuna app fixture, nessun DB.
"""

import pytest

from models.matchmaking.bracket import (
    BRACKET_LOSERS,
    BRACKET_WINNERS,
    MIN_GROUP_DOUBLE_KO_ROUNDS,
    QUALIFIERS_PER_GROUP,
    bracket_schedule,
    final_bracket_size,
    group_count,
    group_format_total_rounds,
    group_phase_is_feasible,
    group_phase_rounds,
    group_player_counts,
    group_schedule,
    group_size_for,
)
from models.matchmaking.group_phase import assign_groups, qualifier_seeding

# ── 1. Aritmetica del girone ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "double_ko_rounds,expected_size", [(2, 8), (3, 16), (4, 32), (5, 64)]
)
def test_group_size_is_two_to_the_rounds_plus_one(double_ko_rounds, expected_size):
    assert group_size_for(double_ko_rounds) == expected_size


@pytest.mark.parametrize("double_ko_rounds", [0, 1, -3])
def test_group_size_rejects_too_few_rounds(double_ko_rounds):
    """Sotto due turni il troncamento non toglierebbe nulla."""
    with pytest.raises(ValueError):
        group_size_for(double_ko_rounds)


def test_fisbb_group_is_eight_players():
    """Il regolamento FISBB: gironi da 8, doppio KO ai primi 2 turni."""
    assert group_size_for(MIN_GROUP_DOUBLE_KO_ROUNDS) == 8


@pytest.mark.parametrize("double_ko_rounds,expected", [(2, 3), (3, 5), (4, 7)])
def test_group_phase_lasts_two_w_minus_one_rounds(double_ko_rounds, expected):
    assert group_phase_rounds(double_ko_rounds) == expected


def test_fisbb_group_schedule_matches_the_regulation():
    """Turno 1: W1. Turno 2: W2 + L1. Turno 3: L2. Nient'altro."""
    schedule = group_schedule(2)

    assert sorted(schedule) == [1, 2, 3]
    assert [(r.bracket_type, r.bracket_round, r.n_matches) for r in schedule[1]] == [
        (BRACKET_WINNERS, 1, 4)
    ]
    assert [(r.bracket_type, r.bracket_round, r.n_matches) for r in schedule[2]] == [
        (BRACKET_WINNERS, 2, 2),
        (BRACKET_LOSERS, 1, 2),
    ]
    assert [(r.bracket_type, r.bracket_round, r.n_matches) for r in schedule[3]] == [
        (BRACKET_LOSERS, 2, 2),
    ]


@pytest.mark.parametrize("double_ko_rounds", [2, 3, 4])
def test_group_schedule_is_a_prefix_of_the_full_double_ko(double_ko_rounds):
    """Il girone non e' un formato nuovo: e' il doppio KO fermato prima.

    Ogni round del girone deve comparire identico — stesso turno di gara,
    stesso numero di match — nello schedule del doppio KO pieno da `G`.
    """
    size = group_size_for(double_ko_rounds)
    full = bracket_schedule(size, double_elimination=True)

    for gara_round, rounds in group_schedule(double_ko_rounds).items():
        for entry in rounds:
            assert entry in full[gara_round]


@pytest.mark.parametrize("double_ko_rounds", [2, 3, 4])
def test_group_qualifies_two_direct_and_two_recovery(double_ko_rounds):
    """L'invariante che giustifica `G = 2^(w+1)`."""
    schedule = group_schedule(double_ko_rounds)
    last_round = max(schedule)

    winners_rounds = [
        entry
        for rounds in schedule.values()
        for entry in rounds
        if entry.bracket_type == BRACKET_WINNERS
    ]
    losers_rounds = [
        entry
        for rounds in schedule.values()
        for entry in rounds
        if entry.bracket_type == BRACKET_LOSERS
    ]

    # I due imbattuti sono i vincitori dell'ultimo round di winners...
    assert max(winners_rounds, key=lambda r: r.bracket_round).n_matches == 2
    # ...i due ripescati quelli dell'ultimo round di recupero, che chiude la
    # fase a gironi.
    last_losers = max(losers_rounds, key=lambda r: r.bracket_round)
    assert last_losers.n_matches == 2
    assert last_losers in schedule[last_round]
    assert 2 + 2 == QUALIFIERS_PER_GROUP


# ── 2. Divisione del campo in gironi ──────────────────────────────────────


@pytest.mark.parametrize(
    "player_count,expected", [(8, 1), (9, 2), (16, 2), (17, 3), (20, 3), (24, 3)]
)
def test_group_count_rounds_up(player_count, expected):
    assert group_count(player_count, 8) == expected


@pytest.mark.parametrize(
    "player_count,groups,expected",
    [(20, 3, [7, 7, 6]), (16, 2, [8, 8]), (17, 3, [6, 6, 5]), (8, 1, [8])],
)
def test_group_player_counts_are_as_even_as_possible(player_count, groups, expected):
    assert group_player_counts(player_count, groups) == expected


def test_nine_players_do_not_split_into_groups_of_eight():
    """Due gironi da 5 e 4: quello da 4 avrebbe meta' tabellone vuota.

    E' l'unico numero di iscritti che il formato rifiuta con `G = 8`, e va
    rifiutato esplicitamente invece di produrre un nodo con due buchi.
    """
    assert group_phase_is_feasible(9, 8) is False
    with pytest.raises(ValueError, match="non si dividono"):
        assign_groups(list(range(1, 10)), 8)


@pytest.mark.parametrize("player_count", [5, 6, 7, 8, 10, 11, 12, 16, 17, 20, 30, 40])
def test_feasible_splits_keep_every_group_more_than_half_full(player_count):
    assert group_phase_is_feasible(player_count, 8) is True
    groups = assign_groups(list(range(1, player_count + 1)), 8)
    assert sum(len(group) for group in groups) == player_count
    assert all(2 * len(group) > 8 for group in groups)


# ── 3. Tabellone finale ───────────────────────────────────────────────────


@pytest.mark.parametrize("groups,expected", [(1, 4), (2, 8), (3, 16), (4, 16), (5, 32)])
def test_final_bracket_holds_four_qualifiers_per_group(groups, expected):
    assert final_bracket_size(groups) == expected


def test_twenty_players_give_three_groups_and_a_sixteen_bracket():
    """Lo scenario del piano: 20 iscritti, 3 gironi, 12 qualificati, 4 bye."""
    groups = group_count(20, 8)
    assert groups == 3
    assert groups * QUALIFIERS_PER_GROUP == 12
    assert final_bracket_size(groups) == 16
    # 3 turni di gironi + 4 turni di tabellone finale
    assert group_format_total_rounds(20, 2) == 7


def test_single_group_still_produces_a_final_bracket():
    """8 iscritti: un girone, 4 qualificati, semifinali + finale."""
    assert group_format_total_rounds(8, 2) == 3 + 2


# ── 4. Composizione dei gironi ────────────────────────────────────────────


def test_serpentine_spreads_the_top_seeds():
    """I primi `g` seed finiscono in gironi distinti, poi il verso si inverte."""
    groups = assign_groups(list(range(1, 25)), 8)

    assert [group[0] for group in groups] == [1, 2, 3]
    assert [group[1] for group in groups] == [6, 5, 4]
    assert [group[2] for group in groups] == [7, 8, 9]


def test_groups_keep_the_seeding_order_inside():
    groups = assign_groups(list(range(1, 21)), 8)
    for group in groups:
        assert group == sorted(group)


def test_assign_groups_is_deterministic():
    players = list(range(1, 21))
    teams = {player: player % 4 for player in players}
    first = assign_groups(players, 8, teams)
    for _ in range(20):
        assert assign_groups(players, 8, teams) == first


def test_without_teams_the_split_is_the_pure_serpentine():
    """Rete di non-regressione: chi non usa le squadre non vede differenze."""
    players = list(range(1, 21))
    assert assign_groups(players, 8, {player: None for player in players}) == (
        assign_groups(players, 8)
    )


def test_teammates_are_spread_across_groups():
    """Otto compagni su 24 iscritti, uno ogni tre seed: il caso che punisce
    la serpentina pura.

    Con 3 gironi la serpentina manda i seed 1, 7, 13, 19 sempre nel girone 0 e
    i seed 4, 10, 16, 22 sempre nel girone 2: quattro compagni in due gironi e
    nessuno nel terzo. La permutazione dentro la riga li ridistribuisce senza
    spostare nessuno di riga, quindi senza toccare l'equilibrio di forza.
    """
    players = list(range(1, 25))
    members = {1, 4, 7, 10, 13, 16, 19, 22}
    teams = {player: ("rossi" if player in members else None) for player in players}

    serpentine = assign_groups(players, 8)
    assert sorted(sum(1 for p in group if p in members) for group in serpentine) == [
        0,
        4,
        4,
    ]

    groups = assign_groups(players, 8, teams)
    assert sorted(sum(1 for p in group if p in members) for group in groups) == [
        2,
        3,
        3,
    ]


def test_a_team_larger_than_the_field_of_groups_is_only_thinned():
    """Dodici compagni su tre gironi: quattro per girone, non dodici in uno.

    Non c'e' modo di evitare che si incontrino — l'obiettivo e' distribuirli.
    """
    players = list(range(1, 25))
    members = set(range(1, 13))
    teams = {player: ("rossi" if player in members else None) for player in players}

    groups = assign_groups(players, 8, teams)
    per_group = [sum(1 for p in group if p in members) for group in groups]

    assert sorted(per_group) == [4, 4, 4]


def test_group_split_rejects_duplicates():
    with pytest.raises(ValueError, match="duplicati"):
        assign_groups([1, 2, 3, 4, 5, 5], 8)


# ── 5. Semina del tabellone finale ────────────────────────────────────────


def test_qualifier_seeding_reads_by_columns():
    """Prima i primi di ogni girone, poi i secondi, poi i ripescati."""
    qualified = [
        [11, 12, 13, 14],  # girone 0: 2 diretti, 2 recuperi
        [21, 22, 23, 24],
        [31, 32, 33, 34],
    ]
    assert qualifier_seeding(qualified) == [
        11,
        21,
        31,
        12,
        22,
        32,
        13,
        23,
        33,
        14,
        24,
        34,
    ]


def test_qualifier_seeding_puts_groupmates_in_different_seeding_bands():
    """Il girone di provenienza e' gestito dall'ordine, non da un secondo
    criterio di separazione: i quattro di uno stesso girone distano `g`."""
    qualified = [[10 * g + rank for rank in range(4)] for g in range(1, 4)]
    order = qualifier_seeding(qualified)

    for group in qualified:
        seeds = sorted(order.index(player) for player in group)
        assert [seeds[i + 1] - seeds[i] for i in range(3)] == [3, 3, 3]


def test_qualifier_seeding_rejects_a_group_with_the_wrong_size():
    with pytest.raises(ValueError, match="qualificare"):
        qualifier_seeding([[1, 2, 3, 4], [5, 6, 7]])


def test_qualifier_seeding_of_no_groups_is_empty():
    assert qualifier_seeding([]) == []
