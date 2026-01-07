# Competition Domain Documentation

## Purpose

The Competition domain manages individual competition rounds (Gara) within tournaments or as standalone events. It handles the complete lifecycle of competitions from setup through inscription to match execution and completion.

**Core Responsibilities:**
- Competition (Gara) lifecycle management
- Player inscription and waitlist management
- Round creation and progression
- State transitions (setup → inscription → playing → completed)
- Advanced round management with locking mechanisms

**Related Domains:**
- See [../matchmaking/CLAUDE.md](../matchmaking/CLAUDE.md) for pairing strategies
- See [../match/CLAUDE.md](../match/CLAUDE.md) for match execution
- See [../campionato/](../campionato/) for multi-competition tournaments
- See [../classification/CLAUDE.md](../classification/CLAUDE.md) for rankings

---

## Quick Reference

### Most-Used Classes

```python
from models.competition.models import Gara, Inscription
from models.competition.services import GaraService
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.state_service import StateService
from models.competition.round_manager import AdvancedRoundManager
from models.competition.withdraw_policy_service import WithdrawPolicyService

# Quick Status Check
from models.status_enum import GaraStatus
if gara.status == GaraStatus.PLAYING.value:
    # Competition is in progress
```

### Common Operations

```python
# Create a competition
gara = GaraService.create_gara(
    number=1,
    name="Prova 1",
    date=datetime.date(2025, 10, 15),
    discipline="palla_8",
    distance=5,
    campionato_id=campionato.id,  # or None for standalone
    time=datetime.time(18, 0),
    rounds_count=3,
    min_participants=6,
    matchmaking_strategy="amalfi"
)

# Inscribe a player
inscription = InscriptionService.inscribe_user(user_id=user.id, gara_id=gara.id)

# Open inscriptions
gara = InscriptionService.open_inscriptions(
    gara_id=gara.id,
    inscription_start=datetime.now(),
    inscription_end=datetime.now() + timedelta(days=7)
)

# Start first round
gara = RoundService.start_first_round(gara_id=gara.id)

# Create next round (for Amalfi and other strategies)
RoundService.create_round_with_strategy(gara_id=gara.id, round_number=2)
```

---

## Key Classes

### Gara Model (`models.py`)

**File**: `models/competition/models.py`

**Purpose**: Represents a single competition round within a tournament or standalone event.

**Database Fields:**
```python
# Identity
id: int (PK)
campionato_id: int (FK, nullable) - None for standalone
director_id: int (FK to user.id, nullable) - for standalone only
number: int - position in campionato (1-10)
name: str(100)
date: date - not null
time: time - nullable but required

# Location & Description
location: str(200)
description: text

# Configuration
rounds_count: int - default 3
min_participants: int - default 6
max_participants: int - nullable
entry_fee: float - default 0.0

# Game Settings
discipline: str(50) - not null (use Discipline enum)
distance: int - not null (racks to win or exact count)
best_of: bool - default False (True="al meglio di", False="esatto numero")

# Inscription Dates
inscription_start: datetime
inscription_end: datetime

# Status & Progress
status: str(20) - default "setup" (use GaraStatus enum)
current_round: int - default 0 (0=not started)

# Policies
withdraw_policy: str(10) - default "Exclude" (use WithdrawPolicy enum)

# Matchmaking Configuration
matchmaking_strategy: str(50) - default "amalfi"
first_round_policy: str(50) - default "random"
odd_number_policy: str(50) - default "bye"
anti_rematch_enabled: bool - default True
```

**Relationships:**
```python
inscriptions: List[Inscription] - cascade delete
matches: List[Match] - cascade delete
director: User - for standalone garas
campionato: Campionato - nullable
```

**Key Properties:**
```python
is_standalone -> bool
    # True if campionato_id is None

directors -> List[User]
    # Computed from DirectorAssignment (not a relationship)
    # Returns co-directors assigned to this gara
```

