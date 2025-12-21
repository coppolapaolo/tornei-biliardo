# Individual Match Domain - Community Match Organization System

## Purpose and Core Responsibilities

The Individual Match domain provides a **player-to-player casual match organization system** for the pool community platform. It enables players to propose matches, discover available opponents, and track casual game results outside of formal tournaments.

**Key Features:**
- **Match Proposals**: Direct invitations or open community requests
- **Player Availability**: Location-based player discovery and scheduling
- **Multi-Set Support**: Single-set and multi-set match configurations
- **Invitation System**: Track pending, accepted, rejected invitations
- **Availability Service**: Notify players when opponents become available at venues
- **Match History**: Track casual game statistics and performance
- **Expiration Management**: Auto-expire old proposals

**Community Value:**
- Connect players for casual practice games
- Build community through social gaming
- Track improvement outside tournaments
- Discover new opponents at local venues
- Coordinate schedules efficiently

**Cross-Domain Integration:**
- Uses: Notification domain for match invitations
- Uses: Location domain for venue-based availability
- Uses: User domain for player profiles
- Distinct from: Competition/Match domains (tournament matches)

---

## Domain Structure

**Files** (4 files, ~2,057 lines total):
```
models/individual_match/
├── models.py                  (~587 lines) - Core match proposal models
├── services.py                (~1,085 lines) - Match proposal and match services
├── availability_service.py    (~354 lines) - Player availability and notifications
└── __init__.py                (~31 lines) - Domain exports
```

---

## Quick Reference

### Common Imports

```python
# Models and Enums
from models.individual_match.models import (
    MatchProposal,
    ProposalInvitation,
    IndividualMatch,
    IndividualRack,
    PlayerAvailability,
    ProposalType,
    ProposalStatus,
    InvitationStatus,
    MatchStatus,  # From status_enum
)

# Services
from models.individual_match.services import (
    MatchProposalService,
    IndividualMatchService,
)
from models.individual_match.availability_service import AvailabilityService
```

### Common Operations

```python
# Create direct match proposal (invite specific players)
proposal = IndividualMatchService.create_direct_proposal(
    proposer_id=user.id,
    invited_user_ids=[player1.id, player2.id],
    location="Sala Biliardo",
    scheduled_at=datetime(2025, 10, 15, 19, 0),
    discipline="palla_8",
    distance=7,
    best_of=True
)

# Create open match proposal (community-wide)
proposal = IndividualMatchService.create_open_proposal(
    proposer_id=user.id,
    location="Sala Biliardo",
    scheduled_at=datetime(2025, 10, 15, 19, 0),
    discipline="palla_9",
    distance=9,
    best_of=True
)

# Accept a proposal
match = IndividualMatchService.accept_proposal(
    user_id=invitee.id,
    proposal_id=proposal.id
)

# Set player availability at venue
availability = AvailabilityService.set_venue_availability(
    user_id=user.id,
    billiard_hall_id=venue.id,
    is_available=True,
    available_days=[1, 2, 3, 4, 5],  # Monday-Friday
    preferred_times="18:00-22:00"
)

# Find available players at venue
players = AvailabilityService.get_available_players_at_venue(
    billiard_hall_id=venue.id,
    exclude_user_id=user.id
)

# Notify available players
count = AvailabilityService.notify_players_of_availability(
    user_id=user.id,
    location="Sala Biliardo",
    message="Disponibile per una partita stasera!"
)
```

---

## Key Classes

### MatchProposal Model

**Purpose**: Represents a match invitation from one player to others (direct or open to community).

**Database Fields:**
```python
id: int (PK)
proposer_id: int (FK to user.id, cascade delete) - not null

# Proposal Details
proposal_type: ProposalType (enum) - not null (DIRECT | OPEN)
status: ProposalStatus (enum) - default PENDING

# Match Details
location: str(255) - not null  # TODO: should reference BilliardHall
scheduled_at: datetime - not null
expires_at: datetime - not null

# Game Configuration
discipline: str(50) - default "palla_8" (use Discipline enum)
distance: int - default 5 (racks per set)
best_of: bool - default True
break_rule: str(20) - default "alternate"
description: text - nullable
entry_fee: numeric(10,2) - default 0

# Multi-Set Configuration (Phase 6: Frontend Integration)
is_multi_set: bool - default False
match_distance: int - nullable (number of sets)
sets_best_of: bool - default True

# Result Tracking
accepted_by_id: int (FK to user.id, set null) - nullable
accepted_at: datetime - nullable

# Timestamps
created_at: datetime
updated_at: datetime
```

**Enums:**
```python
ProposalType:
    DIRECT = "direct"  # Invitation to specific players
    OPEN = "open"      # Open to all eligible players

ProposalStatus:
    PENDING = "pending"     # Waiting for responses
    ACCEPTED = "accepted"   # Someone accepted
    EXPIRED = "expired"     # Time limit reached
    CANCELLED = "cancelled" # Cancelled by proposer
```

**Relationships:**
```python
proposer: User - who created the proposal
accepted_by: User - nullable (who accepted)
invitations: List[ProposalInvitation] - cascade delete (for DIRECT proposals)
individual_match: IndividualMatch - one-to-one, nullable (created when accepted)
```

