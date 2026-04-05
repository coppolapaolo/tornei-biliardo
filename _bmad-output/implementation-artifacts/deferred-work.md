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

- **SSE memory leak** (AR-10): `routes/sse.py` — dict keys for scope_ids never deleted. Add periodic cleanup or prune on poll. Mitigated by PythonAnywhere daily restarts.
- **N+1 queries** (AR-12): Add `joinedload()` for `gara.inscriptions`, `user.director_assignments`, `gara.matches` in hot paths. Need profiling to identify actual bottlenecks first.

**Effort**: ~2 hours total (including profiling)

## ~~Priority 5: Extend TOCTOU ValueError translation~~ ✅ DONE (2026-04-05)

Spec `spec-extend-toctou-translation.md`. `report_result` wrappato con savepoint
pattern ADR-025. `ProposalInvitation.accept` documentato con docstring contract
(metodo model-layer, caller responsabili del wrapping).

## Priority 5b: Add IntegrityError contract docstring to `MatchProposal.accept`

Surfaced during review of spec-extend-toctou-translation. We added a contract
docstring to `ProposalInvitation.accept` but `MatchProposal.accept()` itself is
the method that actually creates the `IndividualMatch` and can fire the UNIQUE
constraint. For consistency, its docstring should also cite ADR-025 and warn
that direct callers (not going through `ProposalService.accept_proposal`) must
wrap the call in the savepoint pattern.

**Effort**: ~10min (pure docstring addition, no behavior change)

## Priority 5c: `report_result` pending-branch is broken dead code

Surfaced while writing tests for Priority 5. In `MatchLifecycleService.report_result`:

```python
if proposal.status.value == "pending":
    individual_match = proposal.accept(reporter_id)  # creates SCHEDULED match
...
MatchLifecycleService.complete_match(...)  # requires IN_PROGRESS → raises
```

`proposal.accept()` creates an `IndividualMatch` with `status=SCHEDULED`, but the
subsequent `complete_match` step requires `status=IN_PROGRESS`, so the pending
branch always raises "Match is not in progress". The branch is never reached from
routes (only `IndividualMatchService.report_result` delegates here, and no route
calls it). This is dead code with an intrinsic bug.

**Approaches**:
- (a) Delete the pending branch entirely (simplest; confirm no external callers)
- (b) Insert a state transition SCHEDULED → IN_PROGRESS before complete_match
- (c) Replace complete_match call with a direct `match.complete_match(winner_id)`
  that skips the status check for the freshly-accepted path

**Effort**: ~30min (option a) or ~1h (option b/c with test coverage)
