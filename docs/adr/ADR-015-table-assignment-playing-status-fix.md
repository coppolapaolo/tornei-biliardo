# ADR-015: Table Assignment - PLAYING Status Physical Constraint

## Status
Accepted

## Date
2026-01-14

## Context

Two bugs were discovered in table assignment and trio permission handling:

**Bug 1: Duplicate Table Assignment Across Rounds**
Users could assign the same physical table to two different PLAYING matches because the system only checked for conflicts within the same round.

Screenshot showed: Match "EMILIO vs MAX P" and "picchio vs EGLE" both assigned to table 7 and both in "In Corso" (PLAYING) status.

**Bug 2: Trio Manager Permission 403 for Standalone Garas**
The `trio_manager_required` decorator assumed all garas belonged to a campionato, passing `campionato_id` (which was `None` for standalone garas) to `campionato_manager_required`, which correctly rejected `None` values with 403.

## Decision

### Bug 1 Fix: Table Assignment Physical Constraint

Changed `TableAssignmentService.reassign_table()` to check for table conflicts with ANY **PLAYING** match in the same gara, regardless of round number.

**Before (Bug):**
```python
# Only checked same round - allowed cross-round table sharing
occupying_match = Match.query.filter_by(
    gara_id=match.gara_id,
    round_number=match.round_number,  # BUG: Only same round
    table_assignment=new_table,
).first()
```

**After (Fix):**
```python
# Check any PLAYING match in gara (physical constraint)
occupying_match = Match.query.filter_by(
    gara_id=match.gara_id,
    table_assignment=new_table,
    status=MatchStatus.PLAYING.value,  # Only PLAYING matches occupy tables
).first()
```

**Rationale:**
- A physical table can only host ONE match at a time
- PENDING matches have scheduled table assignments (not physical occupation)
- COMPLETED matches have historical table records (already finished)
- Only PLAYING matches physically occupy a table

### Bug 2 Fix: Trio Manager Standalone Gara Support

Changed `trio_manager_required` to use `PermissionChecker.can_manage_competition()` which already handles both standalone garas and campionato garas.

**Before (Bug):**
```python
def trio_manager_required(f):
    def decorated_function(*args, **kwargs):
        trio = TrioMatch.query.get_or_404(trio_id)
        campionato_id = trio.match.gara.campionato_id  # None for standalone!
        return campionato_manager_required(_get_tid)(f)(...)  # 403 when None
```

**After (Fix):**
```python
def trio_manager_required(f):
    def decorated_function(*args, **kwargs):
        trio = TrioMatch.query.get_or_404(trio_id)
        gara_id = trio.match.gara_id
        # Uses gara-level check which handles both standalone and campionato garas
        if not PermissionChecker.can_manage_competition(current_user, gara_id):
            abort(403)
        return f(*args, **kwargs)
```

## Consequences

### Positive
- Tables cannot be double-booked for PLAYING matches (physical reality)
- Standalone garas can now use trio matches correctly
- Test suite updated to clearly document the new behavior

### Neutral
- PENDING matches can still share table assignments for scheduling purposes
- COMPLETED matches retain historical table assignments

### Files Changed
- `models/match/table_assignment_service.py` - Table conflict check
- `utils/permissions.py` - `trio_manager_required` decorator
- `tests/new/unit/test_table_assignment_reassign.py` - Updated tests

## Related
- No previous ADR for table assignment
- Relates to match state machine (PENDING → PLAYING → COMPLETED)