**Key Properties:**
```python
@property
def distance_config(self) -> Distance:
    """Get Distance value object for this proposal.

    Returns unified Distance abstraction supporting both single-set
    and multi-set configurations.

    Returns:
        Distance: Immutable distance configuration (None if not specified)
    """
```

**Key Methods:**
```python
is_expired() -> bool:
    """Check if proposal has passed expires_at."""

can_be_accepted_by(user_id: int) -> bool:
    """Check if user can accept this proposal.

    Validation:
    - Status must be PENDING
    - Not expired
    - User is not proposer
    - For DIRECT: user must be invited
    - For OPEN: any user can accept
    """

accept(user_id: int) -> IndividualMatch:
    """Accept the proposal and create an individual match.

    Side effects:
    - Updates status to ACCEPTED
    - Sets accepted_by_id and accepted_at
    - Creates IndividualMatch
    - Rejects/cancels other pending invitations

    Raises:
        ValueError: If user cannot accept
    """

cancel() -> None:
    """Cancel the proposal.

    Side effects:
    - Updates status to CANCELLED
    - Marks all pending invitations as CANCELLED
    """

expire() -> None:
    """Mark proposal as expired.

    Side effects:
    - Updates status to EXPIRED
    - Marks all pending invitations as EXPIRED
    """

get_invitation_for_user(user_id: int) -> Optional[ProposalInvitation]:
    """Get the invitation for a specific user (DIRECT proposals only)."""
```

**Usage Example:**
```python
# Create direct proposal to specific players
proposal = MatchProposal(
    proposer_id=user.id,
    proposal_type=ProposalType.DIRECT,
    location="Sala Biliardo",
    scheduled_at=datetime(2025, 10, 15, 19, 0),
    expires_at=datetime(2025, 10, 15, 17, 0),  # Expires 2h before match
    discipline="palla_8",
    distance=7,
    best_of=True
)
db.session.add(proposal)
db.session.flush()

# Create invitations
for player_id in [player1.id, player2.id]:
    invitation = ProposalInvitation(
        proposal_id=proposal.id,
        invited_user_id=player_id
    )
    db.session.add(invitation)

# Later: player accepts
if proposal.can_be_accepted_by(player1.id):
    match = proposal.accept(player1.id)
    # Creates IndividualMatch, cancels other invitations
```

---

### ProposalInvitation Model

**Purpose**: Individual invitation within a direct match proposal.

**Database Fields:**
```python
id: int (PK)
proposal_id: int (FK to match_proposal.id, cascade delete) - not null
invited_user_id: int (FK to user.id, cascade delete) - not null

status: InvitationStatus (enum) - default PENDING
responded_at: datetime - nullable

# Timestamps
created_at: datetime
updated_at: datetime
```

**Enum:**
```python
InvitationStatus:
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
```

**Relationships:**
```python
proposal: MatchProposal
invited_user: User
```

**Key Methods:**
```python
accept() -> IndividualMatch:
    """Accept this invitation.

    Delegates to proposal.accept(invited_user_id).

    Side effects:
    - Updates status to ACCEPTED
    - Sets responded_at
    - Creates IndividualMatch via proposal

    Raises:
        ValueError: If status is not PENDING
    """

reject() -> None:
    """Reject this invitation.

    Side effects:
    - Updates status to REJECTED
    - Sets responded_at

    Raises:
        ValueError: If status is not PENDING
    """
```

**Usage Example:**
```python
# User receives invitation
invitation = ProposalInvitation.query.filter_by(
    proposal_id=proposal.id,
    invited_user_id=current_user.id
).first()

# User accepts
if invitation and invitation.status == InvitationStatus.PENDING:
    match = invitation.accept()
    # Creates IndividualMatch, updates all related statuses
```

---

### IndividualMatch Model

**Purpose**: Actual match entity created when proposal is accepted.

**Database Fields:**
```python
id: int (PK)
proposal_id: int (FK to match_proposal.id) - nullable

# Players
player1_id: int (FK to user.id, cascade delete) - not null
player2_id: int (FK to user.id, cascade delete) - not null

# Match Details
location: str(255) - not null  # TODO: reference proposal.location?
scheduled_at: datetime - not null
status: MatchStatus (enum) - default SCHEDULED

# Game Configuration
discipline: str(50) - default "palla_8"
distance: int - default 5
best_of: bool - default True
break_rule: str(20) - default "alternate"

# Multi-Set Configuration (Phase 6: Frontend Integration)
is_multi_set: bool - default False
match_distance: int - nullable (number of sets)
sets_best_of: bool - default True

# Optional
entry_fee: numeric(10,2) - nullable
notes: text - nullable

# Results
started_at: datetime - nullable
completed_at: datetime - nullable
player1_score: int - default 0  # Racks or sets won
player2_score: int - default 0  # Racks or sets won
winner_id: int (FK to user.id) - nullable

# Timestamps
created_at: datetime
updated_at: datetime
```

**Enum:**
```python
MatchStatus (from status_enum):
    # Tournament matches
    PENDING = "pending"
    PLAYING = "playing"

    # Individual matches
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"

    # Common
    COMPLETED = "completed"
    VALIDATED = "validated"
    CANCELLED = "cancelled"
```

**Relationships:**
```python
proposal: MatchProposal - nullable (backref)
player1: User
player2: User
winner: User - nullable
racks: List[IndividualRack] - cascade delete, ordered by rack_number
```

