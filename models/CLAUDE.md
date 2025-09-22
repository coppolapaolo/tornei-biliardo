# Models Directory - Community Platform Architecture

This directory contains the domain models for the American Pool community platform, organized using Domain-Driven Design principles to support both current tournament features and future community expansion.

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