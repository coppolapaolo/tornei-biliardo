# Deferred Work — Architecture Review Residuals

Created: 2026-04-04
Source: Adversarial Review (AR) + Edge Case Hunter (ECH) session

## ~~Priority 1: Migrate remaining inline str(e) to safe_json_error~~ ✅ DONE (2026-04-04)

Migrated all `except Exception` blocks that exposed `str(e)` in JSON responses across 10 route files.
`routes/player/privacy.py` only had `except ValueError` (intentional user-facing messages) — no change needed.
Also cleaned up flash messages in dual AJAX/flash routes and removed legacy `print`/`traceback` debugging.

## ~~Priority 2: UNIQUE constraints for TOCTOU race conditions~~ ✅ DONE (2026-04-05)

Spec `spec-unique-constraints-toctou.md` (status: done, commit `1d0a486`). Migrazione
`20260405_unique_constraints_toctou.py` + UniqueConstraint su `individual_match.proposal_id`
e `proposal_invitation(proposal_id, invited_user_id)` + traduzione `IntegrityError` →
`ValueError` nei service. Test integration coprono tutte le race condition.

## ~~Priority 3: EventBus error monitoring~~ ✅ DONE (2026-04-05)

Spec `spec-eventbus-error-monitoring.md`. Aggiunto `sentry_sdk.capture_exception` con
`extra` context (event_type, event_id, handler_name, domain) + `add_breadcrumb` per il
flusso eventi in `EventBus.publish()`. Import guard con fallback no-op, safety net
try/except attorno alle chiamate Sentry.

## ~~Priority 3b: Double-capture logger.error + Sentry LoggingIntegration~~ ✅ DONE (2026-04-05)

Spec `spec-eventbus-sentry-dedupe.md`. Risolto con `ignore_logger("models.events.base")`
dentro il try/except import esistente. Net: 1 solo Sentry event per handler failure
(da explicit capture) invece di 3 (2 auto-log + 1 explicit).

## ~~Priority 4: Performance optimizations (profile first)~~ ✅ DONE (2026-04-05)

Low priority — no user-reported issues.

- ~~**SSE memory leak** (AR-10)~~ ✅ DONE (2026-04-05): `routes/sse.py` —
  added throttled `_maybe_sweep_stale_scope_ids` (max once per 30s)
  that prunes `scope_id` keys whose event lists are entirely stale
  (older than `MAX_EVENT_AGE`). Triggered from both `emit_event` and
  `_get_events_since` (polling is sustained even when emits stop).
  5 unit tests in `test_sse_event_store_cleanup.py`.
- ~~**N+1 queries** (AR-12)~~ ✅ DONE (2026-04-05): Fixed via inspection
  (no profiling needed — three loops were blatant):
  - `ClassificationService._count_gare_played` — `for gara in gare: gara.matches` → `selectinload(Gara.matches)`
  - `ScoreAggregator.aggregate_campionato_scores` — same pattern → `selectinload(Gara.matches)`
  - `CommunityService.get_director_performance` — `for g in managed_garas: g.inscriptions` → re-query with `selectinload(Gara.inscriptions)` after dedup
  Each loop went from O(n_gare) lazy queries to 1 batched IN-query.
  `user.director_assignments` was not touched: only used as direct
  attribute access per-request, no obvious N+1 loop.

**Effort**: ~2 hours total (including profiling)

## ~~Priority 5: Extend TOCTOU ValueError translation~~ ✅ DONE (2026-04-05)

Spec `spec-extend-toctou-translation.md`. `report_result` wrappato con savepoint
pattern ADR-025. `ProposalInvitation.accept` documentato con docstring contract
(metodo model-layer, caller responsabili del wrapping).

## ~~Priority 5b: Add IntegrityError contract docstring to `MatchProposal.accept`~~ ✅ DONE (2026-04-05)

Added ADR-025 contract docstring to `MatchProposal.accept` modeled on the
existing `ProposalInvitation.accept` docstring. Pure documentation, no
behavior change. Cites `uq_individual_match_proposal` UNIQUE constraint and
points callers to `ProposalService.accept_proposal` /
`MatchLifecycleService.report_result` as reference implementations of the
savepoint + ValueError translation pattern.

## ~~Priority 5c: `report_result` pending-branch is broken dead code~~ ✅ DONE (2026-04-05)

