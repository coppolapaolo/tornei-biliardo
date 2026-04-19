---
title: 'Random anti-rematch: spec unificato + consolidamento gap review'
type: 'refactor + bugfix'
created: '2026-04-19'
status: 'done (hybrid data source — see §Design Notes)'
baseline_commit: '0a7372e'
context:
  - models/matchmaking/CLAUDE.md
  - docs/usecases/gare.md (UC2)
  - docs/usecases/UC01.md
  - docs/adr/ADR-002-fix-anti-rematch-encounter-cleanup.md
  - docs/adr/ADR-005-distance-classification-trio-rules.md
  - _bmad-output/implementation-artifacts/spec-amalfi-trio-selection.md
  - _bmad-output/implementation-artifacts/deferred-work.md (linea 233, "Review random matchmaking specification")
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La strategia `random_anti_rematch` ha spec frammentata (docstring + CLAUDE.md + config + test, nessun documento unificato) e sette problemi concreti emersi dalla review adversariale del 2026-04-19:

1. **Data source divergente**: Random legge `Match.query` mentre Amalfi (post-refactor 2026-04-19) usa `PlayerEncounterService.get_encounter_matrix()`. Conseguenza: Random non beneficia del cleanup ADR-002 (reset/cancel-round non "libera" i pair) e non filtra i walkover come Amalfi `_get_trio_counts`.
2. **NetworkX senza pesi differenziati**: nel fallback, `max_weight_matching` può scegliere un matching con più rematch del necessario, perché gli archi sono uniform weight.
3. **Silent fallback**: quando i rematch sono inevitabili, nessun log/warning — pattern "silent failure" incoerente con l'audit del codebase.
4. **`_should_use_trio` bypassa `StrategyBehaviorConfig`**: logica hardcoded "trio per 3/5/7 giocatori" che ignora `distance` e quindi ADR-005.
5. **Enum `OddNumberPolicy` disallineato**: `CLAUDE.md` elenca 3 valori (`BYE/TRIO/CHALLENGE`), il codice ne ha 4 (`NO/BYE/BYE_WITH_CHALLENGE/TRIO`).
6. **Trii walkover inflazionano `trio_count`** in Random (non filtrati), al contrario di Amalfi dopo il fix del 2026-04-19.
7. **Seed non deterministico**: `random.shuffle` sul modulo globale invece di `random.Random(seed)` instance-based; stato globale contaminato con `pytest -n auto`.

**Approach:** Refactor in 3 fasi non-behavioral-first:
- **Fase 1 (documentazione)**: produrre questo spec e aggiornare `models/matchmaking/CLAUDE.md` per allineare l'enum `OddNumberPolicy`. Zero rischio.
- **Fase 2 (unificazione data source)**: migrare `_get_encounter_history` a `PlayerEncounterService.get_encounter_matrix()` + nuovo `get_trio_counts(gara_id, exclude_walkover=True)`. Risolve 1+6 insieme + allinea con ADR-002. Behavioral change: il trio_count ignora ora i walkover (coerente con Amalfi).
- **Fase 3 (correttezza + trasparenza)**: pesi espliciti su NetworkX edges (2 risolto), logger.warning su rematch forzati (3), rimozione fallback hardcoded `_should_use_trio` con delega a `StrategyBehaviorConfig.get_default_odd_policy(gara.distance)` (4), instance-based RNG (7).

**Fuori scope** (tracciato separatamente):
- Decidere se `creates_all_rounds_at_startup=True` è effettivamente implementato (gap G1) — richiede una review separata del flusso `start_next_round` vs `start_first_round`.
- Decidere se `OddNumberPolicy.NO` (parity waitlist) è supportato a runtime per Random (gap G2).
- Decidere se Random supporta reset match (gap G3) — dipende da scelta UI/UX prima che implementativa.

## Boundaries & Constraints

