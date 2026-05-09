# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

### Essential Commands
```bash
# Start development server
python app.py

# Run all tests (use -n 4 for integration to avoid SQLite deadlocks)
pytest tests/new/ -n 4

# Run specific test types
pytest tests/new/unit/ -n auto          # Unit tests: -n auto OK
pytest tests/new/integration/ -n 4      # Integration: MUST use -n 4 (SQLite concurrency)

# Run single test file
pytest tests/new/unit/test_specific.py -v -n auto

# Debug single test (no parallel, with output)
pytest tests/new/unit/test_file.py::test_name -v -s

# Type check (MANDATORY before commits)
pyright

# Format code
black . && flake8

# Internationalization (i18n)
pybabel extract -F babel.cfg -o messages.pot .  # Extract new strings
pybabel update -i messages.pot -d translations  # Update catalogs
pybabel compile -d translations                 # Compile translations

# Documentation
python scripts/generate_schema_docs.py          # Regenerate DB schema docs
```

### Key Files & Locations
- **Application Entry**: `app.py` - Flask factory pattern
- **Configuration**: `config.py` - Environment-based config
- **Database**: `instance/billiard_campionato.db` (SQLite dev)
- **Domain Documentation**: `models/CLAUDE.md`, `routes/CLAUDE.md`, `tests/CLAUDE.md`
- **Template Documentation**: `templates/CLAUDE.md` - Jinja2/JS integration patterns

### CI/CD & Deployment

**Production URL**: https://www.torneibiliardo.it

```bash
# Run migrations (with tracking)
python migrations/runner.py              # Run pending migrations
python migrations/runner.py --status     # Show migration status
python migrations/runner.py --mark-all-applied  # Init existing DB

# Deploy to PythonAnywhere (manual)
cd /home/paolocoppola/mysite
git pull origin main
python migrations/runner.py
# Web app auto-reloads on push via GitHub Actions
```

**GitHub Actions** (`.github/workflows/ci.yml`):
- Runs unit tests and pyright on every push/PR
- Reloads PythonAnywhere web app on push to main
- Git pull and migrations must be run manually or via scheduled task

**PythonAnywhere Scheduled Task** (optional, daily on free tier):
- Setup: Tasks → set time → `/home/paolocoppola/mysite/venv/bin/python /home/paolocoppola/mysite/scripts/auto_deploy.py`
- Runs git pull, pip install, migrations, and reloads the app once per day

---

## Project Overview

Flask-based **community platform for American Pool enthusiasts** focused on tournament organization and match management.

**Core Features:**
- Tournament (campionati) and competition (gare) organization
- Individual match proposals and community meetups
- Flexible matchmaking strategies (Amalfi, Round-Robin, Elimination, Random)
- Player statistics and challenge system
- Gamification system (XP, levels, achievements, streaks, quests)
- Guest access for public tournament viewing

---

## Things to Remember

Before writing any code:

1. **State how you will verify** this change works (test, bash command, browser check, etc.)
2. **Write the test or verification step first**
3. **Then implement the code**
4. **Run verification and iterate** until it passes

---

## Critical Conventions

### 1. Timezone Handling
The application uses **UTC-based datetime convention** throughout via the `utc_now()` utility.

```python
# ✅ CORRECT
from models.base import utc_now
now = utc_now()

# ❌ WRONG
from datetime import datetime
now = datetime.now()       # Local time, not UTC
now = datetime.utcnow()   # Deprecated in Python 3.12+
```

`utc_now()` uses `datetime.now(timezone.utc).replace(tzinfo=None)` internally — non-deprecated API, but returns naive datetimes compatible with SQLite.

- **Column defaults**: Use `default=utc_now` (no parens — callable reference)
- **Frontend**: Use `|datetime_local` filter to display UTC → Italian time (UTC+2)

### 2. "Race to N" Terminology (NOT "Best of N")
The application uses **"Race to N"** terminology (Italian: "Al N").

- **"Race to 5"** = First player to WIN 5 racks wins
- **Maximum racks** = (2 × distance) - 1 = 9 racks for race to 5
- **Database field**: `distance` = winning score threshold

```python
# ✅ CORRECT
gara.distance = 5  # Race to 5 (first to 5 racks wins)
gara.best_of = False  # Always False for Race to N

# ❌ WRONG
gara.distance = 9  # This means "race to 9", not "best of 9"
```

### 3. Transaction Management
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

### 4. Soft Delete (User Model)
User model has soft delete with automatic session-level filtering.

```python
# Automatic filtering - excludes is_deleted=True
users = User.query.all()

# Include deleted records
all_users = User.query.with_deleted().all()

# ✅ CORRECT - Soft delete preserves relationships
user.anonymize()

# ❌ WRONG - Never hard delete User records
db.session.delete(user)  # Breaks foreign key relationships
```