**Key Properties:**
```python
@property
def distance_config(self) -> Distance:
    """Get Distance value object for this individual match.

    Returns unified Distance abstraction supporting both single-set
    and multi-set configurations.
    """

@property
def rack_score(self) -> RackScore:
    """Get RackScore value object for this match.

    Returns current rack scoring.
    """
```

**Key Methods:**
```python
start_match() -> None:
    """Start the match.

    Side effects:
    - Updates status to IN_PROGRESS
    - Sets started_at to now

    Raises:
        ValueError: If status is not SCHEDULED
    """

add_rack_result(winner_id: int, rack_number: Optional[int] = None) -> IndividualRack:
    """Add a rack result to the match.

    Args:
        winner_id: ID of player who won the rack
        rack_number: Optional rack number (auto-assigned if None)

    Side effects:
    - Creates IndividualRack
    - Updates player1_score or player2_score
    - Checks for match completion
    - If match is won, calls complete_match()

    Raises:
        ValueError: If status is not IN_PROGRESS or winner is invalid
    """

complete_match(winner_id: int) -> None:
    """Complete the match with a winner.

    Side effects:
    - Updates status to COMPLETED
    - Sets completed_at to now
    - Sets winner_id

    Raises:
        ValueError: If status is not IN_PROGRESS
    """

cancel_match(reason: Optional[str] = None) -> None:
    """Cancel the match.

    Args:
        reason: Optional cancellation reason (added to notes)

    Side effects:
    - Updates status to CANCELLED
    - Appends reason to notes

    Raises:
        ValueError: If status is COMPLETED
    """

get_opponent(user_id: int) -> Optional[User]:
    """Get the opponent for a given user."""

get_user_score(user_id: int) -> int:
    """Get score for a specific user."""
```

**Usage Example:**
```python
# Match created from accepted proposal
match = IndividualMatch(
    proposal_id=proposal.id,
    player1_id=proposer.id,
    player2_id=accepter.id,
    location="Sala Biliardo",
    scheduled_at=proposal.scheduled_at,
    discipline="palla_8",
    distance=7,
    best_of=True
)
db.session.add(match)

# Later: start match
match.start_match()
# status=IN_PROGRESS, started_at=now

# Add rack results
rack1 = match.add_rack_result(winner_id=player1.id)
rack2 = match.add_rack_result(winner_id=player2.id)
rack3 = match.add_rack_result(winner_id=player1.id)
# ... continue until match is won

# Match automatically completes when target score reached
# status=COMPLETED, completed_at=now, winner_id=player1.id
```

---

### IndividualRack Model

**Purpose**: Individual rack within an individual match (detailed scoring).

**Database Fields:**
```python
id: int (PK)
match_id: int (FK to individual_match.id, cascade delete) - not null
rack_number: int - not null
winner_id: int (FK to user.id) - not null

# Optional Details
break_player_id: int (FK to user.id) - nullable
notes: text - nullable

# Timestamps
created_at: datetime
updated_at: datetime
```

**Constraints:**
```python
UNIQUE(match_id, rack_number) - one rack per number per match
```

**Relationships:**
```python
match: IndividualMatch
winner: User
break_player: User - nullable
```

**Usage Example:**
```python
# Created automatically by match.add_rack_result()
rack = IndividualRack(
    match_id=match.id,
    rack_number=3,
    winner_id=player1.id,
    break_player_id=player2.id,
    notes="Great safety battle"
)
db.session.add(rack)
```

---

### PlayerAvailability Model

**Purpose**: Player availability preferences for match locations (legacy string-based).

**Database Fields:**
```python
id: int (PK)
user_id: int (FK to user.id, cascade delete) - not null
location: str(255) - not null  # TODO: should reference BilliardHall

# Availability Preferences
is_available: bool - default True
preferred_days: str(20) - nullable (JSON array of weekday numbers)
preferred_times: str(50) - nullable (e.g., "18:00-22:00")

# Timestamps
created_at: datetime
updated_at: datetime
```

**Constraints:**
```python
UNIQUE(user_id, location) - one availability record per user per location
```

**Relationships:**
```python
user: User
```

**Usage Note:**
This model is **legacy** and uses string-based location. Prefer using `UserLocationAvailability` from the location domain for venue-based availability.

---

## Services

### IndividualMatchService

**Purpose**: Core service for match proposal and match management.

**All methods use `@transactional(domain="individual_match")` for transaction management.**

#### Proposal Creation

```python
@transactional(domain="individual_match")
def create_direct_proposal(
    proposer_id: int,
    invited_user_ids: List[int],
    location: str,
    scheduled_at: datetime,
    expires_at: Optional[datetime] = None,  # Defaults to 2h before scheduled_at
    discipline: Optional[str] = None,
    distance: Optional[int] = None,
    best_of: bool = False,
    break_rule: Optional[str] = None,
    description: Optional[str] = None,
    entry_fee: Optional[float] = None,
) -> MatchProposal:
    """Create a direct match proposal to specific players.

    Side effects:
    - Creates MatchProposal
    - Creates ProposalInvitation for each invited_user_id
    - Sends notification to each invited user via NotificationFactory

    Returns: MatchProposal with invitations created
    """
```