Option (a): deleted the pending branch from `MatchLifecycleService.report_result`
along with its ADR-025 savepoint wrap (now unnecessary — the sole live path
for `proposal.accept()` on a PENDING proposal remains `ProposalService.accept_proposal`,
which keeps its own savepoint). Removed 2 tests that covered only the dead
branch (`test_report_result_race_raises_value_error`,
`test_report_result_savepoint_only_catches_integrity_error`). Also cleaned up
the contract docstrings on `MatchProposal.accept` / `ProposalInvitation.accept`
to no longer cite `report_result` as a savepoint reference implementation.

## ~~Priority 5d: Orphan facade `report_result`~~ ✅ DONE (2026-04-05)

Grep confirmed zero `.report_result(` callers across `*.py` (source + tests).
Deleted both `MatchLifecycleService.report_result` and its facade
pass-through `IndividualMatchService.report_result`, plus the now-unused
`MatchProposal` import in `match_lifecycle_service.py`. Pyright clean,
77 individual_match/toctou tests pass.

## ~~Deferred: Unify `get_status()` and `compute_campionato_status()`~~ ✅ DONE (2026-04-06)

Source: Review of terminate-campionato feature (2026-04-06).

`Campionato.get_status()` (in `models.py`) and `compute_campionato_status()` (in `statistics_service.py`) implement the same logic independently. Both were modified to add the `terminated_at` short-circuit. Any future change to one risks silent divergence from the other. Consider making `get_status()` delegate to `compute_campionato_status()` or vice versa.

## ~~Refactor: unificare data source anti-rematch (salto + Step 3)~~ ✅ DONE (2026-04-19)

Source: Review Amalfi trio (2026-04-07), ECH #3.

`_crea_coppie_algoritmo_amalfi` ora carica `encounter_matrix` una sola volta (cached 10 min) e la riusa sia nel loop salto (Step 1) sia nella companion selection (Step 3). Metodo `_have_already_played` rimosso. I test di regressione che bypassavano il service (`PlayerEncounter.record_encounter` diretto) ora usano `PlayerEncounterService.record_match_encounters(match)` per coerenza con la produzione (cache invalidation automatica).

## ~~Trio forfeit: gestione in create_matches_from_pairings~~ ✅ DONE (2026-04-19)

Spec `spec-trio-forfeit-round-creation.md`. Dispatch sul numero di forfeit
nel trio: 0/3 invariato, 1/3 convertito in Match 2-player pending,
2/3 walkover completato (winner = survivor), 3/3 walkover completato
(winner = players[0]). Zero schema changes. 7 regression test in
`tests/new/unit/test_round_creation_trio_forfeit.py`.

## ~~Walkover non registra PlayerEncounter / gamification / classification side effects~~ ✅ DONE (2026-04-19)

Spec `spec-walkover-side-effects-unified.md`. Tutti e 3 i branch walkover
(bye, 2-player forfeit, trio 2/3 e 3/3) ora passano attraverso
`MatchStateService.to_completed()`. `Match.is_walkover` property derivata
(nessuna colonna nuova). XP handler skippa forfeiter via
`WithdrawPolicyService.get_forfeit_inscriptions`. Rating handler skip su
walkover. `_process_trio_match` walkover branch credita winner con
`round_distance` racks. Amalfi `_get_trio_counts` filtra trii con 0
rack. `initialize_matchup()` al walkover creation per risolvere admin
reset crash. 26 test (13 unit + 4 integration + 9 trio_forfeit).

## ~~Residui da review walkover unified (2026-04-19)~~ ✅ ALL DONE (2026-04-19)

Scoperti dai 3 reviewer (Blind Hunter + Edge Case Hunter + Acceptance
Auditor) durante step-04 del bmad-quick-dev. Tutti chiusi in una singola
sessione di cleanup.

- ~~**Broad `except Exception` in XP handler**~~ ✅ DONE (2026-04-19):
  Walkover detection (match lookup + `WithdrawPolicyService.get_forfeit_user_ids`)
  spostata FUORI dal try/except top-level di `handle_match_completed_for_xp`.
  Un errore di lookup ora raisa e viene catturato da `EventBus.publish()`
  (logger.error + Sentry), invece di lasciare `forfeit_ids={}` che
  silenziosamente routava XP ai forfeiter. Regression test
  `TestWalkoverDetectionErrorsPropagate` in
  `tests/new/unit/gamification/test_match_completed_handler_isolation.py`.

- ~~**`AchievementService` calls non wrapped**~~ ✅ DONE (2026-04-19):
  Le 4 `check_and_award_achievement` nel winner-branch di
  `handle_match_completed_for_xp` ora sono iterate in un loop con
  try/except individuale — un achievement failing logga warning e
  non blocca i successivi né streak/quest. Regression test
  `TestAchievementIsolation` in stesso file.