**Key Methods:**
```python
get_display_name() -> str
    # Returns formatted name with campionato/standalone info

get_real_status() -> str
    # Returns actual status considering round completion and inscription expiry
    # Possible values: setup, inscription, inscription_closed, playing,
    #                  round_completed, tournament_completed, completed

get_status_badge_info() -> dict
    # Returns {"class": "bg-success", "text": "In Corso"} for UI

can_start_new_round() -> bool
    # True if status=playing, current_round < rounds_count,
    # all current round matches are completed

can_inscribe() -> bool
    # True if status=inscription and within inscription dates

is_user_inscribed(user_id: int) -> bool
    # Checks if user has active inscription

validate_strategy_configuration() -> dict
    # Validates matchmaking strategy configuration
    # Returns dict of errors (empty if valid)

can_cancel_round(round_number: Optional[int] = None) -> bool
    # True if round can be cancelled (no results entered)

get_winning_score() -> int
    # Returns score needed to win (distance or distance//2 + 1)

is_match_finished(score1: int, score2: int) -> bool
    # Checks if scores indicate match completion

get_active_inscriptions_count() -> int
    # Count non-withdrawn, non-waitlist inscriptions

get_waitlist_count() -> int
    # Count waitlist inscriptions

is_full() -> bool
    # True if max_participants reached

has_waitlist() -> bool
    # True if max_participants set and gara is full
```

**Usage Examples:**
```python
# Create standalone competition
gara = GaraService.create_gara(
    number=1,
    name="Friday Night Tournament",
    date=date.today() + timedelta(days=7),
    discipline="palla_9",
    distance=7,
    campionato_id=None,  # Standalone
    director_id=current_user.id,
    time=time(19, 0),
    location="Bar Sport",
    min_participants=8,
    max_participants=16
)

# Check if ready to start
if gara.can_inscribe():
    # Open for inscriptions
elif gara.can_start_new_round():
    # Ready for next round
else:
    real_status = gara.get_real_status()
    # Handle based on real status
```

---

### Inscription Model (`models.py`)

**File**: `models/competition/models.py`

**Purpose**: Represents a player's registration to a competition.

**Database Fields:**
```python
id: int (PK)
user_id: int (FK to user.id) - not null
gara_id: int (FK to gara.id, cascade delete) - not null
created_at: datetime - default utcnow
initial_order: int - nullable (sorteggio iniziale)

# Withdrawal
is_withdrawn: bool - default False
withdrawn_at: datetime - nullable

# Forfait (added Oct 2025)
is_forfeit: bool - default False
forfeit_at: datetime - nullable

# Waitlist
is_waitlist: bool - default False
waitlist_position: int - nullable
```

**Relationships:**
```python
user: User
gara: Gara
```

**Usage Examples:**
```python
# Get active participants
active = [i for i in gara.inscriptions if not i.is_withdrawn and not i.is_waitlist]

# Get waitlist
waitlist = [i for i in gara.inscriptions
            if i.is_waitlist and not i.is_withdrawn]

# Query active count
active_count = Inscription.query.filter_by(
    gara_id=gara.id,
    is_withdrawn=False,
    is_waitlist=False
).count()
```

---

### GaraService (`services.py`)

**File**: `models/competition/services.py`

**Purpose**: Main service facade for Gara operations. Delegates to specialized services for specific concerns.

**Key Methods:**

#### Competition CRUD

