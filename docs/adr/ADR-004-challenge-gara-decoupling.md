# ADR-004: Challenge/Gara Domain Decoupling

**Date**: 2025-12-30
**Status**: Accepted
**Sprint**: Sprint 11

## Context

The Challenge domain had an improper coupling with the Competition (Gara) domain:

1. **ChallengeAttempt.gara_id** - Challenge attempt knew about competitions
2. **GaraChallenge models** - Located in `models/challenge/` but managing competition logic
3. **GaraChallengeService** - Located in Challenge domain but orchestrating competition integration

This violated Domain-Driven Design principles: the dependency arrow pointed in the wrong direction. Challenge → Gara instead of Competition → Challenge.

### Problematic Code (Before)

```
models/challenge/
├── models.py              # Contains ChallengeAttempt.gara_id  <-- WRONG
├── gara_challenge_models.py  # Competition-specific models  <-- WRONG LOCATION
└── gara_challenge_service.py # Competition-specific service <-- WRONG LOCATION
```

### Business Context

The coupling exists for legitimate features:
- **Bye Replacement (Amalfi)**: When odd players, bye player completes a challenge
- **Integrated Challenges**: Challenges executed during tournament rounds
- **Challenge Classification**: Rankings based on challenge performance in a gara

However, the Challenge domain should be a **pure domain** - unaware of competitions.

## Decision

Invert the dependency direction: **Competition → Challenge** (not Challenge → Gara).

### Changes Made

1. **Moved files to Competition domain**:
   - `models/challenge/gara_challenge_models.py` → `models/competition/gara_challenge.py`
   - `models/challenge/gara_challenge_service.py` → `models/competition/gara_challenge_service.py`

2. **Created new bridge entity**:
   - `models/competition/gara_bye_challenge.py` - Links ChallengeAttempt to Gara for bye replacement

3. **Maintained backward compatibility**:
   - Old import paths re-export from new locations with DeprecationWarning
   - `models/challenge/__init__.py` updated to re-export from Competition

4. **Updated all imports** across codebase to use new locations

### Architecture After

```
models/challenge/           # PURE DOMAIN
├── models.py              # Challenge, ChallengeAttempt (NO gara_id)
├── services.py            # ChallengeService
├── gara_challenge_models.py  # DEPRECATED re-export
└── gara_challenge_service.py # DEPRECATED re-export

models/competition/         # OWNS INTEGRATION
├── gara_challenge.py      # GaraChallenge, GaraChallengeAttempt, GaraChallengeClassification
├── gara_challenge_service.py
└── gara_bye_challenge.py  # NEW: Bridge for bye replacement
```

### Dependency Direction

```
Competition Domain ──────────────> Challenge Domain
    │                                   │
    │ imports:                          │ exports:
    │ - GaraChallenge                   │ - Challenge
    │ - GaraChallengeService            │ - ChallengeAttempt
    │ - GaraByeChallenge                │ - ChallengeService
    │                                   │
    └───────────────────────────────────┘
            (Challenge is unaware)
```

## Consequences

### Positive
- Challenge domain is now pure (no competition knowledge)
- Clear domain boundaries
- Proper dependency direction (stable abstractions principle)
- Easier to test Challenge domain in isolation
- Competition owns all integration logic

### Negative
- Requires database migration for `gara_bye_challenge` table (pending)
- `ChallengeAttempt.gara_id` deprecation requires data migration (pending)
- Temporary backward compatibility layer adds complexity

### Pending Work (Future Sprints)
- FASE 4: Migrate bye logic to use `GaraByeChallenge`
- FASE 5: Deprecate and remove `ChallengeAttempt.gara_id`
- FASE 6: Create database migration script

## Implementation Notes

### Migration Strategy
1. Create `gara_bye_challenge` table
2. Migrate existing `ChallengeAttempt.gara_id` data to new table
3. Update bye match creation to use `GaraByeChallenge`
4. Mark `ChallengeAttempt.gara_id` as deprecated
5. Remove field in future release

### Backward Compatibility
Re-exports with deprecation warnings allow gradual migration:
```python
# Old (deprecated, shows warning)
from models.challenge.gara_challenge_models import GaraChallenge

# New (preferred)
from models.competition.gara_challenge import GaraChallenge

# Or via package
from models.competition import GaraChallenge
```

## References

- **TODO_BACKLOG.md**: Section "P2 - Design Questions: Challenge/Gara Coupling"
- **models/challenge/models.py**: Lines 307-316 (TODO comments)
- **models/competition/gara_challenge.py**: New location with updated docstrings