- ~~**`is_walkover` su Match detached**~~ ✅ DONE (2026-04-19):
  `Match.is_walkover` ora usa `db.session.query(Rack).filter_by(match_id=self.id).count()`
  invece di `self.racks or []`, evitando il lazy-load che andava in
  `DetachedInstanceError` in dispatch async futuri. 2 regression test
  (detached walkover, detached match con rack) in `TestIsWalkoverProperty`.

- ~~**Trio event handlers miss player3**~~ ✅ DONE (2026-04-19):
  `MatchCompletedEvent` ora espone `player_ids: Optional[List[int]]` + helper
  `get_all_player_ids()` che fa fallback a `[player1_id, player2_id]`.
  `MatchStateService._emit_completion_event` popola `player_ids` con
  `trio_match.player_ids` quando `match.is_trio`, altrimenti con la coppia
  standard. Il gamification handler itera `get_all_player_ids()` per
  streak/quest — trio p3 finalmente riceve weekly streak e quest progress
  (sia in partite normali che walkover dove è survivor). 2 regression test
  `TestTrioPlayerIds` in
  `tests/new/unit/gamification/test_match_completed_handler_isolation.py`.

- ~~**Walkover trii storici in prod hanno `current_player*_id=NULL`**~~ ✅ DONE (2026-04-19):
  Migration `20260419_backfill_walkover_trio_matchup.py` popola
  `current_player1_id=player1_id`, `current_player2_id=player2_id`,
  `waiting_player_id=player3_id` per trii `is_completed=True AND
  current_player1_id IS NULL AND` senza trio_rack attivi. Per rack 1 il
  matchup è costante (P1 vs P2, P3 aspetta) indipendente da distance, quindi
  si evita di reimplementare la logica Python in SQL. Idempotente (filtro
  `current_player1_id IS NULL`). 6 regression test in
  `tests/new/unit/test_backfill_walkover_trio_migration.py`.

## ~~Classification trio walkover: racks registrati come 0-0-0~~ ✅ DONE (2026-04-19)

Spec `spec-walkover-side-effects-unified.md`. `ScoreAggregator._process_trio_match`
ora ha branch walkover che assegna `round_distance` racks al winner (0 agli altri)
quando `trio.is_completed and trio.total_racks_played == 0 and winner_id`.

## ~~Amalfi `_get_trio_counts` conta walkover come trio giocato~~ ✅ DONE (2026-04-19)

Spec `spec-walkover-side-effects-unified.md`. Filtro Python-level su
`total_racks_played > 0` in `_get_trio_counts`. Solo trii "contestati"
contribuiscono alla rotazione.

## ~~`forfeit_user_ids` non passato da `RoundService.start_first_round`~~ ✅ DONE (2026-04-19)

Spec `spec-fix-forfeit-first-round.md`. `RoundService.start_first_round`
ora calcola `forfeit_user_ids` una volta (via `WithdrawPolicyService.get_forfeit_inscriptions`)
e lo passa a entrambi i call-site di `create_matches_from_pairings`
(branch random e non-random). 5 regression test in
`tests/new/unit/test_start_first_round_forfeit.py`.

## ~~Residui da review fix-forfeit-first-round (2026-04-19)~~ ✅ ALL DONE (2026-04-19)

Scoperti dai 3 reviewer (Blind Hunter + Edge Case Hunter + Acceptance
Auditor) durante step-04 del bmad-quick-dev. Tutti chiusi in una singola
sessione di cleanup.

- ~~**Waitlist + forfeit interaction untested**~~ ✅ DONE (2026-04-19):
  `WithdrawPolicyService.get_forfeit_inscriptions` ora filtra per
  `is_waitlist=False` (defense-in-depth contro waitlist promotion che
  preservi `is_forfeit=True`). 3 regression test in
  `tests/new/unit/test_withdraw_policy_forfeit_filter.py`.

- ~~**Copy-paste drift risk tra `start_first_round` e `_create_round_impl`**~~ ✅ DONE (2026-04-19):
  Estratto `WithdrawPolicyService.get_forfeit_user_ids(gara_id) -> set[int]`.
  Entrambi i call-site (`start_first_round` in `round_service.py` e
  `_create_round_impl` in `round_creation.py`) ora chiamano l'helper;
  qualsiasi futura modifica (es. withdrawn-mid-round) tocca un solo punto.
  3 regression test `TestGetForfeitUserIds` in
  `tests/new/unit/test_withdraw_policy_forfeit_filter.py`.

