# Competition Domain

## Purpose

Manages individual competition rounds (Gara) within tournaments or as standalone events.

**Core Responsibilities:**
- Gara lifecycle management (setup → inscription → playing → completed)
- Player inscription and waitlist management
- Round creation and progression
- Advanced round management with locking mechanisms

**Related Domains:** [matchmaking/](../matchmaking/) for pairing, [match/](../match/) for scoring, [campionato/](../campionato/) for multi-gara tournaments.

---

## Quick Reference

```python
from models.competition.models import Gara, Inscription
from models.competition.services import GaraService
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.state_service import StateService
from models.competition.round_manager import AdvancedRoundManager
from models.status_enum import GaraStatus

# Create gara
gara = GaraService.create_gara(
    number=1, name="Prova 1", date=date(2025, 10, 15),
    discipline="palla_8", distance=5,
    campionato_id=campionato.id,  # or None + director_id for standalone
    time=time(18, 0), rounds_count=3, min_participants=6
)

# Open inscriptions
gara = InscriptionService.open_inscriptions(
    gara_id=gara.id,
    inscription_start=datetime.now(),
    inscription_end=datetime.now() + timedelta(days=7)
)

# Inscribe player (auto-waitlist if full)
inscription = InscriptionService.inscribe_user(user_id=user.id, gara_id=gara.id)

# Start first round
gara = RoundService.start_first_round(gara_id=gara.id)

# Create next round
counts = RoundService.create_round_with_strategy(gara_id=gara.id, round_number=2)
# Returns: (total, normal, bye, trio)

# Check round lock status
from models.competition.round_manager import RoundLockStatus
lock = AdvancedRoundManager.get_round_lock_status(gara.id, round_number=2)
if lock == RoundLockStatus.LOCKED:
    # Cannot modify - subsequent round exists
```

---

## Key Models

### Gara
**Key Fields:** `campionato_id` (nullable for standalone), `director_id`, `status`, `date`, `time`, `discipline`, `distance`, `best_of`, `rounds_count`, `current_round`, `min_participants`, `max_participants`, `matchmaking_strategy`, `withdraw_policy`

**Status Values:** `setup`, `inscription`, `playing`, `completed`

**Key Methods:**
- `get_real_status()` - Actual status (considers round completion, inscription expiry)
- `can_start_new_round()` - All current matches completed?
- `can_inscribe()` - In inscription period?
- `is_full()` / `has_waitlist()` - Capacity checks
- `validate_strategy_configuration()` - Validate matchmaking config

### Inscription
**Key Fields:** `user_id`, `gara_id`, `is_withdrawn`, `is_forfeit`, `is_waitlist`, `waitlist_position`, `initial_order`

---

## Services

### GaraService (Facade)
- `create_gara(...)`, `update_gara(...)`, `delete_gara(...)`
- `soft_delete_gara(gara_id, cascade_option)` - "delete_all" or "keep_matches"
- `add_director(...)`, `remove_director(...)`

### InscriptionService
- `inscribe_user(...)` - Auto-waitlist if full
- `uninscribe_user(...)` - Promotes first waitlist
- `admin_uninscribe_user(...)` - With notification
- `open_inscriptions(...)`, `modify_inscription_dates(...)`

### RoundService
- `start_first_round(...)` - Shuffles inscriptions, creates first round
- `create_round_with_strategy(...)` - Idempotent, locks previous round
- `cancel_first_round_startup(...)` - Return to inscription state

### StateService
- `to_inscription(gara)` - setup → inscription
- `reopen_setup(gara)` - inscription → setup
- `start_playing(gara)` - inscription → playing
- `complete(gara)` - playing → completed

### AdvancedRoundManager
- `get_round_lock_status(gara_id, round_number)` - LOCKED/UNLOCKED
- `can_modify_match(match_id)` - Returns (bool, reason)
- `reset_match_with_validation(match_id)` - Respects locking
- `cancel_round(gara_id, round_number)` - Delete round matches

---

## Do Not

- **Do not use `status` directly for UI** - Use `get_real_status()` which considers round completion
- **Do not forget director requirement** - Standalone gara needs `director_id`, campionato gara inherits directors
- **Do not assume idempotency fails** - `create_round_with_strategy()` returns counts if round exists
- **Do not call `db.session.commit()`** - All services use `@transactional`
- **Do not hard-delete inscriptions** - Use soft delete/withdraw mechanisms
- **Do not modify locked rounds** - Check `get_round_lock_status()` first
- **Do not confuse Random strategy** - Creates ALL rounds at startup, others create one at a time

---

## State Machine

```
setup ──→ inscription ──→ playing ──→ completed
         ↑           ↓
         └───────────┘
```

---

## Cross-References

- **Matchmaking**: [../matchmaking/](../matchmaking/) - Pairing strategies (Amalfi, Round-Robin, Elimination)
- **Match Execution**: [../match/](../match/) - Match and scoring
- **Classification**: [../classification/](../classification/) - Rankings
