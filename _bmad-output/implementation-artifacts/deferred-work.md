# Deferred Work — Architecture Review Residuals

Created: 2026-04-04
Source: Adversarial Review (AR) + Edge Case Hunter (ECH) session

## ~~Priority 1: Migrate remaining inline str(e) to safe_json_error~~ ✅ DONE (2026-04-04)

Migrated all `except Exception` blocks that exposed `str(e)` in JSON responses across 10 route files.
`routes/player/privacy.py` only had `except ValueError` (intentional user-facing messages) — no change needed.
Also cleaned up flash messages in dual AJAX/flash routes and removed legacy `print`/`traceback` debugging.

## Priority 2: UNIQUE constraints for TOCTOU race conditions (requires migration)

Two race conditions from ECH analysis. SQLite single-writer mitigates risk but constraints provide DB-level safety.

1. **`individual_match` table** — add UNIQUE on `proposal_id` to prevent double-accept of same proposal
   - ECH-1: Two users accept same OPEN proposal concurrently → 2 matches created
   - ECH-6: Proposal accepted after expiration (TOCTOU)

2. **`proposal_invitation` table** — add UNIQUE on `(proposal_id, invited_user_id)` to prevent duplicate invitations
   - ECH-21: No duplicate check on `invite_player_to_match`

**Implementation**:
- Create migration `migrations/20260405_unique_constraints_toctou.py`
- Add `UniqueConstraint` to models
- Handle `IntegrityError` in services as fallback

**Effort**: ~1 hour (migration + model + service error handling)

## Priority 3: EventBus error monitoring

AR-8: `EventBus.publish()` catches handler exceptions, logs them, but has no monitoring.
If a handler fails repeatedly (e.g., the rating handler bug we fixed), no alert is raised.

**Approach options**:
- Add error counter per handler + log WARNING after N failures
- Or integrate with GlitchTip/Sentry (already configured in app.py)

**Effort**: ~1 hour

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