**Usage Example:**
```python
proposal = IndividualMatchService.create_direct_proposal(
    proposer_id=current_user.id,
    invited_user_ids=[player1.id, player2.id],
    location="Sala Biliardo",
    scheduled_at=datetime(2025, 10, 15, 19, 0),
    discipline="palla_8",
    distance=7,
    best_of=True,
    description="Partita amichevole per pratica"
)
# Notifications sent automatically to player1 and player2
```

---

```python
@transactional(domain="individual_match")
def create_open_proposal(
    proposer_id: int,
    location: str,
    scheduled_at: datetime,
    expires_at: Optional[datetime] = None,
    discipline: Optional[str] = None,
    distance: Optional[int] = None,
    best_of: bool = False,
    break_rule: Optional[str] = None,
    description: Optional[str] = None,
    entry_fee: Optional[float] = None,
) -> MatchProposal:
    """Create an open match proposal for all eligible players.

    Returns: MatchProposal (no invitations created)
    """
```

**Usage Example:**
```python
proposal = IndividualMatchService.create_open_proposal(
    proposer_id=current_user.id,
    location="Sala Biliardo",
    scheduled_at=datetime(2025, 10, 15, 19, 0),
    discipline="palla_9",
    distance=9,
    best_of=True,
    description="Cerco avversario per partita race to 9"
)
# Visible to all players with availability at "Sala Biliardo"
```

---

#### Proposal Management

```python
def get_user_proposals(
    user_id: int,
    include_expired: bool = False
) -> Dict[str, List[MatchProposal]]:
    """Get proposals organized by user relationship.

    Returns:
        {
            "created": List[MatchProposal],      # User created these
            "received": List[MatchProposal],     # User was directly invited
            "available": List[MatchProposal],    # Open proposals user can accept
        }

    Filtering:
    - Expires old pending proposals automatically
    - Filters available open proposals by user location availability
    - Excludes expired proposals unless include_expired=True
    """

@transactional(domain="individual_match")
def accept_proposal(user_id: int, proposal_id: int) -> IndividualMatch:
    """Accept a match proposal.

    Validates proposal.can_be_accepted_by(user_id).
    Delegates to proposal.accept(user_id).

    Returns: Created IndividualMatch

    Raises:
        ValueError: If user cannot accept
        404: If proposal not found
    """

@transactional(domain="individual_match")
def reject_invitation(user_id: int, proposal_id: int) -> None:
    """Reject a direct invitation.

    Finds ProposalInvitation and calls invitation.reject().

    Raises:
        404: If invitation not found
    """

@transactional(domain="individual_match")
def cancel_proposal(user_id: int, proposal_id: int) -> None:
    """Cancel a match proposal.

    Validates user is proposer and status is PENDING.
    Calls proposal.cancel().

    Raises:
        ValueError: If user is not proposer or status is not PENDING
        404: If proposal not found
    """
```

**Usage Example:**
```python
# Get user's proposals
proposals = IndividualMatchService.get_user_proposals(current_user.id)

# Show created proposals
for proposal in proposals["created"]:
    print(f"Your proposal at {proposal.location}: {proposal.status.value}")

# Show received invitations
for proposal in proposals["received"]:
    print(f"Invited by {proposal.proposer.username}")

# Show available open proposals
for proposal in proposals["available"]:
    print(f"Open match at {proposal.location}")

# Accept a proposal
match = IndividualMatchService.accept_proposal(
    user_id=current_user.id,
    proposal_id=proposal.id
)
```

---

#### Match Management

```python
@transactional(domain="individual_match")
def start_match(match_id: int, user_id: int) -> IndividualMatch:
    """Start an individual match.

    Validates user is one of the players.
    Calls match.start_match().

    Raises:
        ValueError: If user is not a player
        404: If match not found
    """

@transactional(domain="individual_match")
def submit_rack_result(
    match_id: int,
    user_id: int,
    winner_id: int,
    rack_number: int,
    notes: Optional[str] = None,
) -> IndividualRack:
    """Submit result for a rack in individual match.

    Validates:
    - User is part of match
    - Winner is valid player
    - Rack number doesn't already exist

    Side effects:
    - Creates IndividualRack
    - Updates match scores
    - Checks for match completion using RackScore
    - If complete, sets status=COMPLETED and winner_id

    Raises:
        ValueError: If validation fails
        404: If match not found
    """

@transactional(domain="individual_match")
def complete_match(match_id: int, winner_id: int, user_id: int) -> IndividualMatch:
    """Complete a match.

    Validates user is one of the players.
    Calls match.complete_match(winner_id).

    Raises:
        ValueError: If user is not a player or match not in progress
        404: If match not found
    """

@transactional(domain="individual_match")
def cancel_match(
    match_id: int,
    user_id: int,
    reason: Optional[str] = None
) -> IndividualMatch:
    """Cancel a match.

    Validates user is one of the players.
    Calls match.cancel_match(reason).

    Raises:
        ValueError: If user is not a player or match is completed
        404: If match not found
    """
```

---

#### Statistics & Queries