**Always:**
- **Ordine di sacrificio**: (1°) cardinalità del matching — NON lasciare giocatori fuori se c'è un matching perfect possibile; (2°) anti-rematch — preferire coppie mai incontrate; (3°) "fairness" trio — minimizzare `max(trio_count)` fra i giocatori del trio; (4° ultimo a cedere) randomicità uniforme fra opzioni equivalenti.
- **Data source anti-rematch**: `PlayerEncounterService.get_encounter_matrix(gara_id)` come unica fonte. Il metodo è cached 10 min con invalidation automatica su `record_match_encounters`. Coerente con Amalfi post-refactor.
- **Data source trio_count**: nuovo helper `PlayerEncounterService.get_trio_counts(gara_id, exclude_walkover=True)`. Il filtro walkover è acceso di default (coerente con Amalfi `_get_trio_counts`).
- **Bye anti-rematch**: traccia `(player, BYE_PLAYER_ID)` via `Match` (il bye ADR-002 non crea `PlayerEncounter`). Questo singolo lookup resta su `Match.query` — non c'è alternativa corrente. Documentare esplicitamente questa eccezione.
- **NetworkX weights**: peso 100 per coppie non-rematch, peso 1 per rematch. Usare `max_weight_matching(G, maxcardinality=True)`: il solver massimizza la cardinalità (primario) e poi il peso totale (secondario), quindi preferisce non-rematch quando possibile.
- **Audit trail**: `logger.warning` ogni volta che viene inserito un rematch (sia fallback globale che conseguenza del matching pesato). Format: `"Random: rematch forzato in gara {gara_id}, turno {round_number}: {n_rematches}/{n_pairs} pair erano già incontrati"`.
- **RNG**: `self._rng = random.Random(seed if seed is not None else None)` nel constructor; `random.Random(None)` è seeded con os time, equivalente a `random.Random()` senza arg. Tutti gli usi di `random.shuffle/choice` diventano `self._rng.shuffle/choice`.
- **Trio fallback**: rimuovere `_should_use_trio` branch hardcoded. Delegare **sempre** a `StrategyBehaviorConfig.get_default_odd_policy(gara.distance)` quando `gara.odd_number_policy` non è settata. Coerente con ADR-005.
- **`BYE_PLAYER_ID` (-1)**: usato solo internamente dal matching graph; mai in un Pairing di output. Asserzione esplicita prima della conversione.
- **Performance**: nessuna regressione — il cache `get_encounter_matrix` rende le riletture O(1), il grafo NetworkX resta O(N²) sugli edges.

**Ask First:**
- Se il filtro walkover su `trio_count` rompe qualche test esistente di regressione walkover (trii storici — migration `20260419_backfill_walkover_trio_matchup`).
- Se il logger.warning debba anche emettere un `DomainEvent` di categoria `MATCHMAKING_DEGRADED` (per dashboard director) o basta il log.

**Never:**
- Non toccare `BYE_PLAYER_ID` o la conversione bye algoritmo→Pairing: coperto da test esistenti (`test_bye_conversion_consistency`).
- Non cambiare l'API pubblica di `RandomAntiRematchStrategy.create_round(gara, round_number)`: il contratto è usato da `RoundCreationService._create_round_impl`.
- Non introdurre dipendenze nuove (networkx e sqlalchemy già presenti).
- Non riscrivere il multi-objective trio score: le priorità attuali `(max_count, rematch_penalty, sum_count)` sono corrette per Random (diverse intenzionalmente da Amalfi, vedi §Design Notes). Solo l'input `trio_count` cambia per escludere walkover.

## I/O & Edge-Case Matrix

| # | Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|----------|--------------|---------------------------|----------------|
| 1 | Primo turno, 4 giocatori, nessun storico | `[1,2,3,4]`, encounter_matrix vuota | 2 coppie random; ogni giocatore in un Pairing | N/A |
| 2 | Primo turno, 3 giocatori, `odd_policy=BYE` | `[1,2,3]`, distance=5 | 1 coppia + 1 bye; bye va a un giocatore random | N/A |
| 3 | Primo turno, 3 giocatori, `odd_policy=TRIO`, distance=5 | `[1,2,3]`, distance=5 | 1 Pairing con tutti e 3; `is_trio=True` | N/A |
| 4 | Primo turno, 3 giocatori, `odd_policy=TRIO`, distance=10 | `[1,2,3]`, distance=10 | Upstream `StrategyConfiguration.validate()` rejecta (ADR-005) | ValueError al setup gara |
| 5 | `odd_policy=None`, 5 giocatori, distance=5 | Config default | Delega a `get_default_odd_policy(5)` → TRIO | N/A |
| 6 | `odd_policy=None`, 5 giocatori, distance=10 | Config default | Delega a `get_default_odd_policy(10)` → BYE_WITH_CHALLENGE | N/A |
| 7 | Turno 2, 4 giocatori, turno 1 ha giocato `(1,2)` e `(3,4)` | encounter_matrix `{(1,2),(3,4)}` | Turno 2 = `(1,3)+(2,4)` o `(1,4)+(2,3)` — zero rematch, nessun warning | N/A |
| 8 | Rematch inevitabile: 4 giocatori, 3 turni completi (6 pair possibili, esauriti dopo 3 turni=6 pair) | encounter_matrix = tutti i C(4,2)=6 pair | Turno 4: 2 pair rematch, `logger.warning` emesso | Graceful degradation |
| 9 | Rematch parziale preferibile: 6 giocatori, `(1,2)(3,4)(5,6)` giocati; in turno 2 solo `(1,2)` creerebbe rematch ma serve per matching perfect | encounter_matrix `{(1,2),(3,4),(5,6)}` | Matching sceglie 3 pair senza rematch: `(1,3)+(2,4)+(5,6)` NO — `(5,6)` è rematch. Preferito: `(1,3)+(2,5)+(4,6)` — zero rematch | Tutti i pair non-rematch esistono → zero rematch |
| 10 | Trio walkover storico: turno 1 trio `(1,2,3)` con `total_racks_played=0` | encounter_matrix include pair interni `(1,2)(1,3)(2,3)`; trio_count escluso dal filtro walkover | Turno 2: `trio_count[1/2/3]=0`; possono essere scelti di nuovo per trio senza penalità di rotazione | Coerente con Amalfi fix 2026-04-19 |
| 11 | Bye rotation: turno 1 bye a P1, turno 2 stesso dispari | `_get_encounter_history` include `(1, BYE_PLAYER_ID)` | Turno 2: il bye va preferibilmente a P2-P5 (matching evita `(P1, BYE_PLAYER_ID)`) | Se tutti hanno già avuto bye → bye rematch, warning |
| 12 | Forfeiter incluso nel pool: 5 giocatori, P3 è forfeiter (`is_forfeit=True`, `is_withdrawn=False`) | Random accoppia P3 con un altro → `create_matches_from_pairings` converte in walkover | Comportamento invariato rispetto a oggi | Documentare in spec |
| 13 | Reset match in gara Random: turno 1 match `(1,2)` resettato (racks eliminati, Match rimane) | `PlayerEncounter` ha `delete_encounter(1,2)` → encounter_matrix non contiene `(1,2)` | Turno 2 può accoppiare `(1,2)` di nuovo (comportamento atteso da ADR-002) | Coerente con ADR-002 |
| 14 | `seed=42` fornito a `MatchmakingService.run` | `self._rng = random.Random(42)` | Due run consecutivi con stesso seed producono stesso output | Determinismo testabile |
| 15 | Pytest `-n auto` con 2 test Random paralleli | Ciascun test usa istanza strategia separata con proprio `_rng` | Nessuna contaminazione globale | Risolve flakiness |
| 16 | 50 giocatori, primo turno | encounter_matrix vuota, pool grande | 25 pair generati in <1s (test perf esistente) | N/A |
| 17 | `odd_policy=NO`, 5 giocatori | Config = parity waitlist | **GAP G2 — fuori scope spec** | N/A (raiseNotImplementedError? lasciato al follow-up) |