```python
@transactional
def create_gara(
    number: int,
    name: str,
    date,
    discipline: str,
    distance: int,
    campionato_id: Optional[int] = None,
    director_id: Optional[int] = None,
    **kwargs
) -> Gara:
    """Create a competition (standalone or within campionato).

    Business Rule: Every gara needs a responsible:
    - Campionato gara: managed by campionato directors
    - Standalone gara: requires explicit director_id

    Raises:
        ValueError: If neither campionato_id nor director_id provided
        ValueError: If date is in the past
        ValueError: If time not provided in kwargs
        ValueError: If strategy configuration invalid
    """

@staticmethod
def get_gara_by_id(gara_id: int) -> Optional[Gara]:
    """Retrieve a Gara by ID."""

@transactional
def update_gara(gara_id: int, **kwargs) -> Gara:
    """Update gara fields.

    Only allowed if can_be_modified() returns True.
    Handles special cases for date_str and time_str.
    """

@transactional
def delete_gara(gara_id: int) -> None:
    """Delete gara if possible (no inscriptions)."""

@transactional
def cancel_gara_with_notifications(
    gara_id: int,
    cancelled_by_id: int
) -> None:
    """Cancel gara and notify all participants."""

@transactional
def soft_delete_gara(
    gara_id: int,
    deleted_by_id: int,
    cascade_option: str,
    reason: str = ""
) -> None:
    """Soft delete gara (admin only).

    Args:
        gara_id: ID of gara to delete
        deleted_by_id: Admin user ID performing deletion
        cascade_option: "delete_all" or "keep_matches"
        reason: Optional deletion reason

    Cascade Options:
    - "delete_all": Soft delete gara and all related data
    - "keep_matches": Detach matches (gara_id = NULL) before soft delete.
      Detached matches become "Match Individuali" visible in player history.

    Note: Only admin can soft delete. Directors cannot delete gare.
    """
```

#### Round Management (Facade to RoundService)

```python
@staticmethod
def start_first_round(gara_id: int) -> Gara:
    """Delegate to RoundService."""

@staticmethod
def create_round_with_strategy(
    gara_id: int,
    round_number: int,
    discipline_override: Optional[str] = None
) -> tuple[int, int, int, int]:
    """Delegate to RoundService.
    Returns: (total_matches, normal_matches, bye_matches, trio_matches)
    """

@staticmethod
def update_round_progression(gara_id: int) -> None:
    """Delegate to RoundService."""
```

#### State Machine (Facade to StateService)

```python
@staticmethod
def to_inscription(
    gara_id: int,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None
) -> Gara:
    """Transition setup → inscription."""

@staticmethod
def reopen_setup(gara_id: int) -> Gara:
    """Transition inscription → setup."""

@staticmethod
def start_playing(gara_id: int) -> Gara:
    """Transition inscription → playing."""

@staticmethod
def complete(gara_id: int) -> Gara:
    """Transition playing → completed."""
```

#### Director Management

```python
@transactional
def add_director(
    gara_id: int,
    user_id: int,
    assigned_by_id: int
) -> bool:
    """Add co-director to gara.

    Returns: True if added, False if already exists
    Raises: ValueError if user is admin
    """

@transactional
def remove_director(gara_id: int, user_id: int) -> bool:
    """Remove co-director from gara."""
```

#### Advanced Operations

```python
@transactional
def reset_tournament_to_round(
    gara_id: int,
    target_round: int,
    admin_id: int,
    reset_reason: str
) -> OperationResult:
    """Reset tournament to specific round, removing all subsequent data."""

@transactional
def cancel_tournament(
    gara_id: int,
    admin_id: int,
    cancellation_reason: str,
    refund_entry_fees: bool = False,
    notify_participants: bool = True
) -> OperationResult:
    """Cancel tournament completely."""
```

---

### InscriptionService (`inscription_service.py`)

**File**: `models/competition/inscription_service.py`

**Purpose**: Manages player inscriptions and waitlist operations.

**Key Methods:**

