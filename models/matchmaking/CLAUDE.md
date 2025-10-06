# Matchmaking Domain Documentation

## Purpose

The Matchmaking domain provides flexible tournament pairing algorithms with a unified strategy pattern. It coordinates player matchups for competitions using various strategies while handling edge cases like odd numbers, anti-rematch logic, and bye management.

**Core Responsibilities:**
- Player pairing generation for tournament rounds
- Strategy pattern implementation (Amalfi, Round-Robin, Elimination, Random)
- First round policies (random, classification-based, rating-based)
- Odd number handling (byes, trio matches, challenge substitution)
- Anti-rematch logic across rounds

**Related Domains:**
- See [../competition/CLAUDE.md](../competition/CLAUDE.md) for competition management
- See [../match/CLAUDE.md](../match/CLAUDE.md) for match execution
- See [../classification/CLAUDE.md](../classification/CLAUDE.md) for rankings
- See [../rating/](../rating/) for player skill ratings

---

## Quick Reference

### Most-Used Classes

```python
from models.matchmaking.service import MatchmakingService
from models.matchmaking.strategies.base import Pairing, BaseStrategy
from models.matchmaking.strategies.amalfi import AmalfiStrategy
from models.matchmaking.configuration import (
    MatchmakingStrategy,
    FirstRoundPolicy,
    OddNumberPolicy
)
from models.matchmaking.bootstrap import get_registry

# Get strategy registry
registry = get_registry()
strategy = registry.get("amalfi")

# Generate pairings
pairings = strategy.create_round(gara, round_number=1)
```

### Common Operations

```python
# Generate pairings for a round
from models.matchmaking.bootstrap import get_registry

registry = get_registry()
strategy = registry.get("amalfi")
pairings = strategy.create_round(gara, round_number=1)

# Each pairing contains:
for pairing in pairings:
    print(f"Player 1: {pairing.player1_id}")
    print(f"Player 2: {pairing.player2_id}")
    print(f"Is bye: {pairing.is_bye}")
    print(f"Is trio: {pairing.is_trio}")
```

---

## Key Classes

### Pairing (Value Object) (`strategies/base.py`)

**File**: `models/matchmaking/strategies/base.py`

**Purpose**: Immutable value object representing a match pairing.

**Fields:**
```python
players: Tuple[int, ...] - Player IDs (1-3 players)
is_bye: bool - default False
round_number: Optional[int]
estimated_duration: Optional[int] - minutes
requires_handicap: bool - default False
notes: Optional[str] - Strategy-specific annotations
```

**Key Properties:**
```python
player1_id -> Optional[int]
    # First player ID

player2_id -> Optional[int]
    # Second player ID (None for bye)

is_valid_pairing -> bool
    # Validates pairing structure:
    # - Bye: exactly 1 player
    # - Regular: exactly 2 different players
    # - Trio: exactly 3 different players

is_trio -> bool
    # True if 3-player match
```

**Usage Examples:**
```python
# Regular match
pairing = Pairing(players=(10, 20))
assert pairing.is_valid_pairing
assert not pairing.is_bye
assert not pairing.is_trio

# Bye match
bye_pairing = Pairing(players=(10,), is_bye=True)
assert bye_pairing.is_valid_pairing

# Trio match
trio_pairing = Pairing(players=(10, 20, 30))
assert trio_pairing.is_trio
assert trio_pairing.is_valid_pairing
```

---

### BaseStrategy (Abstract Base Class) (`strategies/base.py`)

**File**: `models/matchmaking/strategies/base.py`

**Purpose**: Abstract base class for all matchmaking strategies.

**Key Methods to Implement:**
```python
def _validate_strategy_specific(self, gara) -> Dict[str, List[str]]:
    """Strategy-specific validation.

    Returns: {"errors": [...], "warnings": [...]}
    """

def _generate_pairings(
    self,
    processed_data: Dict[str, Any],
    round_number: int
) -> Sequence[Pairing]:
    """Generate pairings for a round.

    Args:
        processed_data: Pre-processed tournament data
        round_number: Round number (1-based)

    Returns:
        Sequence of Pairing objects
    """
```