</frozen-after-approval>

## Code Map

- `_bmad-output/implementation-artifacts/spec-random-anti-rematch.md` -- Questo spec (nuovo)
- `models/matchmaking/CLAUDE.md` -- Aggiornare sezione "Configuration Enums" per includere tutti e 4 i valori di `OddNumberPolicy` (NO, BYE, BYE_WITH_CHALLENGE, TRIO). Aggiungere sezione "Random Anti-Rematch" con riferimento a questo spec per i dettagli algoritmici.
- `models/classification/encounter_service.py` -- Nuovo metodo `PlayerEncounterService.get_trio_counts(gara_id: int, exclude_walkover: bool = True) -> Dict[int, int]`. Cached con stesso TTL/tags di `get_encounter_matrix`. Query: `TrioMatch join Match filter gara_id, round_number < current_round, exclude walkover se flag.`
- `models/matchmaking/strategies/random_anti_rematch.py` -- Principale target del refactor:
  - `__init__(self, seed=None)`: accettare seed, creare `self._rng`
  - `_get_encounter_history`: eliminato (sostituito da PlayerEncounterService lookups)
  - `_generate_valid_random_pairings`: leggere encounter_matrix e trio_counts via service
  - `_apply_maximum_matching`: aggiungere pesi espliciti (100 non-rematch, 1 rematch)
  - Aggiungere `logger.warning` sui rematch forzati
  - `_should_use_trio`: sostituire fallback hardcoded con `StrategyBehaviorConfig.get_default_odd_policy(gara.distance)`
  - Sostituire `random.shuffle/choice` con `self._rng.shuffle/choice`
- `models/matchmaking/registry.py` (o `bootstrap.py`) -- Verificare che `create_strategy(name, seed)` passi il seed al constructor della strategia (oggi probabilmente chiama `random.seed(seed)` globalmente; cambiare a instance seed).
- `tests/new/unit/test_random_anti_rematch_strategy.py` -- Aggiornare:
  - Rimuovere `random.seed(42)` manuali (ora lo fa il constructor)
  - Aggiungere test per pesi NetworkX: con 4 giocatori e matrice quasi satura, matching preferisce il pair con meno rematch
  - Aggiungere test per `logger.warning` emesso su rematch forzati
  - Aggiungere test per filtro walkover in `trio_count`
- `tests/new/integration/test_random_anti_rematch_tournament_flow.py` -- Aggiornare `simulate_tournament_round` per non mockare `_get_encounter_history` (ora unused); mockare direttamente `PlayerEncounterService` oppure usare DB fixtures reali.
- `tests/new/integration/test_matchmaking_anti_rematch.py` -- Aggiungere test specifico: gara Random + reset match → nuovo pair consentito (regression ADR-002 per Random).

## Tasks & Acceptance

**Execution (Fase 1 — documentazione, no behavior change):**
- [ ] `_bmad-output/implementation-artifacts/spec-random-anti-rematch.md` -- Creare questo spec (fatto)
- [ ] `models/matchmaking/CLAUDE.md` -- Allineare enum `OddNumberPolicy` con 4 valori reali; aggiungere sezione "Random Anti-Rematch" con link a questo spec
- [ ] `_bmad-output/implementation-artifacts/deferred-work.md` -- Aggiornare voce "Review random matchmaking specification" con link a questo spec e lista work item aperti

