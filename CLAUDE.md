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

### Common Test Commands
```bash
# Run all tests (fast parallel execution)
PYTHONPATH=. pytest tests/new/ -n auto

# Run specific test types
PYTHONPATH=. pytest tests/new/unit/ -n auto
PYTHONPATH=. pytest tests/new/integration/ -n auto

# Run single test file
PYTHONPATH=. pytest tests/new/unit/test_specific.py -v -n auto

# Debug single test (no parallel, with output)
PYTHONPATH=. pytest tests/new/unit/test_file.py::test_name -v -s

# Run with verbose output and stop on first failure
PYTHONPATH=. pytest tests/new/unit/ -v -x --tb=short
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

## 🎯 Critical Terminology: "Race to N" (Al N)

**IMPORTANT**: The application uses "Race to N" terminology (Italian: "Al N"), NOT "Best of N".

### Race to N Definition
- **"Race to 5"** means: First player to WIN 5 racks wins the match
- A match with race to 5 can end 5-0, 5-1, 5-2, 5-3, or 5-4
- **Maximum racks possible** = (2 × distance) - 1 = 9 racks for race to 5

### Migration Context
The codebase recently migrated from "Best of N" to "Race to N" terminology:
- **Old terminology**: "Best of 9" (play up to 9 racks, most wins)
- **New terminology**: "Race to 5" (first to 5 racks wins)
- **Database field**: `distance` field represents the winning score threshold
- **Legacy field**: `best_of` boolean still exists but should always be False for new matches

### Code Examples
```python
# ✅ CORRECT - Race to N
gara.distance = 5  # First to 5 racks wins
gara.best_of = False  # Always False for Race to N

# Match winning condition
if match.player1_score >= gara.distance:
    # Player 1 won (reached 5 racks first)

# Maximum possible racks
max_racks = (2 * gara.distance) - 1  # = 9 for race to 5

