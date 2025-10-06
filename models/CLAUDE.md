# Models Directory - Community Platform Architecture

This directory contains the domain models for the American Pool community platform, organized using Domain-Driven Design principles to support both current tournament features and future community expansion.

## 📂 Documentation Index

This file provides an **overview** of the models architecture. For **detailed domain-specific documentation**, see:

- **[models/competition/CLAUDE.md](competition/CLAUDE.md)**: Gara, Inscription, all competition services (~7,500 lines)
- **[models/matchmaking/CLAUDE.md](matchmaking/CLAUDE.md)**: All matchmaking strategies and algorithms (~5,500 lines)
- **[models/match/CLAUDE.md](match/CLAUDE.md)**: Match, Set, Rack models and services (~3,000 lines)
- **[models/SUBDIRECTORY_DOCS_SUMMARY.md](SUBDIRECTORY_DOCS_SUMMARY.md)**: Complete index of all domain documentation

**Use this file for:** Quick attribute reference, common patterns, architecture overview
**Use domain-specific files for:** Complete class structures, all methods, detailed workflows

## 📋 Quick Reference - Common Attributes & Gotchas

### Critical Attribute Names (Frequently Misspelled/Confused)

**Gara vs Campionato:**
- `Gara`: Single competition round - has `rounds_count`, `current_round`, `matchmaking_strategy`
- `Campionato`: Tournament with multiple gare - has `campionato_type`, `final_playoffs`, `challenge_mode`
- ⚠️ Gara can be standalone (`campionato_id = None`) or part of campionato

**Match Fields:**
- ✅ `player1_score` / `player2_score` - Current score (racks or sets won)
- ✅ `winner_id` - ID of winning player
- ✅ `status` - Use `MatchStatus` enum: `PENDING`, `PLAYING`, `COMPLETED`, `VALIDATED`
- ✅ `is_bye` - Boolean for bye matches (player1 vs X)
- ✅ `is_multi_set` - Boolean indicating multi-set match
- ✅ `current_set_number` - Current set being played (1-indexed)
- ❌ **Common errors**: Using `result` instead of `winner_id`, forgetting to check `is_bye`

**Inscription Fields:**
- ✅ `is_withdrawn` - Boolean for withdrawn inscriptions
- ✅ `is_waitlist` - Boolean for waitlist status
- ✅ `waitlist_position` - Position in waitlist (nullable)
- ❌ **Common error**: Forgetting to filter `is_withdrawn=False` when counting participants

