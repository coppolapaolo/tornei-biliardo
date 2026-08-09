"""
Module: models/matchmaking/bracket.py
Purpose: Aritmetica pura del tabellone (eliminazione diretta e doppio KO)
Requirements: piano "Eliminazione diretta e doppio KO", Step 0

Modulo **puro**: nessuna dipendenza da Flask, SQLAlchemy o dal resto del
dominio. Contiene solo la matematica del tabellone, cosi' che le strategie
di matchmaking (Step 4, 5, 7) e la separazione delle squadre (Step 1)
possano appoggiarsi a un unico posto testabile senza DB.

Convenzioni
-----------
- **slot**: posizione 0-based nel primo turno del tabellone. Il match `j`
  del primo turno accoppia gli slot `2j` e `2j+1`.
- **seed**: numero di testa di serie, 1-based (1 = primo favorito).
- **bracket_round**: turno interno a un bracket, 1-based. Non coincide con
  il turno di gara nel doppio KO, dove un turno di gara puo' contenere due
  round di bracket (winners + losers): la corrispondenza la da'
  `bracket_schedule`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

# Codici persistiti su Match.bracket_type (Step 2)
BRACKET_WINNERS = "W"
BRACKET_LOSERS = "L"
BRACKET_GRAND_FINAL = "GF"
BRACKET_GRAND_FINAL_RESET = "GFR"
BRACKET_THIRD_PLACE = "3P"

# Pavimenti di formato (US-4): sotto queste taglie il tabellone non ha senso
# (per il doppio KO il losers bracket sarebbe troppo corto).
MIN_BRACKET_SIZE_DIRECT_ELIMINATION = 4
MIN_BRACKET_SIZE_DOUBLE_KNOCKOUT = 8


@dataclass(frozen=True)
class BracketRound:
    """Un round di bracket collocato in un turno di gara.

    `n_matches` e' il numero di nodi che il round contiene a tabellone
    pieno; i buchi (bye) possono ridurre i nodi effettivamente
    materializzati nel losers bracket (Step 7).
    """

    bracket_type: str
    bracket_round: int
    n_matches: int


def _require_positive(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} deve essere un intero >= 1, ricevuto {value!r}")


def _require_power_of_two(size: int, name: str = "size") -> None:
    _require_positive(size, name)
    if size & (size - 1) != 0:
        raise ValueError(f"{name} deve essere una potenza di 2, ricevuto {size}")


def bracket_size(player_count: int) -> int:
    """Dimensione del tabellone: `S = 2**ceil(log2(n))`.

    Calcolata con `bit_length` invece di `math.log2` per evitare gli errori
    di arrotondamento in virgola mobile sulle potenze grandi.

    Poiche' `S` e' la potenza di 2 *immediatamente* superiore, i buchi
    `b = S - n` sono sempre meno della meta' degli slot: mai due buchi
    nella stessa coppia, mai un bye oltre il primo turno del winners
    bracket.
    """
    _require_positive(player_count, "player_count")
    return 1 << (player_count - 1).bit_length()


def bracket_levels(size: int) -> int:
    """Numero di turni del winners bracket: `k = log2(S)`."""
    _require_power_of_two(size)
    return size.bit_length() - 1


def standard_bracket_order(size: int) -> List[int]:
    """Ordine canonico "snake" dei seed: indice = slot, valore = seed.

    Costruzione ricorsiva: `order(1) = [1]` e ogni raddoppio sostituisce il
    seed `s` con la coppia complementare `(s, 2m+1-s)`, **alternando il
    verso** a ogni posizione — da cui il nome *snake*. L'alternanza e' cio'
    che distingue questa forma dalla variante non specchiata: le due sono
    equivalenti come struttura (stessi accoppiamenti, stessi turni
    d'incontro) e differiscono solo per la specularita' dei sotto-blocchi.

    Per S=8 produce `[1, 8, 5, 4, 3, 6, 7, 2]`.

    Proprieta' garantite (regola federale di distribuzione):
    - il match `j` del primo turno accoppia seed complementari
      (`order[2j] + order[2j+1] == S + 1`);
    - a ogni livello i primi `2^level` seed cadono in blocchi distinti:
      1 e 2 in meta' opposte, 3 e 4 nei quarti rimasti liberi, 5-8 negli
      ottavi, e cosi' via.
    """
    _require_power_of_two(size)

    order = [1]
    while len(order) < size:
        total = 2 * len(order)
        doubled: List[int] = []
        for index, seed in enumerate(order):
            mirror = total + 1 - seed
            if index % 2 == 0:
                doubled.extend((seed, mirror))
            else:
                doubled.extend((mirror, seed))
        order = doubled
    return order


def meet_round(slot_a: int, slot_b: int) -> int:
    """Turno del winners bracket in cui due slot possono incontrarsi.

    E' il minimo `r >= 1` per cui `slot_a >> r == slot_b >> r`: due slot
    adiacenti si incontrano al turno 1, due slot in meta' opposte di un
    tabellone da `S` al turno `log2(S)`.
    """
    if slot_a < 0 or slot_b < 0:
        raise ValueError("gli slot devono essere >= 0")
    if slot_a == slot_b:
        raise ValueError("meet_round richiede due slot distinti")

    shifted_a, shifted_b = slot_a, slot_b
    rounds = 0
    while shifted_a != shifted_b:
        shifted_a >>= 1
        shifted_b >>= 1
        rounds += 1
    return rounds


def wb_feed(bracket_round: int, slot: int) -> Tuple[int, int, int]:
    """Destinazione del vincitore del match `(bracket_round, slot)`.

    Restituisce `(bracket_round + 1, slot // 2, seat)` con `seat = slot % 2`.
    Il seat **non** viene persistito: e' derivabile dallo slot, e una
    colonna in piu' sarebbe ridondanza desincronizzabile (Step 2).
    """
    _require_positive(bracket_round, "bracket_round")
    if slot < 0:
        raise ValueError("slot deve essere >= 0")
    return (bracket_round + 1, slot // 2, slot % 2)


def losers_feed_permutation(wb_round: int, n_matches: int) -> List[int]:
    """Permutazione dei perdenti del winners bracket verso il losers.

    Il round *maggiore* `L_{2j}` accoppia il vincitore di `(L, 2j-1, s)`
    con il perdente di `(W, j+1, sigma(s))`. La baseline e' l'inversione
    `sigma(s) = n_matches - 1 - s`, che allontana i perdenti recenti dai
    sopravvissuti provenienti dallo stesso ramo.

    E' isolata in una funzione propria — invece che inline nel generatore —
    per poterla raffinare (schemi di incrocio piu' elaborati) senza
    toccare il codice che costruisce il tabellone.

    `wb_round` non e' usato dalla baseline ma fa parte della firma: uno
    schema raffinato dipende dal round di provenienza.
    """
    _require_positive(wb_round, "wb_round")
    _require_positive(n_matches, "n_matches")
    return [n_matches - 1 - s for s in range(n_matches)]


def total_rounds(size: int, *, double_elimination: bool = False) -> int:
    """Turni di gara necessari: `k` per la DE, `2k + 1` per il doppio KO.

    Il `+1` del doppio KO e' la bella (grand final reset), che puo' restare
    vuota: un turno con zero pairing significa "torneo concluso", non
    errore (Step 8).
    """
    levels = bracket_levels(size)
    return 2 * levels + 1 if double_elimination else levels


def bracket_schedule(
    size: int, *, double_elimination: bool = False
) -> Dict[int, List[BracketRound]]:
    """Mappa turno di gara -> round di bracket che vi si giocano.

    Eliminazione diretta: il turno `w` contiene il solo `W_w`.

    Doppio KO (`k = log2(S)`): `W_w` al turno `w`, `L_m` al turno `m + 1`,
    la grand final al turno `2k` e la bella al turno `2k + 1`. Per S=8:
    R1=W1, R2=W2+L1, R3=W3+L2, R4=L3, R5=L4, R6=GF, R7=GFR.

    Conteggi: `W_r` ha `S / 2^r` match; il losers bracket alterna round
    *minori* `L_{2j-1}` e *maggiori* `L_{2j}`, entrambi con
    `S / 2^(j+1)` match, per un totale di `S - 2`.
    """
    _require_power_of_two(size)
    if size < 2:
        raise ValueError("un tabellone richiede almeno 2 slot")

    levels = bracket_levels(size)
    schedule: Dict[int, List[BracketRound]] = {
        w: [BracketRound(BRACKET_WINNERS, w, size >> w)] for w in range(1, levels + 1)
    }

    if not double_elimination:
        return schedule

    for lb_round in range(1, 2 * levels - 1):
        # I round minore (2j-1) e maggiore (2j) condividono lo stesso j.
        j = (lb_round + 1) // 2
        gara_round = lb_round + 1
        schedule.setdefault(gara_round, []).append(
            BracketRound(BRACKET_LOSERS, lb_round, size >> (j + 1))
        )

    schedule.setdefault(2 * levels, []).append(BracketRound(BRACKET_GRAND_FINAL, 1, 1))
    schedule.setdefault(2 * levels + 1, []).append(
        BracketRound(BRACKET_GRAND_FINAL_RESET, 1, 1)
    )
    return schedule