```python
@transactional
def inscribe_user(user_id: int, gara_id: int) -> Optional[Inscription]:
    """Register user to competition.

    If gara is full, user is added to waitlist.

    Business Rules:
    - Admin cannot participate in tournaments
    - Must be within inscription dates
    - Auto-waitlist if max_participants reached

    Raises:
        ValueError: If user is admin
        ValueError: If outside inscription period
    """

@transactional
def uninscribe_user(user_id: int, gara_id: int) -> bool:
    """Cancel user inscription.

    If user was active (not waitlist), promotes first waitlist user
    and sends notification.

    Returns: True if removed, False if not found
    """

@transactional
def admin_uninscribe_user(
    user_id: int,
    gara_id: int,
    admin_user_id: int
) -> bool:
    """Admin/director removes user inscription.

    Sends notification to removed user.
    Promotes first waitlist user if applicable.
    """

@transactional
def open_inscriptions(
    gara_id: int,
    inscription_start: datetime,
    inscription_end: datetime
) -> Gara:
    """Open inscriptions with validation.

    Auto-adjusts end date if after gara date.
    Transitions to inscription state.

    Raises:
        ValueError: If start > end
        ValueError: If end adjusted (informative)
    """

@transactional
def modify_inscription_dates(
    gara_id: int,
    inscription_start: datetime,
    inscription_end: datetime
) -> Gara:
    """Modify inscription dates.

    Smart state management:
    - Before start: setup state
    - During period: inscription state
    - After end: maintains inscription state

    Raises:
        ValueError: If first round already started
        ValueError: If end > gara date
    """

@staticmethod
def can_start_with_current_inscriptions(gara_id: int) -> bool:
    """Check if gara can start with current inscriptions."""
```

**Usage Examples:**
```python
# Inscribe user
try:
    inscription = InscriptionService.inscribe_user(
        user_id=user.id,
        gara_id=gara.id
    )
    if inscription.is_waitlist:
        flash("Aggiunto alla lista d'attesa")
    else:
        flash("Iscrizione confermata")
except ValueError as e:
    flash(str(e), "error")

# Admin uninscribe with notification
success = InscriptionService.admin_uninscribe_user(
    user_id=player.id,
    gara_id=gara.id,
    admin_user_id=current_user.id
)
```

---

### RoundService (`round_service.py`)

**File**: `models/competition/round_service.py`

**Purpose**: Manages round lifecycle, match creation, and strategy integration.

**Key Methods:**

```python
@transactional
def start_first_round(gara_id: int) -> Gara:
    """Start first round with initial draw.

    Behavior depends on strategy:
    - Random strategy: Creates ALL rounds at once
    - Other strategies: Creates only first round

    Business Rules:
    - Shuffles inscriptions for initial_order
    - Validates min_participants
    - Transitions to playing state
    - Creates matches using configured strategy

    Raises:
        ValueError: If gara already started
        ValueError: If insufficient participants
    """

@transactional
def cancel_first_round_startup(gara_id: int) -> Gara:
    """Cancel first round startup.

    Only valid if:
    - current_round == 1
    - No results entered (winner_id is None for all matches)

    Returns gara to inscription state.

    Raises:
        ValueError: If not first round
        ValueError: If results already entered
    """

@transactional
def create_round_with_strategy(
    gara_id: int,
    round_number: int,
    discipline_override: Optional[str] = None
) -> tuple[int, int, int, int]:
    """Create round using configured strategy.

    Idempotent: If matches already exist, returns counts without error.

    Process:
    1. Validate round_number
    2. Check for existing matches (return counts if found)
    3. Get strategy from registry
    4. Generate pairings
    5. Create Match records (normal, bye, trio)
    6. Lock previous round matches

    Returns: (total_matches, normal_matches, bye_matches, trio_matches)

    Raises:
        ValueError: If gara not found
        ValueError: If invalid round_number
        ValueError: If strategy not found
    """

@transactional
def update_round_progression(gara_id: int) -> None:
    """Update round progression and calculate classifications.

    For each round:
    - Checks if all matches completed
    - Updates current_round if needed
    - Calculates RoundClassification if not exists
    """
```

**Usage Examples:**
```python
# Start first round
try:
    gara = RoundService.start_first_round(gara_id=gara.id)
    flash(f"Primo turno avviato con {gara.get_active_inscriptions_count()} partecipanti")
except ValueError as e:
    flash(str(e), "error")

# Create next round (Amalfi, Round-Robin, etc.)
if gara.can_start_new_round():
    counts = RoundService.create_round_with_strategy(
        gara_id=gara.id,
        round_number=gara.current_round + 1
    )
    total, normal, byes, trios = counts
    flash(f"Turno {gara.current_round + 1} creato: {normal} match, {byes} bye, {trios} trio")

# Update progression after match completion
RoundService.update_round_progression(gara_id=gara.id)
```

