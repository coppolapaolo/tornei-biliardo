---
title: 'Walkover side effects unified routing'
type: 'refactor'
created: '2026-04-19'
status: 'done'
baseline_commit: '2f8f97d'
context:
  - 'CLAUDE.md (transactional, event-driven, soft-delete conventions)'
  - 'docs/adr/ADR-005-trio-match-logic.md'
  - 'docs/GAMIFICATION_V2.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** In `models/competition/round_creation.py`, the three walkover branches (bye, 2-player forfeit, trio walkover 2/3 and 3/3) create matches with `status="completed"` directly, bypassing `MatchStateService.to_completed()`. As a result: `PlayerEncounter` is not recorded (anti-rematch sees walkover pairs as "unplayed"), `MatchCompletedEvent` is not published (XP/streak/rating handlers never fire), `_update_classification_if_needed` is skipped, and `table_release_and_reassign` is skipped. Trio walkovers additionally leave `current_player1/2/3_id=NULL` (crash on admin reset), score 0-0-0 racks in classification (winner penalized), and are counted by Amalfi `_get_trio_counts` as "played trios" (winner penalized in future trio rotation).

**Approach:** Route all three walkover branches through `MatchStateService.to_completed()` as the single completion path. In `create_matches_from_pairings`, create each walkover match in `pending` state with the right flags and scores, then call `to_completed(match.id)` inline. Add a `Match.is_walkover` property for downstream handlers. Extend XP handler and rating handler to skip XP/rating for forfeit players (winner included, to cover the 3/3 edge case) using `WithdrawPolicyService`. Extend `ScoreAggregator._process_trio_match` to detect walkover trios and credit the winner with `round_distance` racks. Filter walkover trios out of `_get_trio_counts` in Amalfi. Initialize matchup on walkover trio creation to eliminate the admin-reset crash.

## Boundaries & Constraints

**Always:**
- All walkover completions (bye, 2-player forfeit, trio 2/3, trio 3/3) MUST transit through `MatchStateService.to_completed()` — no direct `status="completed"` assignment in `round_creation.py`.
- `validated_by_admin=True` set at walkover creation for 2-player forfeit matches (required by `to_completed()` for pending non-trio non-bye). Bye and trio are exempt by existing `to_completed()` logic.
- `TrioMatch.initialize_matchup()` invoked at walkover trio creation so `current_player1/2/3_id` are never NULL — admin reset crash disappears as a consequence.
- Forfeit players MUST NOT receive XP or rating updates, whether as loser (2-player and 2/3 trio) or as nominal winner (3/3 trio). Detection via `WithdrawPolicyService.get_forfeit_inscriptions(gara_id)` at handler invocation.
- `_process_trio_match` credits the walkover winner with `round_distance` racks and zero racks to the other two; `matches_won` / `matches_lost` logic unchanged (already uses `winner_id`).
- `_get_trio_counts` counts only TrioMatch rows with `total_racks_played > 0` (contested trios).
- Idempotency: re-invoking `create_matches_from_pairings` on a round already created stays a no-op (existing match-count guard in `_create_round_impl` is untouched).
- Match-level fields for bye / 2-player forfeit / trio walkover keep current values (winner_id, player1_score=round_distance, player2_score=0, is_bye/is_trio flags) — refactor is routing-level, not data-level.

**Ask First:**
- If `to_completed()` turns out to be unsafe to call transitively from `create_matches_from_pairings` due to `@transactional` nesting (e.g. rollback-on-return semantics) — HALT and propose mitigation.
- If any existing event handler subscribed to `MatchCompletedEvent` crashes on walkover inputs in ways not listed here (XP, rating, SSE bridge, classification) — HALT and ask before adding walkover-specific handling.

**Never:**
- No new columns on `Match` or `TrioMatch`. Walkover detection stays derived.
- No creation of "symbolic" `TrioRack` rows to represent walkover racks.
- Do not touch item 4 from `deferred-work.md` (`forfeit_user_ids` not passed from `RoundService.start_first_round`) — separate deferred fix.
- Do not change `MatchStateService.to_completed()` preconditions; work within them.
- Do not emit events manually — rely on `to_completed()`.

## I/O & Edge-Case Matrix

