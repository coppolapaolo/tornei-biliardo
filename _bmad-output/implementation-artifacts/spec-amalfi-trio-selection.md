---
title: 'Amalfi trio selection: anti-rematch + fair rotation'
type: 'bugfix'
created: '2026-04-07'
status: 'done'
baseline_commit: 'e640b6a'
context:
  - docs/SPECIFICHE.md
  - docs/adr/ADR-005-distance-classification-trio-rules.md
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La selezione dei giocatori per il trio nella strategia Amalfi ha tre lacune: (1) non verifica l'anti-rematch tra i 3 giocatori selezionati — possono finire nello stesso trio giocatori che si sono già incontrati; (2) la minimizzazione è binaria (set "ha fatto almeno un trio") anziché contare quanti trio ha fatto ogni giocatore; (3) la specifica in SPECIFICHE.md non definisce i criteri di selezione. Di conseguenza i giocatori più bassi in classifica accumulano trio ripetuti e con gli stessi avversari.

**Approach:** Algoritmo a 3 step. **Step 1 (Salto)**: il salto Amalfi standard gira con BYE sentinel — nessuna modifica alla logica esistente. Il while loop viene refactorizzato per produrre una rappresentazione intermedia (`anchor: int` + `pairs: list[tuple[int,int]]`) anziché Pairing finali. **Step 2 (Swap)**: se l'ancora ha `trio_count > min_trio_count`, viene scambiata con il giocatore in coppia che ha trio_count minimo e, a parità, quello più basso in classifica. Nessun check rematch — è compito dello Step 3. **Step 3 (Compagni)**: tra tutte le C(N-1,2) combinazioni di 2 giocatori dal pool, uno score a tuple `(companion_count_sum, trio_rematches, orphan_rematch, -position_sum)` seleziona i 2 migliori. Infine la ricomposizione converte la rappresentazione intermedia in `Sequence[Pairing]`.

## Boundaries & Constraints

**Always:**
- Ordine di sacrificio (cosa si cede per prima quando i vincoli confliggono): (1°) posizione in classifica — si devia dallo spirito Amalfi pur di evitare rematch; (2°) anti-rematch — si accetta un rematch nel trio pur di garantire rotazione equa; (3° ultima a cedere) rotazione equa — la differenza di trio_count tra giocatori deve restare minima
- Lo Step 1 (salto) non viene modificato nella logica — nessuna condizione aggiuntiva nel cycling. La rotazione è gestita dallo Step 2 (swap post-salto)
- `_amalfi_pairing` resta pure computation: solo letture DB (encounter_matrix, trio_counts, classifiche), nessuna scrittura. Conforme al contratto `@transactional` sul caller (`RoundCreationService`)
- BYE_PLAYER_ID (-1) è usato solo durante il salto; non deve MAI comparire in un Pairing di output. Asserzione esplicita prima della ricomposizione
- `orphan_rematch` nello score è un soft penalty, non un vincolo hard: se tutte le combinazioni producono orfani con rematch, si accetta il male minore
- Quando la compensazione è impossibile (tutti i giocatori hanno lo stesso trio_count), il risultato è "best effort" e i tiebreaker (rematches, classifica) determinano la scelta
- `use_trio` e `use_bye` sono mutuamente esclusivi per gara (odd_number_policy è fissa per tutta la gara)
- Usare `PlayerEncounterService.get_encounter_matrix(gara_id)` per tutti i check anti-rematch nello Step 3 (1 query, lookup in memoria)
- I 3 giocatori del trio nel Pairing di output sono ordinati per posizione in classifica (coerente con il comportamento attuale), indipendentemente da chi è l'ancora

**Ask First:**
- Se lo Step 3 con C(N-1,2) combinazioni risulta troppo lento per tornei molto grandi (>50 giocatori)