---

### StateService (`state_service.py`)

**File**: `models/competition/state_service.py`

**Purpose**: Simple service for managing Gara state transitions with validation.

**State Machine:**
```
setup ──→ inscription ──→ playing ──→ completed
         ↑           ↓
         └───────────┘
```

**Key Methods:**

```python
@staticmethod
def to_inscription(gara: Gara) -> Gara:
    """Transition setup → inscription.

    Requires:
    - Current status: setup
    - inscription_start and inscription_end must be set

    Raises:
        InvalidTransitionError: If not in setup state
        InvalidTransitionError: If inscription dates not set
    """

@transactional
def reopen_setup(gara: Gara) -> Gara:
    """Transition inscription → setup.

    Requires:
    - Current status: inscription
    """

@staticmethod
def start_playing(gara: Gara) -> Gara:
    """Transition inscription → playing.

    Requires:
    - Current status: inscription
    - At least min_participants inscribed

    Side effect: Sets current_round = 1

    Raises:
        InvalidTransitionError: If insufficient participants
    """

@transactional
def complete(gara: Gara) -> Gara:
    """Transition playing → completed.

    Requires:
    - Current status: playing
    - No pending or in-progress matches

    Raises:
        InvalidTransitionError: If matches still in progress
    """
```

**Usage Notes:**
- All methods validate current state before transition
- Use InvalidTransitionError for clear error messages
- StateService methods are called by higher-level services (GaraService, RoundService)

---

### WithdrawPolicyService (`withdraw_policy_service.py`)

**File**: `models/competition/withdraw_policy_service.py`

**Purpose**: Handles player forfeits and withdrawal policies for competitions.

**Key Methods:**

```python
@transactional(domain="competition")
def handle_forfeit(gara_id: int, user_id: int) -> str:
    """Handle player forfeit according to gara's withdraw_policy.

    Two policy behaviors:
    - FORFEIT: Mark player as forfeit but keep in inscriptions
    - EXCLUDE: Remove player from inscriptions completely

    Returns:
        "forfeit_marked" or "excluded"

    Raises:
        ValueError: If gara not found or user not inscribed
    """

@staticmethod
def get_active_inscriptions(gara_id: int) -> list[Inscription]:
    """Get active inscriptions (not withdrawn, not waitlist).

    Includes forfeit players (they still participate in matchmaking).
    """

@staticmethod
def get_forfeit_inscriptions(gara_id: int) -> list[Inscription]:
    """Get inscriptions marked as forfeit (for auto-completion logic)."""

@staticmethod
def is_player_forfeit(gara_id: int, user_id: int) -> bool:
    """Check if a specific player is marked as forfeit in this gara."""
```

**Usage Example:**
```python
from models.competition.withdraw_policy_service import WithdrawPolicyService

# Handle forfeit when player forfeits a match
action = WithdrawPolicyService.handle_forfeit(
    gara_id=match.gara_id,
    user_id=player.id
)
# action = "forfeit_marked" or "excluded"

# Check forfeit status for UI display
is_forfeit = WithdrawPolicyService.is_player_forfeit(
    gara_id=gara.id,
    user_id=player.id
)
```

**Integration Points:**
- Called by `MatchService.forfeit_match()` after match completion
- Used in templates via `player_name_with_forfeit` Jinja filter
- Respects gara's `withdraw_policy` setting (FORFEIT vs EXCLUDE)

---

### AdvancedRoundManager (`round_manager.py`)

**File**: `models/competition/round_manager.py`

**Purpose**: Advanced round management with locking mechanisms and modification control.

**Key Enums:**
```python
class RoundLockStatus(Enum):
    UNLOCKED = "unlocked"
    LOCKED = "locked"  # Subsequent round exists
```

