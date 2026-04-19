---
title: 'Fix forfeit_user_ids passing in start_first_round'
type: 'bugfix'
created: '2026-04-19'
status: 'done'
baseline_commit: '6689470'
context:
  - 'docs/adr/ADR-025-savepoint-toctou-translation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `RoundService.start_first_round` chiama `create_matches_from_pairings` in due branch (strategia `random` e tutte le altre) senza l'argomento `forfeit_user_ids`. Se un iscritto è marcato `is_forfeit=True` prima dell'avvio del primo turno, il matchmaker lo include nei pairings ma il match viene creato come pending normale invece che come walkover auto-completato (2-player forfeit) o trio walkover (3-player con 1/2/3 forfeit). Il resto della pipeline (`_create_round_impl` per turni successivi) già gestisce correttamente i forfeit: solo il primo turno è rotto.

**Approach:** Calcolare `forfeit_user_ids` una sola volta all'inizio di `start_first_round` replicando esattamente il pattern già presente in `_create_round_impl` (`WithdrawPolicyService.get_forfeit_inscriptions`) e passarlo a entrambe le invocazioni di `create_matches_from_pairings`. Per il branch `random` il calcolo è fatto fuori dal loop dei round (valore costante per tutta la transazione di start).

## Boundaries & Constraints

**Always:**
- Riusare `WithdrawPolicyService.get_forfeit_inscriptions(gara_id)` — nessuna query diretta su `Inscription`.
- Calcolare `forfeit_user_ids` una sola volta per chiamata di `start_first_round` (fuori dal loop dei round nel branch random).
- Preservare il pattern esistente di `_create_round_impl:299-305` (literal copy del blocco).

**Ask First:**
- Se emerge che `create_matches_from_pairings` ha altri chiamanti senza `forfeit_user_ids`, NON estendere lo scope — segnalare e fermarsi.

**Never:**
- Modificare la signature di `create_matches_from_pairings` (default `None` è già corretto).
- Toccare `_create_round_impl` o `RoundCancellationService` (fuori scope).
- Estrarre un helper riutilizzabile prematuramente — duplicazione di 4 righe tra `start_first_round` e `_create_round_impl` è accettabile, si valuterà estrazione se compare un terzo call-site.
- Modificare il comportamento dei forfeit mid-tournament per strategia random (i round successivi generati al momento dello start assumono lo stato forfeit al momento del bootstrap — comportamento pre-esistente).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 2-player, 1/2 forfeit, strategia `amalfi` | Gara con 2 iscritti, uno `is_forfeit=True`, `start_first_round` | Match round 1 creato COMPLETED con `winner_id` = non-forfeit, `player_score=round_distance`/`0`, `status="completed"` | N/A |
| 2-player, 2/2 forfeit | Gara con 2 iscritti entrambi `is_forfeit=True` | Match COMPLETED con `winner_id=pairing.players[0]`, scores `round_distance`/`0` | N/A |
| Trio, 1/3 forfeit | Gara con 3 iscritti uno `is_forfeit=True` | Match 2-player pending tra i 2 survivor (no TrioMatch row) | N/A |
| Trio, 2/3 forfeit | Gara con 3 iscritti, 2 `is_forfeit=True` | Match+TrioMatch walkover completato, `winner_id` = survivor, nessuna TrioRack | N/A |
| Trio, 3/3 forfeit | Gara con 3 iscritti, tutti `is_forfeit=True` | Match+TrioMatch walkover completato, `winner_id = players[0]` | N/A |
| No forfeit (happy path) | Gara con iscritti tutti attivi, strategia `amalfi` | Match round 1 pending regolari, zero walkover — comportamento invariato | N/A |
| No forfeit, strategia `random` | Gara `random`, iscritti attivi, round multipli generati | Tutti i round generati con match pending regolari, invariato | N/A |
| Strategia `random` con forfeit | Gara `random` con iscritto `is_forfeit=True`, 3+ round | In TUTTI i round generati, i pairing con il forfeiter diventano walkover/pending-convertiti secondo la matrix | N/A |

</frozen-after-approval>

## Code Map

- `models/competition/round_service.py` — contiene `start_first_round` (righe 37-171 circa); 2 call-site di `create_matches_from_pairings` da fixare (random loop + altre strategie).
- `models/competition/round_creation.py:299-305` — pattern di riferimento da replicare per calcolare `forfeit_user_ids`.
- `models/competition/withdraw_policy_service.py:153-165` — metodo `get_forfeit_inscriptions` già esistente.
- `models/competition/round_creation.py:15-182` — `create_matches_from_pairings` con signature che già accetta `forfeit_user_ids: Optional[Set[int]] = None`.
- `tests/new/unit/test_round_creation_trio_forfeit.py` — prior art per testare `create_matches_from_pairings` con forfeit (helper `_make_gara`, `_trio_pairing`).

