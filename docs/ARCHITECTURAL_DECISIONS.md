# Architectural Decisions Record (ADR)

**Document Version**: 1.0
**Date**: 2025-12-21
**Status**: Active

This document records key architectural decisions made during the development of the tournament management system, addressing design questions found in TODO comments throughout the codebase.

---

## Table of Contents

1. [ADR-001: Match → Gara Coupling](#adr-001-match--gara-coupling)
2. [ADR-002: Gara-Campionato Relationship](#adr-002-gara-campionato-relationship)
3. [ADR-003: Round as Match Property](#adr-003-round-as-match-property)
4. [ADR-004: Set Management in Match](#adr-004-set-management-in-match)
5. [ADR-005: Gara Number Field](#adr-005-gara-number-field)

---

## ADR-001: Match → Gara Coupling

**Location**: `models/match/models.py:474`

**TODO Question**:
```python
# TODO: perche' qui si occupa della gara? un match, dal punto di vista
# astratto non dovrebbe nemmeno sapere cos'e' una gara.
```

### Context

The `Match` model has a method `_check_and_complete_gara_if_needed()` that:
- Checks if all matches in a Gara are completed
- Automatically completes the Gara when conditions are met
- Creates a coupling between Match domain and Competition domain

### Problem

From a pure domain model perspective:
- **Match** represents an abstract game between players
- **Gara** represents a tournament/competition event
- Match shouldn't have knowledge of the competition it belongs to

This creates domain coupling that violates single responsibility principle.

### Decision: **KEEP CURRENT IMPLEMENTATION** ✅

**Rationale**:

1. **Pragmatic Trade-off**: While not ideal from pure DDD perspective, this coupling solves a real problem:
   - Automatic Gara completion happens immediately after the last match
   - No need for separate background jobs or polling
   - Simple, deterministic behavior

2. **Service Layer Alternative Too Complex**:
   - Alternative: Move logic to `MatchService.complete_match()`
   - Problem: Service would still need to know about Gara
   - Result: Same coupling, just moved to different layer

3. **Real-World Usage**:
   - In this application, Matches are ALWAYS part of either:
     - A Gara (tournament match)
     - An IndividualMatch (casual play)
   - Pure "abstract match" without context doesn't exist

4. **Performance**:
   - Current implementation is O(1) - happens during match completion
   - No additional queries or event handling needed
   - Immediate consistency

### Implementation Guidelines

✅ **Current Pattern** (Keep):
```python
class Match:
    def complete_match(self):
        # ... complete match logic ...
        self._check_and_complete_gara_if_needed(self)
```

❌ **Don't Do** (Avoid unnecessary abstraction):
```python
# Over-engineered alternative
class MatchCompletedEvent:
    pass

@event_handler(MatchCompletedEvent)
def check_gara_completion(event):
    # Adds complexity without benefit
```

### Future Considerations

If the coupling becomes problematic (e.g., introducing non-Gara match types):
1. Extract to interface: `MatchContainer` (Gara, Tournament, etc.)
2. Use dependency injection for completion logic
3. Consider event-driven approach only if needed

**Status**: RESOLVED - Current implementation is acceptable ✅

---

## ADR-002: Gara-Campionato Relationship

**Location**: `models/competition/models.py:37-39`

**TODO Question**:
```python
# TODO: è giusto che gara sappia di campionato? oppure sarebbe piu'
# corretto che fosse modellata con una relazione e fosse campionato a
# sapere di gara?
```

### Context

Current implementation:
- `Gara` has optional `campionato_id` foreign key
- `Campionato` has `@property gare` that queries Gara table
- Bidirectional knowledge: both models know about each other

### Problem

Two possible relationship directions:
1. **Current**: Gara → Campionato (Gara knows parent)
2. **Alternative**: Campionato → Gara (Campionato owns children)

### Decision: **KEEP CURRENT IMPLEMENTATION** ✅

**Rationale**:

1. **Query Efficiency**:
   ```python
   # Current (efficient)
   gara = Gara.query.get(id)
   campionato = gara.campionato  # Single query via FK

   # Alternative (requires join or N+1)
   gara = Gara.query.get(id)
   campionato = Campionato.query.join(...).filter(...).first()
   ```

2. **Standalone Gare Support**:
   - `campionato_id` can be NULL (standalone gara)
   - Clean distinction: `if gara.campionato_id` vs separate table
   - Natural representation of optional relationship

3. **Real-World Semantics**:
   - A gara "belongs to" a campionato (or is standalone)
   - Natural to ask: "Which campionato is this gara part of?"
   - Less natural to ask: "Which gare belong to this campionato?" (that's aggregation)

4. **Database Normalization**:
   - FK in Gara table is normalized form
   - Avoids many-to-many junction table for one-to-many relationship

### Implementation Pattern

✅ **Current Pattern** (Keep):
```python
class Gara:
    campionato_id = db.Column(db.Integer, db.ForeignKey('campionato.id'))
    campionato = db.relationship('Campionato', back_populates='gare')

class Campionato:
    @property
    def gare(self):
        return Gara.query.filter_by(campionato_id=self.id).all()
```

### Why Property Instead of Relationship?

The TODO at line 151 mentions:
```python
# TODO: da rivedere se si cambia il modello ed e' Campionato l'unico a
# sapere delle sue gare
```

**Decision**: Keep as `@property` for now because:
- Explicit querying gives control over ordering, filtering
- Can add `.order_by(Gara.number)` easily
- Avoids SQLAlchemy lazy loading issues
- Clear intent: "fetch all related gare"

**Status**: RESOLVED - Current implementation is correct ✅

---

## ADR-003: Round as Match Property

**Location**: `models/match/models.py:29`

**TODO Question**:
```python
# TODO: non sono sicuro che round_number sia una proprieta' di Match e
# che Match debba sapere qual e' il suo round. da verificare il modello
```

### Context

Current implementation:
- `Match` has `round_number` field (1, 2, 3, ...)
- Indicates which round of the tournament this match belongs to
- Used for matchmaking, progression, and display

### Problem

Should Round be:
1. **Current**: Simple integer field on Match
2. **Alternative**: First-class entity (Round model with relationships)

### Decision: **KEEP AS INTEGER FIELD** ✅

**Rationale**:

1. **YAGNI Principle** (You Aren't Gonna Need It):
   - Current needs: Just track which round (1, 2, 3)
   - No additional Round-level data needed
   - No Round-specific behavior or business logic

2. **Simplicity**:
   ```python
   # Current (simple)
   round_1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1)

   # Alternative (complex)
   round = Round.query.filter_by(gara_id=gara.id, number=1).first()
   matches = round.matches  # Extra model, extra queries
   ```

3. **No Round-Level State**:
   - Rounds don't have status (started/completed) - Gara does
   - Rounds don't have settings - Gara does
   - Round is just a grouping mechanism

4. **Query Performance**:
   - Integer field: indexed, fast filtering
   - Separate table: requires join

### When to Introduce Round Entity?

Consider if you need:
- ❌ Round-specific settings (different rules per round) - **Not needed**
- ❌ Round-level state machine - **Not needed**
- ❌ Round-level data (start_time, end_time) - **Tracked at Gara level**
- ❌ Complex round progression logic - **Handled by MatchmakingService**

Currently: **None of these apply**

### Implementation

✅ **Current Pattern** (Keep):
```python
class Match:
    round_number = db.Column(db.Integer)  # Simple, effective
```

❌ **Avoid Premature Abstraction**:
```python
class Round:
    # Don't create until actually needed
    gara_id = ...
    number = ...
    matches = relationship(...)
```

**Status**: RESOLVED - Integer field is sufficient ✅

---

## ADR-004: Set Management in Match

**Location**: `models/match/models.py:236`

**TODO Question**:
```python
# TODO: non sono sicuro che la gestione dei set vada fatta in Match.
# da verificare la progettazione dell'Abstract data type
```

### Context

Current implementation:
- `Match` has `is_multi_set` flag
- `Match` manages Set creation via `get_or_create_set()`
- `Set` model exists as separate entity

### Problem

Should Set management be:
1. **Current**: Match creates and manages Sets
2. **Alternative**: Separate SetService handles Set lifecycle

### Decision: **KEEP IN MATCH** ✅

**Rationale**:

1. **Aggregate Root Pattern**:
   - In DDD terms, Match is the "Aggregate Root"
   - Sets are "Entities" within the Match aggregate
   - Aggregate root controls child entities

2. **Transactional Boundary**:
   - Set lifecycle is tied to Match lifecycle
   - Creating/deleting Match should cascade to Sets
   - Natural transaction boundary

3. **Encapsulation**:
   ```python
   # Good: Match controls its internal structure
   current_set = match.get_or_create_set(set_number)

   # Bad: External service manages Match internals
   current_set = SetService.get_or_create_for_match(match, set_number)
   ```

4. **No Independent Set Operations**:
   - Sets don't exist independently of Match
   - No "find all sets" or "transfer set to different match" use cases
   - Pure composition relationship

### Implementation Pattern

✅ **Current Pattern** (Keep):
```python
class Match:
    @property
    def sets(self):
        return Set.query.filter_by(match_id=self.id).all()

    def get_or_create_set(self, set_number):
        # Match manages its own Sets
```

### Comparison to Real World

This is like:
- ✅ Book manages its Chapters (aggregate)
- ✅ Order manages its OrderItems (aggregate)
- ✅ Match manages its Sets (aggregate)

Not like:
- ❌ School has Students (separate entities)
- ❌ Library has Books (separate entities)

**Status**: RESOLVED - Current design follows DDD aggregate pattern ✅

---

## ADR-005: Gara Number Field

**Location**: `models/competition/models.py:48`

**TODO Question**:
```python
# TODO: number è informazione relativa a Campionato e non a gara
```

### Context

Current implementation:
- `Gara` has `number` field (1, 2, 3, ...)
- Represents sequence number within a Campionato
- Used for ordering and display

### Problem

The number field represents:
- Gara's position in Campionato sequence (1st gara, 2nd gara, ...)
- This is contextual information that only makes sense within a Campionato
- Standalone gare (campionato_id=NULL) have meaningless numbers

### Decision: **KEEP ON GARA, ADD VALIDATION** ✅

**Rationale**:

1. **Practical Display Needs**:
   ```python
   # Common UI pattern
   "Gara #{{ gara.number }} - {{ gara.name }}"
   ```

2. **Query Convenience**:
   ```python
   # Easy to sort
   gare = Gara.query.filter_by(campionato_id=id).order_by(Gara.number)

   # Alternative requires join
   gare = db.session.query(Gara, CampionatoGara.sequence)...
   ```

3. **Database Perspective**:
   - Number is an attribute of Gara within context
   - Like "employee_number" in Employee table
   - Contextual but still belongs to entity

### Improvement: Add Validation

```python
class Gara:
    def clean(self):
        # Validate: standalone gare don't need meaningful numbers
        if self.campionato_id is None:
            self.number = self.number or 1  # Default for standalone
```

### Implementation

✅ **Current Pattern** (Keep with validation):
```python
class Gara:
    number = db.Column(db.Integer, nullable=False)
    campionato_id = db.Column(db.Integer, nullable=True)
```

**Status**: RESOLVED - Keep field, add validation for standalone gare ✅

---

## Summary of Decisions

| ADR | Question | Decision | Rationale |
|-----|----------|----------|-----------|
| 001 | Match → Gara coupling | Keep ✅ | Pragmatic, simple, performant |
| 002 | Gara → Campionato direction | Keep ✅ | Natural FK, efficient queries |
| 003 | Round as entity | Keep as int ✅ | YAGNI, simple, sufficient |
| 004 | Set management in Match | Keep ✅ | DDD Aggregate pattern |
| 005 | Gara number field | Keep ✅ | Practical, add validation |

## General Principles Applied

1. **Pragmatism over Purity**: Choose practical solutions that work
2. **YAGNI**: Don't create abstractions until needed
3. **DDD Patterns**: Follow aggregate root pattern where appropriate
4. **Performance**: Consider query efficiency in decisions
5. **Simplicity**: Prefer simple solutions that are easy to understand

---

## Future Review

These decisions should be revisited if:
- ❌ Requirements change significantly
- ❌ New use cases emerge that don't fit current model
- ❌ Performance problems arise from current design
- ❌ Domain complexity increases substantially

**Last Reviewed**: 2025-12-21
**Next Review**: When requirements change or new use cases emerge
