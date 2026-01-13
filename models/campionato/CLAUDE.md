# Campionato Domain

## Purpose

Tournament container that groups multiple competitions (Gare) under unified configuration and classification.

**Core Responsibilities:**
- Tournament lifecycle management
- Default configuration inheritance for Gare
- Director assignment management
- Aggregated classification across Gare

---

## Quick Reference

```python
from models.campionato.models import Campionato
from models.campionato.services import TournamentService
from models.matchmaking.configuration import MatchmakingStrategy, OddNumberPolicy

service = TournamentService()

# Create campionato with director
campionato = service.create_campionato_with_director(
    name="Campionato Autunno 2025",
    creator_user_id=director.id,
    campionato_type=MatchmakingStrategy.AMALFI.value,
    planned_gare_count=10,
    default_rounds_count=3,
    default_odd_policy=OddNumberPolicy.BYE.value
)

# Get computed status
status = service.get_campionato_status(campionato.id)
# Returns: TournamentStatus (NOT_STARTED, IN_PROGRESS, COMPLETED)

# Add/remove directors
service.add_director(campionato.id, user_id, assigned_by_id)
service.remove_director(campionato.id, user_id)
```

---

## Key Model: Campionato

**Configuration Fields:**
- `campionato_type`: Matchmaking strategy (amalfi, random, etc.)
- `challenge_mode`: Enable challenge drill mode
- `planned_gare_count`: Target number of gare

**Default Values (inherited by Gare):**
- `default_venue_id`, `default_entry_fee`
- `default_rounds_count`, `default_odd_policy`, `default_anti_rematch`

**Computed Properties:**
- `directors`: List of assigned directors (via DirectorAssignment)
- `gare`: Related Gara objects (cascade delete)

**Deprecated Fields** (do not use):
- `without_x` → use `default_odd_policy`
- `final_playoffs` → use PlayoffConfiguration
- `scoring_policy` → automatic from `campionato_type`

---

## Services

### TournamentService

**Creation:**
- `create_campionato(name, **kwargs)` - Basic creation
- `create_campionato_with_director(...)` - Full wizard creation

**Status:**
- `get_campionato_status(id)` - Computed status based on gare states
- `get_campionato_progress(id)` - Progress metrics

**Directors:**
- `add_director(campionato_id, user_id, assigned_by_id)`
- `remove_director(campionato_id, user_id)`

**Lifecycle:**
- `soft_delete_campionato(id, reason)` - Soft delete with cascade options

---

## Status Computation

Status is computed from Gare states, not stored:

```
NOT_STARTED: All gare in setup/inscription
IN_PROGRESS: At least one gara playing, not all completed
COMPLETED: All gare completed
```

---

## Do Not

- **Do not use deprecated fields** - `without_x`, `final_playoffs`, `scoring_policy` are deprecated
- **Do not access `directors` as relationship** - It's a computed property, not modifiable
- **Do not store status** - Use `get_campionato_status()` for computed status
- **Do not call `db.session.commit()`** - Services use `@transactional`
- **Do not use string literals** - Use `MatchmakingStrategy.AMALFI.value`

---

## Cross-References

- **Competition**: [../competition/CLAUDE.md](../competition/CLAUDE.md) - Gare belong to Campionato
- **Classification**: [../classification/](../classification/) - Aggregated rankings
- **User**: [../user/](../user/) - DirectorAssignment
