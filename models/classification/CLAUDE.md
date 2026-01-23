# Classification Domain

## Purpose

Ranking and classification system for tournaments at multiple scopes: round, gara, and campionato.

**Core Responsibilities:**
- Round-by-round classification for matchmaking (Amalfi algorithm)
- Final gara rankings
- Aggregated campionato standings
- Anti-rematch tracking via PlayerEncounter
- Tiebreaker resolution

---

## Quick Reference

```python
from models.classification.models import (
    Classification, RoundClassification, GaraClassification, PlayerEncounter
)
from models.classification.services import (
    ClassificationService, RoundClassificationService,
    StrategyBasedClassificationService
)

# Update campionato classification (cached 5 min)
ClassificationService.update_campionato_classification(campionato_id)

# Calculate round classification (for matchmaking)
RoundClassificationService.calculate_round_classification(gara_id, round_number)

# Strategy-based classification (recommended for new code)
service = StrategyBasedClassificationService()
result = service.calculate_round_classification(gara, round_number)
# Returns: ClassificationResult with PlayerScore list

# Check anti-rematch
encounters = PlayerEncounter.get_encounters_in_gara(gara_id, player1_id, player2_id)
```

---

## Models

### Classification
Campionato-level standings across all gare.

**Fields:** `campionato_id`, `user_id`, `position`, `total_matches_won`, `total_point_difference`, `gare_played`

### RoundClassification
Per-round standings within a gara. Used by matchmaking for pairing.

**Fields:** `gara_id`, `round_number`, `user_id`, `position`, `matches_won`, `racks_won`, `racks_lost`, `point_difference`

### GaraClassification
Final rankings for a completed gara. Includes SSR tiebreaker scores.

**Fields:** `gara_id`, `user_id`, `position`, `matches_won`, `racks_won`, `racks_lost`, `rack_difference`, `spot_shot_wins`

### PlayerEncounter
Tracks player matchups for anti-rematch logic.

**Fields:** `gara_id`, `player1_id`, `player2_id`, `round_number`, `match_id`

---

## Strategy Pattern

Classification uses strategy pattern in `strategies/` subdirectory:

| Strategy | Scope | Usage |
|----------|-------|-------|
| `amalfi_round` | Round | Amalfi per-round classification |
| `amalfi_gara` | Gara | Amalfi final standings |
| `random_round` | Round | Random strategy classification |
| `random_gara` | Gara | Random final standings |

```python
from models.classification.registry import get_classification_registry

registry = get_classification_registry()
strategy = registry.get("amalfi_round")
result = strategy.calculate(gara, round_number)
```

---

## Services

### ClassificationService
- `update_campionato_classification(campionato_id)` - Cached, aggregates all gare

### RoundClassificationService
- `calculate_round_classification(gara_id, round_number)` - For matchmaking
- `get_classification_for_round(gara_id, round_number)` - Query existing

### StrategyBasedClassificationService (Recommended)
- `calculate_round_classification(gara, round_number)` - Strategy-based
- `calculate_gara_classification(gara)` - Final gara standings
- Uses `ScoreAggregator` and `TiebreakerResolver`

---

## Tiebreaker Resolution

Tiebreaker order depends on strategy:

### Random Strategy
1. Total racks won
2. **SSR (Spot Shot Rally)** - loaded from `GaraClassification.spot_shot_wins`
3. Rack difference (racks won - racks lost)
4. Player ID (stability)

### Amalfi Strategy
1. Matches won
2. Rack difference (racks won - racks lost)
3. Head-to-head result
4. Total racks won
5. Initial inscription order

---

## Do Not

- **Do not use legacy static methods** - Prefer `StrategyBasedClassificationService`
- **Do not forget to calculate after round completion** - Matchmaking needs updated classification
- **Do not query PlayerEncounter without gara_id** - Always scope to gara
- **Do not call `db.session.commit()`** - Services use `@transactional`
- **Do not bypass caching** - `update_campionato_classification` is cached for performance

---

## Cross-References

- **Matchmaking**: [../matchmaking/CLAUDE.md](../matchmaking/CLAUDE.md) - Uses RoundClassification for pairing
- **Competition**: [../competition/CLAUDE.md](../competition/CLAUDE.md) - Gara completion triggers classification
- **Campionato**: [../campionato/](../campionato/) - Aggregated Classification
