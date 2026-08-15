"""
Module: models/matchmaking/team_separation.py
Purpose: separazione dei compagni di squadra nel sorteggio del tabellone
Requirements: piano "Eliminazione diretta e doppio KO", Step 1 (US-6, US-10)
Decisione: docs/adr/ADR-039-team-separation-in-the-draw.md

Modulo **puro**: dipende solo dalla stdlib e da `bracket`, l'aritmetica del
tabellone. Nessun accesso al DB, nessun oggetto di dominio: chi chiama
(Step 6) legge le squadre da `Inscription.squadra_id` e passa qui id
opachi.

Il problema
-----------
Dato l'ordine di seeding degli iscritti e la loro squadra, scegliere gli
slot del primo turno in modo che i compagni si incontrino **il piu' tardi
possibile**. Con `c_r` = numero di coppie di compagni che si
incontrerebbero al turno `r`, l'obiettivo e' minimizzare
lessicograficamente `(c_1, ..., c_k)`: il primo componente non nullo e' il
turno del primo derby, quindi "rinviare il piu' possibile" non richiede un
obiettivo separato.

Cosa **non** e' libero
----------------------
- **Seeding.** Le bande sono `banda 0 = {seed 1}` e
  `banda j = {seed 2^(j-1)+1 .. 2^j}`. L'invariante del tabellone canonico
  e' che *ogni blocco di livello j contiene esattamente un seed delle
  bande 0..j*; poiche' la banda `j` ha `2^(j-1)` membri quanti sono i
  blocchi di livello `j-1`, assegnare la banda `j` significa scegliere in
  quale blocco padre entrare. Concretamente: gli slot della banda restano
  quelli canonici, si sceglie solo **quale membro** occupa **quale slot**
  della *sua* banda — esattamente "le teste di serie 5-8 si sorteggiano
  fra i quattro quarti".
- **Bye.** I `b = S - n` buchi sono i seed `n+1..S` e restano ai loro slot
  canonici, cioe' nei blocchi-foglia dei seed `1..b`. Poiche' `S` e' la
  potenza di 2 immediatamente superiore agli iscritti, `b < S/2`: mai due
  buchi nella stessa coppia.

Il costo
--------
Due slot che condividono l'antenato di livello `r` ma non quello di
livello `r+1` si incontrano al turno `k - r`. Pesando ogni coppia di
compagni con `W^(k - turno)` — quindi `W^(k-1)` per un derby al primo
turno, `W^0` per un derby in finale — e scegliendo `W` maggiore di
qualunque `c_r` (`W = S^2`, mentre `c_r <= S^2/4`), **minimizzare la somma
equivale a minimizzare il vettore lessicografico**. Il costo e' quindi
gerarchico su tutta la catena di antenati: un costo solo locale non
distinguerebbe "stessa meta'" da "meta' opposta".

Nota sull'orientamento: il peso cresce con la profondita' dell'antenato
condiviso (condividere il match di primo turno e' il caso peggiore), non
il contrario. E' la direzione imposta dall'obiettivo lessicografico.

L'algoritmo
-----------
Riempimento banda per banda, greedy per taglia di squadra decrescente
(i giocatori piu' vincolati scelgono per primi), poi 2-opt fra membri
della **stessa** banda — l'unico scambio che preserva il seeding — e
infine verifica del turno `R` ottenuto contro il limite teorico
`R* = floor(log2(S/m)) + 1`, con fino a `MAX_RESTARTS` ripartenze guidate
dallo stesso `rng` quando `R < R*` e non ci sono bye (con i bye `R*` resta
un maggiorante ma non e' garantito, quindi non e' un criterio di stop).

A parita' di costo si preferisce **lo slot canonico** del giocatore: senza
squadre il risultato coincide percio' con `standard_bracket_order`, che e'
la rete di non-regressione per chi non usa questa funzione.

Niente `networkx`: il sottoproblema e' un assignment bipartito su <= 64x64
e la sua versione a peso minimo (`minimum_weight_full_matching`)
richiederebbe `scipy`, che non e' fra le dipendenze del progetto.
"""

from __future__ import annotations

import random
from typing import Dict, Hashable, List, Mapping, Optional, Sequence, Tuple

from .bracket import bracket_levels, meet_round, standard_bracket_order

# Ripartenze massime quando il greedy non raggiunge il limite teorico.
MAX_RESTARTS = 8

# Passate massime di 2-opt (rete di sicurezza: il ciclo converge da solo).
MAX_TWO_OPT_PASSES = 32

TeamId = Hashable


def band_of_seed(seed: int) -> int:
    """Banda di seeding di un seed 1-based.

    `banda 0 = {1}`, `banda j = {2^(j-1)+1 .. 2^j}`.
    """
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 1:
        raise ValueError(f"seed deve essere un intero >= 1, ricevuto {seed!r}")
    return 0 if seed == 1 else (seed - 1).bit_length()


