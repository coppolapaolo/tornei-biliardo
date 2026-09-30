# Events Domain

## Purpose

Event-driven architecture infrastructure enabling loose coupling between domains.

**Core Responsibilities:**
- Domain event base class and publish-subscribe pattern
- EventBus for central event dispatching
- Event type definitions for all domains
- Notification handlers for event-driven notifications

---

## Quick Reference

```python
from models.events.base import DomainEvent, EventBus
from models.events.match_events import MatchCompletedEvent
from models.events.competition_events import InscriptionCreatedEvent

# Define event handler with decorator
@EventBus.subscribe(MatchCompletedEvent)
def handle_match_completed(event: MatchCompletedEvent):
    # Award XP, update streaks, etc.
    print(f"Match {event.match_id} completed, winner: {event.winner_id}")

# Or register manually
EventBus.register_handler(MatchCompletedEvent, my_handler, priority=10)

# Publish event (typically done by services)
event = MatchCompletedEvent(
    match_id=123,
    player1_id=10, player1_name="mario",
    player2_id=20, player2_name="luigi",
    winner_id=10,
    score="5-3",
    gara_id=456,
)
EventBus.publish(event)
```

---

## Core Classes

### DomainEvent (Abstract Base)
Base class for all domain events.

**Auto-generated Fields:**
- `event_id`: Unique identifier
- `occurred_at`: Timestamp (UTC)
- `domain`: Source domain
- `metadata`: Additional context

**Required Methods:**
- `get_event_type()` - Event type identifier
- `_get_event_data()` - Event-specific data for serialization

### EventBus
Central dispatcher using publish-subscribe pattern.

**Methods:**
- `subscribe(event_type, priority=0)` - Decorator to register handler
- `register_handler(event_type, handler, priority)` - Manual registration
- `publish(event)` - Dispatch to all handlers
- `disable()` / `enable()` - Control event processing

---

## Event Files

| File | Events |
|------|--------|
| `match_events.py` | `MatchProposalCreatedEvent`, `MatchAcceptedEvent`, `MatchCompletedEvent`, `MatchReopenedEvent`, `IndividualMatchCreatedEvent`, `IndividualMatchCompletedEvent` |
| `competition_events.py` | `CampionatoCreatedEvent`, `CompetitionCreatedEvent`, `CompetitionRegistrationOpenedEvent`, `CompetitionStartedEvent`, `CompetitionCompletedEvent`, `InscriptionCreatedEvent`, `DirectorAssignmentAddedEvent`, `DirectorAssignmentRemovedEvent` |
| `user_events.py` | `UserRegisteredEvent`, `DirectorRequestCreatedEvent`, `DirectorRequestProcessedEvent`, `VenueManagerRequestCreatedEvent`, `VenueManagerRequestProcessedEvent` |
| `availability_events.py` | `PlayerAvailabilityCreatedEvent`, `AvailabilityNotificationEvent` |

---

## Handler Registration

Handlers auto-register on import, so every handler module must be imported at
startup: see the "Register … handlers" block in `app.py` (gamification, rating,
demand, SSE bridge, frontend bridge). `models.events.notification_handlers` is
imported by `models/events/__init__.py`.

**Handler Priority:**
- Higher priority = earlier execution
- Default priority = 0
- Use priority for ordering dependencies

---

## Creating New Events

```python
from dataclasses import dataclass, field
from models.events.base import DomainEvent
from typing import Dict, Any

@dataclass
class MyNewEvent(DomainEvent):
    """Event when something important happens."""

    entity_id: int
    actor_id: int
    some_data: str

    def __post_init__(self):
        super().__post_init__()
        self.domain = "my_domain"

    def get_event_type(self) -> str:
        return "my_domain.something_happened"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "actor_id": self.actor_id,
            "some_data": self.some_data
        }
```

---

## Do Not

- **Do not forget to import handlers in app.py** - Handlers must be imported to register
- **Do not publish events outside transactions** - Events should be part of the transactional boundary
- **Do not raise exceptions in handlers** - They're logged but don't stop other handlers
- **Do not assume handler order** - Use priority if order matters
- **Do not publish from handlers** - Can cause infinite loops; use with caution
- **Do not clear `EventBus._handlers = {}` in test fixtures** - This removes ALL handlers globally and breaks other tests running in parallel. Save and restore instead:
  ```python
  original = {k: list(v) for k, v in EventBus._handlers.items()}
  # ... test code ...
  EventBus._handlers = original
  ```

---

## Cross-References

- **Gamification**: [../gamification/CLAUDE.md](../gamification/CLAUDE.md) - XP/streak handlers
- **Notification**: [../notification/CLAUDE.md](../notification/CLAUDE.md) - Notification handlers
- **All Domains**: Events enable decoupled communication