## ~~Admin reset di walkover trio lascia UI in stato rotto~~ ✅ DONE (2026-04-19)

Spec `spec-walkover-side-effects-unified.md`. `trio_match.initialize_matchup()`
chiamato al walkover creation (branch 2/3 e 3/3), quindi `current_player*_id`
sono sempre popolati. Admin reset + `trio_state_serializer.serialize()`
funziona senza crash. Regression test:
`tests/new/unit/test_walkover_side_effects.py::test_to_playing_then_serialize_no_crash`.

**NOTA**: walkover trii CREATI PRIMA di questo refactor in DB hanno ancora
`current_player*_id=NULL`. Admin reset su di loro continuerebbe a crashare.
Vedere "Residui da review walkover unified" sopra per migration opzionale.

## Redesign playoff configuration UI

Source: Test manuale (2026-04-07).

La UI attuale di configurazione playoff ha diversi problemi:
- Max/min gare non ha senso come parametro
- Distance e rounds dovrebbero essere precompilati (ereditati dal campionato)
- Mancano tutte le opzioni tipiche di gara: selezione primo turno, forfait, gestione dispari, tiebreak, ecc.
- "Add configuration" è criptico — non è chiaro cosa faccia
- Manca la preview dei partecipanti qualificati in base alla classifica

Serve un redesign completo della sezione playoff in `campionato_detail.html` e probabilmente del modello `PlayoffConfig`.

## ~~Review random matchmaking specification~~ ✅ ALL DONE (2026-04-19, 3 fasi complete)

Source: Conversazione Amalfi trio (2026-04-07). Sbloccato da refactor Amalfi 2026-04-19.

Review adversariale + 3 fasi implementative complete. Spec consolidata in `spec-random-anti-rematch.md` (status: done, hybrid data source). Suite: 30/30 unit + 225/225 integration + pyright 0 errori.

### Problemi risolti

- **NetworkX pesi espliciti** (`_apply_weighted_matching`): weight=100 per non-rematch, weight=1 per rematch. Un solo matching invece di due sequenziali. `max_weight_matching(G, maxcardinality=True)` minimizza i rematch forzati.
- **Silent fallback eliminato**: `logger.warning` emesso con gara_id/round_number/n_rematches quando rematch è forzato.
- **Fallback hardcoded `[3,5,7]` rimosso**: `_should_use_trio` ora delega a `StrategyBehaviorConfig.get_default_odd_policy(gara.distance)` quando `gara.odd_number_policy` non è settato. ADR-005 rispettato.
- **Enum `OddNumberPolicy` allineato**: `models/matchmaking/CLAUDE.md` ora elenca i 4 valori reali (NO, BYE, BYE_WITH_CHALLENGE, TRIO) + sezione "Random Anti-Rematch" con link allo spec.
- **RNG instance-based**: `set_context(PairingContext(seed))` sfrutta il meccanismo già presente nel registry. No contaminazione globale con `pytest -n auto`.
- **Walkover filter su trio_counts**: nuovo `PlayerEncounterService.get_trio_counts(gara_id, exclude_walkover=True)` con cache + invalidation. Coerente con Amalfi `_get_trio_counts` (filtro `total_racks_played > 0`).

### Scope change scoperto durante implementazione

**Data source ibrido invece di unificato**. Causa: `RoundService.start_first_round` per Random crea tutti i round in una singola transazione con `db.session.flush()` fra un round e l'altro. `PlayerEncounter` è popolato solo al completamento match → vuoto per i round pre-creati → anti-rematch non funziona se si migra interamente al service.

Soluzione adottata:
- `previous_pairs` → `Match.query` (vecchio comportamento preservato per all-rounds-at-startup)
- `trio_counts` → `PlayerEncounterService.get_trio_counts` (valore aggiunto preservato)

### Gap restanti (tracciati come G1-G3)

- **G1** ✅ VERIFICATO: `creates_all_rounds_at_startup=True` per Random è effettivamente implementato in `round_service.py:79-127`. Non è un gap ma un'intent confermato.
- **G2** PENDING: `OddNumberPolicy.NO` (parity waitlist) — comportamento runtime per Random ancora non specificato, nessun test. Fuori scope review.
- **G3** PENDING: Supporto reset match in gara Random. Limitation documentata (reset non libera il pair perché Match row rimane). Fix richiede decisione UX tra: (a) eliminare Match al reset, (b) `Match.is_reset` colonna, (c) rigenerare round successivi automaticamente.
