# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 📑 Table of Contents

- [🚀 Quick Reference](#-quick-reference)
- [Project Overview](#project-overview)
- [Commands](#commands)
  - [Development Setup](#development-setup)
  - [Testing](#testing)
  - [Code Quality](#code-quality)
- [Architecture](#architecture)
- [Key Business Logic](#key-business-logic)
- [Recent Development History](#recent-development-history)
- [Critical Patterns & Examples](#critical-patterns--examples)
  - [Transaction Management Pattern](#transaction-management-pattern)
  - [Event System Pattern](#event-system-pattern)
  - [Notification Factory Pattern](#notification-factory-pattern)
  - [Strategy Pattern (Matchmaking)](#strategy-pattern-matchmaking)
  - [Service Layer Pattern](#service-layer-pattern)
- [Development Guidelines](#development-guidelines)
- [Production Deployment](#production-deployment)
- [Development Notes](#development-notes)
- [Documentation Structure](#documentation-structure)
- [Refactoring Documentation](#refactoring-documentation)

---

## 🚀 Quick Reference

### Essential Commands
```bash
# Activate virtual environment (REQUIRED for all commands)
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
- **Main Documentation**: This file + subdirectory CLAUDE.md files
- **Specifications**: [docs/SPECIFICHE.md](docs/SPECIFICHE.md) - Complete platform specs
- **Use Cases**: [docs/usecases/](docs/usecases/) - UC01.md, UC02.md, gare.md, convenzioni.md
- **Architecture Decisions**: [docs/adr/](docs/adr/) - ADR-001 and others
- **Refactoring Docs**: [docs/refactoring/](docs/refactoring/) - README.md, REFACTOR_PROGRESS.md

### New Developer Checklist
- [ ] Clone repo and setup virtual environment
- [ ] Install dependencies: `pip install -r requirements.txt requirements-dev.txt`
- [ ] Run application: `python app.py` (creates DB automatically)
- [ ] Run tests: `PYTHONPATH=. pytest tests/new/ -n auto` (should all pass)
- [ ] Read [models/CLAUDE.md](models/CLAUDE.md), [routes/CLAUDE.md](routes/CLAUDE.md), [tests/CLAUDE.md](tests/CLAUDE.md)
- [ ] Read [docs/SPECIFICHE.md](docs/SPECIFICHE.md) for platform overview
- [ ] Review recent development history below
- [ ] Check refactoring status: [docs/refactoring/REFACTOR_PROGRESS.md](docs/refactoring/REFACTOR_PROGRESS.md)

### Quick Architecture Overview
- **Pattern**: Domain-Driven Design with Service Layer + Strategy Pattern
- **Transaction Management**: All services use `@transactional` decorator
- **Type Safety**: 0 pyright errors maintained across codebase
- **Testing**: Unit/Integration/E2E with pytest markers, parallel execution with `-n auto`

---

## Project Overview

This is a Flask-based **community platform for American Pool enthusiasts** that aspires to become the central hub for pool players. While currently focused on tournament organization and match management, the platform is designed to support any pool-related activity and foster a vibrant community of players.

**Current Features:**
- Tournament (campionati) and competition (gare) organization
- Individual match proposals and community meetups
- Player statistics and performance tracking
- Flexible matchmaking strategies (Amalfi, Round-Robin, Elimination, Random)
- Challenge system for skill development
- Venue management and location-based features
- Player availability system for community coordination
- Advanced round management and match modification
- Multi-set match system with discipline rotation
- Guest access system for public tournament viewing

**Community Vision:**
- Central platform for pool players to connect and organize
- Support for all American Pool disciplines (8-ball, 9-ball, 10-ball, One Pocket, etc.)
- Future expansion to any pool-related activities and events
- Player rating systems and skill development tools
- Social features for building the pool community

## Commands

### Development Setup
```bash
# Setup virtual environment
python3 -m venv venv
source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run application
python app.py
```

### Testing

**IMPORTANT**: Always use `-n auto` for parallel test execution (user requirement).

```bash
# Run all tests (RECOMMENDED - fast parallel execution)
PYTHONPATH=. pytest tests/new/ -n auto

# Run specific test types (parallel)
PYTHONPATH=. pytest tests/new/ -n auto -m unit
PYTHONPATH=. pytest tests/new/ -n auto -m integration
PYTHONPATH=. pytest tests/new/ -n auto -m e2e

# Run with coverage
pytest --cov

# Run single test with proper path (CRITICAL for imports)
PYTHONPATH=. pytest tests/new/unit/test_specific.py -v -n auto

# Run specific test file or function
PYTHONPATH=. pytest tests/new/integration/test_gare_usecase_1_amalfi_complete_workflow.py -v -n auto
PYTHONPATH=. pytest tests/new/unit/test_file.py::TestClass::test_method -v -n auto

# Run with verbose output and stdout capture disabled
PYTHONPATH=. pytest tests/new/unit/test_specific.py -v -s -n auto

# Stop on first failure with short traceback
PYTHONPATH=. pytest tests/new/unit/ -x --tb=short -n auto

# Quick integration test execution with line-only traceback
PYTHONPATH=. pytest tests/new/integration/ -n auto --tb=line

# Run legacy tests (if needed, without -n auto due to compatibility)
pytest tests/legacy/
```

#### Test Execution Troubleshooting

**Import Errors (ModuleNotFoundError)**:
- ✅ **Always use** `PYTHONPATH=.` prefix for test commands
- Example: `PYTHONPATH=. pytest tests/new/unit/test_file.py`

**Test Isolation Issues**:
- Use `db_session.get()` instead of `db_session.refresh()` in integration tests
- Avoid session conflicts by using proper transaction scoping
- Check for shared state between parallel test runs

**Slow Test Execution**:
- ✅ **Always use** `-n auto` for parallel execution (speeds up tests significantly)
- For debugging, run single test without `-n auto`: `PYTHONPATH=. pytest tests/new/unit/test_file.py::test_name -v -s`

**Flaky Tests**:
- Usually caused by improper database state management
- Check for missing `db_session.commit()` or transaction rollback issues
- Review test fixtures and ensure proper cleanup

**All Tests Must Pass Before Refactoring**:
- See [docs/refactoring/README.md](docs/refactoring/README.md) for test-first policy
- 100% pass rate required before any architectural changes

### Code Quality
```bash
# Format code
black .

# Lint code
flake8

# Type check (MANDATORY before commits)
pyright

# Clean imports
autoflake --remove-all-unused-imports --recursive --in-place .
```

## Architecture

### Application Structure
- **Flask Application Factory Pattern**: `create_app()` in `app.py` with environment-based configuration
- **Domain-Driven Design**: Organized by business domains (competition, matchmaking, rating, etc.)
- **Service Layer Pattern**: Business logic separated into service modules with transaction support
- **Strategy Pattern**: Configurable matchmaking algorithms (Amalfi, round-robin, elimination, random)

### Directory Documentation
Each major directory contains detailed documentation in its own CLAUDE.md file:
- **[models/CLAUDE.md](models/CLAUDE.md)**: Domain models, database architecture, and data structures
- **[routes/CLAUDE.md](routes/CLAUDE.md)**: API endpoints, request handling, and route organization
- **[templates/CLAUDE.md](templates/CLAUDE.md)**: UI components, template architecture, and frontend patterns
- **[tests/CLAUDE.md](tests/CLAUDE.md)**: Testing strategy, test organization, and quality assurance

### Key Components

#### Matchmaking Engine (`models/matchmaking/`)
Flexible tournament pairing system with multiple strategies:
- **Amalfi Strategy**: ✅ Specification-compliant implementation in `models/matchmaking/strategies/amalfi.py`
- **Round-Robin**: All-play-all tournament format
- **Direct Elimination**: Knockout tournament system
- **Random Strategy**: Random pairing with anti-rematch protection
- **Strategy Registration**: ✅ Unified strategy system with consolidated registration
- Configurable first round policies (random, classification-based, rating-based)
- Flexible odd-player handling (byes, trio matches, challenges)
- **Idempotent Operations**: Round creation prevents duplicates
- Real-time classification updates
- Entry point: Strategy pattern through `MatchmakingService`

#### Models (`models/`)
Domain-Driven Design architecture with modular organization:

##### Core Infrastructure
- **Base**: `base.py` - Modular mixins (UtilityMixin, TimestampMixin, SoftDeleteMixin, AuditMixin)
- **Status Enums**: `status_enum.py` - Centralized state enumerations (GaraStatus, MatchStatus, TournamentStatus)
- **Custom Fields**: `fields.py` - EncryptedString for sensitive data (email, phone)
- **Exceptions**: Domain-specific exception handling

##### Primary Business Domains

**User Domain** (`user/`):
- `User`: Core user entity with role-based permissions, soft delete, encrypted personal data
- `TournamentDirector`, `DirectorRequest`: Director promotion system
- `VenueManagerRequest`, `VenueManagement`: Location management permissions

**Competition Domain** (`competition/`):
- `Gara`: Competition rounds (standalone or campionato-based) with time, location, description
- `Inscription`: Player registration for competitions with waitlist support
- **`RoundManager`**: Advanced round management with locking mechanisms and bulk operations
- **Enhanced Services**: Idempotent round creation, match modification validation, cancellation workflows

**Match Domain** (`match/`):
- `Match`: Core match entity with multi-set support, current set tracking
- `Rack`, `MatchResult`: Detailed scoring system for individual racks
- `TrioMatch`: Three-player match support for odd numbers
- **`Set`, `SetRack`**: Multi-set match models with multi-discipline support and rotation

**Matchmaking Domain** (`matchmaking/`):
- Strategy pattern implementation with configurable algorithms
- `AmalfiBinding`: Integration with Amalfi engine
- Strategies: `AdvancedAmalfi`, `RoundRobin`, `DirectElimination`, `RandomAntiRematch`
- **Fixed Registration**: Resolved conflicts between amalfi and amalfi_unified strategies
- Configuration and policy management

##### Specialized Domains

**Classification** (`classification/`): Player rankings and encounter tracking
**Individual Match** (`individual_match/`): 
- Match proposal system with invitations and status management
- **`AvailabilityService`**: Player availability system with location-based matching and notifications
**Challenge** (`challenge/`): Skill challenges and attempts with favorites, X-replacement integration
**Exam** (`exam/`): Challenge-based examination system
**Rating** (`rating/`): Player rating system with handicap rules and categories
**Notification** (`notification/`): Comprehensive notification system with templates and preferences
**Location** (`location/`): Billiard halls and user location availability
**Playoff** (`playoff/`): Elimination tournaments with qualification system
**Tiebreaker** (`tiebreaker/`): Spot shots and rally attempts for tie resolution

##### Cross-Domain Services
- **Orchestration**: Multi-domain operation coordination with OperationResult tracking
- **Transaction**: Distributed transaction management
- **Caching**: Performance optimization with cache manager
- **Optimization**: Query optimizer for database performance

#### Routes (`routes/`)
RESTful endpoints organized by domain:
- `admin/`: Administrative functions split into sub-modules
  - **Enhanced Competition Routes**: Advanced round management, match modification, bulk operations
- `auth.py`: Authentication and authorization
- **`player.py`**: Player management, profiles, and availability system routes
- `challenge.py`: Challenge system
- `individual_match.py`: Individual match management
- `rating.py`: Rating system
- **`main.py`**: Enhanced with guest access routes for public tournament viewing

#### Templates (`templates/`)
Component-based UI with Bootstrap 5:
- **`public/`**: Guest-accessible templates for tournament viewing
- **Enhanced index**: Displays both campionatos and standalone tournaments
- Component-based architecture for reusability

#### Utils (`utils/`)
Shared utilities:
- Database utilities and statistics
- Encryption helpers
- Status UI filters for Jinja templates
- Data reset utilities

### Database
- **Development**: SQLite (`billiard_campionato.db`) in `instance/` folder
- **Production**: PostgreSQL support via DATABASE_URL
- **ORM**: SQLAlchemy with Flask-SQLAlchemy
- **Migrations**: Manual database management
- **Soft Delete**: Implemented for user records

### Configuration
- Environment-based configuration in `config.py`
- Default admin user auto-creation
- Debug mode enabled in development
- Secret key and database URL configurable via environment variables

### Testing Strategy
- **Pytest** with custom markers (unit, integration, e2e, legacy)
- **CRITICAL**: Use `PYTHONPATH=. pytest tests/new/` for proper imports
- Test discovery in `tests/new/` (legacy tests excluded by default)
- **8 Comprehensive Use Case Tests**: Complete integration test coverage
- Coverage reporting with route exclusion
- Integration tests use actual database connections

### Code Style & Quality Assurance
- **Black** formatting (88 character line length)
- **Flake8** linting with extended ignore rules
- **Pyright** type checking - MANDATORY for all new code (currently 0 errors)
- Import organization with autoflake
- Type hints REQUIRED for all new functions and methods
- **Testing** REQUIRED for all new features and bug fixes

## Key Business Logic

### Community Platform Features

#### Individual Match System
- **Match Proposals**: Players can invite others for casual games
- **Open Invitations**: Community-wide match requests
- **Location Integration**: Find players and venues nearby
- **Flexible Scheduling**: Accommodate different availability patterns
- **Availability System**: Location-based player discovery and notification system

#### Tournament System

##### Competition Flow (All 8 Use Cases Implemented)
1. **Tournament Creation**: Admin/Directors create tournaments with flexible strategies
2. **Registration Management**: Inscription handling with waitlist support
3. **Round Execution**: Multiple strategies with anti-rematch logic
4. **Advanced Modification**: Round management with locking and bulk operations
5. **Multi-Set Support**: Complex match formats with discipline rotation
6. **Challenge Integration**: X-replacement system and skill challenges
7. **Guest Access**: Public viewing for community engagement
8. **Player Coordination**: Availability-based match proposals

### User Roles
- **Admin**: System administrator and community moderator
- **Director**: Tournament organizers and community leaders (elevated players)
- **Player**: Community members who can participate in all activities
- **Guest**: Visitors exploring the community (public tournament access)

### Community-Centered Design
Platform built to foster pool community growth and engagement:

**Core Community Features**:
- **Player Connections**: Connect with local and regional pool players
- **Match Organization**: From casual games to formal tournaments
- **Skill Development**: Challenge system and performance tracking
- **Venue Integration**: Find and connect players at billiard halls
- **Social Interaction**: Player profiles, statistics, and community building
- **Availability Coordination**: Location-based player discovery and matching

**Tournament Flexibility**:
- **Multiple Strategies**: Amalfi, Round-Robin, Elimination, Random pairing
- **All Pool Disciplines**: 8-ball, 9-ball, 10-ball, One Pocket, Straight Pool
- **Flexible Formats**: From casual meetups to formal championships
- **Scalable Events**: Support for any size community event
- **Advanced Management**: Round locking, bulk operations, match modifications

## Recent Development History

### Local Date Formatting System (October 2025) - ✅ COMPLETED
Implemented browser-locale date formatting to eliminate inconsistencies between `dd/mm/yyyy` and `mm/dd/yyyy` formats:

### Local Date Formatting System (October 2025) - ✅ COMPLETED
Implemented browser-locale date formatting to eliminate inconsistencies between `dd/mm/yyyy` and `mm/dd/yyyy` formats:

#### Implementation
- **JavaScript Auto-Formatting**: Added `TourneyUtils.formatDate()` functions in `base.html`
- **Locale Detection**: Uses `navigator.language` with fallback to `'it-IT'`
- **Jinja Filters**: Created `date_local`, `datetime_local`, `time_local` filters
- **Template Migration**: Automated migration of 50+ templates with script
- **Pattern**: `{{ date|date_local }}` replaces `{{ date.strftime('%d/%m/%Y') }}`
- **UTC Consistency**: Both `data-utc` and `data-datetime` use same locale

- ✅ **Formato Consistente**: Sempre dd/mm/yyyy indipendentemente dal browser dell'utente
- ✅ **Consistency**: Unified format across entire application
- ✅ **User Experience**: Users see dates in their preferred format
- ✅ **Maintainability**: Centralized date formatting logic

#### Migration Script
- `scripts/migrate_date_formatting.py`: Automated template conversion
- Replaced 56 `strftime()` calls across 50 template files
- See [docs/LOCAL_DATE_FORMATTING.md](docs/LOCAL_DATE_FORMATTING.md) for complete guide

### Type Safety & Architectural Fixes (October 2025) - ✅ COMPLETED
Phase 4 refactoring completed with focus on type safety and architectural corrections:

#### Phase 4.1: Enum Migration
- **Completed**: Replaced 15+ string literals with existing enum values
- **New**: Created EntityType enum for DirectorAssignment
- **Refactored**: Delegated Gara validation methods to StrategyConfiguration
- **Files Modified**: 4 model files with 0 pyright errors, 0 flake8 errors

#### Phase 4.2: Rating System Fix (Critical Architectural Correction)
- **Problem**: Rating systems (Fargo/Elo) incorrectly modeled as Gara property
- **Solution**: Moved ratings to User model where they belong conceptually
- **Changes**:
  - ✅ Added `User.fargo_rating` and `User.elo_rating` fields
  - ✅ Removed `Gara.rating_type` field and RatingType enum
  - ✅ Refactored AmalfiStrategy to use User ratings directly
  - ✅ Updated routes and templates (removed rating_type selectors)
- **Impact**: Correct separation of concerns - Rating (Player) vs Scoring (Classification)
- **Files Modified**: 8 files across models, routes, and templates
- **Quality**: 0 pyright errors, 0 flake8 errors, backward compatible

See [docs/refactoring/CHANGELOG_PHASE_4.md](docs/refactoring/CHANGELOG_PHASE_4.md) for complete details.

### Amalfi Algorithm Refactoring (September 2025) - ✅ COMPLETED
Major refactoring successfully completed - Amalfi algorithm consolidated into unified strategy pattern with full specification compliance:

#### Achievements Completed
1. **New Amalfi Strategy**: ✅ Created `models/matchmaking/strategies/amalfi.py` with BaseStrategy implementation
2. **Directory Migration**: ✅ Complete migration `amalfi/` → `models/matchmaking/strategies/`
3. **Algorithm Consolidation**: ✅ Unified amalfi strategies with specification-compliant behavior
4. **Service Integration**: ✅ MatchmakingService fully integrated with new strategy pattern

#### Implementation Success
- **Specification Compliance**: ✅ New AmalfiStrategy follows clean, specification-compliant interface
- **Test Compatibility**: ✅ All unit tests passing (9/9) with new implementation
- **Integration Working**: ✅ Strategy pattern unified and functional across all use cases
- **Performance Optimized**: ✅ Consolidated implementation more efficient and maintainable

#### Files Successfully Migrated
- `models/matchmaking/strategies/amalfi.py` (✅ NEW - specification-compliant, 15KB)
- `models/matchmaking/service.py` (✅ UPDATED for new strategy pattern)
- `models/matchmaking/bootstrap.py` (✅ UPDATED registration system)
- `models/matchmaking/registry.py` (✅ UPDATED unified registry)
- `amalfi/` directory (✅ COMPLETELY REMOVED)

#### Migration Results
✅ **100% Complete**: Amalfi algorithm successfully modernized and integrated
✅ **Performance**: Improved efficiency through consolidated implementation
✅ **Maintainability**: Clean architecture following established patterns
✅ **Compatibility**: Full backward compatibility maintained for all use cases

### Complete Use Case Implementation (September 2025)
Major architectural completion implementing all 8 documented use cases:

#### New Systems Implemented
1. **Player Availability System** (`models/individual_match/availability_service.py`):
   - Location-based player discovery and matching
   - Notification system for availability alerts
   - Venue-specific availability management

2. **Advanced Round Management** (`models/competition/round_manager.py`):
   - Round locking mechanisms for match modifications
   - Bulk operations for match management
   - Enhanced validation and state tracking

3. **Multi-Set Match Integration**:
   - Verified and enhanced Set/SetRack models
   - Multi-discipline support with rotation modes
   - Current set tracking and completion logic

4. **Challenge System Integration**:
   - X-replacement functionality for bye substitution
   - Complete challenge workflow with scoring
   - Integration with competition system

5. **Guest Access System**:
   - Public routes for tournament viewing
   - Guest-accessible templates
   - Enhanced index with standalone tournaments

#### Technical Improvements
- **Fixed Strategy Registration**: Resolved conflicts between amalfi strategies
- **Idempotent Operations**: Round creation prevents duplicates
- **Type Safety**: Achieved 0 pyright errors across codebase
- **Comprehensive Testing**: 8 integration test files covering all workflows
- **Enhanced Anti-Rematch**: Improved algorithm for better player selection

#### Files Modified/Added (26 files, +7,588/-282 lines)
- **New Services**: `availability_service.py`, `round_manager.py`
- **Enhanced Core**: Competition services, matchmaking engine, Amalfi algorithm
- **New Routes**: Advanced competition management, availability system
- **Templates**: Public access templates, enhanced index
- **Tests**: 8 comprehensive use case integration tests
- **Documentation**: Complete use case specifications

### Comprehensive Competition Management Fixes (September 2025)
Major bug fix session addressing multiple competition workflow issues:

#### Core Issues Fixed
1. **Expired Inscriptions Management**: Added ability to start first round or cancel competition with participant notifications when inscriptions expire
2. **Match Display Issues**: Fixed partial results display for in-progress matches and maintained editability for completed matches
3. **Rack Management**: Resolved rack removal functionality and proper business logic validation for "best of N" vs "exactly N" match formats
4. **Director Permissions**: Enabled director inscription functionality on dashboard
5. **Amalfi Preview System**: Implemented campionato pairing preview without database persistence
6. **Round Management**: Made start round endpoint idempotent to prevent duplicate matches, fixed round completion detection
7. **UI Consistency**: Resolved current round display inconsistencies between different UI components
8. **Statistics Display**: Fixed match statistics in results overview
9. **Status Labels**: Changed "Campionato Completato" to "Gara Completata" for completed competitions
10. **Guest Classification**: Implemented fallback system showing RoundClassification from completed Amalfi provas when general campionato classification unavailable

## Critical Patterns & Examples

### Transaction Management Pattern

All service methods that modify database state MUST use the `@transactional` decorator:

```python
from models.transaction.manager import transactional

class GaraService:
    @transactional
    def create_gara(self, campionato_id: int, data: dict) -> Gara:
        """
        Creates a new gara within a transaction.

        The @transactional decorator:
        - Automatically commits on success
        - Rolls back on exception
        - Handles nested transactions properly
        """
        gara = Gara(
            campionato_id=campionato_id,
            nome=data['nome'],
            date=data['date']
        )
        db.session.add(gara)
        return gara  # Commit happens automatically
```

**Key Rules**:
- ✅ Use `@transactional` for all methods that modify database
- ❌ Never use `db.session.commit()` directly in services (8 exceptions exist for legacy code)
- ✅ Let decorator handle commit/rollback automatically
- ❌ Don't add `@transactional` to methods called within other `@transactional` methods

### Event System Pattern

Domain events decouple components and enable cross-domain notifications:

```python
from models.events.base import DomainEvent, EventType

# 1. Emit an event from a service
class InscriptionService:
    @transactional
    def create_inscription(self, gara_id: int, user_id: int) -> Inscription:
        inscription = Inscription(gara_id=gara_id, user_id=user_id)
        db.session.add(inscription)

        # Emit event for other systems to react
        DomainEvent.emit(
            event_type=EventType.INSCRIPTION_CREATED,
            entity_id=inscription.id,
            entity_type='inscription',
            actor_id=user_id,
            data={'gara_id': gara_id, 'user_id': user_id}
        )

        return inscription

# 2. Listen for events in another service
from models.events.base import event_handler

@event_handler(EventType.INSCRIPTION_CREATED)
def handle_inscription_created(event: DomainEvent) -> None:
    """Send notification when user joins a gara."""
    NotificationFactory.create_notification(
        user_id=event.data['user_id'],
        notification_type='inscription_confirmed',
        related_entity_id=event.data['gara_id']
    )
```

**Available Event Types**:
- `INSCRIPTION_CREATED`, `INSCRIPTION_CANCELLED`
- `MATCH_CREATED`, `MATCH_COMPLETED`
- `GARA_CREATED`, `GARA_COMPLETED`
- `DIRECTOR_REQUEST_CREATED`, `DIRECTOR_REQUEST_APPROVED`
- See `models/events/base.py` for complete list

### Notification Factory Pattern

Centralized notification creation with templates:

```python
from models.notification.factory import NotificationFactory
from models.notification.models import NotificationType, NotificationPriority

# Simple notification
NotificationFactory.create_notification(
    user_id=player.id,
    notification_type=NotificationType.MATCH_ASSIGNED,
    related_entity_id=match.id,
    priority=NotificationPriority.NORMAL
)

# Notification with custom data
NotificationFactory.create_notification(
    user_id=director.id,
    notification_type=NotificationType.DIRECTOR_REQUEST_APPROVED,
    related_entity_id=request.id,
    data={'approved_by': admin.username},
    priority=NotificationPriority.HIGH
)

# Bulk notifications to multiple users
user_ids = [player.id for player in gara.get_participants()]
NotificationFactory.create_bulk_notifications(
    user_ids=user_ids,
    notification_type=NotificationType.GARA_CANCELLED,
    related_entity_id=gara.id,
    priority=NotificationPriority.URGENT
)
```

### Strategy Pattern (Matchmaking)

Flexible tournament pairing with strategy registration:

```python
from models.matchmaking.service import MatchmakingService
from models.matchmaking.config import MatchmakingStrategy

# Use Amalfi strategy for a gara
service = MatchmakingService(
    gara_id=gara.id,
    strategy=MatchmakingStrategy.AMALFI
)

# Create pairings for next round
matches = service.create_next_round()

# Preview pairings without persisting (for campionato)
pairings = service.preview_pairings(
    participants=players,
    strategy=MatchmakingStrategy.ROUND_ROBIN
)
```

**Available Strategies**:
- `AMALFI`: Specification-compliant pairing with anti-rematch
- `ROUND_ROBIN`: All-play-all format
- `DIRECT_ELIMINATION`: Knockout tournament
- `RANDOM_ANTI_REMATCH`: Random with rematch avoidance

### Service Layer Pattern

Services encapsulate business logic with clean separation:

```python
# Facade pattern for backward compatibility
class GaraService:
    """Main service facade."""

    def __init__(self):
        self._state_service = StateService()
        self._inscription_service = InscriptionService()
        self._round_service = RoundService()

    @transactional
    def complete_gara(self, gara_id: int) -> Gara:
        """Delegates to specialized services."""
        gara = self._state_service.transition_to_completed(gara_id)
        self._round_service.finalize_all_rounds(gara_id)
        return gara

# Specialized service for focused responsibility
class StateService:
    """Handles gara state transitions only."""

    @transactional
    def transition_to_completed(self, gara_id: int) -> Gara:
        gara = db.session.get(Gara, gara_id)
        if not self._can_complete(gara):
            raise InvalidStateTransition("Cannot complete gara")

        gara.status = GaraStatus.COMPLETATA
        DomainEvent.emit(EventType.GARA_COMPLETED, gara.id)
        return gara
```

## Development Guidelines

### Type Safety & Quality Standards
**MANDATORY for all new code and modifications:**

1. **Pyright Type Checking**
   - Run `pyright` before every commit
   - Target: Maintain 0 total errors across codebase
   - Fix all new type errors introduced by changes
   - Use proper type hints for all function parameters and return types

2. **Import Management**
   - Add proper imports at top-level to avoid "undefined variable" errors
   - Use `from typing import cast` for LocalProxy conversions
   - Import SQLAlchemy models explicitly for proper type inference

3. **Common Type Patterns**
   ```python
   # LocalProxy casting in routes
   user = cast(User, current_user)
   
   # Enum values in SQLAlchemy filters - ALWAYS use .value
   .filter(Model.status.in_([Enum.VALUE.value, Enum.VALUE2.value]))
   
   # Optional parameters
   def method(param: Optional[int] = None) -> List[str]:
   
   # Forward references
   def method(self) -> "ModelName":
   ```

4. **SQLAlchemy Type Safety**
   - Import model classes at module level
   - Use `.all()` for relationship queries: `gara.inscriptions.all()`
   - Add `# type: ignore[attr-defined]` for complex SQLAlchemy operations

5. **Testing Requirements**
   - All new features MUST have tests in `tests/new/`
   - **CRITICAL**: Run `PYTHONPATH=. pytest tests/new/ -n auto` to verify (parallel execution recommended)
   - Individual tests should pass independently
   - Fix test isolation issues, not test content (use `db_session.get()` instead of `refresh()`)
   - Use TDD approach for refactoring (see `tests/new/refactor/tdd/`)
   - Integration tests require stable database state - avoid session conflicts

### Code Quality Checklist
Before every commit:
```bash
# 1. Format and lint
black .
flake8

# 2. Type check (MANDATORY)
pyright

# 3. Test new functionality (parallel execution)
PYTHONPATH=. pytest tests/new/ -n auto

# 4. Clean imports
autoflake --remove-all-unused-imports --recursive --in-place .
```

## Production Deployment

### PythonAnywhere Configuration

**Environment Setup**:
```bash
# Set environment variables in PythonAnywhere Web tab
FLASK_ENV=production
SECRET_KEY=<strong-random-secret>
DATABASE_URL=<postgresql-connection-string>  # or use SQLite
ADMIN_USERNAME=<admin-username>
ADMIN_EMAIL=<admin-email>
ADMIN_PASSWORD=<strong-admin-password>
```

**WSGI Configuration** (`/var/www/username_pythonanywhere_com_wsgi.py`):
```python
import sys
import os

# Add your project directory to the sys.path
project_home = '/home/username/tornei-biliardo'
if project_home not in sys.path:
    sys.path = [project_home] + sys.path

# Set environment variables
os.environ['FLASK_ENV'] = 'production'

# Import and create app
from app import create_app
application = create_app('production')
```

**Database Migration Workflow**:
1. Test migrations locally with SQLite first
2. Backup production database before changes
3. Apply schema changes via `db.create_all()` or manual migration scripts
4. Verify data integrity post-migration
5. Monitor application logs for errors

**Static Files**:
- Ensure `/static/uploads/` directories exist with proper permissions
- Configure PythonAnywhere to serve static files from `/static/`

**Security Checklist**:
- [ ] `SECRET_KEY` is strong and unique
- [ ] `ADMIN_PASSWORD` is changed from default
- [ ] `DEBUG_MODE = False` in production config
- [ ] Database credentials are secure
- [ ] HTTPS is enabled
- [ ] Static file permissions are restricted

**Monitoring & Logs**:
- Check PythonAnywhere error logs regularly
- Monitor database size (free tier limits)
- Set up error notifications for critical failures

## Development Notes

- The codebase uses Italian comments and variable names in many places
- Git workflow uses feature branches
- **Application is usually running**: No need to restart for most changes
- **Database location**: `instance/` folder (SQLite in dev)
- Production deployment on PythonAnywhere platform
- **Type Safety**: Project maintains 0 pyright errors (achieved through systematic migration including Phase 4)
- **Transaction Management**: All services use `@transactional` decorator pattern for consistency and reliability
- **Service Architecture**: Clean separation between domain services with facade patterns for backward compatibility
- **Architecture principle**: "non cercare mai quick fix, ma scegli sempre le soluzioni più corrette secondo i principi di buona programmazione. non sovraingegnerizzare. Segui sempre soluzioni pulite ed eleganti"
- Comprehensive testing revealed and fixed multiple edge cases in competition workflow
- Flexible matchmaking system now fully supports strategy preview, idempotent operations, and fallback classification display
- All matchmaking strategies (Amalfi, Round-Robin, Elimination, Random) are fully implemented and tested
- **All 8 use cases are now fully implemented** with comprehensive integration tests
- **Refactoring Complete**: Phases 1-4 completed - solid foundation established for future development
- ✅ **REFACTORING STATUS**: All phases successfully completed and merged to main
  - **Phase 1-3**: Transaction management, service decomposition, Amalfi algorithm modernization
  - **Phase 4**: Type safety improvements and architectural fixes (October 2025)
    - Enum migration: 15+ string literals replaced with enum values
    - Rating system fix: Moved Fargo/Elo ratings from Gara to User model
    - Architectural correctness: Rating (Player property) vs Scoring (classification logic)
  - Implementation: Specification-compliant AmalfiStrategy using User ratings directly
  - Migration: Complete directory migration (amalfi/ → models/matchmaking/strategies/)
  - Integration: Unified strategy pattern working across all matchmaking scenarios
  - Testing: All unit and integration tests passing with new implementation
  - Cleanup: Legacy directory, cache files, and architectural issues resolved

## Documentation Structure

This project maintains comprehensive documentation at multiple levels:

### Root Documentation
- **CLAUDE.md**: Project overview, commands, and architecture summary
- **README.md**: User-facing project description and setup instructions

### Directory-Specific Documentation
Each major component has detailed documentation in its subdirectory:

1. **[models/CLAUDE.md](models/CLAUDE.md)**:
   - Domain-Driven Design architecture
   - Model organization and relationships
   - Database schema and mixins
   - Development guidelines for data layer
   - **Quick Reference**: Critical attribute names and common patterns
   - **Detailed Class Structures**: Complete field, method, and relationship documentation for 12+ core models

2. **[routes/CLAUDE.md](routes/CLAUDE.md)**:
   - RESTful API organization
   - Authentication and authorization patterns
   - Request handling and response patterns
   - Security considerations

3. **[templates/CLAUDE.md](templates/CLAUDE.md)**:
   - Component-based UI architecture
   - Bootstrap 5 integration
   - Template organization and reusability
   - Accessibility and responsive design

4. **[tests/CLAUDE.md](tests/CLAUDE.md)**:
   - Testing strategy and organization
   - Unit, integration, and E2E test approaches
   - Coverage targets and quality metrics
   - Performance and security testing

### Domain-Specific Model Documentation
Critical business domains have focused CLAUDE.md files in their subdirectories:

- **[models/competition/CLAUDE.md](models/competition/CLAUDE.md)** (~7,500 lines):
  - Gara, Inscription models with all fields and methods
  - GaraService, InscriptionService, RoundService, StateService, AdvancedRoundManager
  - Complete competition lifecycle workflows
  - State machine, validation patterns, and edge cases

- **[models/matchmaking/CLAUDE.md](models/matchmaking/CLAUDE.md)** (~5,500 lines):
  - BaseStrategy pattern and Pairing value objects
  - All 5 strategies: Amalfi, RoundRobin, DirectElimination, DoubleKnockout, RandomAntiRematch
  - Configuration, anti-rematch logic, odd-player handling
  - Custom strategy implementation guide

- **[models/match/CLAUDE.md](models/match/CLAUDE.md)** (~3,000 lines):
  - Match, Set, SetRack, Rack, TrioMatch models
  - MatchService and RackService with state machines
  - Multi-set, multi-discipline match support
  - Handicap system integration

- **[models/SUBDIRECTORY_DOCS_SUMMARY.md](models/SUBDIRECTORY_DOCS_SUMMARY.md)**:
  - Complete index of all model subdirectory documentation
  - Documentation statistics and metrics
  - Template for creating future domain documentation
  - Recommended priorities for remaining 15+ domains

### Use Case Documentation
- **`docs/usecases/gare.md`**: Complete specification of all 8 implemented use cases
- **`docs/usecases/convenzioni.md`**: Testing conventions and variant notation

### Navigation Guide

**For High-Level Overview:**
- Start with this root **CLAUDE.md** for project structure and commands

**For Domain-Specific Implementation:**
- **Working on Competitions/Gare?** → Read [models/competition/CLAUDE.md](models/competition/CLAUDE.md)
- **Working on Matchmaking/Strategies?** → Read [models/matchmaking/CLAUDE.md](models/matchmaking/CLAUDE.md)
- **Working on Matches/Scoring?** → Read [models/match/CLAUDE.md](models/match/CLAUDE.md)
- **Need Quick Model Reference?** → Check Quick Reference sections in [models/CLAUDE.md](models/CLAUDE.md)

**For Layer-Specific Work:**
- **Routes/API endpoints** → [routes/CLAUDE.md](routes/CLAUDE.md)
- **Templates/UI** → [templates/CLAUDE.md](templates/CLAUDE.md)
- **Testing** → [tests/CLAUDE.md](tests/CLAUDE.md)

**Best Practice:**
- Each subdirectory documentation is self-contained but cross-references related components
- **Follow architectural principles**: Clean, elegant solutions without over-engineering
- Use domain-specific CLAUDE.md files to find exact attribute names and method signatures

## Refactoring Documentation

⚠️ **IMPORTANT: ALL TESTS MUST PASS BEFORE ANY REFACTORING**

The project is undergoing systematic refactoring to improve architecture and maintainability. Complete documentation is located in:

### [docs/refactoring/](docs/refactoring/)
- **[README.md](docs/refactoring/README.md)**: Overview and critical guidelines
- **[REFACTOR_PROGRESS.md](docs/refactoring/REFACTOR_PROGRESS.md)**: Detailed progress tracking

### Critical Rules for Refactoring
1. **Test-First Policy**: 100% test pass rate required before starting
2. **Test-Driven Refactoring**: All tests must remain green after every change
3. **Systematic Methodology**: Follow TDD approach with quality gates
4. **Documentation Updates**: Keep refactoring docs current

### Current Status
- **Task 1.1**: Transaction Management Migration (✅ 100% COMPLETE)
- **Task 1.2**: GaraService Decomposition (✅ 100% COMPLETE)
- **Task 1.3**: UserService Decomposition (✅ 100% COMPLETE)
- **Phase 1**: Service Architecture Foundation (✅ COMPLETE)
- **Phase 2**: Domain Decoupling with Event System + Notification Factory (✅ COMPLETE)
- **Phase 3**: Optimization and Cleanup (✅ COMPLETE)
- **Test Status**: All tests passing, refactoring foundation established

**Latest Improvements (September 2025)**:
- **Transaction Migration Completed**: Successfully migrated 169/177 `db.session.commit()` calls to `@transactional` pattern (100% of applicable commits)
  - **Completed Domains**: All service domains migrated including competition, user, match, challenge, individual match, playoff, exam, classification, rating, venue management, and utilities
  - **Excluded Commits**: 8 commits intentionally left unchanged (transaction manager itself, custom patterns, legacy utilities)
  - **StateService Fixes**: Removed inappropriate transaction decorators from methods called within larger contexts
- **GaraService Decomposition Completed**: Full service extraction with 48.7% code reduction (869/1695 lines)
  - **New Services**: StateService, InscriptionService, RoundService with GaraService facade
  - **Characterization Tests**: Complete test coverage ensuring behavioral compatibility
- **UserService Decomposition Completed**: Service extraction with 56% code reduction achieving clean modular architecture
  - **New Services**: UserPermissionService, VenueManagerService with UserService facade
  - **TDD Implementation**: Comprehensive test-driven development ensuring type safety and behavioral compatibility
- **Code Quality Achievements**: Maintained 0 flake8 errors, 0 pyright errors across all migrated code
- **Test Infrastructure Improvements**: Fixed SQLAlchemy session management patterns in integration tests
- **Enhanced Venue Management**: Added contested request detection with priority notifications
- All major use case workflows have stable test coverage with reliable execution

**Next Developer**: ✅ **PRODUCTION READY**: All refactoring phases (1, 2, 3) completed successfully! Complete foundation established with transaction management, service decomposition, event-driven architecture, notification factory, and modernized Amalfi algorithm. Platform ready for advanced features or production deployment.