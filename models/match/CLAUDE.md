# Match Domain Documentation

## Purpose

The Match domain handles the execution and scoring of individual matches within competitions. It supports both single-rack matches and complex multi-set matches with multiple disciplines.

**Core Responsibilities:**
- Match lifecycle management (pending → playing → completed)
- Rack-level scoring for single matches
- Multi-set match support with Set/SetRack models
- Trio match support (3-player matches)
- Match result validation and state transitions
- Handicap system integration

**Related Domains:**
- See [../competition/CLAUDE.md](../competition/CLAUDE.md) for competition rounds
- See [../matchmaking/CLAUDE.md](../matchmaking/CLAUDE.md) for player pairing
- See [../classification/CLAUDE.md](../classification/CLAUDE.md) for rankings
- See [../rating/](../rating/) for handicap calculations

---

## Quick Reference

### Most-Used Classes

```python
from models.match.models import Match, Rack, TrioMatch, TrioRack
from models.match.set_models import Set, SetRack
from models.match.services import MatchService, RackService
from models.match.trio_config import TrioConfig
from models.status_enum import MatchStatus

# Create match
match = MatchService.create_match(
    gara_id=gara.id,
    round_number=1,
    player1_id=10,
    player2_id=20
)

# Add rack
rack = RackService.add_rack(
    match_id=match.id,
    winner_id=10,
    discipline="palla_8"
)

# Complete match
MatchService.to_completed(match.id)
```

---

## Key Classes

### Match Model (`models.py`)

**Purpose**: Core match entity representing a game between players.

**Critical Fields:**
```python
# Identity
id: int (PK)
gara_id: int (FK, cascade delete)
round_number: int

# Players
player1_id: int (FK to user.id)
player2_id: int (FK to user.id)
is_bye: bool - default False
is_trio: bool - default False

# Scores (Meaning depends on match type)
player1_score: int - default 0  # Racks won (legacy) OR Sets won (multi-set)
player2_score: int - default 0  # Racks won (legacy) OR Sets won (multi-set)
winner_id: int (FK to user.id)

# Multi-Set Configuration
match_distance: int - default 1  # Sets to win
is_multi_set: bool - default False
current_set_number: int - default 1

# Status
status: str(20) - default "pending" (use MatchStatus enum)
is_locked: bool - default False
round_locked: bool - default False

# Discipline Override
discipline: str(50) - nullable (override gara discipline)

# Handicap System
has_handicap: bool - default False
player1_handicap: int - default 0
player2_handicap: int - default 0
handicap_rule_id: int (FK, nullable)
handicap_explanation: str(255)
```

**Key Methods:**
```python
is_completed() -> bool
    # True if status == "completed"

get_effective_discipline() -> str
    # Returns discipline override or gara default

# Multi-Set Methods (proxy to SetLifecycleService)
start_next_set() -> Set
    # Start next set in multi-set match

get_current_set() -> Optional[Set]
    # Get current set being played

complete_set(set_number: int, winner_id: int) -> None
    # Complete a set and check if match finished
```

**Usage Examples:**
```python
# Single-rack match
match = Match(
    gara_id=gara.id,
    round_number=1,
    player1_id=10,
    player2_id=20
)

# Multi-set match
match = Match(
    gara_id=gara.id,
    round_number=1,
    player1_id=10,
    player2_id=20,
    is_multi_set=True,
    match_distance=3  # Best of 5 sets
)

# Check completion
if match.is_completed():
    print(f"Winner: {match.winner_id}")
```

---

### Set Model (`set_models.py`)

**Purpose**: Represents a single set within a multi-set match.

**Critical Fields:**
```python
id: int (PK)
match_id: int (FK to match.id, cascade delete)
set_number: int

# Scoring Configuration
distance: int - default 5 (racks to win)
best_of: bool - default True

# Current Scores
player1_racks: int - default 0
player2_racks: int - default 0

# Status
status: str(20) - default "pending"
winner_id: int (FK to user.id, nullable)
started_at: datetime
completed_at: datetime

# Multi-Discipline Support
discipline: str(50) - nullable
is_multi_discipline: bool - default False
discipline_rotation: JSON - list of disciplines
discipline_assignment: JSON - rack->discipline mapping
```