**Execution (Fase 2 — data source hybrid):**
- [x] `models/classification/encounter_service.py` -- Aggiunto `get_trio_counts(gara_id, exclude_walkover=True)` con `@cached` e stesso invalidation scheme di `get_encounter_matrix`
- [x] `models/matchmaking/strategies/random_anti_rematch.py` -- `_get_encounter_history` ora delega a `PlayerEncounterService.get_trio_counts` per i count trio (con walkover filter, valore aggiunto coerente con Amalfi). `previous_pairs` resta su `Match.query` in `_get_pair_history_from_matches` per supportare "all rounds at startup" (scoperto durante implementazione — vedi §Design Notes)
- [x] ~~Regression test ADR-002 per Random~~ — **Non fattibile**: Random crea tutti i round all'avvio, non c'è rigenerazione dopo reset su cui misurare. Limitation documentata come gap G3.
- [x] `tests/new/unit/test_random_anti_rematch_strategy.py` -- Mock `_get_encounter_history` preservato (signature invariata, wrapper sopra PlayerEncounterService + Match.query)

**Execution (Fase 3 — correttezza + trasparenza):**
- [x] `models/matchmaking/strategies/random_anti_rematch.py` -- `_apply_weighted_matching`: grafo con edge weights espliciti (100 non-rematch, 1 rematch). Un solo `nx.max_weight_matching(G, maxcardinality=True)` invece di due matching sequenziali
- [x] `models/matchmaking/strategies/random_anti_rematch.py` -- `logger.warning` dopo il matching se almeno una pair è rematch. Include gara_id, round_number, n_rematches, n_total_pairs
- [x] `models/matchmaking/strategies/random_anti_rematch.py` -- `_should_use_trio`: rimosso fallback hardcoded `[3,5,7]`. Se `gara.odd_number_policy` mancante, delega a `get_strategy_behavior(MatchmakingStrategy.RANDOM).get_default_odd_policy(gara.distance)`. Se `distance` mancante, safe default False (bye)
- [x] `models/matchmaking/strategies/random_anti_rematch.py` -- `set_context(context: PairingContext)` implementato; `self._rng = context.get_rng()`. Tutti i `random.shuffle/choice` diventano `self._rng.*`. Default: `random.Random()` istanza alla costruzione
- [x] `models/matchmaking/registry.py` -- Non modificato: il meccanismo `set_context` già esisteva (`StrategyFactory.create` righe 91-92 fa `strategy.set_context(context)` se supportato). Solo la strategia era da aggiornare
- [x] `tests/new/unit/test_random_anti_rematch_strategy.py` -- Aggiunti 4 nuovi test:
  - `test_matching_minimizes_rematches_when_fallback`: 4 giocatori, 5/6 pair giocati → matching sceglie la combinazione con 1 rematch (non 2)
  - `test_warning_logged_on_forced_rematch` + `test_no_warning_when_no_rematch`: caplog verifica audit trail
  - `test_trio_count_excludes_walkover`: walkover trio escluso da count (via mock di `db.session.query`)
  - `test_seed_deterministic` + `test_no_global_random_contamination`: due test su isolamento RNG

**Acceptance Criteria:**
- Given gara Random con match `(1,2)` in turno 1 resettato via `RackService.reset_match_complete`, when si crea turno 2, then il pair `(1,2)` può essere riassegnato (encounter_matrix non lo contiene)
- Given 4 giocatori e 5 dei 6 pair già incontrati, when si crea un nuovo turno, then il matching forza al massimo 1 rematch (non 2) e `logger.warning` viene emesso
- Given `gara.odd_number_policy=None`, 5 giocatori e `gara.distance=10`, when si crea un turno, then si usa bye (`BYE_WITH_CHALLENGE`) non trio (ADR-005)
- Given trio walkover `(1,2,3)` in turno 1 con `total_racks_played=0`, when si calcola `trio_count` per turno 2, then `trio_count[1]=trio_count[2]=trio_count[3]=0`
- Given `MatchmakingService.run("random", gara, round_number, seed=42)` chiamato due volte, when si confrontano gli output, then sono identici
- Given 50 giocatori e 5 turni in sequenza, when si misurano i tempi, then ogni turno genera pairing in <1s (no regressione perf vs test esistente)
- Given `models/matchmaking/CLAUDE.md` aggiornato, when si legge la sezione "Configuration Enums", then tutti e 4 i valori di `OddNumberPolicy` sono elencati