All scenarios use `round_distance = D` and `forfeit_user_ids` as the set of forfeiting inscriptions for the gara.

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Bye creation | Pairing with 1 player, `is_bye=True` | `Match(is_bye=True, status=completed)` via `to_completed()`. No `PlayerEncounter` (bye skip in encounter service). `MatchCompletedEvent` emitted. XP handler: no-op (bye has no loser, winner XP skipped because `is_walkover`). Rating handler: no-op. | N/A |
| 2-player 1/2 forfeit | 2-player pairing with 1 forfeit | `Match(is_trio=False, is_bye=False, completed)` via `to_completed()`. 1 `PlayerEncounter` recorded. `MatchCompletedEvent` emitted. Winner receives 50 XP (if not forfeit). Forfeiter: 0 XP. Rating NOT updated for either. | N/A |
| 2-player 2/2 forfeit | 2-player pairing, both forfeit | Same as 1/2 but both players in forfeit set. Winner (= `pairing.players[0]`) is also forfeit → 0 XP for both. Encounter still recorded. Rating NOT updated. | N/A |
| Trio 2/3 walkover | 3-player pairing, 2 forfeits | `Match(is_trio=True, completed)` + `TrioMatch(is_completed=True)` with `initialize_matchup()` called. Winner = survivor. 3 pairwise `PlayerEncounter` recorded. `MatchCompletedEvent` emitted. Winner 50 XP, 2 forfeiters 0 XP. Rating NOT updated. Classification: winner credited with `D` racks via `_process_trio_match` walkover branch. | N/A |
| Trio 3/3 walkover | 3-player pairing, 3 forfeits | Same as 2/3 but nominal winner = `pairing.players[0]`, who is also a forfeiter → 0 XP for all three. Other side effects identical. Classification credits nominal winner with `D` racks. | N/A |
| Admin reset of walkover trio | Walkover trio completed, admin triggers `to_playing` | `to_playing()` succeeds, `trio_state_serializer.serialize()` returns a valid state (current_player*_id already populated from creation-time `initialize_matchup()`). No crash. | N/A |
| Amalfi next-round after walkover | Gara with a walkover trio in round R, computing round R+1 pairings | `_get_trio_counts` returns counts over contested trios only (`total_racks_played > 0`); walkover winner is NOT penalized by elevated trio count. | N/A |

</frozen-after-approval>

## Code Map

- `models/competition/round_creation.py` -- owns the three walkover branches; the routing refactor lives here.
- `models/match/state_service.py` -- `to_completed()` is the unified completion path; read-only reference. `to_playing()` stays as-is (admin-reset fix comes from creation-time init, not from defensive code here).
- `models/match/models.py` -- `Match` gets a new `is_walkover` property (no column). `TrioMatch.initialize_matchup()` reused as-is.
- `models/gamification/event_handlers.py` -- `handle_match_completed_for_xp` gets walkover awareness (skip XP for any player in forfeit set).
- `models/rating/event_handlers.py` -- `handle_match_completed` returns early if `match.is_walkover`.
- `models/classification/score_aggregator.py` -- `_process_trio_match` gets a walkover branch (`total_racks_played==0 and is_completed and winner_id` → credit `D` racks to winner).
- `models/matchmaking/strategies/amalfi.py` -- `_get_trio_counts` filters by `total_racks_played > 0`.
- `models/classification/encounter_service.py` -- read-only; `record_match_encounters` already handles trio pairwise and bye-skip correctly.
- `models/competition/withdraw_policy_service.py` -- read-only; `get_forfeit_inscriptions(gara_id)` is the forfeit source of truth, consumed by handlers.
- `tests/new/unit/test_round_creation_trio_forfeit.py` -- extend existing tests with side-effect assertions (encounter rows, event emission, classification).
- `tests/new/unit/test_walkover_side_effects.py` -- NEW: end-to-end unit coverage of the I/O matrix.

## Tasks & Acceptance

