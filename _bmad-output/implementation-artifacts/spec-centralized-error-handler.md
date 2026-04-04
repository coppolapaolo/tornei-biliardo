---
title: 'Centralized error handler — hide Exception details from JSON responses'
type: 'bugfix'
created: '2026-04-04'
status: 'done'
baseline_commit: '020f61a'
context:
  - 'CLAUDE.md'
  - 'utils/route_helpers.py'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** ~47 JSON endpoints and 2 centralized helpers expose raw `str(e)` from `except Exception` blocks to the client (HTTP 500 responses). This leaks internal error details (stack traces, DB errors, file paths) — a security info-leakage finding from the Adversarial Review. `ValueError`/`PermissionError` messages (HTTP 400) are business logic and OK to expose.

**Approach:** Fix the 2 centralized helpers (`handle_ajax_service_action`, `handle_service_action`) to log `Exception` details server-side and return a generic message to the client. Then fix the `app.py` global 500 handler to also catch JSON requests. For inline `except Exception` blocks in routes, add a dedicated `safe_json_error()` helper and migrate the highest-traffic files.

## Boundaries & Constraints

**Always:**
- `ValueError` and `PermissionError` messages are business logic → keep exposing them to client
- `Exception` messages must be logged server-side at ERROR level with `exc_info=True`
- Client receives only generic message: "Errore interno del server"
- Existing tests must pass unchanged

**Ask First:**
- Migrating inline try/except blocks in routes to use helpers (large scope change)

**Never:**
- Do not change the function signatures of existing helpers
- Do not suppress logging — every hidden error must be logged
- Do not touch `ValueError`/`PermissionError` handling

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| ValueError in JSON endpoint | Invalid business input | `{"success": false, "error": "Messaggio specifico"}`, 400 | Shown to user |
| Exception in JSON endpoint | DB error, unexpected crash | `{"success": false, "error": "Errore interno del server"}`, 500 | Logged server-side |
| Exception in HTML endpoint | Unexpected crash | Flash "Errore interno del server", redirect | Logged server-side |
| Exception in app-level 500 | Unhandled exception | JSON if AJAX, HTML template otherwise | Logged server-side |

</frozen-after-approval>

## Code Map

- `utils/route_helpers.py` -- Central helpers: `handle_ajax_service_action` (line 93-96), `handle_service_action` (line 132-133) expose `str(e)`
- `app.py:279-290` -- Global error handlers (404, 500, 429) — 500 handler returns HTML only, no JSON
- `routes/admin/competition/matches.py` -- 6 inline `except Exception` with `jsonify(str(e))`
- `routes/player/matches.py` -- 9 inline `except Exception` with `jsonify(str(e))`
- `routes/admin/match/scoring.py` -- 4 inline `except Exception` with `jsonify(str(e))`

## Tasks & Acceptance

**Execution:**
- [ ] `utils/route_helpers.py` -- Fix `handle_ajax_service_action` and `handle_service_action`: replace `str(e)` with generic message for `except Exception`, add `logger.error(..., exc_info=True)`
- [ ] `utils/route_helpers.py` -- Add `safe_json_error()` helper for inline use: logs Exception, returns generic JSON 500
- [ ] `app.py` -- Enhance global 500 handler to return JSON for AJAX/JSON requests
- [ ] `routes/admin/competition/matches.py` -- Replace 6 inline `except Exception` blocks with `safe_json_error(e)`
- [ ] `routes/player/matches.py` -- Replace 9 inline `except Exception` blocks with `safe_json_error(e)`
- [ ] `routes/admin/match/scoring.py` -- Replace 4 inline `except Exception` blocks with `safe_json_error(e)`

**Acceptance Criteria:**
- Given an Exception in a JSON endpoint, when the response is returned, then the body contains only "Errore interno del server" and the actual error is in the server log
- Given a ValueError in a JSON endpoint, when the response is returned, then the body contains the specific error message
- Given all existing tests, when run, then they pass unchanged (735 unit + 197 integration)

## Verification

**Commands:**
- `pyright utils/route_helpers.py app.py routes/admin/competition/matches.py routes/player/matches.py routes/admin/match/scoring.py` -- expected: 0 errors
- `pytest tests/new/unit/ -n auto` -- expected: 735 passed
- `pytest tests/new/integration/ -n 4` -- expected: 197 passed

## Suggested Review Order

**Core: centralized error handling**

- New `safe_json_error()` helper + generic message constant + logger setup
  [`route_helpers.py:17`](../../utils/route_helpers.py#L17)

- `handle_ajax_service_action` now logs and hides Exception details
  [`route_helpers.py:97`](../../utils/route_helpers.py#L97)

- `handle_service_action` same fix for non-AJAX flows
  [`route_helpers.py:139`](../../utils/route_helpers.py#L139)

- Global 500 handler returns JSON for AJAX requests
  [`app.py:286`](../../app.py#L286)

**Migration: inline exception blocks**

- Admin trio endpoints (6 handlers) use `safe_json_error`
  [`matches.py:15`](../../routes/admin/competition/matches.py#L15)

- Player match endpoints (9 handlers) use `safe_json_error`
  [`matches.py:11`](../../routes/player/matches.py#L11)

- Admin scoring endpoints (3 handlers) use `safe_json_error`
  [`scoring.py:25`](../../routes/admin/match/scoring.py#L25)
