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

## Priority 4: Performance optimizations (profile first)

Low priority — no user-reported issues.

- ~~**SSE memory leak** (AR-10)~~ ✅ DONE (2026-04-05): `routes/sse.py` —
  added throttled `_maybe_sweep_stale_scope_ids` (max once per 30s)
  that prunes `scope_id` keys whose event lists are entirely stale
  (older than `MAX_EVENT_AGE`). Triggered from both `emit_event` and
  `_get_events_since` (polling is sustained even when emits stop).
  5 unit tests in `test_sse_event_store_cleanup.py`.
- **N+1 queries** (AR-12): Add `joinedload()` for `gara.inscriptions`, `user.director_assignments`, `gara.matches` in hot paths. Need profiling to identify actual bottlenecks first.

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
