"""
Module: models/matchmaking/group_phase.py
Purpose: composizione dei gironi e semina del tabellone finale (formula FISBB)
Requirements: piano "Eliminazione diretta e doppio KO", Step 12

Modulo **puro**: stdlib e `bracket`, nessun DB e nessun oggetto di dominio.
Il chiamante (la strategia doppio KO) passa id opachi gia' ordinati per testa
di serie e riceve indietro la composizione dei gironi.

Due domande, due funzioni
-------------------------
1. **Chi va in quale girone** (`assign_groups`). I gironi si giocano in
   parallelo, quindi devono essere equilibrati: la distribuzione e' a
   *serpentina* — seed 1 al girone A, seed 2 al B, seed 3 al C, seed 4 al C,
   seed 5 al B, e cosi' via — che e' il modo standard di spalmare la forza
   quando i gruppi giocano contemporaneamente.

2. **Con che ordine i qualificati entrano nel tabellone finale**
   (`qualifier_seeding`).

Le squadre, qui
---------------
Dentro il girone un derby e' **tollerato**: c'e' il recupero, chi perde non e'
fuori, e la struttura del doppio KO lo renderebbe comunque quasi impossibile
da evitare (i nodi `W2` e `L1` sono alimentati dagli stessi match del turno 1,
quindi due compagni negli slot 0 e 2 si incontrano al turno 2 comunque vada).

Quel che conta davvero e' **non ammassare i compagni nello stesso girone**, ed
e' un obiettivo che si raggiunge a costo zero: dentro una riga di serpentina i
giocatori hanno seed adiacenti, quindi permutarli fra i gironi della riga non
sposta di nulla l'equilibrio di forza. `assign_groups` sfrutta esattamente
questa liberta'.

Il vincolo forte resta sul **tabellone finale**, che e' eliminazione diretta
pura: li' vale `team_separation.assign_slots` cosi' com'e', applicato dalla
strategia.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .bracket import (
    QUALIFIERS_PER_GROUP,
    group_count,
    group_phase_is_feasible,
    group_player_counts,
)


def assign_groups(
    seeded_players: Sequence[int],
    group_size: int,
    team_of: Optional[Mapping[int, Optional[object]]] = None,
) -> List[List[int]]:
    """Divide gli iscritti in gironi, restituendoli in ordine di seeding.

    Args:
        seeded_players: id in ordine di testa di serie (seed 1 per primo).
        group_size: `G`, taglia del tabellone di ogni girone (potenza di 2).
        team_of: giocatore -> squadra; `None` o chiave assente = senza
            squadra. Serve solo a scegliere *quale* girone dentro una riga di
            serpentina: non sposta nessuno di riga, quindi non altera
            l'equilibrio di forza fra i gironi.

    Returns:
        Una lista per girone, ciascuna in ordine di seeding.

    Raises:
        ValueError: se il campo non si divide senza lasciare un girone mezzo
            vuoto (vedi `bracket.group_phase_is_feasible`).
    """
    players = list(seeded_players)
    n = len(players)
    if n < 2:
        raise ValueError("servono almeno 2 giocatori")
    if len(set(players)) != n:
        raise ValueError("seeded_players contiene duplicati")

    groups = group_count(n, group_size)
    if not group_phase_is_feasible(n, group_size):
        counts = group_player_counts(n, groups)
        raise ValueError(
            f"{n} iscritti non si dividono in gironi da {group_size}: la "
            f"ripartizione sarebbe {counts} e un girone con {min(counts)} "
            f"presenti avrebbe meta' tabellone vuota"
        )

    capacity = group_player_counts(n, groups)
    teams = dict(team_of or {})
    team_sizes: Dict[object, int] = {}
    for player in players:
        team = teams.get(player)
        if team is not None:
            team_sizes[team] = team_sizes.get(team, 0) + 1

    assigned: List[List[int]] = [[] for _ in range(groups)]
    teammates_in_group: List[Dict[object, int]] = [{} for _ in range(groups)]

    for row_index, row in enumerate(_serpentine_rows(n, groups, capacity)):
        row_players = players[row_index * groups : row_index * groups + len(row)]
        for player, target in _match_row_to_groups(
            row_players, row, teams, team_sizes, teammates_in_group
        ):
            assigned[target].append(player)
            team = teams.get(player)
            if team is not None:
                counts = teammates_in_group[target]
                counts[team] = counts.get(team, 0) + 1

    return assigned


def _serpentine_rows(
    player_count: int, groups: int, capacity: Sequence[int]
) -> List[List[int]]:
    """Gironi toccati da ciascuna riga di serpentina, in ordine.

    Le righe piene percorrono i gironi alternando il verso (0..g-1, poi
    g-1..0). L'ultima riga e' parziale e viene filtrata sui gironi che hanno
    ancora capienza: cosi' la ripartizione coincide con
    `group_player_counts`, che e' quella che il chiamante ha gia' usato per
    verificare la fattibilita'.
    """
    remaining = list(capacity)
    rows: List[List[int]] = []
    placed = 0
    row_index = 0

    while placed < player_count:
        order = list(range(groups))
        if row_index % 2 == 1:
            order.reverse()
        available = [target for target in order if remaining[target] > 0]
        row = available[: min(groups, player_count - placed)]
        for target in row:
            remaining[target] -= 1
        rows.append(row)
        placed += len(row)
        row_index += 1

    return rows


def _match_row_to_groups(
    row_players: Sequence[int],
    targets: Sequence[int],
    teams: Mapping[int, Optional[object]],
    team_sizes: Mapping[object, int],
    teammates_in_group: Sequence[Mapping[object, int]],
) -> List[Tuple[int, int]]:
    """Bijezione giocatori-della-riga → gironi-della-riga, evitando i compagni.

    Greedy con i piu' vincolati per primi (squadra piu' numerosa), come in
    `team_separation`: chi ha meno alternative sceglie prima. A parita' di
    compagni gia' presenti vince l'ordine canonico della serpentina, cosi' il
    risultato e' deterministico e senza squadre coincide esattamente con la
    serpentina pura.
    """
    free = list(targets)
    pairs: List[Tuple[int, int]] = []

    def constraint(index: int) -> Tuple[int, int]:
        team = teams.get(row_players[index])
        return (-team_sizes.get(team, 0) if team is not None else 0, index)

    ordered = sorted(range(len(row_players)), key=constraint)

    for index in ordered:
        player = row_players[index]
        team = teams.get(player)
        if team is None:
            continue
        target = min(
            free,
            key=lambda group: (
                teammates_in_group[group].get(team, 0),
                targets.index(group),
            ),
        )
        free.remove(target)
        pairs.append((player, target))

    # I senza-squadra prendono quel che resta, nell'ordine della serpentina.
    placed = {player for player, _ in pairs}
    for player in row_players:
        if player not in placed:
            pairs.append((player, free.pop(0)))

    return pairs


def qualifier_seeding(qualified_by_group: Sequence[Sequence[int]]) -> List[int]:
    """Ordine di testa di serie dei qualificati al tabellone finale.

    Si legge "per colonne": prima i primi qualificati di ogni girone, poi i
    secondi, e cosi' via fino ai quarti. Cioe' i `g` migliori diretti sono i
    seed `1..g`, i secondi diretti i seed `g+1..2g`, e i ripescati occupano la
    seconda meta'.

    Tiene conto del **girone di provenienza**, ma solo in parte: i quattro
    qualificati di uno stesso girone finiscono a distanza `g` l'uno
    dall'altro nell'ordine dei seed, quindi in bande di seeding diverse. Non
    basta a garantire che non si incontrino subito — con `g = 3` i seed 7 e
    10 sono entrambi del primo girone e in un tabellone da 16 sono
    complementari, cioe' si affronterebbero al primo turno. Ad allontanarli
    davvero e' la separazione applicata dalla strategia sopra questo ordine
    (`_assign_slots(..., groups_of=...)`), che quando non ci sono squadre da
    separare usa proprio il girone.
    """
    if not qualified_by_group:
        return []

    expected = {len(group) for group in qualified_by_group}
    if expected != {QUALIFIERS_PER_GROUP}:
        raise ValueError(
            f"ogni girone deve qualificare {QUALIFIERS_PER_GROUP} atleti, "
            f"ricevuto {[len(group) for group in qualified_by_group]}"
        )

    return [
        group[rank]
        for rank in range(QUALIFIERS_PER_GROUP)
        for group in qualified_by_group
    ]


__all__ = ["assign_groups", "qualifier_seeding"]