**Execution:**
- [x] `models/match/models.py` -- add `Match.is_walkover` as a plain `@property` returning `True` iff `status==COMPLETED` AND `winner_id is not None` AND (trio: `trio_match and trio_match.total_racks_played==0`; non-trio: no active `Rack` rows). Bye with winner set is a walkover too.
- [x] `models/competition/round_creation.py` -- refactor bye branch: create `Match(is_bye=True, status="pending", winner_id=..., player1_score=D)` then call `MatchStateService.to_completed(match.id)`.
- [x] `models/competition/round_creation.py` -- refactor 2-player forfeit branch: set `validated_by_admin=True`, `status="pending"`, scores/winner as today, then `to_completed()`.
- [x] `models/competition/round_creation.py` -- refactor trio 2/3 and 3/3 walkover branches: create `Match(is_trio=True, status="pending", ...)` + `TrioMatch(is_completed=True, winner_id=..., ...)`, call `trio_match.initialize_matchup()` to populate `current_player*_id`, then `to_completed(match.id)`.
- [x] `models/gamification/event_handlers.py` -- in `handle_match_completed_for_xp`: if `match.is_walkover`, query `WithdrawPolicyService.get_forfeit_inscriptions(match.gara_id)` and skip XP for any player whose user_id is in the forfeit set (winner included).
- [x] `models/rating/event_handlers.py` -- in `handle_match_completed`: if `match.is_walkover`, return early (no rating change).
- [x] `models/classification/score_aggregator.py` -- in `_process_trio_match`: if `trio.total_racks_played == 0 and trio.is_completed and trio.winner_id is not None`, credit winner with `round_distance` racks, zero racks to the other two players. `matches_won/matches_lost` logic untouched (already keyed off `winner_id`).
- [x] `models/matchmaking/strategies/amalfi.py` -- in `_get_trio_counts`: filter in-Python on loaded results (`total_racks_played > 0`).
- [x] `tests/new/unit/test_round_creation_trio_forfeit.py` -- extend existing 2/3 test assertions: `current_player*_id` is not NULL (matchup initialized at creation).
- [x] `tests/new/unit/test_walkover_side_effects.py` -- NEW: table-driven unit tests for the 7 I/O matrix scenarios.
- [x] `tests/new/integration/test_walkover_integration.py` -- NEW: end-to-end integration tests for XP filtering and rating skip on walkover.

**Acceptance Criteria:**
- Given a bye pairing, when `create_matches_from_pairings` runs, then the bye `Match` is persisted as `completed` with no `PlayerEncounter` rows, a `MatchCompletedEvent` is emitted, and neither XP nor rating side effects occur.
- Given a 2-player pairing with any forfeits, when the function runs, then 1 `PlayerEncounter` row exists, `MatchCompletedEvent` is emitted, no forfeit player gains XP, and no rating delta is applied to either player.
- Given a trio pairing with 2 forfeits, when the function runs, then 3 pairwise `PlayerEncounter` rows exist, the surviving player gains 50 XP, the two forfeiters gain 0 XP, no rating delta, `ScoreAggregator` reports `round_distance` racks for the survivor and 0 for the others, `TrioMatch.current_player*_id` are all non-NULL.
- Given a trio pairing with 3 forfeits, same as 2/3 except no player gains XP (nominal winner is in forfeit set), and classification still credits the nominal winner with `round_distance` racks.
- Given a completed walkover trio, when an admin triggers `to_playing()`, then `trio_state_serializer.serialize()` returns a fully populated current matchup without raising.
- Given a gara with a walkover trio in round 1, when round 2 pairings are computed via Amalfi, then `_get_trio_counts` does not count the walkover trio — the survivor is no more "trio-saturated" than anyone else.
- `pyright`, `black`, and `flake8` clean.
- `pytest tests/new/unit/ -n auto` and `pytest tests/new/integration/ -n 4` green.

## Spec Change Log

### 2026-04-19 — implementation findings

**Bye `MatchCompletedEvent` emission (I/O Matrix row "Bye creation"):**
Spec's frozen row states "MatchCompletedEvent emitted" for bye. Actual
behavior: `MatchStateService._emit_completion_event` has a pre-existing
guard `if match.is_bye or not match.player2_id: return` that skips event
emission for bye (pre-dates this refactor). Net effect matches spec intent
— no XP, no rating, no downstream handler side effects — but the mechanism
is "event never fires" rather than "event fires → handlers skip via
is_walkover". Left unchanged: modifying `_emit_completion_event` would
ripple into every bye consumer for no behavioral gain. Acceptance criterion
(outside frozen) rewritten to match reality; test
`test_bye_records_no_encounter_and_emits_no_event` asserts it.

**`Match.validated_by_admin` is not a column:**
Spec's 2-player forfeit task called for `validated_by_admin=True` in the
Match constructor. Discovery: the attribute exists only on `Rack`, not on
`Match`. The `getattr(match, "validated_by_admin", False)` check in
`MatchStateService.to_completed` relies on a **runtime** attribute set via
SQLAlchemy identity map — established pattern in
`ScoringService._apply_result` (line 547) and `TrioMatch._finalize_trio`
(line 669). Implementation sets it after `db.session.flush()`, just like
those call sites. No schema change (Never clause preserved).