**Never:**
- Non modificare il cycling del salto (righe 339-362) — lo Step 2 opera dopo il salto, non dentro
- Non modificare il modello TrioMatch o il flusso di completamento trio
- Non cambiare come i PlayerEncounter vengono registrati per i trio (già corretto)

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Primo trio, nessun storico | 7 giocatori, round 1 | Salto determina ancora; Step 3 sceglie coppia più bassa (tutti a trio_count=0) | N/A |
| Swap ancora: ancora ha troppi trio | Salto dà ancora P con trio_count=2, min=0 | Step 2 trova Q con count=0 in una coppia; scambia P↔Q; P prende il partner di Q | N/A |
| Swap: a parità di count, preferire basso in classifica | Due candidati swap Q1(pos 2) e Q2(pos 5) entrambi a count=0 | Step 2 sceglie Q2 (più basso in classifica = più Amalfi). Nessun check rematch — è compito dello Step 3 | N/A |
| Swap impossibile (tutti hanno stesso count) | Tutti a trio_count=2, min=2 | Step 2 non scambia (ancora ha già min_count). Salto standard | N/A |
| Rotazione batte classifica (Step 3) | Coppia bassa in classifica ha companion_count_sum=2, coppia alta ha sum=0 | Step 3 sceglie coppia alta (sum più basso vince) | N/A |
| Anti-rematch batte classifica (Step 3) | Due coppie a pari sum, una con rematch nel trio | Step 3 sceglie la coppia senza rematch | N/A |
| Rotazione batte anti-rematch (Step 3) | Coppia con sum=0 ha rematch, coppia con sum=1 no | Step 3 sceglie sum=0 (accetta rematch per rotazione) | N/A |
| Compagni da coppie diverse → orfani | Step 3 sceglie 2 da 2 coppie del salto | I 2 orfani formano nuova coppia; orphan_rematch penalizza ma non blocca | N/A |
| N=3 (caso degenere) | 3 giocatori totali | Salto + BYE produce 4 posizioni: 1 ancora + 1 coppia. Step 3 ha C(2,2)=1 sola combinazione → trio con tutti e 3 | N/A |
| N=5 (Step 3 degenere) | 5 giocatori | Ancora + 2 coppie. Step 3 ha C(4,2)=6 combinazioni ma solo 3 a 0 orfani | N/A |
| Worst case: tutto alto, tutto rematch | Round avanzato, tutti a count=3, tutte le coppie incontrate | Best effort: Step 3 sceglie min di (sum, rematches, orphan_rematch, -position). Risultato sub-ottimale accettato | N/A |
| Torneo molto lungo (turni > C(N,2)) | 7 giocatori, 25 turni | Anti-rematch impossibile ovunque; qualità degrada a tiebreaker su posizione. Comportamento atteso | N/A |

</frozen-after-approval>

## Code Map

- `docs/SPECIFICHE.md` -- Aggiungere criteri selezione trio DENTRO la sezione "Gare amalfi" (dopo riga ~92, dopo la spiegazione del salto — così il lettore conosce già il concetto di "salto")
- `models/matchmaking/strategies/amalfi.py` -- Refactoring del while loop per produrre rappresentazione intermedia; `_get_trio_counts` (nuovo, sostituisce `_get_players_with_trio`); `_swap_anchor_if_needed` (nuovo, Step 2); `_select_trio_companions` (nuovo, Step 3); eliminare `_select_trio_players` (dead code); `_amalfi_pairing`: orchestrazione 3 step + ricomposizione in Pairing
- `tests/new/unit/test_amalfi_trio_selection.py` -- Nuovi test per i 12 scenari della matrice I/O

## Tasks & Acceptance

**Execution:**
- [x] `docs/SPECIFICHE.md` -- Aggiungere dentro la sezione "Gare amalfi" (dopo riga 92, dopo la spiegazione del salto) i criteri di selezione trio: Step 1 salto con BYE, Step 2 swap ancora per rotazione, Step 3 compagni per score. Ordine di sacrificio esplicito
- [x] `models/matchmaking/strategies/amalfi.py` -- Aggiungere metodo `_get_trio_counts(gara_id) -> dict[int, int]` (conta trio per giocatore via TrioMatch query). Eliminare `_get_players_with_trio` nello stesso changeset. Aggiornare il caller in `_amalfi_pairing`
- [x] `models/matchmaking/strategies/amalfi.py` -- Aggiungere metodo `_swap_anchor_if_needed(anchor, pairs, trio_counts, player_to_index) -> tuple[int, list[tuple[int,int]]]`: pure function. `player_to_index: dict[int, int]` mappa player_id → indice di classifica. Se `trio_counts[anchor] > min_trio_count`, cerca tra tutti i giocatori nelle coppie quello con `min(trio_count, -index)` e scambia. Se nessun miglioramento, restituisce invariato
- [x] `models/matchmaking/strategies/amalfi.py` -- Aggiungere metodo `_select_trio_companions(anchor, pairs, trio_counts, encounter_matrix) -> tuple[int, int]`: pure function. Pool = tutti i giocatori nelle coppie (ogni candidato proviene da esattamente una coppia del salto). Per ogni C(pool_size, 2) combinazione, calcola score `(companion_count_sum, trio_rematches, orphan_rematch, -position_sum)`. Restituisce i 2 con score minimo
- [x] `models/matchmaking/strategies/amalfi.py` -- Refactorizzare il while loop in `_amalfi_pairing` per produrre una rappresentazione intermedia quando `use_trio=True`: il salto con BYE sentinel produce `anchor: int` (chi atterra sul BYE) + `pairs: list[tuple[int, int]]` (coppie regolari) anziché Pairing finali. Asserire che BYE_PLAYER_ID non compaia nella rappresentazione intermedia
- [x] `models/matchmaking/strategies/amalfi.py` -- Orchestrare i 3 step in `_amalfi_pairing` quando `use_trio=True`: (1) salto → anchor + pairs, (2) `_swap_anchor_if_needed`, (3) `_select_trio_companions`, (4) ricomporre `Sequence[Pairing]`: un trio Pairing con i 3 giocatori ordinati per classifica + le coppie invariate + eventuale coppia orfani. Verificare che nessun Pairing contenga BYE_PLAYER_ID
- [x] `models/matchmaking/strategies/amalfi.py` -- Eliminare `_select_trio_players` (righe 422-444, dead code dopo il refactoring)
- [x] `tests/new/unit/test_amalfi_trio_selection.py` -- Test per tutti i 12 scenari della matrice I/O. I metodi `_swap_anchor_if_needed` e `_select_trio_companions` sono pure function e possono essere testati direttamente con dati in-memory senza mock DB. Solo `_get_trio_counts` richiede mock/fixture DB