```python
def get_user_matches(
    user_id: int,
    status_filter: Optional[MatchStatus] = None
) -> List[IndividualMatch]:
    """Get individual matches for a user.

    Args:
        user_id: User ID
        status_filter: Optional filter by status

    Returns: List ordered by scheduled_at DESC
    """

def get_user_statistics(user_id: int) -> Dict[str, Any]:
    """Get individual match statistics for a user.

    Returns:
        {
            "total_matches": int,
            "won_matches": int,
            "lost_matches": int,
            "win_percentage": float,
            "total_racks_won": int,
            "total_racks_played": int,
            "rack_win_percentage": float,
            "locations_played": {
                location: {"matches": int, "wins": int},
                ...
            }
        }
    """

def get_user_dashboard_data(user_id: int) -> Dict[str, Any]:
    """Get comprehensive dashboard data for user.

    Returns:
        {
            "proposals": Dict (from get_user_proposals),
            "matches": List[IndividualMatch],
            "active_matches": List[IndividualMatch],
            "recent_matches": List[IndividualMatch] (last 5 completed),
            "availability": Dict (from get_user_availability),
            "statistics": Dict (from get_user_statistics)
        }
    """
```

---

### AvailabilityService

**Purpose**: Player availability management and location-based player discovery with notifications.

**Complex service with 366 lines - handles venue-based player matching.**

#### Availability Management

```python
@transactional(domain="individual_match")
def set_player_availability(
    user_id: int,
    location: str,
    is_available: bool = True,
    preferred_days: Optional[List[int]] = None,
    preferred_times: Optional[str] = None,
) -> PlayerAvailability:
    """Set player availability preferences for a location (legacy).

    Updates existing or creates new PlayerAvailability.
    Stores preferred_days as JSON array.

    Returns: PlayerAvailability
    """

@transactional(domain="individual_match")
def set_venue_availability(
    user_id: int,
    billiard_hall_id: int,
    is_available: bool = True,
    available_days: Optional[List[int]] = None,
    preferred_times: Optional[str] = None,  # Format: "HH:MM-HH:MM"
) -> UserLocationAvailability:
    """Set player availability for a specific venue.

    Uses UserLocationAvailability from location domain.
    Parses preferred_times to time objects.
    Updates existing or creates new availability.

    Returns: UserLocationAvailability
    """
```

**Usage Example:**
```python
# Set availability at specific venue
availability = AvailabilityService.set_venue_availability(
    user_id=current_user.id,
    billiard_hall_id=venue.id,
    is_available=True,
    available_days=[1, 2, 3, 4, 5],  # Monday-Friday
    preferred_times="18:00-22:00"
)

# Set availability at location (legacy)
availability = AvailabilityService.set_player_availability(
    user_id=current_user.id,
    location="Sala Biliardo",
    is_available=True,
    preferred_days=[6, 7],  # Saturday-Sunday
    preferred_times="14:00-20:00"
)
```

---

#### Player Discovery

```python
def get_available_players_at_location(
    location: str,
    exclude_user_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get players available at a specific location (legacy).

    Returns:
        [
            {
                "user_id": int,
                "username": str,
                "location": str,
                "preferred_days": List[int],
                "preferred_times": str,
                "updated_at": datetime
            },
            ...
        ]
    """

def get_available_players_at_venue(
    billiard_hall_id: int,
    exclude_user_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get players available at a specific venue.

    Joins UserLocationAvailability, User, BilliardHall.
    Parses JSON available_days.
    Formats preferred times back to string.

    Returns:
        [
            {
                "user_id": int,
                "username": str,
                "venue_id": int,
                "venue_name": str,
                "available_days": List[int],
                "preferred_times": str,
                "updated_at": datetime
            },
            ...
        ]
    """

def get_user_availability_preferences(user_id: int) -> Dict[str, Any]:
    """Get all availability preferences for a user.

    Combines location-based and venue-based availability.

    Returns:
        {
            "locations": [
                {"id": int, "location": str, "preferred_days": List[int], "preferred_times": str, "type": "location"},
                ...
            ],
            "venues": [
                {"id": int, "venue_id": int, "venue_name": str, "available_days": List[int], "preferred_times": str, "type": "venue"},
                ...
            ]
        }
    """
```

**Usage Example:**
```python
# Find available players at venue
players = AvailabilityService.get_available_players_at_venue(
    billiard_hall_id=venue.id,
    exclude_user_id=current_user.id
)

for player in players:
    print(f"{player['username']} available at {player['venue_name']}")
    print(f"  Days: {player['available_days']}")
    print(f"  Times: {player['preferred_times']}")
```

---

#### Notification System

```python
@transactional(domain="individual_match")
def notify_players_of_availability(
    user_id: int,
    location: str,
    message: Optional[str] = None
) -> int:
    """Notify players who have played at this location about availability.

    Finds users who have played IndividualMatches at this location.
    Sends bulk notification via NotificationFactory.

    Args:
        user_id: User posting availability
        location: Location name
        message: Optional custom message (defaults to "{username} è disponibile...")

    Returns: Count of notifications successfully sent

    Side effects:
    - Creates MATCH_PROPOSAL notifications for all eligible users
    - Uses NotificationFactory.create_bulk_notification()
    """

@transactional(domain="individual_match")
def create_availability_based_match_request(
    requesting_user_id: int,
    target_user_id: int,
    location: str,
    proposed_datetime: Optional[datetime] = None,
    message: Optional[str] = None,
) -> MatchProposal:
    """Create a match request based on availability discovery.

    Creates direct match proposal to target user.
    Defaults to tomorrow if no datetime provided.

    Returns: MatchProposal
    """
```