**Key Methods:**

```python
@staticmethod
def get_round_lock_status(
    gara_id: int,
    round_number: int
) -> RoundLockStatus:
    """Determine lock status of a round.

    Rules:
    - LOCKED: Any subsequent round has matches
    - UNLOCKED: Otherwise
    """

@staticmethod
def can_modify_match(match_id: int) -> Tuple[bool, str]:
    """Check if match can be modified.

    Returns: (can_modify, reason_if_not)

    Rules:
    - Cannot modify if round is LOCKED
    """

@transactional
def reset_match_with_validation(match_id: int) -> Tuple[bool, str]:
    """Reset match with validation and classification updates.

    Business Rules (Use Case 8 requirement):
    - Validates round locking: blocked if subsequent rounds exist
    - Recalculates all classifications for affected rounds
    - Updates round progression (may decrement current_round)
    - Respects table_assignment for match state (PLAYING/PENDING)

    Process:
    1. Check if modification allowed (round locking)
    2. Store original state for rollback
    3. Reset match (intelligent state based on table_assignment)
    4. Recalculate affected classifications
    5. Update round progression

    Returns:
        Tuple[bool, str]: (success, message)
        - success=False if round locked or error
        - message contains failure reason or success confirmation

    Note: admin_override parameter REMOVED (October 2025)
          Locking always enforced per Use Case 8 specification.
    """

@transactional
def cancel_round(gara_id: int, round_number: int) -> Tuple[bool, str]:
    """Cancel entire round with proper validation.

    Business Rules:
    - Can only cancel current round or future rounds
    - Blocked if matches have partial results
    - Admin must reset matches before canceling round
    - Deletes all matches and racks in the round

    Returns:
        Tuple[bool, str]: (success, message)

    Note: admin_override parameter REMOVED (October 2025)
    """
```

**Usage Examples:**
```python
# Check if match can be modified
can_modify, reason = AdvancedRoundManager.can_modify_match(match.id)
if not can_modify:
    flash(reason, "error")  # Es: "Turno bloccato"
else:
    # Allow modification

# Reset match with validation (no more admin_override)
success, message = AdvancedRoundManager.reset_match_with_validation(match.id)
if success:
    flash(message, "success")
else:
    flash(message, "error")  # Round locked message shown

# Check round lock status
lock_status = AdvancedRoundManager.get_round_lock_status(
    gara_id=gara.id,
    round_number=2
)
if lock_status == RoundLockStatus.LOCKED:
    # Show locked icon in UI
    # User cannot modify matches in this round
```

---

## Common Patterns

### Complete Competition Workflow

```python
from models.competition.services import GaraService
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.state_service import StateService

# 1. Create competition
gara = GaraService.create_gara(
    number=1,
    name="Prova 1",
    date=date.today() + timedelta(days=7),
    discipline="palla_8",
    distance=5,
    campionato_id=campionato.id,
    time=time(18, 0),
    rounds_count=3,
    min_participants=6
)

# 2. Open inscriptions
gara = InscriptionService.open_inscriptions(
    gara_id=gara.id,
    inscription_start=datetime.now(),
    inscription_end=datetime.now() + timedelta(days=3)
)

# 3. Players inscribe
for player in players:
    InscriptionService.inscribe_user(
        user_id=player.id,
        gara_id=gara.id
    )

# 4. Start first round
gara = RoundService.start_first_round(gara_id=gara.id)

# 5. Enter match results (see match domain)
# ...

# 6. Create next round
if gara.can_start_new_round():
    RoundService.create_round_with_strategy(
        gara_id=gara.id,
        round_number=gara.current_round + 1
    )

# 7. Complete competition
if gara.current_round == gara.rounds_count:
    gara = StateService.complete(gara)
```

### Waitlist Management