def theoretical_first_derby_round(size: int, largest_team: int) -> int:
    """Limite teorico `R* = floor(log2(S/m)) + 1`.

    E' il turno piu' avanzato a cui il primo derby possa essere rinviato:
    con `m` compagni e `2^L` blocchi di livello `L`, il principio dei
    cassetti impone un incontro non appena `m > 2^L`. Senza bye il limite
    e' raggiungibile dividendo ogni squadra equamente a ogni livello; con i
    bye resta un maggiorante, e l'algoritmo **misura** cio' che ottiene
    invece di assumerlo.

    Con `m = 1` (nessun compagno) vale `k + 1`, cioe' "nessun derby".
    """
    levels = bracket_levels(size)
    if largest_team < 1:
        raise ValueError("largest_team deve essere >= 1")
    return max(1, levels - (largest_team - 1).bit_length() + 1)


def derby_counts_by_round(
    assignment: Sequence[Optional[int]],
    team_of: Mapping[int, Optional[TeamId]],
    size: int,
) -> Tuple[int, ...]:
    """`(c_1, ..., c_k)` per un tabellone gia' assegnato."""
    levels = bracket_levels(size)
    placement = {
        player: slot for slot, player in enumerate(assignment) if player is not None
    }
    return _cost_vector(placement, team_of, levels)


def first_derby_round(counts: Sequence[int]) -> int:
    """Turno del primo derby, o `k + 1` se non ce ne sono."""
    for index, value in enumerate(counts):
        if value:
            return index + 1
    return len(counts) + 1


def assign_slots(
    seeded_players: Sequence[int],
    team_of: Mapping[int, Optional[TeamId]],
    size: int,
    rng: random.Random,
    holes: int,
) -> List[Optional[int]]:
    """Assegna gli iscritti agli slot del primo turno.

    Args:
        seeded_players: id dei giocatori in ordine di seeding (seed 1 per
            primo). La lunghezza e' `n`.
        team_of: giocatore -> squadra; `None` o chiave assente = senza
            squadra, e chi non ha squadra non ha compagni.
        size: `S`, potenza di 2, gia' comprensiva del pavimento di formato.
        rng: sorgente casuale del sorteggio (deterministica a parita' di
            seme).
        holes: `b = S - n`, passato dal chiamante e verificato qui: e' il
            punto in cui le due grandezze devono coincidere, e un
            disallineamento a monte produrrebbe altrimenti un tabellone
            silenziosamente sbagliato.

    Returns:
        Lista lunga `S`: indice = slot, valore = id del giocatore, oppure
        `None` per un buco (l'avversario riceve un bye).
    """
    players = list(seeded_players)
    n = len(players)

    if n < 2:
        raise ValueError("servono almeno 2 giocatori")
    if len(set(players)) != n:
        raise ValueError("seeded_players contiene duplicati")
    levels = bracket_levels(size)  # valida anche che size sia potenza di 2
    if n > size:
        raise ValueError(f"{n} giocatori non entrano in un tabellone da {size}")
    if holes != size - n:
        raise ValueError(
            f"holes={holes} incoerente con size - n = {size - n}: "
            "il chiamante deve dimensionare il tabellone sugli iscritti"
        )
    if 2 * holes >= size:
        raise ValueError(
            f"{holes} buchi su {size} slot violano b < S/2: il tabellone "
            "non e' dimensionato sugli iscritti effettivi"
        )

    slot_of_seed = {
        seed: slot for slot, seed in enumerate(standard_bracket_order(size))
    }
    canonical_slot = {players[seed - 1]: slot_of_seed[seed] for seed in range(1, n + 1)}

    # (membri, slot) per banda. Gli slot dei seed > n sono i buchi e non
    # entrano fra quelli assegnabili: restano dove il canonico li mette.
    bands: List[Tuple[List[int], List[int]]] = []
    for band in range(levels + 1):
        seeds = [1] if band == 0 else list(range(2 ** (band - 1) + 1, 2**band + 1))
        members = [players[seed - 1] for seed in seeds if seed <= n]
        slots = [slot_of_seed[seed] for seed in seeds if seed <= n]
        if members:
            bands.append((members, slots))

    team_members: Dict[TeamId, List[int]] = {}
    for player in players:
        team = team_of.get(player)
        if team is not None:
            team_members.setdefault(team, []).append(player)
    largest_team = max((len(m) for m in team_members.values()), default=1)

    # W deve superare qualunque c_r (<= S^2/4) perche' la somma pesata
    # coincida con l'ordine lessicografico del vettore.
    powers = [(size * size) ** level for level in range(levels + 1)]

    def pair_cost(slot_a: int, slot_b: int) -> int:
        return powers[levels - meet_round(slot_a, slot_b)]

    target_round = theoretical_first_derby_round(size, largest_team)
    best_placement: Optional[Dict[int, int]] = None
    best_vector: Optional[Tuple[int, ...]] = None

    for _ in range(1 + MAX_RESTARTS):
        placement = _greedy_placement(
            bands, team_of, team_members, canonical_slot, pair_cost, rng
        )
        _two_opt(bands, team_of, team_members, placement, pair_cost)
        vector = _cost_vector(placement, team_of, levels)

        if best_vector is None or vector < best_vector:
            best_placement, best_vector = placement, vector

        # Con i bye R* non e' garantito: ripartire non avrebbe un criterio
        # di arresto sensato, quindi si accetta il primo tentativo.
        if holes or first_derby_round(best_vector) >= target_round:
            break

    assert best_placement is not None  # il ciclo gira almeno una volta
    assignment: List[Optional[int]] = [None] * size
    for player, slot in best_placement.items():
        assignment[slot] = player
    return assignment