## Design Notes

**Why a derived `is_walkover` instead of a column:** zero migration cost, detectable from state invariants, and naturally consistent with the only fact that matters: "this match was completed without racks being played". A column would introduce a persisted flag that could drift from reality; detection from `(status, winner_id, racks)` cannot.

**Why drive forfeit detection from `WithdrawPolicyService` at handler time instead of storing `forfeit_player_ids` on Match:** forfeit status is already authoritative on `Inscription`; duplicating it on `Match` adds a second source of truth. The query is cheap (one indexed lookup per gara) and handlers only run once per match completion.

**Why `_process_trio_match` walkover branch (option 2b) instead of symbolic TrioRack rows (2a):** symbolic racks would require synthesizing matchup fields (`player1_id`, `player2_id`, `waiting_player_id`) for every rack, which is either arbitrary (no real rotation happened) or forces a fake rotation that leaks into downstream consumers. Branching in classification isolates the special case to a single function.

**Bye XP note:** the current XP handler skips when `event.winner_id is None`. For bye, `winner_id` IS set (it's the lone player). The `is_walkover` check plus forfeit-set intersection (bye player is not in forfeit set) would otherwise credit the bye winner with 50 XP. Spec's `Always` clause treats bye as walkover, so the handler skips bye XP by treating the bye player as a "walkover participant". Implementation: in the XP handler, when `is_walkover`, additionally skip if `match.is_bye` (no XP on bye for anyone). Kept as a one-liner in the handler, not in the spec clauses, to keep the invariant simple.

## Verification

**Commands:**
- `pytest tests/new/unit/test_walkover_side_effects.py -n auto -v` -- expected: all 7 scenarios pass.
- `pytest tests/new/unit/test_round_creation_trio_forfeit.py -n auto -v` -- expected: all existing + extended tests pass.
- `pytest tests/new/integration/test_walkover_integration.py -n 4 -v` -- expected: integration pass.
- `pytest tests/new/ -n 4` -- expected: full suite green, no regressions.
- `pyright` -- expected: 0 errors.
- `black . && flake8` -- expected: clean.

**Manual checks:**
- None required; the spec is fully test-covered.

## Suggested Review Order

**Entry point — the design intent**

- Unified routing: three walkover branches (bye, 2-player forfeit, trio 2/3 and 3/3) now flow through `MatchStateService.to_completed()` instead of setting status directly.
  [`round_creation.py:15`](../../models/competition/round_creation.py#L15)

**Walkover detection primitive**

- Derived property: no schema change, truthiness from state invariants (completed + winner + no racks ever existed).
  [`models.py:142`](../../models/match/models.py#L142)

**Handler walkover-awareness**

- XP handler: loads forfeit set once, skips XP/streak/quest/achievement for any player in that set (winner included — covers 3/3 trio case).
  [`event_handlers.py:113`](../../models/gamification/event_handlers.py#L113)

- Rating handler: short-circuits on walkover so Elo is never distorted by forfeit outcomes.
  [`event_handlers.py:34`](../../models/rating/event_handlers.py#L34)

**Classification trio walkover**

- Special branch: if trio is completed with zero racks, credit winner with `round_distance` racks and 0 to the other two — parallel to 2-player walkover's `player1_score = round_distance` semantics.
  [`score_aggregator.py:308`](../../models/classification/score_aggregator.py#L308)

**Amalfi trio rotation fairness**

- Filter: walkover trios (0 racks played) no longer count toward rotation — walkover survivors aren't penalized next round.
  [`amalfi.py:506`](../../models/matchmaking/strategies/amalfi.py#L506)

**Tests — regression + comprehensive coverage**

- Updated existing trio-forfeit tests for the new matchup-initialization invariant.
  [`test_round_creation_trio_forfeit.py:190`](../../tests/new/unit/test_round_creation_trio_forfeit.py#L190)

- New unit suite covering the 7 I/O matrix rows + `is_walkover` edge cases.
  [`test_walkover_side_effects.py:1`](../../tests/new/unit/test_walkover_side_effects.py#L1)

- New integration suite: end-to-end XP filtering, rating skip, and encounter recording with real handlers registered.
  [`test_walkover_integration.py:1`](../../tests/new/integration/test_walkover_integration.py#L1)
