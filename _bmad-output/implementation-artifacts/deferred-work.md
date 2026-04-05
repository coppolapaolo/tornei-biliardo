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

## Priority 3b: Investigare double-capture logger.error + Sentry LoggingIntegration

Emerso durante review di spec-eventbus-error-monitoring. Sentry SDK ha `LoggingIntegration`
abilitata di default che cattura i log ERROR come eventi Sentry. In `EventBus.publish()`:

1. `EventHandler.__call__` chiama `logger.error(exc_info=True)` e rilancia (preesistente)
2. `publish()` cattura il re-raise e chiama `logger.error(exc_info=True)` (preesistente)
3. Il nuovo `_capture_handler_exception()` chiama `sentry_sdk.capture_exception()` esplicitamente

Con LoggingIntegration attiva, lo stesso errore genera potenzialmente 2-3 eventi Sentry
per singola failure di handler. Sentry dedupa per fingerprint (issue count stabile) ma
event count gonfia il billing/rate-limit.

**Approcci possibili**:
- Demotare uno dei due `logger.error` a `logger.debug` (violazione boundary "logger.error
  rimane invariato" dello spec originale)
- Configurare `LoggingIntegration(event_level=CRITICAL)` in `app.py` per alzare la soglia
- Aggiungere un filtro Python logging che marca i log già catturati esplicitamente

**Effort**: ~1 hour (include verifica comportamento reale su GlitchTip)

## Priority 4: Performance optimizations (profile first)

Low priority — no user-reported issues.

- **SSE memory leak** (AR-10): `routes/sse.py` — dict keys for scope_ids never deleted. Add periodic cleanup or prune on poll. Mitigated by PythonAnywhere daily restarts.
- **N+1 queries** (AR-12): Add `joinedload()` for `gara.inscriptions`, `user.director_assignments`, `gara.matches` in hot paths. Need profiling to identify actual bottlenecks first.

**Effort**: ~2 hours total (including profiling)

## Priority 5: Extend TOCTOU ValueError translation to other `proposal.accept()` callers

Surfaced during review of spec-unique-constraints-toctou. The new savepoint/ValueError
guard covers `ProposalService.accept_proposal` only. Two other paths call
`proposal.accept()` directly and would surface raw `IntegrityError` if the UNIQUE
constraint fires:

- `models/individual_match/match_lifecycle_service.py:122` (`report_result`) — niche
  path that calls accept on a still-pending proposal during result reporting.
- `models/individual_match/proposal_models.py:323` (`ProposalInvitation.accept`) —
  currently dead from routes (all paths go through `respond_to_invitation` →
  `accept_proposal`), but reachable via tests/direct calls.

**Approach**: Either (a) move savepoint/ValueError wrapping INTO `MatchProposal.accept()`
itself, or (b) guard the two caller sites individually. Option (a) centralizes the
contract but adds error-translation to a model method (architectural smell).

**Effort**: ~30min