**Usage Example:**
```python
# User posts availability
count = AvailabilityService.notify_players_of_availability(
    user_id=current_user.id,
    location="Sala Biliardo",
    message="Disponibile per una partita stasera alle 20:00!"
)
print(f"Notificati {count} giocatori")

# User sees available player and sends match request
proposal = AvailabilityService.create_availability_based_match_request(
    requesting_user_id=current_user.id,
    target_user_id=available_player.id,
    location="Sala Biliardo",
    proposed_datetime=datetime(2025, 10, 15, 20, 0),
    message="Vuoi giocare stasera?"
)
```

---

### MatchProposalService

**Purpose**: Simplified facade for proposal creation and management.

**Delegates to IndividualMatchService for actual implementation.**

```python
def create_proposal(
    proposer_id: int,
    proposal_type: ProposalType,
    location: str,
    scheduled_at: datetime,
    expires_at: datetime,
    discipline: str = "palla_8",
    distance: int = 5,
    best_of: bool = True,
    break_rule: str = "alternate",
    description: Optional[str] = None,
    entry_fee: Optional[float] = None,
    invited_user_ids: Optional[List[int]] = None,
) -> MatchProposal:
    """Create a match proposal (delegates to IndividualMatchService)."""

def get_user_proposals(user_id: int) -> Dict[str, List[MatchProposal]]:
    """Get proposals organized by user relationship (delegates)."""

def accept_proposal(proposal_id: int, user_id: int) -> IndividualMatch:
    """Accept a match proposal (delegates)."""

def cancel_proposal(proposal_id: int, user_id: int) -> None:
    """Cancel a proposal (delegates)."""

@transactional(domain="individual_match")
def expire_proposals() -> int:
    """Mark expired proposals as expired.

    Returns: Count of expired proposals
    """
```

---

## Common Workflows

### Workflow 1: Create and Accept Direct Match Proposal

```python
from models.individual_match.services import IndividualMatchService
from datetime import datetime, timedelta

# User creates direct match proposal
proposal = IndividualMatchService.create_direct_proposal(
    proposer_id=proposer.id,
    invited_user_ids=[player1.id, player2.id],
    location="Sala Biliardo",
    scheduled_at=datetime.now() + timedelta(days=1, hours=19),
    discipline="palla_8",
    distance=7,
    best_of=True,
    description="Partita amichevole per pratica"
)
# Notifications automatically sent to player1 and player2

# Player1 checks proposals
proposals = IndividualMatchService.get_user_proposals(player1.id)
received = proposals["received"]

# Player1 accepts
match = IndividualMatchService.accept_proposal(
    user_id=player1.id,
    proposal_id=proposal.id
)
# Now: proposal.status=ACCEPTED, IndividualMatch created
# Player2's invitation automatically cancelled
```

---

### Workflow 2: Create Open Match Proposal and Accept

```python
# User creates open match proposal
proposal = IndividualMatchService.create_open_proposal(
    proposer_id=proposer.id,
    location="Sala Biliardo",
    scheduled_at=datetime(2025, 10, 15, 19, 0),
    discipline="palla_9",
    distance=9,
    best_of=True,
    description="Cerco avversario per race to 9"
)

# Other players see available proposals
proposals = IndividualMatchService.get_user_proposals(player.id)
available = proposals["available"]

# Available proposals are filtered by:
# 1. User's location availability
# 2. User's match history at location

# Player accepts open proposal
if proposal.can_be_accepted_by(player.id):
    match = IndividualMatchService.accept_proposal(
        user_id=player.id,
        proposal_id=proposal.id
    )
```

---

### Workflow 3: Play Match and Track Results

```python
# Match created from accepted proposal
match = IndividualMatch.query.get(match_id)

# Player1 starts match
IndividualMatchService.start_match(
    match_id=match.id,
    user_id=player1.id
)
# Now: match.status=IN_PROGRESS, started_at=now

# Submit rack results
IndividualMatchService.submit_rack_result(
    match_id=match.id,
    user_id=player1.id,
    winner_id=player1.id,
    rack_number=1
)
# player1_score=1, player2_score=0

IndividualMatchService.submit_rack_result(
    match_id=match.id,
    user_id=player2.id,
    winner_id=player2.id,
    rack_number=2
)
# player1_score=1, player2_score=1

# Continue until match is won
# Match automatically completes when target score reached
# For best_of=True, distance=7: first to 7 wins
# Match completion uses RackScore.is_complete() for validation
```

---

### Workflow 4: Player Availability and Discovery

```python
from models.individual_match.availability_service import AvailabilityService

# User sets availability at venue
availability = AvailabilityService.set_venue_availability(
    user_id=current_user.id,
    billiard_hall_id=venue.id,
    is_available=True,
    available_days=[1, 2, 3, 4, 5],  # Monday-Friday
    preferred_times="18:00-22:00"
)

# Find available players at same venue
players = AvailabilityService.get_available_players_at_venue(
    billiard_hall_id=venue.id,
    exclude_user_id=current_user.id
)

for player in players:
    print(f"{player['username']} available:")
    print(f"  Days: {player['available_days']}")
    print(f"  Times: {player['preferred_times']}")

# Send match request to discovered player
proposal = AvailabilityService.create_availability_based_match_request(
    requesting_user_id=current_user.id,
    target_user_id=players[0]["user_id"],
    location=venue.name,
    proposed_datetime=datetime(2025, 10, 15, 19, 0),
    message="Vuoi giocare domani sera?"
)
```