**Acceptance Criteria:**
- Given 7 giocatori e 5 turni, when si generano tutti i turni, then la differenza tra max e min trio_count per giocatore è ≤ 1
- Given salto che produce ancora con trio_count=2 e min=0, when Step 2 valuta lo swap, then l'ancora viene scambiata con un giocatore a count=0
- Given due candidati swap a pari trio_count a posizioni diverse in classifica, when Step 2 sceglie, then sceglie quello più basso in classifica
- Given tutti i giocatori con lo stesso trio_count, when Step 2 valuta, then nessuno swap (ancora ha già min_count)
- Given Step 3 con coppia a companion_sum=0 con rematch e coppia a sum=1 senza rematch, when si calcola lo score, then vince sum=0 (rotazione batte anti-rematch)
- Given Step 3 sceglie 2 da coppie diverse, when si ricompongono gli abbinamenti, then i 2 orfani formano una coppia e nessun Pairing contiene BYE_PLAYER_ID
- Given N=3, when l'algoritmo gira, then produce un solo trio Pairing con tutti e 3 i giocatori, zero coppie regolari

## Design Notes

### Rappresentazione intermedia

Il while loop del salto oggi produce `Pairing` finali direttamente. Con il trio a 3 step, serve una struttura intermedia tra salto e ricomposizione:

```python
# Output del salto (Step 1) quando use_trio=True:
anchor: int                        # player_id di chi atterra su BYE
pairs: list[tuple[int, int]]       # coppie regolari (player_a, player_b)

# Il BYE_PLAYER_ID (-1) NON compare qui — è usato solo dentro il salto
assert anchor != BYE_PLAYER_ID
assert all(p != BYE_PLAYER_ID for pair in pairs for p in pair)
```

Quando `use_trio=False` (bye mode), il while loop continua a produrre `Pairing` direttamente come oggi — nessun cambio.

### Step 2: Swap dell'ancora

```python
def _swap_anchor_if_needed(self, anchor, pairs, trio_counts, player_to_index):
    """Pure function. Nessuna lettura DB."""
    all_in_pairs = [p for pair in pairs for p in pair]
    min_count = min(
        trio_counts.get(anchor, 0),
        *(trio_counts.get(p, 0) for p in all_in_pairs)
    )
    if trio_counts.get(anchor, 0) <= min_count:
        return anchor, pairs  # Ancora è già a min_count

    # Cerca il miglior candidato swap
    best = min(
        all_in_pairs,
        key=lambda q: (trio_counts.get(q, 0), -player_to_index.get(q, 0))
    )
    if trio_counts.get(best, 0) >= trio_counts.get(anchor, 0):
        return anchor, pairs  # Nessun miglioramento

    # Esegui lo swap: best diventa ancora, anchor entra nella coppia di best
    new_pairs = []
    for a, b in pairs:
        if best == a:
            new_pairs.append((anchor, b))
        elif best == b:
            new_pairs.append((a, anchor))
        else:
            new_pairs.append((a, b))
    return best, new_pairs
```

### Step 3: Score dei compagni