**Provided Methods:**
```python
def create_round(self, gara, round_number: int) -> Sequence[Pairing]:
    """Main entry point for round creation.

    Process:
    1. Validate tournament configuration
    2. Pre-process data (inscriptions, classifications)
    3. Generate pairings
    4. Post-process (handle odd numbers, anti-rematch)

    Returns: List of Pairing objects
    """

def supports_first_round_policy(self, policy: FirstRoundPolicy) -> bool:
    """Check if strategy supports a first round policy."""

def _get_active_inscriptions(self, gara):
    """Get active inscriptions (not withdrawn, not waitlist)."""

def _handle_odd_numbers(
    self,
    players: List[int],
    policy: OddNumberPolicy
) -> Optional[Pairing]:
    """Handle odd number of players based on policy."""
```

**Class Attributes:**
```python
name: str  # Strategy identifier
display_name: str  # UI-friendly name
description: str  # Strategy description
min_players: int  # Minimum players required
max_players: Optional[int]  # Maximum players (None = unlimited)
supports_byes: bool  # Can handle bye matches
requires_classification: bool  # Needs classification data
```

---

### AmalfiStrategy (`strategies/amalfi.py`)

**File**: `models/matchmaking/strategies/amalfi.py`

**Purpose**: Implements the Amalfi tournament pairing algorithm.

**Algorithm Overview:**
- **First Round**: Configurable policy (random, classification, rating)
- **Later Rounds**: Classification-based with "salto" algorithm
- **Anti-Rematch**: Avoids repeated matchups
- **Bye Handling**: Last-place player gets bye

**Configuration:**
```python
name = "amalfi"
display_name = "Amalfi"
min_players = 3
max_players = None
supports_byes = True
requires_classification = True
```

**First Round Policies:**
```python
FirstRoundPolicy.RANDOM  # Random shuffle
FirstRoundPolicy.CLASSIFICATION  # Campionato standings
FirstRoundPolicy.RATING  # Fargo/Elo ratings
```

**Key Methods:**
```python
def _generate_actual_pairings(
    self,
    gara: Gara,
    round_number: int
) -> Sequence[Pairing]:
    """Generate pairings using Amalfi algorithm.

    First round: Uses first_round_policy
    Later rounds: Uses classification from previous round
    """

def _amalfi_pairing(
    self,
    classification: List[RoundClassification],
    round_number: int,
    total_rounds: int
) -> List[Pairing]:
    """Core Amalfi pairing logic.

    Uses "salto" algorithm:
    - Pair players based on remaining rounds and standings
    - Avoid rematches when possible
    - Last player gets bye if odd number
    """

def _calculate_salto(
    self,
    player_rank: int,
    num_players: int,
    remaining_rounds: int
) -> int:
    """Calculate opponent offset based on Amalfi algorithm."""
```

**Usage Examples:**
```python
strategy = AmalfiStrategy()

# First round (random policy)
gara.first_round_policy = FirstRoundPolicy.RANDOM.value
pairings = strategy.create_round(gara, round_number=1)

# Second round (classification-based)
pairings = strategy.create_round(gara, round_number=2)
# Uses RoundClassification from round 1
```

---

### Other Strategies

#### RoundRobinStrategy (`strategies/round_robin.py`)
- All-play-all tournament format
- Each player faces every other player once
- Calculates optimal rounds automatically
- No byes (must have even players or handle trio)

#### DirectEliminationStrategy (`strategies/direct_elimination.py`)
- Single-elimination knockout tournament
- Winners advance, losers eliminated
- Rounds calculated as log2(players)
- Bye handling for non-power-of-2 player counts

#### RandomAntiRematchStrategy (`strategies/random_anti_rematch.py`)
- Random pairings with anti-rematch logic
- Attempts to avoid repeated matchups
- Falls back to any pairing if no valid non-rematch available
- Good for casual tournaments

#### DoubleKnockoutStrategy (`strategies/double_knockout.py`)
- Double-elimination tournament
- Losers get second chance in losers bracket
- Complex bracket management
- Finals between winners bracket and losers bracket champions

