# Playoff Domain

## Purpose

Playoff system for campionato end-of-season tournaments with qualification management.

**Core Responsibilities:**
- Playoff configuration per campionato
- Qualification criteria and position-based selection
- Player invitation and confirmation workflow
- Elite/Academy division support

---

## Quick Reference

```python
from models.playoff.models import (
    PlayoffConfiguration, PlayoffQualification, PlayoffTournament,
    PlayoffType, QualificationStatus
)
from models.playoff.services import PlayoffService

# Create playoff configuration
config = PlayoffConfiguration(
    campionato_id=campionato.id,
    name="Elite Playoff",
    playoff_type=PlayoffType.TOP_N,
    max_participants=6,
    positions_from=1,
    positions_to=6,
    min_garas_played=5
)

# Generate qualifications from classification
PlayoffService.generate_qualifications(config.id)

# Invite player
PlayoffService.invite_player(qualification_id=qual.id)

# Player confirms
PlayoffService.confirm_participation(qualification_id=qual.id, user_id=player.id)
```

---

## Playoff Types

| Type | Description |
|------|-------------|
| `TOP_N` | Top N players by position |
| `ELITE_ACADEMY` | Split into Elite and Academy divisions |
| `BOTTOM_EXCLUDE` | Exclude top players (e.g., 3rd and below only) |
| `CONDITIONAL` | Custom criteria via JSON |

---

## Models

### PlayoffConfiguration
Defines playoff rules for a campionato.

**Key Fields:**
- `campionato_id`, `name`, `playoff_type`
- `max_participants`, `min_garas_played`
- `positions_from`, `positions_to` (position range)
- `qualification_criteria` (JSON for complex rules)
- `location`, `scheduled_date`, `entry_fee`
- `is_active`, `auto_generate`

### PlayoffQualification
Individual player qualification record.

**Key Fields:**
- `playoff_config_id`, `user_id`, `classification_position`
- `status`: PENDING → CONFIRMED / DECLINED / EXPIRED / REPLACED
- `invited_at`, `responded_at`, `replaced_by_id`

### PlayoffTournament
Actual playoff tournament (links to generated Campionato).

**Key Fields:**
- `playoff_config_id`, `generated_campionato_id`
- `status`, `started_at`, `completed_at`

---

## Qualification Flow

```
Classification Complete
        ↓
generate_qualifications() → Creates PlayoffQualification records
        ↓
invite_player() → Sets status=PENDING, sends notification
        ↓
    ┌───────┴───────┐
    ↓               ↓
confirm()       decline()
    ↓               ↓
CONFIRMED      DECLINED → invite next eligible
```

---

## Do Not

- **Do not manually create qualifications** - Use `generate_qualifications()`
- **Do not skip min_garas_played check** - Players must meet minimum participation
- **Do not forget to invite** - Qualifications are created but not auto-invited
- **Do not call `db.session.commit()`** - Services use `@transactional`

---

## Cross-References

- **Campionato**: [../campionato/CLAUDE.md](../campionato/CLAUDE.md) - Source of playoffs
- **Classification**: [../classification/](../classification/) - Position-based qualification