# ❌ WRONG - Old "Best of" thinking
gara.distance = 9  # This means "race to 9", not "best of 9"
```

### Display Formatting
Use the `format_distance` and `format_distance_short` Jinja filters:
```jinja
{{ gara.distance|format_distance }}  {# Outputs: "Al 5" #}
{{ gara.distance|format_distance_short }}  {# Outputs: "5" #}
```

---

## Architecture

### Application Structure
- **Flask Application Factory Pattern**: `create_app()` in `app.py`
- **Domain-Driven Design**: Organized by business domains (competition, matchmaking, rating, etc.)
- **Service Layer Pattern**: Business logic with `@transactional` decorator
- **Strategy Pattern**: Configurable matchmaking algorithms
- **Value Object Pattern**: Distance and Score are immutable value objects (recent refactoring)

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
- **Soft Delete**: Automatic filtering via session event listener (see below)

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

### Soft Delete Pattern (CRITICAL)
**IMPORTANT**: User model has soft delete with automatic filtering enabled.

```python
# ✅ AUTOMATIC FILTERING - Most queries filter soft-deleted users automatically
users = User.query.all()  # Excludes is_deleted=True automatically

# ✅ EXPLICIT FILTERING - When automatic filtering doesn't apply
active_users = User.query.filter_by(is_deleted=False).all()

# ⚠️ INCLUDE DELETED - Use with_deleted() to see soft-deleted records
all_users = User.query.with_deleted().all()

# ✅ SOFT DELETE - Use anonymize() method
user.anonymize()  # Sets is_deleted=True, encrypts PII, preserves FK integrity

# ❌ WRONG - Never hard delete User records
db.session.delete(user)  # This breaks foreign key relationships
```

**Implementation**: Soft delete filtering is implemented via SQLAlchemy session event listener in `models/user/soft_delete_filter.py`. The filter is registered globally in `app.py`.

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

### Value Object Pattern (Distance & Score)
**IMPORTANT**: Recent refactoring introduced immutable value objects for Distance and Score.

```python
from models.match.value_objects import Distance, Score

# ✅ CORRECT - Use value objects for business logic
distance = Distance(5)  # Race to 5
max_racks = distance.max_racks  # 9 (calculated: 2*5-1)
score = Score(player1_racks=3, player2_racks=2, distance=distance)
is_finished = score.is_match_finished()  # False (neither reached 5)

# ✅ DISPLAY - Use format methods
display = distance.format()  # "Al 5"
short = distance.format_short()  # "5"
score_display = score.format()  # "3-2"

# ❌ WRONG - Don't use raw integers for business logic
max_racks = (2 * 5) - 1  # Duplicates business logic, error-prone
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
- Legacy tests (`tests/legacy/`) are not maintained

### Code Quality Checklist
```bash
# Before every commit:
black . && flake8
pyright
PYTHONPATH=. pytest tests/new/ -n auto
```

### Important Gotchas

#### 1. Race to N vs Multi-Set
```python
# Single match - distance = winning racks threshold
gara.distance = 5  # Race to 5 racks

# Multi-set match - match_distance = winning sets threshold
match.is_multi_set = True
match.match_distance = 3  # First to win 3 sets
set.distance = 5  # Each set is race to 5 racks
```

#### 2. Soft Delete Awareness
```python
# ✅ Automatic filtering (most cases)
user = User.query.get(user_id)  # Returns None if soft-deleted

# ✅ Check is_active for Flask-Login
if user.is_active:  # False if is_deleted=True
    # User is active

# ⚠️ Use with_deleted() to bypass filter
all_users = User.query.with_deleted().all()
```

#### 3. Enum Comparisons
```python
# ✅ CORRECT - Use .value
if gara.status == GaraStatus.PLAYING.value:

# ❌ WRONG - Compares to enum object
if gara.status == GaraStatus.PLAYING:
```

#### 4. Distance Value Objects
```python
# ✅ CORRECT - Use value objects
from models.match.value_objects import Distance
distance = Distance(gara.distance)
max_racks = distance.max_racks

# ❌ WRONG - Raw calculation
max_racks = (2 * gara.distance) - 1  # Duplicates logic
```

#### 5. Test Execution Path
```bash
# ✅ CORRECT - Set PYTHONPATH
PYTHONPATH=. pytest tests/new/ -n auto

# ❌ WRONG - Import errors
pytest tests/new/  # Missing PYTHONPATH
```

---

## Testing Commands

```bash
# Run all tests (RECOMMENDED - fast parallel execution)
PYTHONPATH=. pytest tests/new/ -n auto

# Run specific test types
PYTHONPATH=. pytest tests/new/unit/ -n auto
PYTHONPATH=. pytest tests/new/integration/ -n auto

# Run single test file
PYTHONPATH=. pytest tests/new/unit/test_specific.py -v -n auto

# Debug single test (without parallel)
PYTHONPATH=. pytest tests/new/unit/test_file.py::test_name -v -s

# Run with coverage
PYTHONPATH=. pytest tests/new/ -n auto --cov=models --cov=routes

# Run specific test pattern
PYTHONPATH=. pytest tests/new/ -k "amalfi" -v -n auto
```

---

## Development Notes

- **Type Safety**: Project maintains 0 pyright errors
- **Transaction Management**: All services use `@transactional` decorator
- **Testing**: Use `-n auto` for parallel execution (user requirement)
- **Architecture principle**: Clean, elegant solutions without over-engineering
- **Terminology**: "Race to N" (Al N), not "Best of N"
- **Soft Delete**: Automatic filtering via session listener for User model
- **Value Objects**: Distance and Score are immutable value objects
- Codebase uses Italian comments in many places
- Application usually running - no need to restart for most changes
- **All 8 use cases fully implemented** with comprehensive integration tests

---

## Common Mistakes to Avoid

### 1. Wrong Distance Terminology
```python
# ❌ WRONG
gara.distance = 9  # Thinking "best of 9"

# ✅ CORRECT
gara.distance = 5  # Race to 5 (max 9 racks)
```

### 2. Hard Deleting Users
```python
# ❌ WRONG - Breaks foreign keys
db.session.delete(user)

# ✅ CORRECT - Soft delete preserves relationships
user.anonymize()
```

### 3. Missing PYTHONPATH
```bash
# ❌ WRONG - Import errors
pytest tests/new/

# ✅ CORRECT
PYTHONPATH=. pytest tests/new/ -n auto
```

### 4. Forgetting @transactional
```python
# ❌ WRONG - Manual commit error-prone
def create_gara(data):
    gara = Gara(**data)
    db.session.add(gara)
    db.session.commit()  # Manual commit

# ✅ CORRECT - Automatic transaction management
@transactional
def create_gara(data):
    gara = Gara(**data)
    db.session.add(gara)
    return gara  # Commit happens automatically
```

### 5. Not Using Value Objects
```python
# ❌ WRONG - Raw calculation duplicates logic
max_racks = (2 * gara.distance) - 1

# ✅ CORRECT - Use value object
distance = Distance(gara.distance)
max_racks = distance.max_racks
```

---

## Additional Documentation

- **[models/CLAUDE.md](models/CLAUDE.md)**: Complete model reference with all fields and methods
- **[routes/CLAUDE.md](routes/CLAUDE.md)**: Route handlers and API endpoints
- **[tests/CLAUDE.md](tests/CLAUDE.md)**: Testing strategy and test organization
- **[docs/SPECIFICHE.md](docs/SPECIFICHE.md)**: Complete platform requirements (Italian)
- **[docs/usecases/gare.md](docs/usecases/gare.md)**: Detailed workflow documentation