### 5. Enum Comparisons
```python
# ✅ CORRECT - Use .value
if gara.status == GaraStatus.PLAYING.value:

# ❌ WRONG - Compares to enum object
if gara.status == GaraStatus.PLAYING:
```

### 6. Value Objects (Distance & Score)
Use immutable value objects for distance and score business logic:

```python
from models.match.distance import Distance

# Via factory method
distance = Distance.from_gara(gara)
winning_racks = distance.get_winning_racks()

# Via model property
distance_cfg = match.distance_config
```

**ADR-027 — `Distance` VO is the single source of truth for match scoring.**

In ogni path di scoring/validation/aggregation usa `match.distance_config` o
le property `Match.effective_*`. NON leggere `match.gara.distance` o
`match.gara.is_race_to` direttamente — gli override per turno
(`RoundConfiguration`) verrebbero silenziosamente persi.

```python
# ✅ CORRECT - rispetta override per turno
distance = match.distance_config
if distance.is_race_to_racks:
    winning = distance.get_winning_racks()
else:
    total = match.player1_score + match.player2_score
    if total == distance.racks: ...

# ❌ WRONG - bypassa RoundConfiguration
if match.gara.is_race_to:  # override per turno persi!
    winning = match.gara.distance_config.get_winning_racks()
```