# --------------------------------------------------------------------------
# Interni
# --------------------------------------------------------------------------


def _cost_vector(
    placement: Mapping[int, int],
    team_of: Mapping[int, Optional[TeamId]],
    levels: int,
) -> Tuple[int, ...]:
    """`(c_1, ..., c_k)` da una mappa giocatore -> slot."""
    counts = [0] * (levels + 1)
    by_team: Dict[TeamId, List[int]] = {}
    for player, slot in placement.items():
        team = team_of.get(player)
        if team is not None:
            by_team.setdefault(team, []).append(slot)

    for slots in by_team.values():
        for index, slot_a in enumerate(slots):
            for slot_b in slots[index + 1 :]:
                counts[meet_round(slot_a, slot_b)] += 1
    return tuple(counts[1:])


def _teammate_slots(
    player: int,
    team_of: Mapping[int, Optional[TeamId]],
    team_members: Mapping[TeamId, List[int]],
    placement: Mapping[int, int],
    exclude: Tuple[int, ...] = (),
) -> List[int]:
    """Slot gia' occupati dai compagni di `player`."""
    team = team_of.get(player)
    if team is None:
        return []
    return [
        placement[mate]
        for mate in team_members[team]
        if mate != player and mate not in exclude and mate in placement
    ]


def _greedy_placement(
    bands: Sequence[Tuple[List[int], List[int]]],
    team_of: Mapping[int, Optional[TeamId]],
    team_members: Mapping[TeamId, List[int]],
    canonical_slot: Mapping[int, int],
    pair_cost,
    rng: random.Random,
) -> Dict[int, int]:
    """Riempimento banda per banda, giocatori piu' vincolati per primi."""
    placement: Dict[int, int] = {}

    for members, slots in bands:
        free = list(slots)
        for player in _greedy_order(members, team_of, team_members, rng):
            mates = _teammate_slots(player, team_of, team_members, placement)
            best_cost: Optional[int] = None
            candidates: List[int] = []
            for slot in free:
                cost = sum(pair_cost(slot, mate) for mate in mates)
                if best_cost is None or cost < best_cost:
                    best_cost, candidates = cost, [slot]
                elif cost == best_cost:
                    candidates.append(slot)

            # A parita' di costo lo slot canonico: senza squadre l'output
            # coincide con standard_bracket_order.
            preferred = canonical_slot[player]
            chosen = preferred if preferred in candidates else rng.choice(candidates)
            placement[player] = chosen
            free.remove(chosen)

    return placement


def _greedy_order(
    members: Sequence[int],
    team_of: Mapping[int, Optional[TeamId]],
    team_members: Mapping[TeamId, List[int]],
    rng: random.Random,
) -> List[int]:
    """Membri della banda per taglia di squadra decrescente.

    Lo shuffle prima dell'ordinamento stabile fornisce il tie-break
    casuale fra squadre di pari taglia, ed e' cio' che rende diverse le
    ripartenze.
    """
    shuffled = list(members)
    rng.shuffle(shuffled)

    def team_size(player: int) -> int:
        team = team_of.get(player)
        return len(team_members[team]) if team is not None else 0

    return sorted(shuffled, key=lambda player: -team_size(player))


def _two_opt(
    bands: Sequence[Tuple[List[int], List[int]]],
    team_of: Mapping[int, Optional[TeamId]],
    team_members: Mapping[TeamId, List[int]],
    placement: Dict[int, int],
    pair_cost,
) -> None:
    """Scambi migliorativi fra membri della stessa banda (in place).

    Lo scambio intra-banda e' l'unica mossa locale che preserva il vincolo
    di seeding. La coppia `(p, q)` stessa non cambia turno d'incontro —
    restano sui medesimi due slot — quindi e' esclusa dal delta.
    """
    for _ in range(MAX_TWO_OPT_PASSES):
        improved = False
        for members, _slots in bands:
            for index, player_a in enumerate(members):
                for player_b in members[index + 1 :]:
                    slot_a, slot_b = placement[player_a], placement[player_b]
                    mates_a = _teammate_slots(
                        player_a, team_of, team_members, placement, (player_b,)
                    )
                    mates_b = _teammate_slots(
                        player_b, team_of, team_members, placement, (player_a,)
                    )
                    if not mates_a and not mates_b:
                        continue

                    before = sum(pair_cost(slot_a, m) for m in mates_a) + sum(
                        pair_cost(slot_b, m) for m in mates_b
                    )
                    after = sum(pair_cost(slot_b, m) for m in mates_a) + sum(
                        pair_cost(slot_a, m) for m in mates_b
                    )
                    if after < before:
                        placement[player_a], placement[player_b] = slot_b, slot_a
                        improved = True
        if not improved:
            return