---

### Workflow 5: Notify Available Players

```python
# User posts availability at location
count = AvailabilityService.notify_players_of_availability(
    user_id=current_user.id,
    location="Sala Biliardo",
    message="Disponibile per una partita stasera alle 20:00!"
)
print(f"Notificati {count} giocatori che hanno giocato qui")

# Other players receive MATCH_PROPOSAL notification
# They can respond by:
# 1. Creating direct proposal to current_user
# 2. Accepting if current_user creates open proposal
```

---

### Workflow 6: User Dashboard

```python
# Get comprehensive dashboard data
dashboard = IndividualMatchService.get_user_dashboard_data(current_user.id)

# Proposals (created, received, available)
print(f"Created proposals: {len(dashboard['proposals']['created'])}")
print(f"Received invitations: {len(dashboard['proposals']['received'])}")
print(f"Available open matches: {len(dashboard['proposals']['available'])}")

# Active matches
for match in dashboard["active_matches"]:
    opponent = match.get_opponent(current_user.id)
    print(f"Match vs {opponent.username}: {match.status.value}")

# Recent completed matches
for match in dashboard["recent_matches"]:
    opponent = match.get_opponent(current_user.id)
    score = f"{match.get_user_score(current_user.id)}-{match.get_user_score(opponent.id)}"
    print(f"vs {opponent.username}: {score}")

# Statistics
stats = dashboard["statistics"]
print(f"Win rate: {stats['win_percentage']:.1f}%")
print(f"Rack win rate: {stats['rack_win_percentage']:.1f}%")

# Availability
for venue in dashboard["availability"]["venues"]:
    print(f"Available at {venue['venue_name']}: {venue['preferred_times']}")
```

---

## Important Notes

### Transaction Management

**All service methods use `@transactional(domain="individual_match")` decorator:**
- Automatic commit on success
- Automatic rollback on error
- Never call `db.session.commit()` directly

---

### Proposal Expiration

**Proposals automatically expire:**
```python
# Set expires_at when creating
proposal = IndividualMatchService.create_direct_proposal(
    ...,
    scheduled_at=datetime(2025, 10, 15, 19, 0),
    expires_at=datetime(2025, 10, 15, 17, 0)  # Expires 2h before match
)

# Or let service default to 2h before scheduled_at
proposal = IndividualMatchService.create_direct_proposal(
    ...,
    scheduled_at=datetime(2025, 10, 15, 19, 0)
    # expires_at defaults to scheduled_at - 2 hours
)

# Run periodic cleanup
expired_count = MatchProposalService.expire_proposals()
```

**Best Practice**: Run `expire_proposals()` hourly via cron job.

---

### Multi-Set Support (Phase 6: Frontend Integration)

**Both MatchProposal and IndividualMatch support multi-set configuration:**
```python
# Create multi-set proposal
proposal = MatchProposal(
    ...,
    is_multi_set=True,
    distance=5,  # Racks per set
    match_distance=3,  # Sets to win
    sets_best_of=True
)

# Access via Distance value object
distance_config = proposal.distance_config
# Returns: Distance(racks=5, is_multi_set=True, sets=3, sets_best_of=True)
```

**Important**: Frontend integration pending - multi-set UI not yet implemented.

---

### Notification Integration

**Notifications sent automatically on proposal creation:**
```python
# Direct proposal → notifications to invited users
IndividualMatchService.create_direct_proposal(
    proposer_id=proposer.id,
    invited_user_ids=[player1.id, player2.id],
    ...
)
# Automatically sends MATCH_PROPOSAL notifications to player1 and player2

# Errors in notification creation don't block proposal creation
# Failed notifications are logged but proposal still succeeds
```

---

### Location vs Venue

**Two availability systems coexist:**

1. **Legacy string-based** (`PlayerAvailability`):
   - Uses `location: str` field
   - Deprecated but still supported
   - Used by `get_available_players_at_location()`

2. **Venue-based** (`UserLocationAvailability`):
   - Uses `billiard_hall_id: int` foreign key
   - Preferred for new code
   - Used by `get_available_players_at_venue()`

**Recommendation**: Use venue-based availability for new features.

---

### Score Interpretation

**`player1_score` and `player2_score` meaning:**
- **Single-set match** (`is_multi_set=False`): Scores represent **racks won**
- **Multi-set match** (`is_multi_set=True`): Scores represent **sets won**

**Always check `is_multi_set` before interpreting scores.**

---

### Proposal Acceptance Rules

**For DIRECT proposals:**
- User must be explicitly invited (ProposalInvitation exists)
- Invitation status must be PENDING
- Proposal status must be PENDING
- Not expired
- User is not proposer

**For OPEN proposals:**
- Any user can accept
- User must have availability at location (checked by `get_user_proposals()`)
- Proposal status must be PENDING
- Not expired
- User is not proposer

---

### Error Handling

**Common errors:**
```python
# ValueError: User cannot accept
try:
    match = IndividualMatchService.accept_proposal(user.id, proposal.id)
except ValueError as e:
    # Proposal expired, user not invited, or status not PENDING
    print(f"Cannot accept: {e}")

# 404: Proposal not found
try:
    match = IndividualMatchService.accept_proposal(user.id, 99999)
except werkzeug.exceptions.NotFound:
    # Proposal doesn't exist
    print("Proposal not found")
```