---

### MatchmakingService (`service.py`)

**File**: `models/matchmaking/service.py`

**Purpose**: Service orchestrator for matchmaking operations.

**Key Methods:**
```python
def run(
    self,
    strategy_name: str,
    gara,
    round_number: int
) -> Sequence[Pairing]:
    """Execute matchmaking strategy.

    Args:
        strategy_name: Strategy identifier ("amalfi", "round_robin", etc.)
        gara: Competition object
        round_number: Round number (1-based)

    Returns:
        List of Pairing objects
    """
```

**Usage Examples:**
```python
from models.matchmaking.service import MatchmakingService

service = MatchmakingService()
pairings = service.run(
    strategy_name="amalfi",
    gara=gara,
    round_number=1
)

# Process pairings
for pairing in pairings:
    if pairing.is_bye:
        # Handle bye match
        pass
    elif pairing.is_trio:
        # Handle trio match
        pass
    else:
        # Handle regular match
        pass
```

---

### Strategy Registry (`bootstrap.py`)

**File**: `models/matchmaking/bootstrap.py`

**Purpose**: Central registry for all matchmaking strategies.

**Key Functions:**
```python
def get_registry() -> EngineRegistry:
    """Get initialized strategy registry.

    Registered strategies:
    - "amalfi": AmalfiStrategy
    - "round_robin": RoundRobinStrategy
    - "direct_elimination": DirectEliminationStrategy
    - "random_anti_rematch": RandomAntiRematchStrategy
    - "double_knockout": DoubleKnockoutStrategy
    """
```

**Usage Examples:**
```python
from models.matchmaking.bootstrap import get_registry

# Get registry
registry = get_registry()

# List available strategies
strategies = registry.list_strategies()
# Returns: ["amalfi", "round_robin", "direct_elimination", ...]

# Get specific strategy
strategy = registry.get("amalfi")
if strategy:
    pairings = strategy.create_round(gara, 1)
```

---

### Configuration (`configuration.py`)

**File**: `models/matchmaking/configuration.py`

**Purpose**: Configuration classes and enums for matchmaking.

**Key Enums:**
```python
class MatchmakingStrategy(str, Enum):
    AMALFI = "amalfi"
    ROUND_ROBIN = "round_robin"
    DIRECT_ELIMINATION = "direct_elimination"
    DOUBLE_KNOCKOUT = "double_knockout"
    RANDOM_ANTI_REMATCH = "random"

class FirstRoundPolicy(str, Enum):
    RANDOM = "random"
    CLASSIFICATION = "classification"
    RATING = "rating"

class OddNumberPolicy(str, Enum):
    BYE = "bye"
    TRIO = "trio"
    CHALLENGE = "challenge"  # X-replacement with challenges
```

**StrategyConfiguration Class:**
```python
@dataclass
class StrategyConfiguration:
    """Encapsulates matchmaking strategy configuration."""

    strategy: MatchmakingStrategy
    first_round_policy: FirstRoundPolicy
    odd_number_policy: OddNumberPolicy
    anti_rematch_enabled: bool

    @classmethod
    def from_gara(cls, gara) -> "StrategyConfiguration":
        """Create configuration from Gara object."""

    def validate(
        self,
        num_players: Optional[int] = None,
        distance: Optional[int] = None,
        best_of: Optional[bool] = None
    ) -> List[str]:
        """Validate configuration.

        Returns: List of error messages (empty if valid)
        """

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
```

**Strategy Constraints:**
```python
STRATEGY_CONSTRAINTS = {
    MatchmakingStrategy.AMALFI: {
        "min_players": 3,
        "max_players": None,
        "requires_rating_system": False,
        "supports_odd_numbers": True,
        "supported_odd_policies": [OddNumberPolicy.BYE, OddNumberPolicy.CHALLENGE],
        "description": "Adaptive pairing with anti-rematch"
    },
    # ... other strategies
}
```

---

## Common Patterns

### Complete Matchmaking Workflow