## Tasks & Acceptance

**Execution:**
- [x] `models/competition/round_service.py` — in `start_first_round`, dopo lo shuffle e PRIMA dei due branch strategy (riga ~68), aggiungere il blocco `forfeit_user_ids = set(i.user_id for i in WithdrawPolicyService.get_forfeit_inscriptions(gara_id))` importando `WithdrawPolicyService`. Passare `forfeit_user_ids=forfeit_user_ids` a entrambe le chiamate `create_matches_from_pairings` (righe 111-117 branch random e 153-159 branch altre strategie).
- [x] `tests/new/unit/test_start_first_round_forfeit.py` — nuovo file: 5 regression test che invocano `RoundService.start_first_round` direttamente (DB isolato via `db_session` + `isolated_players` fixture), coprendo scenari amalfi-4p-1forfeit (non-random branch), trio 1/3, trio 2/3, random multi-round (random branch), happy path zero-forfeit (invarianza). Per soddisfare i `min_players` delle strategie: amalfi/trio scenarios usano 3-4 giocatori, random usa 2.

**Acceptance Criteria:**
- Given una gara `amalfi` con 4 iscritti (amalfi richiede min_players=3) di cui uno `is_forfeit=True`, when `RoundService.start_first_round(gara_id)`, then il match del round 1 che contiene il forfeiter viene creato con `status="completed"` e `winner_id` = iscritto non-forfeit, mentre gli altri match restano `pending`.
- Given una gara `random` con 3 iscritti di cui uno `is_forfeit=True` e `rounds_count=3`, when `RoundService.start_first_round(gara_id)`, then in ogni round il forfeiter non appare mai in un match pending regolare (sempre walkover o pairing convertito).
- Given una gara senza forfeit, when `start_first_round`, then il comportamento è invariato rispetto a prima del fix (tutti i match pending, nessun walkover spurio).
- `pyright` ritorna 0 errori.
- `pytest tests/new/ -n 4` green (zero regressioni).

## Spec Change Log

- **2026-04-19 — review iteration 1 (patch)** — Acceptance auditor finding: AC1 letterale ("2 iscritti con amalfi") impossibile perché `AmalfiStrategy.min_players=3`. AC1 amended a "4 iscritti" riflettendo lo scenario testato. Known-bad state avoided: spec che richiede uno scenario irrealizzabile, generando confusione in review future. KEEP: invariante "forfeit pre-start applicabile a tutte le strategie" (copertura con random nelle altre AC).

## Verification

**Commands:**
- `pyright` — expected: 0 errors.
- `pytest tests/new/unit/test_start_first_round_forfeit.py -v -n auto 2>&1 | tail -1` — expected: "N passed".
- `pytest tests/new/unit/test_round_creation_trio_forfeit.py -n auto 2>&1 | tail -1` — expected: existing tests still pass.
- `pytest tests/new/integration/test_gare_usecase_1_amalfi.py tests/new/integration/test_gare_usecase_2_random.py -n 4 2>&1 | tail -1` — expected: "N passed".

## Suggested Review Order

**Fix implementation**

- Entry point: forfeit set computed once after shuffle, before the random/non-random branch.
  [`round_service.py:76`](../../models/competition/round_service.py#L76)

- Random-branch call site: multi-round loop now routes forfeiters to walkover for every generated round.
  [`round_service.py:129`](../../models/competition/round_service.py#L129)

- Non-random-branch call site: single-round parallel pass-through preserving strategy-specific flow.
  [`round_service.py:172`](../../models/competition/round_service.py#L172)

**Reference implementation (unchanged, for comparison)**

- Pattern 1:1 copiato in `start_first_round`: `get_forfeit_inscriptions` + `set(...)`.
  [`round_creation.py:299`](../../models/competition/round_creation.py#L299)

**Regression tests**

- Non-random branch coverage (amalfi 4p, 1 forfeit).
  [`test_start_first_round_forfeit.py:79`](../../tests/new/unit/test_start_first_round_forfeit.py#L79)

- Trio 1/3 conversion — spec I/O matrix row 3.
  [`test_start_first_round_forfeit.py:114`](../../tests/new/unit/test_start_first_round_forfeit.py#L114)

- Trio 2/3 walkover — spec I/O matrix row 4.
  [`test_start_first_round_forfeit.py:137`](../../tests/new/unit/test_start_first_round_forfeit.py#L137)

- Random branch multi-round propagation — spec I/O matrix row 8.
  [`test_start_first_round_forfeit.py:161`](../../tests/new/unit/test_start_first_round_forfeit.py#L161)

- Happy path invariance (no forfeit) — verify fix doesn't regress normal flow.
  [`test_start_first_round_forfeit.py:186`](../../tests/new/unit/test_start_first_round_forfeit.py#L186)
