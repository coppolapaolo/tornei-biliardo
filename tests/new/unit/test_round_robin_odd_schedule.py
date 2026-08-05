"""Regression: lo schedule Round Robin per N dispari deve ruotare le coppie.

Bug (code review 2026-06-09, HIGH correttezza) —
`models/matchmaking/strategies/round_robin.py:137`:

Per un numero DISPARI di giocatori il ramo dispari ricalcolava
`active_players` dall'ordine FISSO `player_ids` togliendo solo il giocatore
in bye, e accoppiava sempre simmetricamente (`active[i]` vs `active[-(i+1)]`).
La geometria degli accoppiamenti non ruotava mai: molte coppie si ripetevano
ogni turno e altre non si incontravano mai, violando l'invariante
"tutti contro tutti esattamente una volta".

Lo scenario esatto del finding (5 giocatori) produceva ad es. (p2,p3)
ripetuta e le coppie (p0,p1)/(p0,p2)/(p2,p4)/(p3,p4) mai giocate.

Il ramo pari era già corretto (metodo del poligono): questi test coprono
entrambi i casi per evitare regressioni.
"""

from __future__ import annotations

from itertools import combinations
from typing import List, Tuple

import pytest

from models.matchmaking.strategies.round_robin import RoundRobinStrategy


def _flatten(schedule: List[List[Tuple[int, ...]]]):
    """Estrae (coppie, bye) da uno schedule.

    Ritorna (pairs, byes) dove pairs è la lista di frozenset{a, b} per ogni
    match a 2 giocatori e byes è la lista di id che riposano.
    """
    pairs: List[frozenset] = []
    byes: List[int] = []
    for round_pairings in schedule:
        for pairing in round_pairings:
            if len(pairing) == 1:
                byes.append(pairing[0])
            elif len(pairing) == 2:
                pairs.append(frozenset(pairing))
    return pairs, byes


@pytest.mark.unit
@pytest.mark.parametrize("n", [3, 5, 7, 9])
def test_odd_round_robin_is_complete_and_unique(n: int):
    """N dispari: ogni coppia esattamente una volta, un bye a testa, N turni."""
    strategy = RoundRobinStrategy()
    players = list(range(100, 100 + n))

    schedule = strategy._generate_round_robin_schedule(players)

    # Un turno per giocatore (ognuno riposa una volta).
    assert len(schedule) == n

    pairs, byes = _flatten(schedule)

    # Ogni coppia possibile compare esattamente una volta.
    expected_pairs = {frozenset(c) for c in combinations(players, 2)}
    assert len(pairs) == len(expected_pairs), "Numero di match errato"
    assert len(set(pairs)) == len(pairs), "Coppia ripetuta nello schedule"
    assert set(pairs) == expected_pairs, "Alcune coppie non si incontrano mai"

    # Ogni giocatore riposa esattamente una volta.
    assert sorted(byes) == players


@pytest.mark.unit
def test_odd_round_robin_five_players_specific_scenario():
    """Scenario esatto del finding: 5 giocatori, nessuna coppia ripetuta."""
    strategy = RoundRobinStrategy()
    players = [0, 1, 2, 3, 4]

    schedule = strategy._generate_round_robin_schedule(players)
    pairs, byes = _flatten(schedule)

    # Prima del fix (p2,p3) ricorreva e mancavano (p0,p1),(p0,p2),(p2,p4),(p3,p4).
    assert len(set(pairs)) == 10
    assert frozenset((0, 1)) in pairs
    assert sorted(byes) == players


@pytest.mark.unit
@pytest.mark.parametrize("n", [4, 6, 8])
def test_even_round_robin_unchanged(n: int):
    """N pari: nessuna regressione — tutte le coppie una volta, nessun bye."""
    strategy = RoundRobinStrategy()
    players = list(range(200, 200 + n))

    schedule = strategy._generate_round_robin_schedule(players)

    assert len(schedule) == n - 1

    pairs, byes = _flatten(schedule)
    expected_pairs = {frozenset(c) for c in combinations(players, 2)}
    assert set(pairs) == expected_pairs
    assert len(set(pairs)) == len(pairs)
    assert byes == []
