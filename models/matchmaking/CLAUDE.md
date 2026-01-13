# Matchmaking Domain

## Purpose

Tournament pairing algorithms with unified strategy pattern.

**Core Responsibilities:**
- Player pairing generation for tournament rounds
- Strategy pattern (Amalfi, Round-Robin, Elimination, Random)
- First round policies (random, classification, rating)
- Odd number handling (byes, trio matches)
- Anti-rematch logic across rounds

---

## Quick Reference

```python
from models.matchmaking.bootstrap import get_registry
from models.matchmaking.configuration import (
    MatchmakingStrategy, FirstRoundPolicy, OddNumberPolicy
)

# Get strategy and generate pairings
registry = get_registry()
strategy = registry.get(MatchmakingStrategy.AMALFI.value)
pairings = strategy.create_round(gara, round_number=1)

# Process pairings
for pairing in pairings:
    if pairing.is_bye:
        # Single player, automatic win
        pass
    elif pairing.is_trio:
        # 3-player match (pairing.players has 3 IDs)
        pass
    else:
        # Regular match
        player1, player2 = pairing.player1_id, pairing.player2_id
```

---

## Key Classes

### Pairing (Value Object)
Immutable dataclass representing a match pairing.

**Fields:** `players` (tuple of IDs), `is_bye`, `round_number`, `notes`

**Properties:** `player1_id`, `player2_id`, `is_trio`, `is_valid_pairing`

### BaseStrategy (Abstract)
Base class for all strategies. Implement `_generate_pairings()` and `_validate_strategy_specific()`.

**Class Attributes:** `name`, `display_name`, `min_players`, `max_players`, `supports_byes`, `requires_classification`

### EngineRegistry
Strategy registry with factory capabilities.

```python
registry.get(MatchmakingStrategy.AMALFI.value)  # Get strategy
registry.available()  # List strategy names
registry.create_strategy(name, seed=42)  # Deterministic for testing
```

---

## Strategies

| Strategy | Description | Min Players |
|----------|-------------|-------------|
| `amalfi` | Classification-based with anti-rematch | 3 |
| `round_robin` | All-play-all | 3 |
| `direct_elimination` | Single knockout | 2 |
| `double_knockout` | Winners + losers brackets | 4 |
| `random` | Random with anti-rematch | 2 |

### Amalfi Algorithm
- **Round 1**: Configurable (random, classification, rating)
- **Round 2+**: Classification-based "salto" algorithm
- **Odd players**: Last-place gets bye

### Random Anti-Rematch
- Uses NetworkX maximum cardinality matching
- Multi-objective trio selection: fairness → anti-rematch → efficiency

---

## Configuration Enums

```python
class MatchmakingStrategy(str, Enum):
    AMALFI = "amalfi"
    ROUND_ROBIN = "round_robin"
    DIRECT_ELIMINATION = "direct_elimination"
    DOUBLE_KNOCKOUT = "double_knockout"
    RANDOM = "random"

class FirstRoundPolicy(str, Enum):
    RANDOM = "random"
    CLASSIFICATION = "classification"
    RATING = "rating"

class OddNumberPolicy(str, Enum):
    BYE = "bye"
    TRIO = "trio"
    CHALLENGE = "challenge"
```

---

## Do Not

- **Do not use string literals** - Use `MatchmakingStrategy.AMALFI.value` not `"amalfi"`
- **Do not use round_number=0** - Round numbers are 1-based
- **Do not modify Pairing after creation** - Frozen dataclass
- **Do not skip validation** - Call `strategy.validate()` before `create_round()`
- **Do not forget classification for Amalfi** - Rounds 2+ need `RoundClassification` from previous round
- **Do not call strategy directly from routes** - Use `RoundService.create_round_with_strategy()`

---

## Cross-References

- **Competition**: [../competition/CLAUDE.md](../competition/CLAUDE.md) - Round management
- **Match**: [../match/CLAUDE.md](../match/CLAUDE.md) - Match execution
- **Classification**: [../classification/](../classification/) - Rankings for Amalfi