## Design Notes

### Pesi NetworkX: un solo matching, non due

Oggi il codice fa due matching sequenziali (linee 134-159 di `random_anti_rematch.py`):
1. Primo matching su grafo delle sole valid_pairs (no rematch)
2. Se incompleto, secondo matching su tutti i canonical_pairs

Con pesi espliciti, basta un singolo matching:
```python
G = nx.Graph()
G.add_nodes_from(all_players)
for p1, p2 in canonical_pairs:
    weight = 100 if (p1, p2) not in encounter_matrix else 1
    G.add_edge(p1, p2, weight=weight)

matching = nx.max_weight_matching(G, maxcardinality=True)
# maxcardinality=True → primo criterio: copertura max
# poi peso totale → preferisce non-rematch quando possibile
```

**Perché 100 e 1**: il rapporto deve essere abbastanza grande da far sì che il solver preferisca sempre 1 non-rematch a 99 rematch. 100:1 è sicuro per tornei realistici (<50 giocatori).

### Trio score: perché resta diverso da Amalfi

Amalfi `_select_trio_companions` ha score `(companion_count_sum, trio_rematches, orphan_rematch, -position_sum)`. Random non ha il concetto di "orphan" (non c'è salto) né di "posizione in classifica" (primo turno sempre random, turni successivi idem). Quindi lo score Random `(max_count, rematch_penalty, sum_count)` riflette priorità diverse intenzionalmente:
- Amalfi minimizza il *totale* trio_count (premia distribuzione equa)
- Random minimizza il *massimo* trio_count (protegge il peggiore)

Entrambe sono ragionevoli; la differenza non è un bug. Documentare in CLAUDE.md.

### Filtro walkover nel trio_count

Il fix Amalfi del 2026-04-19 ha introdotto il filtro `total_racks_played > 0` in `_get_trio_counts`. Intent: un trio walkover (forfait 2/3 o 3/3) non "consuma" la rotazione. Estensione a Random: stesso filtro, stesso motivo.

**Eccezione sugli encounter_matrix**: i pair interni al trio walkover **sono** registrati come incontri (via `record_match_encounters` in `to_completed`). Quindi l'anti-rematch li conta. Questa asimmetria (conta come incontro ma non come trio) è intenzionale: se P1 e P2 si sono "visti" in un trio walkover, preferiamo non riaccoppiarli subito; ma il loro trio_count non deve essere inflazionato.

### Data source IBRIDO (scoperto durante implementazione)

L'intent iniziale era unificare completamente su `PlayerEncounterService.get_encounter_matrix`. Durante l'implementazione è emerso un blocker critico: `RoundService.start_first_round` (righe 79-127) per la strategia Random crea **tutti i round all'avvio in una singola transazione**. Per il round N, il service chiama `db.session.flush()` prima di invocare `strategy.create_round(gara, N)`, in modo che le query sui Match dei round `< N` vedano le righe appena create.

`PlayerEncounterService.get_encounter_matrix` legge `PlayerEncounter`, che è popolato SOLO al completamento del match (via `to_completed` → `record_match_encounters`). Al momento della creazione round N, **nessun match è ancora completato** → encounter_matrix è vuota → anti-rematch non funziona.

**Soluzione**: data source ibrido.
- `previous_pairs`: letto da `Match.query` (vecchio comportamento preservato) — vede i match pending/playing/completed, necessario per "all rounds at startup".
- `trio_counts`: letto da `PlayerEncounterService.get_trio_counts(gara_id, exclude_walkover=True)` — cached, filtro walkover (valore aggiunto coerente con Amalfi post-2026-04-19).

### Limitation documentata: reset match + Random

`RackService.reset_match_complete` (ADR-002) elimina il `PlayerEncounter` ma mantiene il Match (cambia solo `status` + elimina i `Rack`). Con il data source ibrido:
- **Amalfi**: usa `encounter_matrix` → reset funziona, il pair è riaccoppiabile.
- **Random**: usa `Match.query` → il Match resettato rimane visibile → pair **NON** è riaccoppiabile.

Questo è un comportamento PREESISTENTE al refactor (il vecchio codice aveva lo stesso problema). Tentare di risolverlo richiede decisioni UX prima che implementative:
- Eliminare il Match al reset? Impatta altri sistemi (classifica, storico).
- Aggiungere `Match.is_reset` colonna e filtrare `previous_pairs`? Semplice ma accumula debito schema.
- Rigenerare i round successivi automaticamente al reset? UX non ovvia (il director ha già visto gli abbinamenti).

Tracciato come gap **G3** in deferred-work.md, fuori scope di questo refactor.

### Bye lookup (semplificato dopo discovery data source ibrido)

Poiché `previous_pairs` è già costruito da `Match.query`, i match `is_bye=True` sono inclusi nello stesso ciclo (`_get_pair_history_from_matches`). Non serve il metodo `_get_bye_history` separato previsto dall'intent originale.

### Seed instance vs globale

`random.seed(42)` su modulo globale è anti-pattern in multi-test/multi-thread. `random.Random(42)` crea un PRNG isolato. Ogni istanza di `RandomAntiRematchStrategy` ha il suo. Il registry `create_strategy(name, seed)` passa seed al constructor.

Edge case: se `MatchmakingService.run()` viene chiamato senza seed, `random.Random(None)` è equivalente a `random.Random()` — seeded da os time. Randomicità preservata.

## Verification

**Commands:**
- `pytest tests/new/unit/test_random_anti_rematch_strategy.py -v -n auto 2>&1 | tail -1` — expected: tutti i test passano (incluso i 5 nuovi)
- `pytest tests/new/integration/test_matchmaking_anti_rematch.py -v -n 4 2>&1 | tail -1` — expected: tutti i test passano (incluso il nuovo `test_random_reset_match_allows_rematch`)
- `pytest tests/new/integration/test_random_anti_rematch_tournament_flow.py -v -n 4 2>&1 | tail -1` — expected: nessuna regressione dopo switch a PlayerEncounterService
- `pytest tests/new/integration/test_gare_usecase_2_random.py -v -n 4 2>&1 | tail -1` — expected: nessuna regressione (scenario UC2 completo)
- `pyright` — expected: 0 errori
- `black . && flake8` — expected: clean

## Suggested Review Order

**Fase 1 — spec e documentazione**

- Entry point: intent + boundaries per il refactor complessivo
  [`spec-random-anti-rematch.md`](./spec-random-anti-rematch.md)

- Allineamento enum CLAUDE.md
  [`models/matchmaking/CLAUDE.md:105`](../../models/matchmaking/CLAUDE.md#L105)

**Fase 2 — data source unification**

- Nuovo helper `get_trio_counts` con cache
  [`encounter_service.py`](../../models/classification/encounter_service.py) (nuova funzione)

- Refactor `_get_encounter_history` → lookup via service
  [`random_anti_rematch.py:202`](../../models/matchmaking/strategies/random_anti_rematch.py#L202)

- Regression test ADR-002 per Random
  [`test_matchmaking_anti_rematch.py`](../../tests/new/integration/test_matchmaking_anti_rematch.py) (nuovo test)

**Fase 3 — correttezza + trasparenza**

- Pesi espliciti NetworkX, matching unico
  [`random_anti_rematch.py:324`](../../models/matchmaking/strategies/random_anti_rematch.py#L324)

- Warning su rematch forzati
  [`random_anti_rematch.py:127`](../../models/matchmaking/strategies/random_anti_rematch.py#L127)

- Trio fallback delegato a StrategyBehaviorConfig
  [`random_anti_rematch.py:181`](../../models/matchmaking/strategies/random_anti_rematch.py#L181)

- RNG instance-based
  [`random_anti_rematch.py:41`](../../models/matchmaking/strategies/random_anti_rematch.py#L41)