```python
# Check if gara is full
if gara.is_full():
    # Show waitlist info
    waitlist_count = gara.get_waitlist_count()
    print(f"{waitlist_count} players in waitlist")

# Inscribe user (auto-waitlist if full)
inscription = InscriptionService.inscribe_user(
    user_id=user.id,
    gara_id=gara.id
)

if inscription.is_waitlist:
    print(f"Position in waitlist: {inscription.waitlist_position}")
else:
    print("Confirmed inscription")

# When user uninscribes, first waitlist is auto-promoted
InscriptionService.uninscribe_user(
    user_id=leaving_user.id,
    gara_id=gara.id
)
# First waitlist user receives notification
```

### Strategy Configuration

```python
# Validate strategy before creating gara
errors = gara.validate_strategy_configuration()
if errors:
    for field, error in errors.items():
        print(f"{field}: {error}")

# Get strategy constraints
constraints = gara.get_strategy_constraints()
# Returns dict with:
# - min_players, max_players
# - requires_rating_system
# - supports_odd_numbers
# - supported_odd_policies
# - description

# Calculate optimal rounds for strategy
optimal_rounds = gara.calculate_rounds_for_strategy(
    num_players=len(inscriptions)
)
```

---

## Important Notes

### Business Rules

1. **Admin Cannot Participate**: Admin users cannot inscribe to competitions (ValueError raised)

2. **Director Requirement**: Every gara needs a responsible:
   - Campionato gara: Managed by campionato directors
   - Standalone gara: Requires explicit director_id

3. **Inscription Dates**:
   - inscription_end cannot be after gara date
   - Auto-adjusted with informative error if needed

4. **Waitlist Promotion**:
   - Automatic when active inscription is cancelled
   - First in waitlist promoted
   - Positions recalculated for remaining waitlist
   - Notification sent to promoted user

5. **Round Locking**:
   - Rounds locked when subsequent round exists
   - Prevents accidental modifications
   - Admin override available

6. **Soft Delete with Keep Matches**:
   - When deleting gara with "keep_matches" option, matches are detached (gara_id = NULL)
   - Detached matches become "Match Individuali" visible in player history
   - Match.distance_config handles null gara with sensible defaults
   - Templates use `match.gara_id` checks before accessing gara properties

### Gotchas

1. **Status vs Real Status**: Use `get_real_status()` instead of `status` field for UI display. It accounts for round completion and inscription expiry.

2. **Strategy-Specific Behavior**: Random strategy creates ALL rounds at startup, others create one round at a time.

3. **Idempotent Round Creation**: `create_round_with_strategy()` is idempotent - returns counts if round already exists.

4. **Relationship Access**: `gara.directors` is a computed property, not a relationship. Cannot use `.append()` or `.remove()`.

5. **Transaction Management**: All service methods use `@transactional` decorator. Never call `db.session.commit()` in these methods.

### Edge Cases

1. **Odd Number of Players**: Handled by `odd_number_policy`:
   - `bye`: Player vs X (auto-win)
   - `trio`: Three-player matches
   - `challenge`: X-replacement with challenges

2. **Inscription Dates Modification**: Smart state management transitions between setup/inscription based on current time vs dates.

3. **First Round Cancellation**: Special method for first round only. For other rounds, use `cancel_current_round_startup()`.

4. **Match Locking**: Previous round matches locked when new round created. Prevents modifications that would invalidate classifications.

---

## Examples

### Create Standalone Competition

```python
from datetime import date, time, timedelta

gara = GaraService.create_gara(
    number=1,
    name="Friday Night 8-Ball",
    date=date.today() + timedelta(days=7),
    time=time(19, 0),
    discipline="palla_8",
    distance=5,
    best_of=True,
    campionato_id=None,  # Standalone
    director_id=current_user.id,
    location="Bar Sport Milano",
    description="Weekly 8-ball tournament",
    rounds_count=3,
    min_participants=8,
    max_participants=16,
    entry_fee=5.0,
    matchmaking_strategy="amalfi",
    first_round_policy="random",
    odd_number_policy="bye",
    anti_rematch_enabled=True
)
```

