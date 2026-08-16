# Rating Domain

## Purpose

Player skill rating and handicap system for balanced competition.

**Core Responsibilities:**
- Player category assignment (A/B/C/D)
- Rating systems (Elo, internal)
- Handicap rules for match distance adjustments
- Rating history tracking

---

## Quick Reference

```python
from models.rating.models import (
    PlayerCategory, PlayerRating, HandicapRule,
    CategoryLevel, RatingSystem
)
from models.rating.services import RatingService

# Assign player category
category = RatingService.assign_category(
    user_id=player.id,
    category=CategoryLevel.B,
    assigned_by_id=admin.id,
    reason="Based on tournament performance"
)

# Get current category
current = PlayerCategory.get_user_current_category(player.id)

# Calculate handicap for match
handicap = RatingService.calculate_handicap(
    player1_id=10,
    player2_id=20,
    base_distance=5
)
# Returns: {player1_distance: 5, player2_distance: 4, explanation: "..."}
```

---

## Category Levels

| Level | Description | Typical Elo |
|-------|-------------|-------------|
| A | Advanced | 1800+ |
| B | Intermediate | 1500-1799 |
| C | Beginner | 1200-1499 |
| D | Novice | <300 |

---

## Models

### PlayerCategory
Player's assigned skill category.

**Key Fields:**
- `user_id`, `category` (A/B/C/D)
- `assigned_by_id`, `assigned_at`, `reason`
- `is_active`, `expires_at`

**Methods:**
- `get_user_current_category(user_id)` - Active category
- `expire_category()` - Deactivate

### PlayerRating
External rating system scores.

**Key Fields:**
- `user_id`, `rating_system` (ELO/INTERNAL)
- `rating_value`, `confidence_level`
- `source`, `last_updated`

### HandicapRule
Rules for distance adjustments based on category differences.

**Key Fields:**
- `category_higher`, `category_lower`
- `distance_adjustment` (positive = advantage to lower)
- `description`, `is_active`

---

## Rating Systems

| System | Source | Usage |
|--------|--------|-------|
| ELO | Internal calculation | Match-based updates |
| INTERNAL | Club assignment | Custom ratings |

---

## Handicap Calculation

```python
# Example: A vs C player, base distance 5
# HandicapRule: A vs C = +2 adjustment for C

player1 (A): distance = 5
player2 (C): distance = 5 + 2 = 7

# C player needs 7 racks to win, A player needs 5
```

---

## Do Not

- **Do not have multiple active categories** - Expire old before assigning new
- **Do not apply handicap without rule** - Check `HandicapRule.is_active`
- **Do not trust expired ratings** - Check `last_updated` for freshness
- **Do not call `db.session.commit()`** - Services use `@transactional`

---

## Cross-References

- **Match**: [../match/CLAUDE.md](../match/CLAUDE.md) - Handicap fields on Match
- **Matchmaking**: [../matchmaking/CLAUDE.md](../matchmaking/CLAUDE.md) - FirstRoundPolicy.RATING
- **User**: [../user/](../user/) - `elo_rating` field
