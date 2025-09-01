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

## Development Notes

- The codebase uses Italian comments and variable names in many places
- Git workflow uses feature branches (current: `refactor/step-1-admin-routes-split`)
- Application runs on `http://localhost:5000` by default
- Production deployment on PythonAnywhere platform