---

## Cross-References

### Depends On (External dependencies)

- **User Domain** (`models/user/models.py`): User model for players
- **Location Domain** (`models/location/models.py`): BilliardHall, UserLocationAvailability
- **Notification Domain** (`models/notification/`): NotificationFactory for invitations
- **Match Domain** (`models/match/distance.py`): Distance and RackScore value objects
- **Transaction Domain** (`models/transaction/`): @transactional decorator

### Used By (Domains that use individual matches)

- **Routes** (`routes/individual_match.py`): Individual match routes
- **Routes** (`routes/player.py`): Player dashboard and availability

### Distinct From

**Competition/Match Domains** (`models/competition/`, `models/match/`):
- **Individual Match**: Casual player-to-player games, no tournament structure
- **Competition Match**: Formal tournament matches within gara/campionato

**Key Differences:**
- IndividualMatch has no `gara_id` - standalone
- IndividualMatch uses MatchProposal invitation system
- Competition Match uses matchmaking strategies

---

### Related Documentation

- **[models/notification/CLAUDE.md](../notification/CLAUDE.md)**: Notification system integration
- **[models/user/CLAUDE.md](../user/CLAUDE.md)**: User model and permissions
- **[models/location/CLAUDE.md](../location/)**: Venue-based availability system
- **[models/match/CLAUDE.md](../match/CLAUDE.md)**: Distance/Score value objects

---

## Testing Individual Matches

### Unit Tests

```python
def test_proposal_expiration():
    proposal = MatchProposal(
        proposer_id=user.id,
        proposal_type=ProposalType.OPEN,
        location="Test",
        scheduled_at=datetime.now() + timedelta(days=1),
        expires_at=datetime.now() - timedelta(hours=1)  # Already expired
    )

    assert proposal.is_expired() is True
    assert proposal.can_be_accepted_by(other_user.id) is False

def test_match_completion():
    match = IndividualMatch(
        player1_id=player1.id,
        player2_id=player2.id,
        location="Test",
        scheduled_at=datetime.now(),
        distance=3,  # Race to 3
        best_of=True
    )
    match.start_match()

    # Player1 wins 3 racks
    match.add_rack_result(player1.id)  # 1-0
    match.add_rack_result(player1.id)  # 2-0
    match.add_rack_result(player1.id)  # 3-0

    # Match should be automatically completed
    assert match.status == MatchStatus.COMPLETED
    assert match.winner_id == player1.id
```

### Integration Tests

```python
def test_proposal_workflow(db_session):
    # Create proposal
    proposal = IndividualMatchService.create_direct_proposal(
        proposer_id=proposer.id,
        invited_user_ids=[invitee.id],
        location="Test Venue",
        scheduled_at=datetime.now() + timedelta(days=1),
        distance=5,
        best_of=True
    )

    # Check invitation created
    invitation = ProposalInvitation.query.filter_by(
        proposal_id=proposal.id,
        invited_user_id=invitee.id
    ).first()
    assert invitation is not None
    assert invitation.status == InvitationStatus.PENDING

    # Accept proposal
    match = IndividualMatchService.accept_proposal(invitee.id, proposal.id)

    # Verify state
    assert proposal.status == ProposalStatus.ACCEPTED
    assert match.player1_id == proposer.id
    assert match.player2_id == invitee.id
    assert invitation.status == InvitationStatus.ACCEPTED
```

---

## Performance Considerations

### Query Optimization

**Use eager loading for relationships:**
```python
# ✅ Efficient - single query
proposals = db.session.query(MatchProposal)\
    .options(joinedload(MatchProposal.proposer))\
    .options(joinedload(MatchProposal.invitations))\
    .filter_by(status=ProposalStatus.PENDING)\
    .all()

# ❌ Inefficient - N+1 queries
proposals = MatchProposal.query.filter_by(status=ProposalStatus.PENDING).all()
for proposal in proposals:
    print(proposal.proposer.username)  # Lazy load for each proposal
```

---

### Cleanup Operations

**Run periodic cleanup to prevent database bloat:**
```python
# Expire old proposals (hourly cron)
MatchProposalService.expire_proposals()

# Delete old completed matches (monthly)
cutoff = datetime.now() - timedelta(days=90)
old_matches = IndividualMatch.query.filter(
    IndividualMatch.status == MatchStatus.COMPLETED,
    IndividualMatch.completed_at < cutoff
).all()
for match in old_matches:
    db.session.delete(match)
db.session.commit()
```

---

## Future Enhancements

### Location Integration
- **TODO**: Replace `location: str` with `billiard_hall_id: int` foreign key
- **TODO**: Migrate PlayerAvailability to UserLocationAvailability
- **TODO**: Remove duplicate location fields from IndividualMatch

### Multi-Set Frontend
- **Phase 6**: Implement multi-set UI for match proposals
- **Phase 6**: Add set-by-set scoring interface
- **Phase 6**: Display set history in match views

### Advanced Matchmaking
- **Future**: ELO-based opponent suggestions
- **Future**: Availability overlap detection (time windows)
- **Future**: Recurring match proposals (weekly games)

### Social Features
- **Future**: Match commenting and chat
- **Future**: Post-match reviews and ratings
- **Future**: Player rivalry tracking
