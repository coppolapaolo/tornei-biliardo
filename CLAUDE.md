# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚀 Quick Reference

### Essential Commands
```bash
# ALWAYS activate virtual environment first (Mac)
source venv/bin/activate

# Start development server
python app.py

# Run all tests (ALWAYS use -n auto for parallel execution)
PYTHONPATH=. pytest tests/new/ -n auto

# Type check (MANDATORY before commits)
pyright

# Format code
black . && flake8
```

### Key Files & Locations
- **Application Entry**: [app.py](app.py) - Flask factory pattern
- **Configuration**: [config.py](config.py) - Environment-based config
- **Database**: `instance/billiard_campionato.db` (SQLite dev)
- **Documentation**: [models/CLAUDE.md](models/CLAUDE.md), [routes/CLAUDE.md](routes/CLAUDE.md), [tests/CLAUDE.md](tests/CLAUDE.md)

### Development Setup
```bash
# Setup virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt requirements-dev.txt

# Run application
python app.py
```

---

## Project Overview

Flask-based **community platform for American Pool enthusiasts** focused on tournament organization and match management.

**Core Features:**
- Tournament (campionati) and competition (gare) organization
- Individual match proposals and community meetups
- Flexible matchmaking strategies (Amalfi, Round-Robin, Elimination, Random)
- Player statistics and challenge system
- Guest access for public tournament viewing

---

## ⏰ Critical: Timezone & Datetime Handling

**IMPORTANT**: The application uses **UTC-based datetime convention** throughout.

### Rules
- **Backend**: Always use `datetime.utcnow()` - NEVER `datetime.now()`
- **Frontend**: Use `|datetime_local` filter to display UTC → Italian time (UTC+2)
- **JavaScript**: Convert local input to UTC before sending to backend

```python
# ✅ CORRECT
now = datetime.utcnow()
user.created_at = datetime.utcnow()

# ❌ WRONG
now = datetime.now()
```

---

## Architecture

### Application Structure
- **Flask Application Factory Pattern**: `create_app()` in `app.py`
- **Domain-Driven Design**: Organized by business domains (competition, matchmaking, rating, etc.)
- **Service Layer Pattern**: Business logic with `@transactional` decorator
- **Strategy Pattern**: Configurable matchmaking algorithms

### Key Components

#### Models (`models/`)
- **User Domain** (`user/`): User, DirectorAssignment, promotion workflows
- **Competition Domain** (`competition/`): Gara, Inscription, RoundManager
- **Match Domain** (`match/`): Match, Set, Rack, multi-set support
- **Matchmaking Domain** (`matchmaking/`): Strategy pattern with Amalfi, Round-Robin, etc.
- **Notification** (`notification/`): Event-driven notification system

#### Database
- **Development**: SQLite (`billiard_campionato.db`) in `instance/` folder
- **Production**: PostgreSQL support via DATABASE_URL
- **ORM**: SQLAlchemy with Flask-SQLAlchemy

---

## Critical Patterns & Examples

### Transaction Management Pattern
All service methods that modify database state MUST use `@transactional`:

```python
from models.transaction.manager import transactional

class GaraService:
    @transactional
    def create_gara(self, campionato_id: int, data: dict) -> Gara:
        gara = Gara(campionato_id=campionato_id, nome=data['nome'])
        db.session.add(gara)
        return gara  # Commit happens automatically
```

### Event System Pattern
```python
from models.events.base import DomainEvent, EventType

# Emit event
DomainEvent.emit(
    event_type=EventType.INSCRIPTION_CREATED,
    entity_id=inscription.id,
    actor_id=user_id
)

# Listen for events
@event_handler(EventType.INSCRIPTION_CREATED)
def handle_inscription_created(event: DomainEvent) -> None:
    NotificationFactory.create_notification(...)
```

### Strategy Pattern (Matchmaking)
```python
from models.matchmaking.service import MatchmakingService
from models.matchmaking.config import MatchmakingStrategy

service = MatchmakingService(gara_id=gara.id, strategy=MatchmakingStrategy.AMALFI)
matches = service.create_next_round()
```

---

## Development Guidelines

### Type Safety (MANDATORY)
- Run `pyright` before every commit - maintain 0 errors
- Use proper type hints for all functions
- Import models explicitly for type inference

### Testing Requirements
- All new features MUST have tests in `tests/new/`
- **CRITICAL**: Use `PYTHONPATH=. pytest tests/new/ -n auto`
- Test isolation: use `db_session.get()` not `refresh()`

### Code Quality Checklist
```bash
# Before every commit:
black . && flake8
pyright
PYTHONPATH=. pytest tests/new/ -n auto
```

---

## Testing Commands

```bash
# Run all tests (RECOMMENDED - fast parallel execution)
PYTHONPATH=. pytest tests/new/ -n auto

# Run specific test types
PYTHONPATH=. pytest tests/new/ -n auto -m unit
PYTHONPATH=. pytest tests/new/ -n auto -m integration

# Run single test
PYTHONPATH=. pytest tests/new/unit/test_specific.py -v -n auto

# Debug single test (without parallel)
PYTHONPATH=. pytest tests/new/unit/test_file.py::test_name -v -s
```

---

## Development Notes

- **Type Safety**: Project maintains 0 pyright errors
- **Transaction Management**: All services use `@transactional` decorator
- **Testing**: Use `-n auto` for parallel execution (user requirement)
- **Architecture principle**: Clean, elegant solutions without over-engineering
- Codebase uses Italian comments in many places
- Application usually running - no need to restart for most changes
- **All 8 use cases fully implemented** with comprehensive integration tests