**Key Methods:**
```python
can_be_modified() -> bool
    # True if status == "playing"

add_rack_result(winner_id: int, rack_number: int = None, discipline_override: str = None) -> SetRack
    # Add rack result to set

is_completed() -> bool
    # Check if set is finished

get_score_summary() -> Dict[str, Any]
    # Returns current scores and winner

# Multi-Discipline Methods
configure_multi_discipline(disciplines: List[str], mode: str = "rotation") -> None
    # Configure multi-discipline mode

set_discipline_assignment(rack_disciplines: Dict[int, str]) -> None
    # Set specific rack->discipline mapping

get_discipline_for_rack(rack_number: int) -> str
    # Get discipline for specific rack
```

---

### MatchService (`services.py`)

**Purpose**: Business logic and state machine for matches.

**Key Methods:**

```python
@transactional
def create_match(
    gara_id: int,
    round_number: int,
    player1_id: int,
    player2_id: Optional[int] = None,
    is_bye: bool = False
) -> Match:
    """Create a match with pending status."""

# State Machine
@transactional
def to_playing(match_id: int) -> Match:
    """Transition pending → playing"""

@transactional
def to_completed(match_id: int) -> Match:
    """Transition playing → completed

    Also records PlayerEncounter for anti-rematch logic.
    """

def reset_to_pending(match_id: int, clear_validation: bool = True) -> OperationResult:
    """Reset match to pending (clears racks)

    NOTE: NOT decorated with @transactional due to custom
    transaction management with OperationResult pattern.
    """

# Trio Match Support
@transactional
def create_trio_match(match_id: int, player3_id: int) -> TrioMatch:
    """Create trio match entity."""
```

**State Machine:**
```
pending ──→ playing ──→ completed
  ↑           ↓
  └───────────┘ (admin reset)
```

---

### RackService (`services.py`)

**Purpose**: Rack-level scoring management.

**Key Methods:**
```python
@transactional
def add_rack(
    match_id: int,
    winner_id: int,
    discipline: Optional[str] = None
) -> Rack:
    """Add rack to match and update scores.

    Automatically transitions match to playing if pending.
    Completes match if winning score reached.
    """

@transactional
def remove_rack(rack_id: int) -> bool:
    """Remove rack and update match scores.

    Reopens match to playing if was completed.
    Returns True if removed, False if not found.
    """

@transactional
def reset_match_complete(match_id: int) -> None:
    """Remove all racks from match and reset to pending."""
```

---

### TrioMatch Model (`models.py`)

**Purpose**: Represents a 3-player match using round-robin format.

**Critical Fields:**
```python
id: int (PK)
match_id: int (FK to match.id, unique)
player1_id: int (FK to user.id)
player2_id: int (FK to user.id)
player3_id: int (FK to user.id)

# Current matchup (who is playing, who waits)
current_player1_id: int (FK to user.id)
current_player2_id: int (FK to user.id)
waiting_player_id: int (FK to user.id)

# Completion state
is_completed: bool - default False
bonus_applied: bool - default False
winner_id: int (FK to user.id, nullable)
```

**Computed Properties (from TrioRack records):**
```python
@property
def player1_racks(self) -> int
@property
def player2_racks(self) -> int
@property
def player3_racks(self) -> int
@property
def total_racks_played(self) -> int
@property
def current_round(self) -> int
@property
def current_rack_in_round(self) -> int
@property
def last_rack(self) -> Optional[TrioRack]
```

**Key Methods:**
```python
# NOTE: add_rack_win(), remove_last_rack(), reset() moved to TrioScoringService

def get_current_state() -> dict
    # UI state dict (proxy to TrioStateSerializer.serialize)

def confirm_result_by_player(user_id: int) -> dict
    # Player confirms trio result (all 3 needed)

def confirm_result_by_admin() -> dict
    # Admin confirms trio result (bypasses player confirmations)

def handle_forfeit(forfeiting_player_id: int, added_by_id: int = None) -> bool
    # Handle player forfeit

def initialize_matchup() -> None
    # Set up initial matchup (P1 vs P2, P3 waits)

@property
def trio_config(self) -> TrioConfig
    # Get round-robin configuration based on gara distance
```

---

### TrioRack Model (`models.py`)

**Purpose**: Individual rack record for trio matches. Enables undo functionality.

**Critical Fields:**
```python
id: int (PK)
trio_match_id: int (FK to trio_match.id, cascade delete)
rack_number: int
winner_id: int (FK to user.id)

# Matchup snapshot
player1_id: int (FK to user.id)
player2_id: int (FK to user.id)
waiting_player_id: int (FK to user.id)

# Audit
added_by_id: int (FK to user.id)
created_at: datetime

# Soft delete for undo
is_deleted: bool - default False
removed_by_id: int (FK to user.id, nullable)
removed_at: datetime (nullable)
```

