# ADR-023: Match Status Handling and Real-time Polling Fixes

**Date:** 2026-02-04
**Status:** Accepted
**Context:** Bug fixes for match validation, status display, and real-time updates

---

## Summary

This ADR documents several related bug fixes discovered during testing of the gara management system:

1. **Missing `emit_gara_event` in player routes** - Directors couldn't see real-time score updates
2. **Tie match validation blocked** - "Esattamente N" matches couldn't be validated when tied
3. **Mobile template missing `validated` status** - Completed matches showed wrong status on mobile
4. **Missing "Lista d'Attesa" option** - Odd handling dropdown was incomplete in gara creation wizards

---

## Problem 1: Directors Not Seeing Real-time Score Updates

### Context

When players added/removed racks via their routes (`/player/match/<id>/racks/add`), the gara_detail page watched by directors didn't update in real-time.

### Root Cause

The player routes in `routes/player/matches.py` emitted events to the **MATCH scope** only:
```python
emit_match_event(match_id, "rack_added", {...})  # → MATCH scope
```

But the gara_detail page polls the **GARA scope**:
```javascript
window.Polling.reloadOnEvents({
    url: '/sse/poll/gara/' + garaId,
    reloadOn: ['match_completed', 'match_updated', ...]
});
```

The admin routes (`routes/admin/match.py`) correctly emitted to both scopes:
```python
emit_match_event(match_id, "rack_added", {...})  # For match_detail
emit_gara_event(gara_id, "match_updated", {...})  # For gara_detail
```

### Solution

Added `emit_gara_event()` calls to all player rack operations:
- `add_rack_simplified()`
- `remove_rack_simplified()`
- `confirm_match_result()`
- `reject_match_result()`
- `forfeit_match()`

```python
from routes.sse import emit_match_event, emit_gara_event

emit_match_event(match_id, "rack_added", {...})

# NEW: Also emit to gara scope for directors
if match.gara_id:
    emit_gara_event(match.gara_id, "match_updated", {
        "match_id": match_id,
        "player1_score": match.player1_score,
        "player2_score": match.player2_score,
    })
```

**Files changed:** `routes/player/matches.py`

---

## Problem 2: Tie Match Validation Blocked

### Context

For gare configured as "Esattamente N" (e.g., exactly 6 racks), a match ending 3-3 is a valid tie. However, the validation endpoint returned an error:

```
"Pareggio: impossibile validare senza un vincitore"
```

### Root Cause

The validation logic in `routes/admin/match.py` assumed every match must have a winner:

```python
if match.player1_score > match.player2_score:
    match.winner_id = match.player1_id
elif match.player2_score > match.player1_score:
    match.winner_id = match.player2_id
else:
    return jsonify({"error": "Pareggio: impossibile validare..."})  # BLOCKED!
```

### Solution

Allow ties by removing the error and letting `winner_id` remain `NULL`:

```python
if match.player1_score > match.player2_score:
    match.winner_id = match.player1_id
elif match.player2_score > match.player1_score:
    match.winner_id = match.player2_id
# else: Pareggio - winner_id rimane NULL (consentito)
```

**Files changed:** `routes/admin/match.py`

---

## Problem 3: Mobile Template Missing `validated` Status

### Context

A match confirmed by players showed as "Completata" on desktop but had no status badge on mobile, displaying with wrong border color and action buttons.

### Root Cause

The system has two "finished" states:
- `completed` - When players confirm
- `validated` - When admin validates (optional)

Desktop template (`_match_result_row.html`) handled both:
```jinja2
{% set is_finished = match.status in ['completed', 'validated'] %}
```

Mobile template (`_match_card.html`) only checked `completed`:
```jinja2
{% elif match.status == 'completed' %}  {# Missed 'validated'! #}
```

### Solution

Added unified `is_finished` helper to mobile template:

```jinja2
{# Helper: check if match is finished (completed or validated) #}
{% set is_finished = match.status in ['completed', 'validated'] %}

{# Use is_finished everywhere instead of match.status == 'completed' #}
{% set p1_wins = is_finished and match.winner_id == match.player1_id %}
{% elif is_finished %}
<span class="badge bg-success">{{ _('Completata') }}</span>
```

**Files changed:** `templates/components/_match_card.html`

---

## Problem 4: Missing "Lista d'Attesa" Odd Handling Option

### Context

When creating a new gara, the "Gestione Dispari" dropdown was missing the "Lista d'Attesa" option (value: `no`).

### Root Cause

The dropdown in both gara creation templates only had 3 options instead of 4:
- `bye` - Riposo
- `bye_with_challenge` - Riposo con Challenge
- `trio` - Match a 3 Giocatori
- ~~`no` - Lista d'Attesa~~ ← MISSING

### Solution

Added the missing option to both templates:

**`templates/components/_new_gara_modal.html`** (campionato gara wizard):
```html
<option value="no" {% if campionato.default_odd_policy == 'no' %}selected{% endif %}>
    Lista d'Attesa
</option>
```

**`templates/admin/gara_create_standalone.html`** (standalone gara form):
```html
<option value="no">Lista d'Attesa</option>
```

**Files changed:**
- `templates/components/_new_gara_modal.html`
- `templates/admin/gara_create_standalone.html`

---

## Testing Verification

1. **Polling fix**: Director on gara_detail sees score updates when players add racks
2. **Tie validation**: "Esattamente 6" match at 3-3 can be validated as a tie
3. **Mobile status**: Completed/validated matches show green "Completata" badge
4. **Odd handling**: All 4 options visible in gara creation wizards

---

## Lessons Learned

1. **Event scoping**: When emitting events, consider ALL pages that need updates, not just the current one
2. **Status consistency**: Templates should handle ALL valid enum values, not just common ones
3. **Template parity**: Desktop and mobile templates must handle the same set of conditions
4. **Dropdown completeness**: Form options must match backend enum/model options

---

## Related Files

- `models/status_enum.py` - Defines `MatchStatus` with `COMPLETED` and `VALIDATED`
- `routes/sse.py` - Event store and polling endpoints
- `routes/sse_bridge.py` - Domain event to SSE routing
- `static/js/polling.js` - Frontend polling utility