L'unico posto autorizzato a leggere `self.gara.distance`/`is_race_to` sono i
fallback dentro `Match.effective_*` (per restituire il default della gara
quando non c'è override). Vedi `docs/adr/ADR-027-round-level-configuration-enforcement.md`.

### 7. Translated Strings in JavaScript (CRITICAL)
When embedding translated strings in JavaScript, **ALWAYS use `|tojson`** filter. This prevents syntax errors from apostrophes and special characters in Italian text.

```javascript
// ❌ WRONG - Apostrophe in "l'avvio" breaks JS string
alert('{{ _("Errore durante l'avvio del turno") }}');
// Generates: alert('Errore durante l'avvio del turno');  // SYNTAX ERROR!

// ✅ CORRECT - |tojson escapes and adds proper quotes
alert({{ _("Errore durante l'avvio del turno")|tojson }});
// Generates: alert("Errore durante l'avvio del turno");  // Works!

// For concatenation with variables:
alert({{ _("Errore:")|tojson }} + ' ' + errorMessage);
```

**Why this matters**: Italian text often contains apostrophes (`l'avvio`, `l'errore`, `l'iscrizione`). Without `|tojson`, these break JavaScript strings and cause silent failures that block ALL JavaScript on the page.

#### Python-style Placeholders in JS Strings (AVOID)
**NEVER use `%(name)s` placeholders** in translated strings that will be interpolated by JavaScript. Flask-Babel attempts to substitute these at render time, causing `KeyError` if no value is provided.

```javascript
// ❌ WRONG - Flask-Babel tries to substitute %(count)s → KeyError
const i18n = {
    confirmDelete: {{ _("Elimina %(count)s elementi?")|tojson }}
};
const msg = i18n.confirmDelete.replace('%(count)s', count);

// ✅ CORRECT - Use JS-style placeholder, bypass Flask-Babel for this string
const i18n = {
    confirmDeleteTemplate: "Elimina {count} elementi?"  // Not translated, or use ngettext
};
const msg = i18n.confirmDeleteTemplate.replace('{count}', count);

// ✅ ALTERNATIVE - Pass the value at render time (if value is known)
const msg = {{ _("Elimina %(count)s elementi?", count=items|length)|tojson }};
```

**Rule**: If JavaScript will do the interpolation, don't use `%(...)s` placeholders in `_()`.

### 8. Onclick Attributes with tojson (CRITICAL)
When using `|tojson` in HTML onclick attributes, **use single quotes for the attribute**:

```html
{# ❌ WRONG - tojson produces "..." which breaks double-quoted attribute #}
<span onclick="myFunc({{ player_name|tojson }})">
{# Renders as: onclick="myFunc("John")" - BROKEN HTML! #}

{# ✅ CORRECT - single quotes for attribute, tojson produces double quotes inside #}
<span onclick='myFunc({{ player_name|tojson }})'>
{# Renders as: onclick='myFunc("John")' - Valid HTML #}
```

**Why**: `|tojson` always produces JSON strings with double quotes. Using single quotes for the onclick attribute avoids quote conflicts.

### 9. Sequential Date Validation for Campionato Gare
Gare within a campionato must have dates in chronological order by `number`:

```python
# ✅ CORRECT - Gara 2 after Gara 1
gara1.date = date(2026, 1, 15)  # number=1
gara2.date = date(2026, 1, 22)  # number=2

# ❌ WRONG - Gara 2 before Gara 1 raises ValueError
gara1.date = date(2026, 1, 22)  # number=1
gara2.date = date(2026, 1, 15)  # number=2 → raises ValueError

# Same-day gare are allowed if time is sequential
gara1.date, gara1.time = date(2026, 1, 15), time(14, 0)  # number=1
gara2.date, gara2.time = date(2026, 1, 15), time(18, 0)  # number=2 → OK
```

**Rules**:
- Gara N must have date/time `>=` the gara with highest number `< N`
- Gara N must have date/time `<=` the gara with lowest number `> N`
- Standalone gare (no campionato) have no sequential validation

See `docs/adr/ADR-016-gara-sequential-date-validation.md` for details.

### 10. Migration Naming Convention
New migrations use date-prefixed naming:

```bash
# Create new migration file
touch migrations/20260125_description.py
```

Migration files must:
- Define `migration_name` variable for tracking
- Be idempotent (safe to run multiple times)
- Use `op.execute()` for raw SQL on SQLite

### 11. Email Service (Flask-Mail)
Use `EmailService` for all email sending:

```python
from models.shared.email_service import EmailService

email_service = EmailService()
email_service.send_email(
    to=user.email,
    subject=_("Subject"),
    template="email/template.html",
    **template_context
)
```

Configuration via environment: `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`.
See `docs/AUTHENTICATION.md` for full setup.

### 12. Gamification Frontend Bridge
Domain events trigger toast notifications via the frontend bridge:

```python
from models.gamification.frontend_bridge import flash_gamification_event, GamificationEventType

flash_gamification_event(GamificationEventType.XP, {
    "amount": 50,
    "title": _("XP Guadagnati!"),
    "subtitle": _("Continua così!")
})
```

See `docs/GAMIFICATION_V2.md` for event types and animation system.

---

## Architecture

### Application Structure
- **Flask Application Factory Pattern**: `create_app()` in `app.py`
- **Domain-Driven Design**: Organized by business domains
- **Service Layer Pattern**: Business logic with `@transactional` decorator
- **Strategy Pattern**: Configurable matchmaking algorithms
- **Event-Driven Architecture**: Domain events for loose coupling

### Key Domains (`models/`)

| Domain | Purpose | Key Files |
|--------|---------|-----------|
| **user/** | Users, roles, permissions | User, DirectorAssignment, VenueManagement |
| **competition/** | Gara, Inscription, round management | Gara, GaraService |
| **match/** | Match, Set, Rack, scoring | Match, multi-set support |
| **matchmaking/** | Pairing strategies | Amalfi, Round-Robin, Elimination, Random |
| **gamification/** | XP, levels, achievements, streaks | LevelService, StreakService |
| **notification/** | Event-driven notifications | NotificationFactory |
| **individual_match/** | Casual match proposals | MatchProposal, PlayerAvailability |
| **events/** | Domain event system | DomainEvent, EventBus |

### Database
- **Development**: SQLite (`instance/billiard_campionato.db`)
- **Production**: SQLite on PythonAnywhere (`/home/paolocoppola/mysite/instance/billiard_campionato.db`)
- **ORM**: SQLAlchemy with Flask-SQLAlchemy

---

## Common Patterns

### Event System
```python
from models.events.base import DomainEvent, EventType

# Emit event
DomainEvent.emit(
    event_type=EventType.INSCRIPTION_CREATED,
    entity_id=inscription.id,
    actor_id=user_id
)
```

### Matchmaking Strategies
```python
from models.matchmaking.service import MatchmakingService
from models.matchmaking.config import MatchmakingStrategy

service = MatchmakingService(gara_id=gara.id, strategy=MatchmakingStrategy.AMALFI)
matches = service.create_next_round()
```

**Note**: The Random Anti-Rematch strategy uses `networkx` for maximum cardinality matching on the anti-rematch graph. Don't reimplement graph algorithms — use `nx` (already in requirements.txt).

### Multi-Set Matches
```python
# Single match - distance = winning racks threshold
gara.distance = 5  # Race to 5 racks

# Multi-set match - match_distance = winning sets threshold
match.is_multi_set = True
match.match_distance = 3  # First to win 3 sets
set.distance = 5  # Each set is race to 5 racks
```

---

## Development Guidelines

### Type Safety (MANDATORY)
- Run `pyright` before every commit - maintain 0 errors
- Use proper type hints for all functions
- Pyright config (`pyrightconfig.json`) disables `reportCallIssue` due to SQLAlchemy mixin inheritance issues (pyright doesn't recognize that `db.Model` generates constructors accepting column names as kwargs)

### Code Quality Checklist
```bash
# Before every commit:
black . && flake8
pyright
pytest tests/new/unit/ -n auto && pytest tests/new/integration/ -n 4
```

### Testing Requirements
- All new features MUST have tests in `tests/new/`
- Test isolation: use `db_session.get()` not `refresh()`
- Legacy tests (`tests/legacy/`) are not maintained
- Unit tests: `-n auto` OK; Integration tests: `-n 4` (SQLite concurrency)
- **EventBus isolation**: Never clear `EventBus._handlers = {}` in tests - preserve and restore:
  ```python
  @pytest.fixture(autouse=True)
  def preserve_handlers():
      original = {k: list(v) for k, v in EventBus._handlers.items()}
      yield
      EventBus._handlers = original
  ```

---

## Common Mistakes to Avoid

| Mistake | Correct Approach |
|---------|------------------|
| `datetime.now()` or `datetime.utcnow()` | `utc_now()` from `models.base` |
| `gara.distance = 9` (thinking best of 9) | `gara.distance = 5` (race to 5) |
| `db.session.delete(user)` | `user.anonymize()` |
| `gara.status == GaraStatus.PLAYING` | `gara.status == GaraStatus.PLAYING.value` |
| `pytest tests/new/integration/ -n auto` | `pytest tests/new/integration/ -n 4` (SQLite deadlock) |
| Manual `db.session.commit()` | Use `@transactional` decorator |
| `alert('{{ _("l'errore") }}')` in JS | `alert({{ _("l'errore")\|tojson }})` |
| `{{ _("%(count)s items")\|tojson }}` + JS replace | Use `"{count} items"` with JS replace |
| `onclick="func({{ x\|tojson }})"` | `onclick='func({{ x\|tojson }})'` (single quotes) |
| Gara N with date before gara N-1 | Ensure date/time is sequential by number (ADR-016) |
| `EventBus._handlers = {}` in tests | Preserve and restore handlers (breaks notifications/gamification) |
| Manual SMTP sending | Use `EmailService` for all emails |
| `max(rack_number) WHERE is_deleted=False` | Include ALL records for sequential IDs with UNIQUE constraints |
| `@transactional` on facade AND inner service | Only decorate the innermost method (nested causes rollback) |
| `match.gara.distance` in scoring/validation | Use `match.distance_config` or `match.effective_*` (ADR-027) |
| `RoundConfiguration` salvato solo in `localStorage` | API endpoint `POST /admin/gara/<id>/round-config/<n>` (ADR-027) |

---

## Additional Documentation

- **[docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md)**: Auto-generated database schema (tables, columns, FKs) - regenerate with `python scripts/generate_schema_docs.py`
- **[docs/AUTHENTICATION.md](docs/AUTHENTICATION.md)**: Email verification, password reset, Flask-Mail setup
- **[docs/GAMIFICATION_V2.md](docs/GAMIFICATION_V2.md)**: Frontend bridge, toast notifications, mascot system
- **[models/CLAUDE.md](models/CLAUDE.md)**: Complete model reference with all fields and methods
- **[routes/CLAUDE.md](routes/CLAUDE.md)**: Route handlers and API endpoints
- **[tests/CLAUDE.md](tests/CLAUDE.md)**: Testing strategy and test organization
- **[models/gamification/CLAUDE.md](models/gamification/CLAUDE.md)**: Gamification system (XP, achievements, streaks)
- **[docs/SPECIFICHE.md](docs/SPECIFICHE.md)**: Complete platform requirements (Italian)
- **[docs/usecases/gare.md](docs/usecases/gare.md)**: Detailed workflow documentation
- **[docs/UI_CONVENTIONS.md](docs/UI_CONVENTIONS.md)**: UI conventions (icons, colors, design decisions)
- **[docs/adr/](docs/adr/)**: Architecture Decision Records (ADR)
- **[docs/adr/ADR-027-round-level-configuration-enforcement.md](docs/adr/ADR-027-round-level-configuration-enforcement.md)**: Override per turno persistiti server-side + uso obbligatorio di `Distance` VO nello scoring

---

## Debugging Tips

### @transactional Not Persisting Data
If data changes in memory but doesn't persist to DB, check if the decorator is actually applied:

```python
# Check if decorator is applied
from models.competition.state_service import StateService
func = StateService.some_method
print(f'Has __wrapped__: {hasattr(func, "__wrapped__")}')  # False = no decorator!

# Compare imports (circular import detection)
from models.base import transactional as base_t
from models.transaction.manager import transactional as manager_t
print(f'Same: {base_t is manager_t}')  # False = circular import problem!
```

See `docs/adr/ADR-012-transactional-circular-import-fix.md` for a detailed case study.

---

## Development Notes

- Codebase uses Italian comments in many places
- Application usually running - no need to restart for most changes
- All 8 tournament use cases fully implemented with comprehensive integration tests
- Gamification system is event-driven and decoupled from core domains

---

## Audit Status

Codebase audit completed (Dec 2025): 0 FAIL, 0 WARNING. Details in `docs/AUDIT_REFACTORING_PLAN.md`.