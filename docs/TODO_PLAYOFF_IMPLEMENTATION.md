# Playoff Feature Implementation Plan

**Status**: Planned Feature (not yet implemented)
**Priority**: P2 (Feature, not Bug)
**Last Updated**: 2025-12-29

## Overview

The Playoff system allows automatic qualification and creation of special tournaments
at the end of a Campionato season. Models are defined but integration with existing
services is incomplete.

## Current State

### What Exists

The domain models in `models/playoff/models.py` are well-defined:

1. **PlayoffConfiguration**: Defines qualification criteria for a playoff
   - `PlayoffType`: TOP_N, ELITE_ACADEMY, CONDITIONAL, BOTTOM_EXCLUDE
   - Criteria stored as JSON
   - Response deadline for player confirmations

2. **PlayoffQualification**: Individual player qualification status
   - `QualificationStatus`: PENDING, CONFIRMED, DECLINED, EXPIRED, REPLACED
   - Tracks confirmation/decline responses
   - Replacement mechanism for declined spots

3. **PlayoffTournament**: The actual playoff competition
   - Links to a Gara for match execution
   - Tracks registration and completion

### What's Missing

The `start_registration()` method in `PlayoffTournament` (lines 379-415) has
commented-out code that cannot work because:

1. **Wrong Service Method (Line 396)**:
   ```python
   # GaraService.create_gara() exists but has different signature:
   # Expected: campionato_id, director_id, name, location, date, is_playoff
   # Actual:   number, name, date, discipline, distance, campionato_id, director_id, **kwargs
   ```

2. **Non-existent Method (Line 411)**:
   ```python
   # GaraService.inscribe_user() does NOT exist
   # Should use: InscriptionService.inscribe_user(user_id, gara_id)
   ```

## Required APIs

### GaraService.create_gara

**Current Signature** (`models/competition/services.py:45`):
```python
@transactional
def create_gara(
    number: int,              # Required
    name: str,                # Required
    date,                     # Required
    discipline: str,          # Required
    distance: int,            # Required
    campionato_id: Optional[int] = None,
    director_id: Optional[int] = None,
    **kwargs                  # time, location, etc.
) -> Gara
```

**Missing Kwargs for Playoff**:
- `is_playoff: bool` - Flag to mark as playoff gara (doesn't exist in Gara model)
- Need to decide: Add flag or use naming convention?

### InscriptionService.inscribe_user

**Correct Method** (`models/competition/inscription_service.py:39`):
```python
@transactional
def inscribe_user(user_id: int, gara_id: int) -> Optional[Inscription]
```

## Implementation Steps

### Phase 1: Model Fixes

1. **Add `is_playoff` flag to Gara** (optional, could use naming convention instead):
   ```python
   # In models/competition/models.py
   is_playoff = db.Column(db.Boolean, nullable=False, default=False)
   ```

2. **Fix PlayoffTournament.start_registration()**:
   - Use correct GaraService.create_gara() signature
   - Use InscriptionService.inscribe_user() instead of non-existent method

### Phase 2: Service Implementation

1. **Create PlayoffService** (`models/playoff/services.py`):
   ```python
   class PlayoffService:
       @transactional
       def create_playoff_gara(
           self,
           playoff_tournament: PlayoffTournament
       ) -> Gara:
           """Create the Gara for a playoff tournament."""
           config = playoff_tournament.configuration

           return GaraService.create_gara(
               number=1,
               name=playoff_tournament.name,
               date=playoff_tournament.campionato_date or datetime.now(),
               discipline=config.campionato.gare[0].discipline,  # Inherit from campionato
               distance=config.campionato.gare[0].distance,
               campionato_id=config.campionato_id,
               director_id=None,  # Use campionato directors
               time=datetime.time(18, 0),
               location=playoff_tournament.location or "TBD",
               max_participants=config.max_participants,
               entry_fee=float(config.entry_fee) if config.entry_fee else 0.0
           )

       @transactional
       def inscribe_qualified_players(
           self,
           gara_id: int,
           qualifications: List[PlayoffQualification]
       ) -> int:
           """Inscribe all confirmed qualified players."""
           inscribed_count = 0
           for qual in qualifications:
               if qual.status == QualificationStatus.CONFIRMED:
                   try:
                       InscriptionService.inscribe_user(
                           user_id=qual.user_id,
                           gara_id=gara_id
                       )
                       inscribed_count += 1
                   except Exception as e:
                       # Log error but continue with other players
                       pass
           return inscribed_count
   ```

### Phase 3: Integration

1. **Add Campionato.playoff_configurations relationship**
2. **Create admin routes for playoff configuration** (`routes/playoff/`)
3. **Add UI for player qualification confirmation**
4. **Integrate with notification system**

### Phase 4: Testing

1. Unit tests for PlayoffService
2. Integration tests for full playoff workflow
3. E2E tests for admin configuration and player confirmation

## Design Decisions Needed

1. **Playoff Gara Type**:
   - Add `is_playoff` boolean flag to Gara?
   - Or use naming convention / separate type?

2. **Director Assignment**:
   - Use campionato directors automatically?
   - Allow separate director assignment for playoff?

3. **Qualification Deadline**:
   - How to handle expired qualifications?
   - Auto-promote from classification or require manual intervention?

## Related Files

- `models/playoff/models.py` - Domain models (exists, needs integration)
- `models/competition/services.py` - GaraService (exists, correct signature)
- `models/competition/inscription_service.py` - InscriptionService (exists, correct signature)
- `models/playoff/services.py` - PlayoffService (to be created)
- `routes/playoff/` - Admin routes (to be created)

## References

- TODO_BACKLOG.md - Original P0 bug report (now P2 Planned Feature)
- SPECIFICHE.md - Original requirements for playoff system