### Handle Inscription Workflow

```python
# Open inscriptions
try:
    gara = InscriptionService.open_inscriptions(
        gara_id=gara.id,
        inscription_start=datetime.now(),
        inscription_end=datetime.now() + timedelta(days=3)
    )
    flash("Iscrizioni aperte!", "success")
except ValueError as e:
    flash(str(e), "error")

# User inscription
try:
    inscription = InscriptionService.inscribe_user(
        user_id=current_user.id,
        gara_id=gara.id
    )

    if inscription.is_waitlist:
        flash(f"Aggiunto alla lista d'attesa (posizione {inscription.waitlist_position})", "info")
    else:
        flash("Iscrizione confermata!", "success")

except ValueError as e:
    flash(str(e), "error")

# Check if can start
if InscriptionService.can_start_with_current_inscriptions(gara.id):
    # Show "Start Tournament" button
    pass
```

### Multi-Round Tournament

```python
# Start first round
gara = RoundService.start_first_round(gara_id=gara.id)
print(f"Round 1 started with {gara.get_active_inscriptions_count()} players")

# After matches complete, create next round
while gara.current_round < gara.rounds_count:
    if gara.can_start_new_round():
        # Create next round
        counts = RoundService.create_round_with_strategy(
            gara_id=gara.id,
            round_number=gara.current_round + 1
        )
        total, normal, byes, trios = counts
        print(f"Round {gara.current_round + 1}: {normal} matches, {byes} byes, {trios} trios")

        # Update progression
        RoundService.update_round_progression(gara_id=gara.id)
    else:
        # Wait for current round to complete
        break

# Complete tournament
if gara.current_round == gara.rounds_count:
    all_completed = all(
        m.status == MatchStatus.COMPLETED.value
        for m in gara.matches
        if m.round_number == gara.current_round
    )
    if all_completed:
        gara = StateService.complete(gara)
        print("Tournament completed!")
```

### Advanced Round Management

```python
from models.competition.round_manager import AdvancedRoundManager, RoundLockStatus

# Check lock status before allowing modifications
lock_status = AdvancedRoundManager.get_round_lock_status(
    gara_id=gara.id,
    round_number=2
)

if lock_status == RoundLockStatus.LOCKED:
    flash("Turno bloccato: esiste un turno successivo", "error")
    # User cannot modify this round
else:
    # Allow modifications

# Reset specific match with validation (no more admin_override)
success, message = AdvancedRoundManager.reset_match_with_validation(match_id=match.id)

if success:
    flash(message, "success")
    # Classifications automatically recalculated
    # Round progression updated (may decrement current_round)
    # Match state set based on table_assignment
else:
    flash(message, "error")  # Round locked or other error

# Cancel entire round (no more admin_override)
success, message = AdvancedRoundManager.cancel_round(
    gara_id=gara.id,
    round_number=gara.current_round
)
```

---

## File Structure

```
models/competition/
├── __init__.py                 # Package exports
├── models.py                   # Gara, Inscription models
├── services.py                 # GaraService (main facade)
├── inscription_service.py      # InscriptionService (extracted)
├── round_service.py            # RoundService (extracted)
├── state_service.py            # StateService (state machine)
├── round_manager.py            # AdvancedRoundManager (locking)
└── round_configuration.py      # Round-specific configs
```

---

## Cross-References

- **Matchmaking**: [../matchmaking/CLAUDE.md](../matchmaking/CLAUDE.md) - Pairing strategies
- **Match Execution**: [../match/CLAUDE.md](../match/CLAUDE.md) - Match and scoring
- **Classification**: [../classification/CLAUDE.md](../classification/CLAUDE.md) - Rankings
- **User Management**: [../user/CLAUDE.md](../user/CLAUDE.md) - Players and directors
- **Campionato**: [../campionato/](../campionato/) - Multi-competition tournaments
- **Root Architecture**: [../CLAUDE.md](../CLAUDE.md) - Overall domain organization