```python
from models.matchmaking.bootstrap import get_registry
from models.competition.models import Gara
from models.match.models import Match

# 1. Get strategy
registry = get_registry()
strategy = registry.get("amalfi")

# 2. Validate configuration
gara = Gara.query.get(gara_id)
errors = strategy.validate(gara)
if errors.has_errors:
    # Handle errors
    pass

# 3. Generate pairings
pairings = strategy.create_round(gara, round_number=1)

# 4. Create Match records
for pairing in pairings:
    if pairing.is_bye:
        # Bye match
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=pairing.player1_id,
            player2_id=None,
            is_bye=True,
            player1_score=gara.get_winning_score(),
            winner_id=pairing.player1_id,
            status="completed"
        )
    elif pairing.is_trio:
        # Trio match
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=pairing.players[0],
            player2_id=pairing.players[1],
            is_trio=True
        )
        # Create TrioMatch record separately
    else:
        # Regular match
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=pairing.player1_id,
            player2_id=pairing.player2_id
        )

    db.session.add(match)

db.session.commit()
```

### Anti-Rematch Logic

```python
from models.matchmaking.policies import anti_rematch_allowed

# Check if pairing is allowed (hasn't happened before)
allowed = anti_rematch_allowed(
    gara_id=gara.id,
    player1_id=10,
    player2_id=20,
    current_round=2
)

if not allowed:
    # Find alternative pairing
    pass
```

### Custom Strategy Implementation

```python
from models.matchmaking.strategies.base import BaseStrategy, Pairing
from typing import Sequence, Dict, Any, List

class CustomStrategy(BaseStrategy):
    """Custom tournament pairing strategy."""

    name = "custom"
    display_name = "Custom Strategy"
    description = "Custom pairing algorithm"
    min_players = 2
    max_players = None
    supports_byes = True
    requires_classification = False

    def _validate_strategy_specific(self, gara) -> Dict[str, List[str]]:
        """Validate tournament for custom strategy."""
        errors = []
        warnings = []

        # Add custom validation
        inscriptions = self._get_active_inscriptions(gara)
        if len(inscriptions) < 4:
            warnings.append("Works best with 4+ players")

        return {"errors": errors, "warnings": warnings}

    def _generate_pairings(
        self,
        processed_data: Dict[str, Any],
        round_number: int
    ) -> Sequence[Pairing]:
        """Generate custom pairings."""
        gara = processed_data["gara"]
        inscriptions = self._get_active_inscriptions(gara)

        players = [i.user_id for i in inscriptions]
        pairings = []

        # Implement custom pairing logic
        # Example: Random pairing
        import random
        random.shuffle(players)

        for i in range(0, len(players) - 1, 2):
            pairing = Pairing(
                players=(players[i], players[i + 1]),
                round_number=round_number
            )
            pairings.append(pairing)

        # Handle odd number
        if len(players) % 2 == 1:
            bye_pairing = Pairing(
                players=(players[-1],),
                is_bye=True,
                round_number=round_number
            )
            pairings.append(bye_pairing)

        return pairings

# Register custom strategy
from models.matchmaking.bootstrap import get_registry

registry = get_registry()
registry.register("custom", CustomStrategy())
```

---

## Important Notes

### Business Rules

1. **Anti-Rematch Logic**: Strategies attempt to avoid pairing players who have already faced each other. Falls back to any pairing if no alternative exists.

2. **Odd Number Handling**: Configurable policies:
   - **BYE**: Last-place player gets automatic win
   - **TRIO**: Three-player matches
   - **CHALLENGE**: X-replacement with skill challenges

3. **First Round Policies** (Amalfi):
   - **RANDOM**: Shuffle players randomly
   - **CLASSIFICATION**: Use campionato standings
   - **RATING**: Use Fargo/Elo ratings from User model

4. **Classification Requirement**: Some strategies (Amalfi) require RoundClassification data from previous rounds.

### Gotchas

1. **Strategy Names**: Use registry names, not enum values:
   - ✅ `registry.get("amalfi")`
   - ❌ `registry.get(MatchmakingStrategy.AMALFI)`

