# Location Domain

## Purpose

Venue management and player availability tracking for match coordination.

**Core Responsibilities:**
- Billiard hall registry with facility details
- Player availability per venue
- Location-based player discovery
- Venue manager assignments

---

## Quick Reference

```python
from models.location.models import BilliardHall, UserLocationAvailability, DayOfWeek
from models.location.services import LocationService

# Create venue
venue = BilliardHall(
    name="Sala Biliardo Roma",
    address="Via Roma 123",
    city="Roma",
    number_of_tables=8,
    hourly_rate=15.00
)

# Set player availability
LocationService.set_user_availability(
    user_id=player.id,
    billiard_hall_id=venue.id,
    available_days=[DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY, DayOfWeek.FRIDAY],
    preferred_time_start="18:00",   # "%H:%M"
    preferred_time_end="22:00",
    is_available=True
)

# Find players available at venue at a given time
players = LocationService.find_available_players(
    billiard_hall_id=venue.id,
    proposed_datetime=datetime(2026, 10, 14, 19, 0),
)
```

---

## Models

### BilliardHall
Venue with facility and contact information.

**Key Fields:**
- `name`, `address`, `city`, `postal_code`, `country`
- `phone`, `email`, `website`
- `number_of_tables`, `table_names` (JSON), `table_types` (JSON)
- `business_hours` (JSON), `hourly_rate`, `currency`
- `is_active`, `verified`, `added_by_id`
- `latitude`, `longitude` (for mapping)

### UserLocationAvailability
Player availability at a specific venue.

**Key Fields:**
- `user_id`, `billiard_hall_id`
- `is_available`
- `available_days` (JSON list of DayOfWeek values)
- `preferred_time_start`, `preferred_time_end`
- `notify_on_proposals`, `notify_on_cancellations`, `advance_notice_hours`, `max_distance_km`

### DayOfWeek (Enum)
`MONDAY=1` through `SUNDAY=7`

---

## Services

### LocationService
- `create_billiard_hall(...)` - Create venue
- `set_user_availability(...)` - Set/update player availability
- `find_available_players(billiard_hall_id, proposed_datetime)` - Find opponents
- `get_user_locations(user_id)` - All venues for user

`get_available_players_at_venue` and `notify_players_of_availability` live on
`AvailabilityService` (`models/individual_match/availability_service.py`).

---

## Do Not

- **Do not store JSON manually** - Use model methods for `table_names`, `business_hours`
- **Do not query without venue context** - Always scope availability to venue
- **Do not call `db.session.commit()`** - Services use `@transactional`
- **Do not trust unverified venues** - Check `verified` flag for official venues

---

## Cross-References

- **Individual Match**: [../individual_match/CLAUDE.md](../individual_match/CLAUDE.md) - Location-based proposals
- **User**: [../user/](../user/) - VenueManagement for venue managers
- **Campionato**: [../campionato/](../campionato/) - `default_venue_id`