```python
# Pool = tutti i giocatori nelle coppie (esclusa l'ancora)
# Ogni candidato proviene da esattamente una coppia del salto/swap

score = (
    companion_count_sum,  # sum trio_count dei soli 2 compagni (ancora è costante, esclusa)
    trio_rematches,       # quante delle 3 coppie nel trio si sono già incontrate (0-3)
    orphan_rematch,       # 1 se i 2 orfani si sono già incontrati, 0 se stessa coppia o no
    -position_sum,        # indice in classifica più alto tra i 2 compagni (Amalfi spirit)
)
# orphan_rematch = 0 se i 2 compagni vengono dalla stessa coppia (nessun orfano)
# orphan_rematch è un SOFT PENALTY: penalizza la scelta ma non la blocca
```

### Ricomposizione in Pairing

```python
# Dopo Step 2 e 3:
trio_players = sorted([anchor, comp1, comp2], key=lambda p: player_to_index[p])
result = [Pairing(players=tuple(trio_players), is_bye=False, round_number=turno)]

for a, b in final_pairs:  # Coppie non toccate + eventuale coppia orfani
    result.append(Pairing(players=(a, b), is_bye=False, round_number=turno))
```

### Trade-off accettati (da review)

- La qualità della coppia orfani in termini di distanza in classifica NON è un criterio: potrebbe risultare in orfani #1 vs #7. Accettato perché un 5° elemento nello score aggiungerebbe complessità senza beneficio significativo
- Sciogliere coppie del salto può ricreare rematch che il salto aveva evitato: coperto all'~80% da `orphan_rematch`, il rischio residuo è accettato
- In tornei molto lunghi (turni > C(N,2)) la qualità degli abbinamenti trio degrada: comportamento atteso, non un bug
- Il salto (Step 1) usa `_have_already_played()` (query per-coppia) mentre Step 3 usa `encounter_matrix` (query singola): inconsistenza accettata. Refactoring opzionale per far usare la matrice anche al salto

## Verification

**Commands:**
- `pytest tests/new/unit/test_amalfi_trio_selection.py -v -n auto` -- expected: tutti i test passano
- `pytest tests/new/unit/test_amalfi_business_logic.py -v -n auto` -- expected: test esistenti non rotti
- `pytest tests/new/integration/ -n 4` -- expected: nessuna regressione
- `pyright` -- expected: 0 errori

## Suggested Review Order

**Specifica e algoritmo core**

- Entry point: orchestrazione 3 step (salto → swap → companions → ricomposizione)
  [`amalfi.py:408`](../../models/matchmaking/strategies/amalfi.py#L408)

- Step 2: swap ancora per rotazione equa — pure function
  [`amalfi.py:535`](../../models/matchmaking/strategies/amalfi.py#L535)

- Step 3: selezione compagni con score a tuple — pure function, C(N-1,2)
  [`amalfi.py:577`](../../models/matchmaking/strategies/amalfi.py#L577)

- Conteggio trio per giocatore (sostituisce set binario)
  [`amalfi.py:510`](../../models/matchmaking/strategies/amalfi.py#L510)

**Salto refactoring (rappresentazione intermedia)**

- Salto loop: BYE sentinel anche in trio mode, produce anchor + pairs intermedi
  [`amalfi.py:309`](../../models/matchmaking/strategies/amalfi.py#L309)

- Condizione 3 (bye) disabilitata in trio mode — BYE è sempre accessibile
  [`amalfi.py:347`](../../models/matchmaking/strategies/amalfi.py#L347)

- Fallback safety valve: preferisce non-BYE, BYE solo come ultima risorsa
  [`amalfi.py:357`](../../models/matchmaking/strategies/amalfi.py#L357)

**Specifica utente**

- Criteri selezione trio aggiunti nella sezione "Gare amalfi"
  [`SPECIFICHE.md:94`](../../docs/SPECIFICHE.md#L94)

**Test**

- Pure function tests: swap (5 test) + companions (7 test)
  [`test_amalfi_trio_selection.py:30`](../../tests/new/unit/test_amalfi_trio_selection.py#L30)

- Integration tests: 9 test end-to-end con mock DB
  [`test_amalfi_trio_selection.py:270`](../../tests/new/unit/test_amalfi_trio_selection.py#L270)

- AC1: fairness multi-round (5 turni × 7 giocatori, max-min trio_count ≤ 1)
  [`test_amalfi_trio_selection.py:487`](../../tests/new/unit/test_amalfi_trio_selection.py#L487)

- AC6: orphan recomposition end-to-end
  [`test_amalfi_trio_selection.py:533`](../../tests/new/unit/test_amalfi_trio_selection.py#L533)