2. **Pairing Immutability**: Pairing is a frozen dataclass. Cannot modify after creation.

3. **Round Number**: Always 1-based (never 0).

4. **Validation**: Always call `strategy.validate()` before `create_round()`. Validation errors prevent pairing generation.

5. **Active Inscriptions**: Strategies automatically filter out withdrawn and waitlist inscriptions.

### Edge Cases

1. **Insufficient Players**: Each strategy has `min_players`. Attempting to create pairings with fewer players raises ValueError.

2. **Non-Power-of-2** (Elimination): Direct elimination handles non-power-of-2 player counts with byes in first round.

3. **Anti-Rematch Failure**: If no valid non-rematch pairing exists (rare), strategy pairs players anyway to avoid deadlock.

4. **Classification Missing**: Amalfi raises error if previous round classification not found. Ensure `RoundClassification.calculate_classification_after_round()` is called.

---

## Examples

### Amalfi Tournament

```python
from models.matchmaking.bootstrap import get_registry
from models.competition.models import Gara
from models.matchmaking.configuration import FirstRoundPolicy

# Configure gara
gara = Gara(
    matchmaking_strategy="amalfi",
    first_round_policy=FirstRoundPolicy.RANDOM.value,
    odd_number_policy="bye",
    anti_rematch_enabled=True,
    rounds_count=3
)

# Get strategy
registry = get_registry()
strategy = registry.get("amalfi")

# Generate first round (random)
pairings_r1 = strategy.create_round(gara, round_number=1)

# After matches complete and classification calculated
# Generate second round (classification-based)
pairings_r2 = strategy.create_round(gara, round_number=2)

# Generate third round
pairings_r3 = strategy.create_round(gara, round_number=3)
```

### Round-Robin Tournament

```python
from models.matchmaking.bootstrap import get_registry

registry = get_registry()
strategy = registry.get("round_robin")

# Calculate required rounds
num_players = len(gara.inscriptions)
required_rounds = num_players - 1 if num_players % 2 == 0 else num_players

# Generate all rounds
for round_num in range(1, required_rounds + 1):
    pairings = strategy.create_round(gara, round_number=round_num)
    # Create matches...
```

### Strategy Comparison

```python
from models.matchmaking.bootstrap import get_registry

registry = get_registry()

# List all strategies
for strategy_name in registry.list_strategies():
    strategy = registry.get(strategy_name)

    print(f"Strategy: {strategy.display_name}")
    print(f"  Min players: {strategy.min_players}")
    print(f"  Supports byes: {strategy.supports_byes}")
    print(f"  Requires classification: {strategy.requires_classification}")
    print(f"  Description: {strategy.description}")
```

---

## File Structure

```
models/matchmaking/
├── __init__.py
├── bootstrap.py                # Strategy registry initialization
├── configuration.py            # Enums, StrategyConfiguration
├── policies.py                 # Anti-rematch, odd number policies
├── registry.py                 # EngineRegistry implementation
├── service.py                  # MatchmakingService orchestrator
├── amalfi_challenge_bye_service.py  # X-replacement with challenges
└── strategies/
    ├── __init__.py
    ├── base.py                 # BaseStrategy, Pairing, ValidationResult
    ├── amalfi.py               # AmalfiStrategy
    ├── round_robin.py          # RoundRobinStrategy
    ├── direct_elimination.py   # DirectEliminationStrategy
    ├── double_knockout.py      # DoubleKnockoutStrategy
    └── random_anti_rematch.py  # RandomAntiRematchStrategy
```

---

## Cross-References

- **Competition Management**: [../competition/CLAUDE.md](../competition/CLAUDE.md)
- **Match Execution**: [../match/CLAUDE.md](../match/CLAUDE.md)
- **Classification**: [../classification/CLAUDE.md](../classification/CLAUDE.md)
- **Challenge System**: [../challenge/CLAUDE.md](../challenge/CLAUDE.md)
- **Rating System**: [../rating/](../rating/)
- **Root Architecture**: [../CLAUDE.md](../CLAUDE.md)
