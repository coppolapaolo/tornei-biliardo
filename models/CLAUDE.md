# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Models Directory - Domain Models

Domain models for the American Pool community platform using Domain-Driven Design principles.

---

## Critical Conventions

### Enum Comparisons (CRITICAL)

**Always use `.value` when comparing status fields:**

```python
from models.status_enum import GaraStatus, MatchStatus

# ✅ Correct
if gara.status == GaraStatus.PLAYING.value:
if match.status == MatchStatus.COMPLETED.value:

# ❌ Wrong - compares to enum object, not string
if gara.status == GaraStatus.PLAYING:
```

### Transaction Management

**All service methods that modify state MUST use `@transactional`:**

```python
from models.transaction.manager import transactional

@transactional
def create_inscription(gara_id: int, user_id: int) -> Inscription:
    inscription = Inscription(gara_id=gara_id, user_id=user_id)
    db.session.add(inscription)
    return inscription  # Commit happens automatically
```

### Soft Delete (User Model)

```python
# ✅ Correct - filter out deleted users
active_users = User.query.filter_by(is_deleted=False).all()

# ✅ Soft delete preserves relationships
user.anonymize()

# ❌ Wrong - breaks foreign key relationships
db.session.delete(user)
```

### Soft Delete + UNIQUE Constraints

When calculating sequential IDs (like `rack_number`) with a UNIQUE constraint, **include deleted records**:

```python
# ❌ WRONG - Causes UNIQUE constraint violation after soft-delete
max_num = db.session.query(func.max(Rack.rack_number)) \
    .filter_by(match_id=match_id, is_deleted=False).scalar()
next_num = (max_num or 0) + 1  # If deleted racks 1-4 exist, returns 1 → CONFLICT!

# ✅ CORRECT - Include ALL records for sequential IDs
max_num = db.session.query(func.max(Rack.rack_number)) \
    .filter_by(match_id=match_id).scalar()  # No is_deleted filter
next_num = (max_num or 0) + 1  # Returns 5 after deleted racks 1-4
```

**Rule**: UNIQUE constraints apply to ALL rows (active + deleted). Always include deleted records when calculating the next sequential ID.

### "Race to N" Terminology

The application uses **"Race to N"** (Italian: "Al N"), NOT "Best of N":

```python
# ✅ Correct - Race to 5 means first to WIN 5 racks
gara.distance = 5  # First to 5 racks wins
# Maximum possible racks = (2 × 5) - 1 = 9

# ❌ Wrong - This means "race to 9", not "best of 9"
gara.distance = 9
```

### Distance VO obbligatorio per scoring (ADR-027)

`Match` espone `is_race_to`, `match_distance`, `is_race_to_sets` come
override per turno (NULL = eredita da gara). Le property `effective_*` e
`distance_config` materializzano i fallback. **Non leggere mai
`match.gara.distance` o `match.gara.is_race_to` direttamente**: gli override
per turno verrebbero persi.

```python
# ✅ Correct
distance = match.distance_config
if distance.is_race_to_racks:
    winning = distance.get_winning_racks()

# ❌ Wrong - bypassa override per turno
if match.gara.is_race_to:
    winning = match.gara.distance_config.get_winning_racks()
```

Vedi `docs/adr/ADR-027-round-level-configuration-enforcement.md`.

---

## Domain Architecture

### Core Domains

| Domain | Purpose | Key Models |
|--------|---------|------------|
| `user/` | Users, roles, permissions | User, DirectorAssignment, VenueManagement |
| `competition/` | Gara, inscriptions | Gara, Inscription |
| `match/` | Match execution, scoring | Match, Set, Rack, TrioMatch, TrioRack |
| `matchmaking/` | Pairing strategies | AmalfiStrategy, RoundRobinStrategy, etc. |
| `campionato/` | Tournament container | Campionato |
| `classification/` | Rankings | Classification, RoundClassification |
| `gamification/` | XP, achievements, streaks | LevelService, StreakService |

### Key Relationships

**Gara vs Campionato:**
- `Gara`: Single competition - can be standalone (`campionato_id = None`) or part of campionato
- `Campionato`: Tournament containing multiple gare

**Match Scores:**
```python
if match.is_multi_set:
    # player1_score/player2_score = SETS won
else:
    # player1_score/player2_score = RACKS won
```

---

## Common Gotchas

### Filtering Active Inscriptions

```python
# ❌ Common error - forgetting to filter
count = len(gara.inscriptions)

# ✅ Correct - filter withdrawn and waitlist
active = Inscription.query.filter_by(
    gara_id=gara.id,
    is_withdrawn=False,
    is_waitlist=False
).count()
```

### Computed Properties vs Relationships

```python
# directors is a PROPERTY, not a relationship
directors = gara.directors  # Queries DirectorAssignment table

# ❌ Wrong - can't modify like a relationship
gara.directors.append(user)  # This will fail
```

### Standalone Gara Check

```python
# ✅ Check before accessing campionato
if gara.campionato_id:
    name = gara.campionato.name
else:
    name = gara.name  # Standalone

# Or use property
if gara.is_standalone:
    # Handle standalone
```

### Role Properties

```python
# These are PROPERTIES, not fields
user.is_admin      # True if role == "admin"
user.is_director   # True if role == "director"
user.is_player     # True if role == "player"

# ❌ Wrong - can't set directly
user.is_admin = True  # This won't work
```

---

## Infrastructure

### Event System

```python
from models.events.base import DomainEvent, EventType

DomainEvent.emit(
    event_type=EventType.INSCRIPTION_CREATED,
    entity_id=inscription.id,
    actor_id=user_id
)
```

### Matchmaking Strategies

```python
from models.matchmaking.service import MatchmakingService
from models.matchmaking.config import MatchmakingStrategy

service = MatchmakingService(gara_id=gara.id, strategy=MatchmakingStrategy.AMALFI)
matches = service.create_next_round()
```

### Base Classes

- `BaseModel`: Business entities with timestamps
- `SimpleModel`: Utility methods only
- `SoftDeleteMixin`: Soft delete support
- `TimestampMixin`: created_at/updated_at

---

## Do Not

- **Do not compare enums without `.value`** - Database stores strings, not enum objects
- **Do not call `db.session.commit()` in services** - Use `@transactional` decorator
- **Do not hard-delete User records** - Use `user.anonymize()` for GDPR compliance
- **Do not modify computed properties** - `gara.directors`, `user.is_admin` are read-only
- **Do not confuse `distance` semantics** - "Race to N" means first to WIN N racks

---

## Subdomain Documentation

For detailed domain-specific documentation, see:
- `models/competition/CLAUDE.md` - Gara, Inscription services
- `models/matchmaking/CLAUDE.md` - Pairing strategies
- `models/match/CLAUDE.md` - Match, Set, Rack models
- `models/user/CLAUDE.md` - User, roles, permissions
- `models/gamification/CLAUDE.md` - XP, levels, achievements