**User Roles & Permissions:**
- ✅ `user.role` - String: `"admin"`, `"director"`, `"player"`
- ✅ `user.is_admin` - Property (not field)
- ✅ `user.is_director` - Property (not field)
- ✅ `user.is_venue_manager` - Property (checks VenueManagement assignments)
- ❌ **Common error**: Trying to set `is_admin` directly (it's a computed property)

**Rating Systems (Phase 4 Refactoring):**
- ✅ `User.fargo_rating` - Fargo rating (player property)
- ✅ `User.elo_rating` - Elo rating (player property)
- ✅ `Campionato.scoring_policy` - Campionato classification system ("classic", "fargo", "elo")
- ❌ **REMOVED**: `Gara.rating_type` (moved to User model)

### Relationship Names (Plural vs Singular)

**One-to-Many (Collection - Plural):**
```python
gara.inscriptions          # List of Inscription objects
gara.matches               # List of Match objects
campionato.gare            # List of Gara objects
user.inscriptions          # List of Inscription objects
user.classifications       # List of Classification objects
match.racks                # List of Rack objects
match.sets                 # List of Set objects (for multi-set)
challenge.attempts         # Dynamic query for ChallengeAttempt
notification.user          # Single User (exception - named 'user')
```

**Many-to-One (Single Object - Singular):**
```python
inscription.user           # Single User object
inscription.gara           # Single Gara object
match.gara                 # Single Gara object
match.player1              # Single User object
match.player2              # Single User object
match.winner               # Single User object
gara.campionato            # Single Campionato object (nullable)
```

**Special Cases:**
```python
user.director_assignments  # List of DirectorAssignment (backref)
gara.directors             # Property (not relationship) - computed from DirectorAssignment
campionato.directors       # Property (not relationship) - computed from DirectorAssignment
```

### Common Query Patterns

**Get active inscriptions:**
```python
active = [i for i in gara.inscriptions if not i.is_withdrawn and not i.is_waitlist]
# Or use filter
active_count = Inscription.query.filter_by(
    gara_id=gara.id,
    is_withdrawn=False,
    is_waitlist=False
).count()
```

**Check match status:**
```python
from models.status_enum import MatchStatus
if match.status == MatchStatus.COMPLETED.value:  # Note: .value for enum comparison
    # Process completed match
```

**Access relationship safely:**
```python
# ✅ Correct - handles SQLAlchemy lazy loading
inscriptions_list = gara.inscriptions.all() if hasattr(gara.inscriptions, 'all') else gara.inscriptions

# ❌ Wrong - may fail with lazy loading
for inscription in gara.inscriptions:  # May cause AttributeError
```

### Status Enums (Always use .value for comparisons)

```python
from models.status_enum import GaraStatus, MatchStatus, TournamentStatus

# ✅ Correct
if gara.status == GaraStatus.PLAYING.value:

# ❌ Wrong
if gara.status == GaraStatus.PLAYING:  # This compares to enum object, not string
```

## Architecture Overview

The models are organized into business domains with clear separation of concerns:

### Core Infrastructure

#### `base.py` - Foundation Components
- **UtilityMixin**: Database operations (save, delete, find_by_id, to_dict)
- **TimestampMixin**: Automatic created_at/updated_at tracking
- **SoftDeleteMixin**: Soft deletion with is_deleted property
- **AuditMixin**: Created/updated by user tracking
- **ValidationMixin**: Model validation framework
- **BaseModel**: Full-featured base with timestamps and utilities
- **SimpleModel**: Utility methods only, no timestamps
- **Database utilities**: get_or_create, bulk_create

#### `status_enum.py` - State Management
Centralized enumerations for application states:
- **GaraStatus**: setup, inscription, playing, completed
- **ProvaDerivedStatus**: inscription_closed, ready_to_start, round_completed, tournament_completed
- **TournamentStatus**: setup, registration_open, in_progress, completed
- **MatchStatus**: pending, playing, completed, validated
- **DirectorRequestStatus**: pending, approved, rejected
- **PlayoffConfirmationStatus**: pending, confirmed, declined

#### `fields.py` - Custom Field Types
- **EncryptedString**: Encrypted storage for sensitive data (email, phone)

#### `exceptions.py` - Domain Exceptions
Domain-specific exception classes for proper error handling.

## Business Domains

### User Domain (`user/`)
**Purpose**: Community member management and social features

**Models**:
- `User`: Community member profile with encrypted personal data, soft delete
- `TournamentDirector`: Community leaders and event organizers
- `DirectorRequest`: Promotion requests to become community organizers
- `VenueManagerRequest`: Requests to manage specific pool halls
- `VenueManagement`: Venue-specific management for community spaces

**Community Features**:
- Role-based community permissions (admin, director, player, guest)
- Player profiles with statistics and preferences
- Social connections and friend systems (future expansion)
- Privacy-compliant personal data management
- Community leadership promotion workflow

### Campionato Domain (`campionato/`)
**Purpose**: Multi-round tournament management and championship organization

**Models**:
- `Campionato`: Championship tournaments with multiple competitions (gare)

**Features**:
- Multi-competition championship tournaments
- Tournament type configuration (Amalfi, Round-Robin, etc.)
- Advanced options: challenge mode, final playoffs, scoring policies
- Tournament lifecycle and progression management
- Championship-wide statistics and standings

### Competition Domain (`competition/`)
**Purpose**: Competition round management

**Models**:
- `Gara`: Competition rounds (standalone or campionato-based)
- `Inscription`: Player registration with waitlist support

**Features**:
- Standalone competitions support
- Time, location, and description metadata
- Configurable rounds count and minimum participants
- Withdrawal policies (Forfeit/Exclude)

### Match Domain (`match/`)
**Purpose**: Match execution and scoring

**Models**:
- `Match`: Core match entity with multi-set support
- `Rack`: Individual rack scoring
- `MatchResult`: Match outcome and statistics
- `TrioMatch`: Three-player matches for odd numbers
- `Set`, `SetRack`: Multi-set competition support

**Features**:
- Single and multi-set match formats
- Current set tracking
- Bye match support
- Detailed rack-level scoring

### Matchmaking Domain (`matchmaking/`)
**Purpose**: Flexible player pairing system with multiple strategies

**Strategy Pattern Implementation**:
- **Base Strategy**: Abstract matchmaking interface
- **Amalfi Strategy**: Dynamic pairing based on remaining rounds and standings
- **Round-Robin Strategy**: Complete all-play-all tournament format
- **Direct Elimination**: Traditional knockout tournament system
- **Double Knockout**: Elimination with single reprieve
- **Random Strategy**: Random pairing with anti-rematch protection

**Configuration System**:
- **First Round Policies**: Random, classification-based, rating-based
- **Odd Player Handling**: Byes, trio matches, challenges
- **Forfeit Policies**: Exclude or automatic losses
- **Strategy Registry**: Dynamic strategy selection and configuration

### Classification Domain (`classification/`)
**Purpose**: Player rankings and statistics

**Models**:
- `Classification`: Overall tournament rankings
- `RoundClassification`: Round-specific rankings
- `PlayerEncounter`: Head-to-head tracking

### Individual Match Domain (`individual_match/`)
**Purpose**: Community-driven casual match organization

**Models**:
- `MatchProposal`: Community match invitation system
- `ProposalInvitation`: Social invitation tracking
- `IndividualMatch`: Casual matches between community members
- `IndividualRack`: Detailed scoring for skill tracking
- `PlayerAvailability`: Community member scheduling

**Community Features**:
- Open and targeted match proposals
- Community-wide match visibility
- Location-based match finding
- Social interaction through gaming
- Skill development through casual play

### Specialized Domains

#### Challenge Domain (`challenge/`)
Skill development system for pool players with practice challenges and community leaderboards.

#### Exam Domain (`exam/`)
Challenge-based examination system for skill assessment.

#### Rating Domain (`rating/`)
Community-wide player rating and skill assessment system supporting all pool disciplines.

#### Notification Domain (`notification/`)
Community communication system for match invitations, tournament updates, and social interactions.

#### Location Domain (`location/`)
Pool hall and community venue management with member availability tracking.

#### Playoff Domain (`playoff/`)
Elimination tournament system with qualification management.

#### Tiebreaker Domain (`tiebreaker/`)
Spot shot and rally systems for tie resolution.

## Cross-Domain Services

### Orchestration (`orchestration/`)
**Purpose**: Coordinate multi-domain operations
- `DomainOrchestrator`: Cross-domain operation coordination
- `OperationResult`: Operation outcome tracking
- `OperationType`: Operation classification

### Transaction (`transaction/`)
**Purpose**: Distributed transaction management
- Transaction boundary management
- Rollback coordination

### Caching (`caching/`)
**Purpose**: Performance optimization
- Cache manager for expensive operations
- Strategic cache invalidation

### Optimization (`optimization/`)
**Purpose**: Database performance
- Query optimization strategies
- Performance monitoring

### Events (`events/`)
**Purpose**: Domain decoupling through event-driven architecture
- `DomainEvent`: Base class for all domain events with timestamp and metadata
- `EventBus`: Central publish-subscribe event dispatcher with error handling
- **Event Types**: Domain-specific events for loose coupling
  - `UserEvents`: User registration, profile updates, role changes
  - `CompetitionEvents`: Competition lifecycle, inscription changes, status updates
  - `MatchEvents`: Match creation, scoring updates, completion
  - `AvailabilityEvents`: Player availability changes, location updates
- **Notification Handlers**: Event-driven notification delivery system
- **Error Handling**: Robust error handling with logging and graceful degradation

## Development Guidelines

### Model Creation
1. Inherit from appropriate base class:
   - `BaseModel`: For business entities needing timestamps
   - `SimpleModel`: For lookup tables or simple entities
   - Use specific mixins for targeted functionality

2. Follow domain boundaries:
   - Place models in appropriate domain directories
   - Use cross-references sparingly
   - Prefer services for cross-domain logic

3. Strategy Pattern Implementation:
   - New matchmaking strategies inherit from base strategy interface
   - Register strategies in the strategy registry
   - Implement required methods: `create_pairings()`, `supports_first_round_policy()`, etc.
   - Follow consistent naming conventions for strategy classes

### Naming Conventions
- Model classes: PascalCase (e.g., `MatchProposal`)
- Table names: snake_case (e.g., `match_proposal`)
- Foreign keys: `{model}_id` (e.g., `user_id`)
- Enum values: UPPER_CASE (e.g., `PENDING`)

### Database Relationships
- Use appropriate cascade options
- Implement soft delete where audit trail needed
- Prefer explicit foreign key names
- Use back_populates for bidirectional relationships

### Service Integration
- Models focus on data structure and basic validation
- Complex business logic belongs in service layers
- Use domain services for cross-model operations
- Transaction management handled by service layer

---

## 📚 Detailed Model Class Structures

### User Domain

#### User Model (`user/models.py`)

**Database Fields:**
```python
id: int (PK)
username: str(80) - unique, not null
email: EncryptedString(200) - unique, nullable (encrypted)
password_hash: str(120) - not null
role: str(20) - default "player" (admin|director|player)
phone: EncryptedString(100) - nullable (encrypted)
fargo_rating: int - nullable (player skill rating)
elo_rating: int - nullable (player skill rating)
previous_username: str(80) - nullable (for soft delete)
is_deleted: bool - soft delete flag (from SoftDeleteMixin)
deleted_at: datetime - soft delete timestamp (from SoftDeleteMixin)
created_at: datetime (from TimestampMixin)
updated_at: datetime (from TimestampMixin)
```

**Relationships:**
```python
inscriptions: List[Inscription] - all user inscriptions
match_results: List[MatchResult] - match results submitted by user
classifications: List[Classification] - campionato classifications
round_classifications: List[RoundClassification] - gara round classifications
player1_encounters: List[PlayerEncounter] - encounters as player1
player2_encounters: List[PlayerEncounter] - encounters as player2
director_request: DirectorRequest - pending director request (singular)
director_assignments: List[DirectorAssignment] - director assignments (backref)
standalone_garas: List[Gara] - standalone garas created by user (backref)
```

**Key Properties:**
```python
is_admin -> bool - True if role == "admin"
is_director -> bool - True if role == "director"
is_player -> bool - True if role == "player"
is_venue_manager -> bool - True if has active VenueManagement assignment
is_active -> bool - True if not soft deleted (Flask-Login integration)
```

**Key Methods:**
```python
set_password(password: str) -> None
check_password(password: str) -> bool
anonymize() -> None - soft delete with PII removal
can_manage_campionato(campionato_id: int) -> bool
can_manage_competition(competition_id: int) -> bool
can_view_admin_panel() -> bool
can_inscribe_to_competition(competition_id: int) -> bool
can_manage_venue(venue_id: int) -> bool
get_managed_venues() -> List[BilliardHall]
get_managed_campionatos() -> List[Campionato]
get_statistics() -> Dict[str, Any] - comprehensive user statistics
```

**Usage Examples:**
```python
# Authentication
user.set_password("secure_password")
if user.check_password(input_password):
    # Login successful

# Permissions
if user.can_manage_competition(gara.id):
    # Allow editing

# Statistics
stats = user.get_statistics()
# Returns: total_matches, won_matches, win_percentage, tournaments_played, etc.
```

---

#### DirectorAssignment Model (`user/models.py`)

**Database Fields:**
```python
user_id: int (PK, FK to user.id)
entity_type: str(20) (PK) - "campionato" or "gara" (use EntityType enum)
entity_id: int (PK) - ID of campionato or gara
assigned_by_id: int (FK to user.id) - not null
assigned_at: datetime - default utcnow
```

**Relationships:**
```python
director: User - the director user
assigned_by: User - admin who assigned
```

**Key Properties:**
```python
campionato: Campionato - returns campionato if entity_type == "campionato"
gara: Gara - returns gara if entity_type == "gara"
```

**Legacy Aliases:**
```python
TournamentDirector = DirectorAssignment  # Backward compatibility
GaraDirector = DirectorAssignment  # Backward compatibility
```

---

### Competition Domain

#### Gara Model (`competition/models.py`)

**Database Fields:**
```python
id: int (PK)
campionato_id: int (FK, nullable) - None for standalone
director_id: int (FK to user.id, nullable) - for standalone only
number: int - not null (position in campionato)
name: str(100)
date: date - not null
time: time - nullable

# Location & Description
location: str(200)
description: text

# Configuration
rounds_count: int - default 3
min_participants: int - default 6
max_participants: int - nullable
entry_fee: float - default 0.0

# Game Settings
discipline: str(50) - not null (use Discipline enum)
distance: int - not null
best_of: bool - default False

# Inscription Dates
inscription_start: datetime
inscription_end: datetime

# Status
status: str(20) - default "setup" (use GaraStatus enum)
current_round: int - default 0

# Policies
withdraw_policy: str(10) - default "Exclude" (use WithdrawPolicy enum)

# Matchmaking Configuration
matchmaking_strategy: str(50) - default "amalfi" (use MatchmakingStrategy enum)
first_round_policy: str(50) - default "random" (use FirstRoundPolicy enum)
odd_number_policy: str(50) - default "bye" (use OddNumberPolicy enum)
anti_rematch_enabled: bool - default True
```

**Relationships:**
```python
inscriptions: List[Inscription] - cascade delete
matches: List[Match] - cascade delete
director: User - for standalone garas
campionato: Campionato - nullable (via campionato_id)
round_classifications: List[RoundClassification] - cascade delete (backref)
player_encounters: List[PlayerEncounter] - cascade delete (backref)
```

**Key Properties:**
```python
is_standalone -> bool - True if campionato_id is None
directors -> List[User] - computed from DirectorAssignment (not a relationship)
```

**Key Methods:**
```python
get_display_name() -> str
get_real_status() -> str - considers round completion and inscriptions
get_status_badge_info() -> dict - UI badge configuration
can_start_new_round() -> bool
can_inscribe() -> bool
is_user_inscribed(user_id: int) -> bool
validate_strategy_configuration() -> bool
calculate_rounds_for_strategy(num_players: int) -> int
get_strategy_constraints() -> dict
can_modify_inscription_dates() -> bool
can_be_modified() -> bool - only in setup with no inscriptions
can_be_deleted() -> bool - only in setup with no inscriptions
can_cancel_round(round_number: int = None) -> bool
get_winning_score() -> int
is_match_finished(score1: int, score2: int) -> bool
copy_settings_from(source_gara: Gara) -> None
get_active_inscriptions_count() -> int
get_waitlist_count() -> int
is_full() -> bool
has_waitlist() -> bool
```

**Usage Examples:**
```python
# Check if user can inscribe
if gara.can_inscribe() and not gara.is_user_inscribed(user.id):
    # Allow inscription

# Get participants count
active_count = gara.get_active_inscriptions_count()

# Check status
real_status = gara.get_real_status()  # Handles round completion states
```

---

#### Campionato Model (`campionato/models.py`)

**Database Fields:**
```python
id: int (PK)
name: str(100) - not null

# Configuration
campionato_type: str(50) - default "amalfi" (use MatchmakingStrategy enum)
without_x: bool - default False
final_playoffs: bool - default True
challenge_mode: bool - default False
scoring_policy: str(50) - default "classic" ("classic"|"fargo"|"elo")

# Status & Lifecycle
is_active: bool - default True
created_at: datetime - default utcnow
updated_at: datetime - default utcnow (auto-update)

# Soft Delete
is_deleted: bool - default False
deleted_at: datetime - nullable
deleted_reason: str(255) - nullable
```

**Relationships:**
```python
gare: List[Gara] - cascade delete
classifications: List[Classification] - cascade delete (backref)
playoff_configurations: List[PlayoffConfiguration] - cascade delete
```

**Key Properties:**
```python
directors -> List[User] - computed from DirectorAssignment (not a relationship)
```

**Key Methods:**
```python
can_be_modified() -> bool - no gara with inscriptions
can_be_deleted() -> bool - no gara with inscriptions
get_status() -> str - aggregated from gare statuses
can_be_hard_deleted() -> bool - no completed matches
get_status_badge_class() -> str - CSS class for UI
get_status_text() -> str - display text
has_playoff_configurations() -> bool
can_generate_playoffs() -> bool
generate_playoff_qualifications() -> dict
get_playoff_status() -> dict
soft_delete(reason: str = "") -> bool
restore() -> bool - restore soft-deleted campionato
get_scoring_policy_name() -> str
set_scoring_policy(policy_name: str) -> None
```

**Class Methods:**
```python
get_active_campionatos() -> Query - filter is_deleted=False
get_deleted_campionatos() -> Query - filter is_deleted=True
```

---

#### Inscription Model (`competition/models.py`)

**Database Fields:**
```python
id: int (PK)
user_id: int (FK to user.id) - not null
gara_id: int (FK to gara.id, cascade delete) - not null
created_at: datetime - default utcnow
initial_order: int - nullable (sorteggio iniziale)

# Withdrawal
is_withdrawn: bool - default False
withdrawn_at: datetime - nullable

# Waitlist
is_waitlist: bool - default False
waitlist_position: int - nullable
```

**Relationships:**
```python
user: User
gara: Gara
```

**Usage Examples:**
```python
# Get active participants
active = [i for i in gara.inscriptions if not i.is_withdrawn and not i.is_waitlist]

# Check waitlist
waitlist = [i for i in gara.inscriptions if i.is_waitlist and not i.is_withdrawn]
```

---

### Match Domain

#### Match Model (`match/models.py`)

**Database Fields:**
```python
id: int (PK)
gara_id: int (FK to gara.id, cascade delete) - not null
round_number: int - not null (1, 2, 3, ...)

# Players
player1_id: int (FK to user.id)
player2_id: int (FK to user.id)
is_bye: bool - default False
is_trio: bool - default False

# Scores
player1_score: int - default 0 (racks or sets won)
player2_score: int - default 0 (racks or sets won)
winner_id: int (FK to user.id)

# Multi-set Configuration
match_distance: int - default 1 (sets to win)
is_multi_set: bool - default False
current_set_number: int - default 1

# Game Settings
discipline: str(50) - nullable (override gara discipline)

# Status
status: str(20) - default "pending" (use MatchStatus enum)
is_locked: bool - default False (match-specific lock)
round_locked: bool - default False (round-wide lock)
created_at: datetime - default utcnow

# Venue Management
table_assignment: str(10) - nullable

# Handicap
has_handicap: bool - default False
player1_handicap: int - default 0
player2_handicap: int - default 0
handicap_rule_id: int (FK) - nullable
handicap_explanation: str(255) - nullable
```

**Relationships:**
```python
player1: User
player2: User
winner: User
gara: Gara
handicap_rule: HandicapRule
racks: List[Rack] - cascade delete
sets: List[Set] - cascade delete, ordered by set_number
tiebreakers: List[Tiebreaker] - cascade delete
trio_match: TrioMatch - backref, singular
```

**Key Methods:**
```python
apply_handicap(handicap_data: dict) -> None
get_effective_score(player_id: int) -> int
get_handicap_info() -> dict
is_completed() -> bool
get_effective_discipline() -> str
start_next_set() -> Set
get_current_set() -> Optional[Set]
complete_set(set_number: int, winner_id: int) -> None
get_match_summary() -> dict
needs_tiebreaker() -> bool
has_active_tiebreaker() -> bool
get_active_tiebreaker() -> Tiebreaker
can_start_tiebreaker() -> bool
supports_multi_discipline() -> bool
configure_set_disciplines(set_disciplines: Dict[int, str]) -> None
get_multi_discipline_summary() -> Dict[str, Any]
```

**Usage Examples:**
```python
# Check if match is completed
if match.is_completed():
    # Process results

# Multi-set match
if match.is_multi_set:
    current_set = match.get_current_set()
    summary = match.get_match_summary()
    # summary includes sets won, current set, etc.

# Get effective discipline (override or gara default)
discipline = match.get_effective_discipline()
```

---

#### Set Model (`match/set_models.py`)

**Database Fields:**
```python
id: int (PK)
match_id: int (FK to match.id, cascade delete) - not null
set_number: int - not null

# Scoring Configuration
distance: int - default 5
best_of: bool - default True

# Scores
player1_racks: int - default 0
player2_racks: int - default 0

# Status
status: str(20) - default "pending" (pending|playing|completed)
winner_id: int (FK to user.id) - nullable
started_at: datetime - nullable
completed_at: datetime - nullable

# Multi-discipline Support
discipline: str(50) - nullable (primary discipline)
is_multi_discipline: bool - default False
discipline_rotation: JSON - nullable (list of disciplines)
discipline_assignment: JSON - nullable (rack->discipline mapping)

# Timestamps
created_at: datetime
updated_at: datetime
```

**Relationships:**
```python
match: Match
winner: User
racks: List[SetRack] - cascade delete, ordered by rack_number
```

**Constraints:**
```python
UNIQUE(match_id, set_number) - one set per number per match
```

**Key Methods:**
```python
can_be_modified() -> bool
configure_multi_discipline(disciplines: List[str], mode: str = "rotation") -> None
set_discipline_assignment(rack_disciplines: Dict[int, str]) -> None
get_discipline_for_rack(rack_number: int) -> str
get_discipline_summary() -> Dict[str, Any]
start_set() -> None
add_rack_result(winner_id: int, rack_number: int = None, discipline_override: str = None) -> SetRack
is_completed() -> bool
get_score_summary() -> Dict[str, Any]
get_rack_history() -> List[Dict[str, Any]]
```

---

### Classification Domain

#### Classification Model (`classification/models.py`)

**Database Fields:**
```python
id: int (PK)
campionato_id: int (FK to campionato.id, cascade delete) - not null
user_id: int (FK to user.id) - not null
position: int
total_matches_won: int - default 0
total_point_difference: int - default 0
gare_played: int - default 0

# Timestamps
created_at: datetime
updated_at: datetime
```

**Relationships:**
```python
campionato: Campionato
user: User
```

---

#### RoundClassification Model (`classification/models.py`)

**Database Fields:**
```python
id: int (PK)
gara_id: int (FK to gara.id, cascade delete) - not null
round_number: int - not null
user_id: int (FK to user.id) - not null

# Classification Data
position: int - not null
matches_won: int - default 0
rack_difference: int - default 0 (for Amalfi) or total racks won (for Random)
previous_position: int - nullable

# Metadata
created_at: datetime
```

**Relationships:**
```python
gara: Gara
user: User
```

**Constraints:**
```python
UNIQUE(gara_id, round_number, user_id) - one entry per player per round
```

**Static Methods:**
```python
@transactional
calculate_classification_after_round(gara_id: int, round_number: int) -> List[Tuple]
# Calculates classification based on matches up to specified round
# For Random strategy: orders by total racks won
# For other strategies: orders by matches won, then rack difference
```

**Usage Note:**
- For Random strategy, `rack_difference` stores **total racks won** (not difference)
- For other strategies, `rack_difference` stores actual difference (racks_won - racks_lost)

---

### Notification Domain

#### Notification Model (`notification/models.py`)

**Database Fields:**
```python
id: int (PK)
user_id: int (FK to user.id, cascade delete) - not null

# Content
notification_type: NotificationType (enum) - not null
title: str(255) - not null
message: text - not null
priority: NotificationPriority (enum) - default NORMAL

# Status & Timing
status: NotificationStatus (enum) - default PENDING
sent_at: datetime - nullable
read_at: datetime - nullable
expires_at: datetime - nullable

# Related Entities
related_entities: text - nullable (JSON string)

# Action
action_url: str(255) - nullable
action_text: str(100) - nullable

# Delivery Tracking
delivery_attempts: int - default 0
last_attempt_at: datetime - nullable

# Timestamps
created_at: datetime
updated_at: datetime
```

**Enums:**
```python
NotificationType: MATCH_PROPOSAL, MATCH_ACCEPTED, MATCH_DECLINED,
                  TOURNAMENT_INVITATION, TOURNAMENT_REGISTRATION, etc.
NotificationPriority: LOW, NORMAL, HIGH, URGENT
NotificationStatus: PENDING, SENT, READ, DISMISSED, EXPIRED
```

**Relationships:**
```python
user: User
```

**Key Methods:**
```python
get_related_entities() -> Dict[str, Any]
set_related_entities(entities: Dict[str, Any]) -> None
mark_as_sent() -> None
mark_as_read() -> None
dismiss() -> None
is_expired() -> bool
expire() -> None
can_be_delivered() -> bool
```

---

### Challenge Domain

#### Challenge Model (`challenge/models.py`)

**Database Fields:**
```python
id: int (PK)
description: text - not null
image_path: str(255) - not null

# Scoring Configuration
pass_fail_only: bool - default False

# Metadata
created_by_id: int (FK to user.id) - nullable
is_active: bool - default True

# Timestamps
created_at: datetime
updated_at: datetime
```

**Relationships:**
```python
attempts: List[ChallengeAttempt] - lazy="dynamic", cascade delete
favorites: List[ChallengeFavorite] - lazy="dynamic", cascade delete
created_by: User
```

**Key Methods:**
```python
get_statistics() -> Dict[str, Any]
# Returns: total_attempts, unique_players, average_score, median_score,
#          max_score_achieved, perfect_score_count, pass_rate (None for numeric)

get_user_best_attempt(user_id: int) -> Optional[ChallengeAttempt]
can_be_used_for_x_replacement() -> bool
get_display_name() -> str
```

**Key Properties:**
```python
image_filename -> Optional[str] - extracts filename from image_path
```

**Important Notes:**
- For **numeric challenges** (`pass_fail_only=False`): `passed` field is always `None`
- For **pass/fail challenges** (`pass_fail_only=True`): `passed` field is explicitly set
- Only numeric challenges can be used for X-replacement in tournaments

---

#### ChallengeAttempt Model (`challenge/models.py`)

**Database Fields:**
```python
id: int (PK)
challenge_id: int (FK to challenge.id, cascade delete) - not null
user_id: int (FK to user.id, cascade delete) - not null

# Attempt Details
score: int - nullable (None if not completed)
passed: bool - nullable (Only for pass/fail challenges, None for numeric)
completed: bool - default False
attempted_at: datetime - default utcnow

# Notes
notes: text - nullable

# Gara Integration (for X-replacement)
gara_id: int (FK to gara.id, set null) - nullable
round_number: int - nullable

# Timestamps
created_at: datetime
updated_at: datetime
```

**Relationships:**
```python
challenge: Challenge
user: User
gara: Gara - nullable
```

**Key Methods:**
```python
complete_attempt(score: int = None, passed: bool = None) -> None
# For numeric challenges: requires score parameter, passed stays None
# For pass/fail challenges: requires passed parameter, score = 1/0
```

---

### Location Domain

#### BilliardHall Model (`location/models.py`)

**Database Fields:**
```python
id: int (PK)
name: str(255) - not null
address: text - nullable
city: str(100) - nullable
postal_code: str(20) - nullable
country: str(100) - default "Italy"

# Contact
phone: str(50) - nullable
email: str(255) - nullable
website: str(255) - nullable

# Facility
number_of_tables: int - nullable
table_types: text - nullable (JSON string)
amenities: text - nullable (JSON string)

# Business Hours
business_hours: text - nullable (JSON string)

# Pricing
hourly_rate: numeric(10,2) - nullable
currency: str(3) - default "EUR"

# Status
is_active: bool - default True
verified: bool - default False
added_by_id: int (FK to user.id) - nullable

# Coordinates
latitude: float - nullable
longitude: float - nullable

# Timestamps
created_at: datetime
updated_at: datetime
```

**Relationships:**
```python
added_by: User
user_availabilities: List[UserLocationAvailability] - cascade delete
```

**Key Methods:**
```python
get_table_types() -> List[str]
set_table_types(types: List[str]) -> None
get_amenities() -> List[str]
set_amenities(amenities: List[str]) -> None
get_business_hours() -> Dict[str, Dict[str, str]]
set_business_hours(hours: Dict) -> None
is_open_at(day: DayOfWeek, time_check: time) -> bool
get_available_users(day: DayOfWeek = None) -> List[User]
get_full_address() -> str
can_be_verified() -> bool
is_complete_for_verification() -> bool
```

---

### Individual Match Domain

#### MatchProposal Model (`individual_match/models.py`)

**Database Fields:**
```python
id: int (PK)
proposer_id: int (FK to user.id, cascade delete) - not null

# Proposal Details
proposal_type: ProposalType (enum) - not null (DIRECT|OPEN)
status: ProposalStatus (enum) - default PENDING

# Match Details
location: str(255) - not null
scheduled_at: datetime - not null
expires_at: datetime - not null

# Game Configuration
discipline: str(50) - default "palla_8"
distance: int - default 5
best_of: bool - default True
break_rule: str(20) - default "alternate"
description: text - nullable
entry_fee: numeric(10,2) - default 0

# Result Tracking
accepted_by_id: int (FK to user.id, set null) - nullable
accepted_at: datetime - nullable

# Timestamps
created_at: datetime
updated_at: datetime
```

**Enums:**
```python
ProposalType: DIRECT (specific players), OPEN (all eligible)
ProposalStatus: PENDING, ACCEPTED, EXPIRED, CANCELLED
```

**Relationships:**
```python
proposer: User
accepted_by: User - nullable
invitations: List[ProposalInvitation] - cascade delete (for DIRECT proposals)
individual_match: IndividualMatch - one-to-one, nullable
```

**Key Methods:**
```python
is_expired() -> bool
can_be_accepted_by(user_id: int) -> bool
accept(user_id: int) -> IndividualMatch
cancel() -> None
expire() -> None
get_invitation_for_user(user_id: int) -> Optional[ProposalInvitation]
```

---

## 🔍 Model Relationship Patterns

### Accessing Relationships Safely

**SQLAlchemy relationships can be lazy-loaded or relationship properties. Always check before iterating:**

```python
# ✅ Safe access pattern
inscriptions_list = getattr(gara, "inscriptions", []) or []
for inscription in inscriptions_list:
    # Process inscription

# ✅ Alternative with hasattr
if hasattr(gara.inscriptions, 'all'):
    inscriptions = gara.inscriptions.all()
else:
    inscriptions = gara.inscriptions

# ❌ Unsafe - may fail with AttributeError
for inscription in gara.inscriptions:
    # This can fail if inscriptions is a Query object
```

### Counting Related Objects

```python
# ✅ Direct query (most efficient)
count = Inscription.query.filter_by(gara_id=gara.id, is_withdrawn=False).count()

# ✅ Using method (if available)
count = gara.get_active_inscriptions_count()

# ⚠️ Less efficient but safe
inscriptions_list = getattr(gara, "inscriptions", []) or []
count = sum(1 for i in inscriptions_list if not i.is_withdrawn)
```

### Foreign Key Access

```python
# ✅ Always check None for nullable FKs
if gara.campionato_id:
    campionato = db.session.get(Campionato, gara.campionato_id)
    # Use campionato

# ✅ Or use relationship (handles None automatically)
if gara.campionato:
    # Use gara.campionato
```

---

## 🎯 Common Usage Patterns

### User Statistics Dashboard

```python
user = User.query.get(user_id)
stats = user.get_statistics()

# stats contains:
# - total_inscriptions, total_matches, won_matches, lost_matches
# - win_percentage, tournaments_played, provas_played
# - total_racks_won, total_racks_played, rack_win_percentage
```

### Gara Status Management

```python
# Get real status (considers round completion and inscription expiry)
real_status = gara.get_real_status()

# Possible values:
# - GaraStatus.SETUP.value ("setup")
# - GaraStatus.INSCRIPTION.value ("inscription")
# - ProvaDerivedStatus.INSCRIPTION_CLOSED.value ("inscription_closed")
# - GaraStatus.PLAYING.value ("playing")
# - ProvaDerivedStatus.ROUND_COMPLETED.value ("round_completed")
# - ProvaDerivedStatus.TOURNAMENT_COMPLETED.value ("campionato_completed")
# - GaraStatus.COMPLETED.value ("completed")

# Get badge info for UI
badge = gara.get_status_badge_info()
# Returns: {"class": "bg-success", "text": "In Corso"}
```

### Match Completion with Multi-Set Support

```python
if match.is_multi_set:
    # Get current set
    current_set = match.get_current_set()

    # Add rack result to current set
    rack = current_set.add_rack_result(winner_id=user.id)

    # Set completion is checked automatically
    # If set is won, match.complete_set() is called
    # If match is won, match status becomes COMPLETED

    # Get match summary
    summary = match.get_match_summary()
    # Returns sets won by each player, current set, completion status
else:
    # Legacy single-set match
    # Racks are added directly to match
```

### Classification Calculation

```python
from models.classification.models import RoundClassification

# Calculate classification after round completion
sorted_players = RoundClassification.calculate_classification_after_round(
    gara_id=gara.id,
    round_number=gara.current_round
)

# For each player, RoundClassification is created/updated with:
# - position (1, 2, 3, ...)
# - matches_won
# - rack_difference (or total racks for Random strategy)
# - previous_position (from previous round)
```

### Challenge Attempts

```python
challenge = Challenge.query.get(challenge_id)

# For numeric challenge
attempt = ChallengeAttempt(challenge_id=challenge.id, user_id=user.id)
attempt.complete_attempt(score=12)  # passed stays None

# For pass/fail challenge
attempt = ChallengeAttempt(challenge_id=challenge.id, user_id=user.id)
attempt.complete_attempt(passed=True)  # score = 1

# Get statistics
stats = challenge.get_statistics()
# For numeric: pass_rate is None
# For pass/fail: pass_rate is percentage
```

---

## ⚠️ Important Gotchas & Best Practices

### 1. Enum Comparisons

**Always use `.value` when comparing enum fields:**
```python
# ✅ Correct
if gara.status == GaraStatus.PLAYING.value:

# ❌ Wrong - compares to enum object
if gara.status == GaraStatus.PLAYING:
```

### 2. Soft Delete Awareness

**User model has soft delete - always check:**
```python
# ✅ Correct - filter out deleted users
active_users = User.query.filter_by(is_deleted=False).all()

# ✅ Use is_active property (Flask-Login integration)
if user.is_active:
    # User is not soft deleted
```

### 3. Relationship Collection Access

**SQLAlchemy relationships may be Query objects or lists:**
```python
# ✅ Safe pattern for both
inscriptions_list = getattr(gara, "inscriptions", []) or []

# ❌ Dangerous - may fail
for inscription in gara.inscriptions:  # Can raise AttributeError
```

### 4. Director Assignments

**`directors` is a computed property, not a relationship:**
```python
# ✅ Correct - property
directors = gara.directors  # Queries DirectorAssignment table

# ❌ Wrong - trying to access as relationship
gara.directors.append(user)  # This will fail
```

### 5. Match Score Interpretation

**`player1_score` and `player2_score` meaning depends on match type:**
```python
if match.is_multi_set:
    # Scores represent SETS won
    print(f"Sets: {match.player1_score}-{match.player2_score}")
else:
    # Scores represent RACKS won
    print(f"Racks: {match.player1_score}-{match.player2_score}")
```

### 6. Gara Standalone vs Campionato

**Always check `campionato_id` before accessing campionato:**
```python
# ✅ Correct
if gara.campionato_id:
    # Gara is part of campionato
    name = gara.campionato.name
else:
    # Standalone gara
    name = gara.name

# ✅ Or use property
if gara.is_standalone:
    # Handle standalone
```

### 7. Rating vs Scoring Policy

**After Phase 4 refactoring:**
```python
# ✅ Correct - User rating (player skill metric)
user.fargo_rating = 650
user.elo_rating = 1800

# ✅ Correct - Campionato classification scoring system
campionato.scoring_policy = "classic"  # or "fargo" or "elo"

# ❌ REMOVED - No longer exists
# gara.rating_type = "fargo"  # This field was removed
```

### 8. Transaction Management

**Services should use `@transactional` decorator:**
```python
from models.transaction.manager import transactional

@transactional
def create_inscription(gara_id: int, user_id: int) -> Inscription:
    # No need for db.session.commit() - decorator handles it
    inscription = Inscription(gara_id=gara_id, user_id=user_id)
    db.session.add(inscription)
    return inscription  # Commit happens automatically
```

---

## 📖 Additional Resources

- **Status Enums**: See `models/status_enum.py` for all status values
- **Configuration**: See `models/matchmaking/configuration.py` for strategy constraints
- **Services**: Each domain has service modules (`services.py`) for business logic
- **Specifications**: See `docs/SPECIFICHE.md` for complete platform requirements
- **Use Cases**: See `docs/usecases/gare.md` for detailed workflow documentation