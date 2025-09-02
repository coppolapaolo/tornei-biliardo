# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Flask-based billiards tournament management web application with an advanced tournament algorithm called "Sistema Amalfi". The app manages players, tournaments, matches, and provides statistical tracking.

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
```bash
# Run tests (excludes legacy tests by default)
pytest

# Run specific test types
pytest -m unit
pytest -m integration
pytest -m e2e

# Run with coverage
pytest --cov

# Run legacy tests (if needed)
pytest tests/legacy/
```

### Code Quality
```bash
# Format code
black .

# Lint code
flake8

# Clean imports
autoflake --remove-all-unused-imports --recursive --in-place .
```

## Architecture

### Application Structure
- **Flask Application Factory Pattern**: `create_app()` in `app.py` with environment-based configuration
- **Domain-Driven Design**: Organized by business domains (competition, matchmaking, rating, etc.)
- **Service Layer Pattern**: Business logic separated into service modules with transaction support
- **Strategy Pattern**: Configurable matchmaking algorithms (Amalfi, round-robin, elimination)

### Key Components

#### Amalfi Engine (`amalfi/`)
Core tournament algorithm for automatic player matchmaking:
- Dynamic round pairing with anti-rematch logic
- Handles odd players with trio matches or byes
- Real-time classification updates
- Entry point: `AmalfiEngine.create_round_matches()`

#### Models (`models/`)
Domain-organized with extensive relationships:
- **Base**: `base.py` contains common model functionality
- **User**: Player management with soft delete and permissions
- **Competition**: Tournaments, rounds (Prova), matches
- **Matchmaking**: Pairing strategies and encounter tracking
- **Rating**: Player rating system
- **Challenge**: Individual challenges between players
- **Notification**: System notifications

#### Routes (`routes/`)
RESTful endpoints organized by domain:
- `admin/`: Administrative functions split into sub-modules
- `auth.py`: Authentication and authorization
- `player.py`: Player management and profiles
- `challenge.py`: Challenge system
- `individual_match.py`: Individual match management
- `rating.py`: Rating system

#### Utils (`utils/`)
Shared utilities:
- Database utilities and statistics
- Encryption helpers
- Status UI filters for Jinja templates
- Data reset utilities

### Database
- **Development**: SQLite (`billiard_tournament.db`)
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
- Test discovery in `tests/new/` (legacy tests excluded by default)
- Coverage reporting with route exclusion
- Integration tests use actual database connections

### Code Style
- **Black** formatting (88 character line length)
- **Flake8** linting with extended ignore rules
- Import organization with autoflake
- Type hints where applicable

## Key Business Logic

### Tournament Flow
1. **Tournament Creation**: Admin/Director creates tournaments with multiple rounds (Prova)
2. **Player Registration**: Players register for individual rounds with waitlist support
3. **Matchmaking**: Amalfi algorithm creates optimal pairings avoiding rematches
4. **Match Execution**: Players compete in rounds with real-time scoring
5. **Classification**: Automatic ranking updates after each round
6. **Playoffs**: Optional elimination rounds after main tournament

### User Roles
- **Admin**: System administrator (configured in environment)
- **Director**: Can create/manage tournaments (elevated player)
- **Player**: Can register and participate in tournaments
- **Guest**: Visitor access only

### Amalfi Algorithm
Advanced matchmaking system that:
- Pairs players based on remaining rounds and current standings
- Prevents player rematches throughout tournament
- Handles odd numbers via trio matches or bye rounds
- Maintains competitive balance while avoiding repetitive matchups

## Recent Development History

### Comprehensive Competition Management Fixes (September 2025)
Major bug fix session addressing multiple competition workflow issues:

#### Core Issues Fixed
1. **Expired Inscriptions Management**: Added ability to start first round or cancel competition with participant notifications when inscriptions expire
2. **Match Display Issues**: Fixed partial results display for in-progress matches and maintained editability for completed matches
3. **Rack Management**: Resolved rack removal functionality and proper business logic validation for "best of N" vs "exactly N" match formats
4. **Director Permissions**: Enabled director inscription functionality on dashboard
5. **Amalfi Preview System**: Implemented tournament pairing preview without database persistence
6. **Round Management**: Made start round endpoint idempotent to prevent duplicate matches, fixed round completion detection
7. **UI Consistency**: Resolved current round display inconsistencies between different UI components
8. **Statistics Display**: Fixed match statistics in results overview
9. **Status Labels**: Changed "Torneo Completato" to "Prova Completata" for completed competitions
10. **Guest Classification**: Implemented fallback system showing RoundClassification from completed Amalfi provas when general tournament classification unavailable

#### Technical Solutions Implemented
- Enhanced `ProvaService` with cancellation and notification workflows
- Added preview functionality to `AmalfiEngine` without database modifications  
- Improved database transaction handling in competition endpoints
- Added comprehensive error handling and validation throughout competition workflow
- Implemented intelligent classification fallback logic for guest home page
- Fixed template endpoint references and permission decorators for standalone competitions

#### Files Modified (21 files, +468/-77 lines)
- Backend services: `models/competition/services.py`, `amalfi/engine.py`, `routes/admin/competition.py`
- UI components: Multiple template files in `templates/components/` and `templates/admin/`
- Status system: `utils/status_ui.py` for badge text corrections
- Database models: Enhanced validation in `models/competition/models.py`

## Development Notes

- The codebase uses Italian comments and variable names in many places
- Git workflow uses feature branches (current: `refactor/step-1-admin-routes-split`)
- Application runs on `http://localhost:5000` by default
- Production deployment on PythonAnywhere platform
- Comprehensive testing revealed and fixed multiple edge cases in competition workflow
- Amalfi tournament system now fully supports preview, idempotent operations, and fallback classification display