**Design Pattern:**
- Follows `Rack` model OO pattern
- Counters are **computed properties** from active records
- Soft delete enables undo without losing history
- Only last rack can be removed (round-robin sequence is fixed)

---

## Common Patterns

### Single-Rack Match Workflow

```python
from models.match.services import MatchService, RackService

# 1. Create match (done by RoundService)
match = MatchService.create_match(
    gara_id=gara.id,
    round_number=1,
    player1_id=10,
    player2_id=20
)

# 2. Add racks as they are played
rack1 = RackService.add_rack(match.id, winner_id=10)  # Player 1 wins rack
rack2 = RackService.add_rack(match.id, winner_id=20)  # Player 2 wins rack
rack3 = RackService.add_rack(match.id, winner_id=10)  # Player 1 wins rack
# ...

# 3. Match auto-completes when winning score reached
# If distance=5 and best_of=True, winning score = 3
# After 3rd rack won by player 1, match is completed
```

### Multi-Set Match Workflow

```python
from models.match.services import MatchService
from models.match.set_models import Set

# 1. Create multi-set match
match = Match(
    gara_id=gara.id,
    round_number=1,
    player1_id=10,
    player2_id=20,
    is_multi_set=True,
    match_distance=3  # Best of 5 sets (first to 3)
)
db.session.add(match)
db.session.commit()

# 2. Create first set
set1 = Set(match_id=match.id, set_number=1, distance=5, best_of=True)
db.session.add(set1)
db.session.commit()

# 3. Add racks to current set
set1.add_rack_result(winner_id=10)  # Rack 1
set1.add_rack_result(winner_id=20)  # Rack 2
set1.add_rack_result(winner_id=10)  # Rack 3
# ...

# 4. When set completes, it updates match scores
if set1.is_completed():
    match.complete_set(set1.set_number, set1.winner_id)

# 5. Start next set if match not finished
if not match.is_completed():
    set2 = match.start_next_set()
    # Continue with set2...
```

---

## Important Notes

### Score Interpretation

**CRITICAL**: `player1_score` and `player2_score` meaning depends on match type:
- **Single-rack match** (`is_multi_set=False`): Scores = racks won
- **Multi-set match** (`is_multi_set=True`): Scores = sets won

### State Transitions

**Match Status:**
- `PENDING`: Match created, no racks yet
- `PLAYING`: At least one rack added
- `COMPLETED`: Winning score reached or admin marked complete

**Auto-Transitions:**
- `add_rack()`: pending → playing (first rack)
- `add_rack()`: playing → completed (winning score reached)
- `remove_rack()`: completed → playing (if score no longer winning)

### Anti-Rematch Integration

When `MatchService.to_completed()` is called, it automatically records a `PlayerEncounter` for anti-rematch logic in future rounds.

### Standalone Matches (Match Individuali)

Matches can exist without a gara (`gara_id = NULL`) in two scenarios:
1. **Soft delete with keep_matches**: When a gara/campionato is soft deleted with "Mantieni match" option
2. **Future**: Individual matches proposed outside tournaments

**Handling in Code:**
```python
# Distance value object handles null gara
distance = Distance.from_match(match)  # Works even if match.gara is None
# Uses defaults: racks=5, is_race_to=True

# Check for standalone match
if match.gara_id is None:
    # This is a standalone "Match Individuale"
    # Use match.created_at for date
    # Use match.discipline for discipline
```

**Templates must check `match.gara` before accessing:**
```jinja2
{% if match.gara %}
    {{ match.gara.discipline }}
{% else %}
    {{ match.discipline|replace('_', ' ')|title }}
{% endif %}
```

---

## Do Not

- **Do not interpret scores without checking `is_multi_set`** - Scores are racks (single) or sets (multi-set)
- **Do not call `db.session.commit()`** - Use `@transactional` in services
- **Do not access `match.gara` without null check** - Standalone matches have `gara_id=NULL`
- **Do not forget `@transactional` on `reset_to_pending`** - Uses custom transaction with OperationResult
- **Do not manually complete matches** - Use `RackService.add_rack()` which auto-completes

---

## Cross-References

- **Competition**: [../competition/CLAUDE.md](../competition/CLAUDE.md)
- **Matchmaking**: [../matchmaking/CLAUDE.md](../matchmaking/CLAUDE.md)
- **Classification**: [../classification/CLAUDE.md](../classification/CLAUDE.md)
- **Root**: [../CLAUDE.md](../CLAUDE.md)
