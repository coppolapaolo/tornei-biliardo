# User Domain Documentation

## Purpose

The User domain is the **central entity** of the community platform, referenced by ALL other domains. It manages user identity, authentication, roles, permissions, and director/venue manager workflows.

**Core Responsibilities:**
- User authentication and password management
- Role-based access control (Admin, Director, Player)
- Director promotion workflow with request system
- Venue manager assignment and permissions
- User statistics and profile management
- Soft delete with PII anonymization
- Encrypted personal data (email, phone)

**Related Domains:**
- [models/competition/CLAUDE.md](../competition/CLAUDE.md): Inscription, GaraDirector assignments
- [models/notification/CLAUDE.md](../notification/CLAUDE.md): User notifications
- [models/individual_match/CLAUDE.md](../individual_match/CLAUDE.md): Match proposals, availability
- [models/location/CLAUDE.md](../location/): BilliardHall, venue management
- [models/events/](../events/): DirectorRequestCreatedEvent, UserEvents

---

## 📦 Domain Structure

**Files** (10 total, 3,653 lines):
- `models.py` (504 lines): User, DirectorAssignment, DirectorRequest, VenueManagement models
- `services.py` (472 lines): UserService facade
- `permission_service.py` (449 lines): UserPermissionService - director requests
- `venue_manager_service.py` (497 lines): VenueManagerService - venue management
- `profile_service.py` (416 lines): UserProfileService - CRUD operations
- `stats_service.py` (259 lines): UserStatsService - statistics
- `permissions.py` (884 lines): PermissionChecker, RoleRequirement decorators
- `role_enum.py` (8 lines): UserRole enum
- `soft_delete_filter.py` (44 lines): SQLAlchemy soft delete filter
- `__init__.py` (120 lines): Package exports

---

## Quick Reference

### Most-Used Classes

```python
from models.user import User, DirectorAssignment, DirectorRequest, VenueManagement
from models.user.services import UserService
from models.user.permission_service import UserPermissionService
from models.user.venue_manager_service import VenueManagerService
from models.user.permissions import PermissionChecker, RoleRequirement
from models.user.role_enum import UserRole
```

### Common Operations

```python
# Create user
user = UserService.create_user(
    username="mario",
    email="mario@example.com",
    password="secure123",
    role="player"  # or "director" or "admin"
)

# Check role
if user.is_admin:
    # Admin operations
elif user.is_director:
    # Director operations
elif user.is_player:
    # Player operations

# Check permissions
if user.can_manage_competition(gara_id):
    # User can manage this gara

# Request director promotion
request = UserPermissionService.create_director_request(user.id)

# Process director request (admin only)
UserPermissionService.process_director_request(
    request_id=request.id,
    admin_user=admin,
    approve=True
)

# Soft delete with anonymization
user.anonymize()
db.session.commit()
```

---

## Key Classes

### User ([models.py:35-306](models.py))

**Purpose**: Core user entity with authentication, roles, permissions, and statistics

**Database Fields:**
```python
id: int (PK)
username: str(80) - unique, not null
email: EncryptedString(200) - unique, encrypted PII
password_hash: str(120) - bcrypt hash
role: str(20) - "admin", "director", "player" (default)
phone: EncryptedString(100) - encrypted PII, nullable
fargo_rating: int - Fargo rating (Phase 4), nullable
elo_rating: int - Elo rating (Phase 4), nullable
previous_username: str(80) - for soft delete, nullable
created_at: datetime - auto (TimestampMixin)
updated_at: datetime - auto (TimestampMixin)
deleted_at: datetime - soft delete (SoftDeleteMixin), nullable
```

**Mixins:**
- `UserMixin` (Flask-Login): Authentication integration
- `BaseModel`: SQLAlchemy base
- `TimestampMixin`: Auto created_at/updated_at
- `SoftDeleteMixin`: Soft delete with deleted_at

**Relationships:**
```python
inscriptions: List[Inscription] - competition inscriptions
match_results: List[MatchResult] - match results
classifications: List[Classification] - campionato rankings
round_classifications: List[RoundClassification] - round rankings
player1_encounters: List[PlayerEncounter] - matches as player1
player2_encounters: List[PlayerEncounter] - matches as player2
director_request: DirectorRequest - pending director request (viewonly)
director_assignments: List[DirectorAssignment] - director assignments (backref)
```

**Key Methods:**

**Authentication:**
```python
def set_password(self, password: str) -> None
    """Hash and set password using bcrypt."""

def check_password(self, password: str) -> bool
    """Verify password against hash."""
```

**Role Properties:**
```python
@property
def is_admin(self) -> bool
    """True if user role is 'admin'."""

@property
def is_director(self) -> bool
    """True if user role is 'director'."""

@property
def is_player(self) -> bool
    """True if user role is 'player'."""

@property
def is_venue_manager(self) -> bool
    """True if user has active VenueManagement assignment."""

@property
def is_active(self) -> bool
    """Flask-Login: True if not soft deleted."""
```

**Permission Methods:**
```python
def can_manage_campionato(self, campionato_id: int) -> bool
    """Check if user can manage campionato (admin or assigned director)."""

def can_manage_competition(self, competition_id: int) -> bool
    """Check if user can manage gara (admin or assigned director)."""

def can_view_admin_panel(self) -> bool
    """Admin only."""

def can_inscribe_to_competition(self, competition_id: int) -> bool
    """True if player AND not manager of competition."""

def can_manage_venue(self, venue_id: int) -> bool
    """Check if user can manage specific venue."""

def get_managed_venues(self) -> List[BilliardHall]
    """Get list of venues user can manage."""
```

**Management Methods:**
```python
def get_managed_campionatos(self) -> List[Campionato]
    """Campionatos user can manage (admin: all, director: assigned)."""

def get_statistics(self) -> Dict[str, Any]
    """Complete user statistics for dashboard."""
    # Returns: total_inscriptions, total_matches, won_matches, lost_matches,
    #          win_percentage, tournaments_played, provas_played,
    #          total_racks_won, total_racks_played, rack_win_percentage
```

**Soft Delete:**
```python
def anonymize(self) -> None
    """Soft delete with PII anonymization.

    Sets:
    - deleted_at = now
    - previous_username = current username
    - username = "deleted-{id}-{date}"
    - email = None
    - phone = None
    - password_hash = "!deleted!"
    """
```

**Usage Examples:**

```python
# Create admin user
admin = UserService.create_user(
    username="admin",
    email="admin@example.com",
    password="admin123",
    role=UserRole.ADMIN.value
)

# Authenticate
if user.check_password("password123"):
    # Login success
    login_user(user)

# Check permissions
if user.can_manage_competition(gara.id):
    # Allow competition management
    gara.status = GaraStatus.PLAYING

# Get user statistics
stats = user.get_statistics()
print(f"Win rate: {stats['win_percentage']}%")

# Soft delete user
user.anonymize()
db.session.commit()
# username becomes "deleted-42-20251007"
# email and phone are nulled
```

---

### DirectorAssignment ([models.py:311-354](models.py))

**Purpose**: Generic director assignment to campionato or gara (formerly TournamentDirector)

**Database Fields:**
```python
user_id: int (PK, FK user.id)
entity_type: str(20) (PK) - "campionato" or "gara"
entity_id: int (PK) - campionato_id or gara_id
assigned_by_id: int (FK user.id) - admin who assigned
assigned_at: datetime - assignment timestamp
```

**Composite Primary Key**: (user_id, entity_type, entity_id)

**Relationships:**
```python
director: User - the director user
assigned_by: User - admin who made assignment
```

**Properties:**
```python
@property
def campionato(self) -> Optional[Campionato]
    """Get campionato if entity_type == 'campionato'."""

@property
def gara(self) -> Optional[Gara]
    """Get gara if entity_type == 'gara'."""
```

**Legacy Aliases:**
```python
TournamentDirector = DirectorAssignment  # Backward compatibility
GaraDirector = DirectorAssignment  # Backward compatibility
```

**Usage Examples:**

```python
# Assign director to campionato
assignment = DirectorAssignment(
    user_id=director.id,
    entity_type="campionato",
    entity_id=campionato.id,
    assigned_by_id=admin.id
)
db.session.add(assignment)
db.session.commit()

# Query director assignments
assignments = DirectorAssignment.query.filter_by(
    user_id=user.id,
    entity_type="campionato"
).all()

campionatos = [a.campionato for a in assignments if a.campionato]

# Check if user is director for entity
is_director = DirectorAssignment.query.filter_by(
    user_id=user.id,
    entity_type="gara",
    entity_id=gara.id
).first() is not None
```

---

### DirectorRequest ([models.py:359-399](models.py))

**Purpose**: Director promotion request workflow with admin approval

**Database Fields:**
```python
id: int (PK)
user_id: int (FK user.id) - requesting user
requested_at: datetime - request timestamp
status: str(20) - "pending", "approved", "rejected"
processed_at: datetime - when processed, nullable
processed_by_id: int (FK user.id) - admin who processed, nullable
notes: text - rejection reason or notes, nullable
```

**Relationships:**
```python
user: User - requesting user
processed_by: User - admin who processed
```

**State Methods:**
```python
def approve(self, admin: User) -> None
    """Approve request and promote user to director.

    Sets:
    - status = "approved"
    - processed_at = now
    - processed_by = admin
    - user.role = "director"
    """

def reject(self, admin: User, notes: Optional[str] = None) -> None
    """Reject request with optional notes.

    Sets:
    - status = "rejected"
    - processed_at = now
    - processed_by = admin
    - notes = provided notes
    """
```

**Usage Examples:**

```python
# Player requests director promotion
request = UserPermissionService.create_director_request(player.id)
# Creates request with status="pending"
# Emits DirectorRequestCreatedEvent for admin notifications

# Admin approves request
UserPermissionService.process_director_request(
    request_id=request.id,
    admin_user=admin,
    approve=True
)
# User role becomes "director"
# Status becomes "approved"

# Admin rejects request
UserPermissionService.process_director_request(
    request_id=request.id,
    admin_user=admin,
    approve=False,
    notes="Insufficient experience"
)
# Status becomes "rejected"
```

---

### VenueManagement ([models.py:402-437](models.py))

**Purpose**: Venue manager assignment tracking

**Database Fields:**
```python
id: int (PK)
user_id: int (FK user.id) - venue manager
venue_id: int (FK billiard_hall.id) - managed venue
assigned_by_id: int (FK user.id) - admin who assigned
assigned_at: datetime - assignment timestamp
is_active: bool - active status (default True)
```

**Relationships:**
```python
user: User - venue manager
venue: BilliardHall - managed venue
assigned_by: User - admin who made assignment
```

**Usage Examples:**

```python
# Assign venue manager
assignment = VenueManagement(
    user_id=player.id,
    venue_id=venue.id,
    assigned_by_id=admin.id,
    is_active=True
)
db.session.add(assignment)
db.session.commit()

# Check if user manages venue
if user.can_manage_venue(venue.id):
    # Allow venue operations

# Get managed venues
venues = user.get_managed_venues()
for venue in venues:
    print(f"{user.username} manages {venue.name}")

# Deactivate manager
assignment.is_active = False
db.session.commit()
```

---

### VenueManagerRequest ([models.py:440-504](models.py))

**Purpose**: Venue manager request workflow (similar to DirectorRequest)

**Database Fields:**
```python
id: int (PK)
user_id: int (FK user.id) - requesting user
venue_id: int (FK billiard_hall.id) - requested venue
requested_at: datetime - request timestamp
status: str(20) - "pending", "approved", "rejected"
motivation: text - why user wants to manage venue
processed_at: datetime - when processed, nullable
processed_by_id: int (FK user.id) - admin who processed, nullable
notes: text - admin notes, nullable
```

**Relationships:**
```python
user: User - requesting user
venue: BilliardHall - requested venue
processed_by: User - admin who processed
```

**Usage Examples:**

```python
# Player requests venue manager role
request = VenueManagerService.create_venue_manager_request(
    user_id=player.id,
    venue_id=venue.id,
    motivation="I play here weekly and want to organize tournaments"
)

# Admin processes request
VenueManagerService.process_venue_manager_request(
    request_id=request.id,
    admin_user=admin,
    approve=True
)
# Creates VenueManagement assignment
```

---

## Services

### UserService (Facade) ([services.py:62-186](services.py))

**Purpose**: Facade for all user operations, delegates to specialized services

**Architecture**: Task 1.3 Decomposition - Backward compatibility facade

**Delegates To:**
- `UserProfileService`: User CRUD and authentication
- `UserPermissionService`: Roles and director requests
- `UserStatsService`: Statistics and analytics
- `VenueManagerService`: Venue management workflow

**Key Methods** (all delegate to specialized services):
```python
@staticmethod
def create_user(username: str, email: str, password: str,
                role: str = "player", phone: Optional[str] = None) -> User
    """Create new user."""

@staticmethod
def update_user(user_id: int, **kwargs) -> User
    """Update user fields."""

@staticmethod
def change_password(user_id: int, old_password: str, new_password: str) -> bool
    """Change user password with verification."""

@staticmethod
def promote_to_director(user_id: int, promoted_by_id: int) -> bool
    """Promote user to director role."""

@staticmethod
def soft_delete_user(user_id: int) -> User
    """Soft delete user with anonymization."""

@staticmethod
def list_all_users() -> List[User]
    """List all active users."""
```

---

### UserPermissionService ([permission_service.py](permission_service.py))

**Purpose**: User permissions and director request management

**Transaction Management**: Uses `@transactional(domain="user")`

**Key Methods:**

```python
@staticmethod
@transactional(domain="user")
def create_director_request(user_id: int) -> DirectorRequest
    """Create director promotion request.

    Validation:
    - User must exist
    - User not already director/admin
    - No pending request exists

    Emits: DirectorRequestCreatedEvent
    """

@staticmethod
@transactional(domain="user")
def process_director_request(request_id: int, admin_user: User,
                             approve: bool, notes: Optional[str] = None) -> DirectorRequest
    """Process director request (approve/reject).

    On approve:
    - User.role = "director"
    - Emits DirectorRequestApprovedEvent

    On reject:
    - Emits DirectorRequestRejectedEvent
    """

@staticmethod
@read_only(domain="user")
def get_pending_director_requests() -> List[DirectorRequest]
    """Get all pending director requests."""
```

**Usage Examples:**

```python
# Player requests promotion
try:
    request = UserPermissionService.create_director_request(player.id)
    flash("Director request submitted", "success")
except ValueError as e:
    flash(str(e), "error")

# Admin gets pending requests
pending = UserPermissionService.get_pending_director_requests()
for req in pending:
    print(f"{req.user.username} requested at {req.requested_at}")

# Admin approves
request = UserPermissionService.process_director_request(
    request_id=request.id,
    admin_user=admin,
    approve=True
)
# User is now director
```

---

### VenueManagerService ([venue_manager_service.py](venue_manager_service.py))

**Purpose**: Venue management request and assignment workflow

**Transaction Management**: Uses `@transactional(domain="user")`

**Key Methods:**

```python
@staticmethod
@transactional(domain="user")
def create_venue_manager_request(user_id: int, venue_id: int,
                                 motivation: str) -> VenueManagerRequest
    """Create venue manager request.

    Validation:
    - User must exist and be player
    - Venue must exist
    - No pending request for same venue
    - Motivation required

    Emits: VenueManagerRequestCreatedEvent
    """

@staticmethod
@transactional(domain="user")
def process_venue_manager_request(request_id: int, admin_user: User,
                                  approve: bool, notes: Optional[str] = None) -> VenueManagerRequest
    """Process venue manager request.

    On approve:
    - Creates VenueManagement assignment
    - Emits VenueManagerRequestApprovedEvent
    """
```

---

### PermissionChecker ([permissions.py](permissions.py))

**Purpose**: Static permission checking utility

**Key Methods:**

```python
@staticmethod
def can_manage_campionato(user: User, campionato_id: int) -> bool
    """Check if user can manage campionato."""

@staticmethod
def can_manage_competition(user: User, competition_id: int) -> bool
    """Check if user can manage gara."""

@staticmethod
def is_director_of_gara(user: User, gara_id: int) -> bool
    """Check if user is assigned director of gara."""
```

**Decorators:**

```python
@role_required(UserRole.ADMIN)
def admin_only_route():
    """Only admins can access."""

@permission_required("manage_competition", competition_id_param="gara_id")
def edit_gara(gara_id):
    """Only directors/admins of gara can access."""
```

---

## Common Workflows

### 1. User Registration and Authentication

```python
# Register new user
user = UserService.create_user(
    username="paolo",
    email="paolo@example.com",
    password="secure123",
    role=UserRole.PLAYER.value
)
# User created with hashed password
# Email is encrypted in database

# Login
user = User.query.filter_by(username="paolo").first()
if user and user.check_password("secure123"):
    login_user(user)
    redirect(url_for("dashboard.index"))
```

### 2. Director Promotion Workflow

```python
# Step 1: Player requests promotion
request = UserPermissionService.create_director_request(player.id)
# DirectorRequestCreatedEvent emitted
# Admin receives notification

# Step 2: Admin reviews request
pending_requests = UserPermissionService.get_pending_director_requests()
for req in pending_requests:
    print(f"{req.user.username} - {req.requested_at}")

# Step 3: Admin approves
request = UserPermissionService.process_director_request(
    request_id=request.id,
    admin_user=admin,
    approve=True
)
# User.role = "director"
# DirectorRequestApprovedEvent emitted
# User receives notification
```

### 3. Director Assignment to Campionato

```python
# Admin assigns director to campionato
from models.user.models import DirectorAssignment

assignment = DirectorAssignment(
    user_id=director.id,
    entity_type="campionato",
    entity_id=campionato.id,
    assigned_by_id=admin.id
)
db.session.add(assignment)
db.session.commit()

# Check permission
if user.can_manage_campionato(campionato.id):
    # Director can manage this campionato
    # Allow inscription management, gara creation, etc.
```

### 4. Venue Manager Workflow

```python
# Step 1: Player requests venue manager
request = VenueManagerService.create_venue_manager_request(
    user_id=player.id,
    venue_id=venue.id,
    motivation="I play here 3x per week and want to organize leagues"
)

# Step 2: Admin approves
VenueManagerService.process_venue_manager_request(
    request_id=request.id,
    admin_user=admin,
    approve=True
)
# VenueManagement assignment created

# Step 3: Check permission
if user.can_manage_venue(venue.id):
    # Allow venue-specific operations
    venue.business_hours = "Mon-Fri 14:00-23:00"
```

### 5. User Statistics Dashboard

```python
# Get complete statistics
stats = user.get_statistics()

print(f"""
User: {user.username}
Total Matches: {stats['total_matches']}
Win Rate: {stats['win_percentage']}%
Tournaments: {stats['tournaments_played']}
Rack Win Rate: {stats['rack_win_percentage']}%
""")

# Or use UserStatsService for more detailed stats
from models.user.stats_service import UserStatsService

detailed = UserStatsService.get_user_statistics(user.id)
```

### 6. Soft Delete with Anonymization

```python
# Soft delete user (GDPR compliance)
user = User.query.get(user_id)
user.anonymize()
db.session.commit()

# User data after anonymization:
# username: "deleted-42-20251007"
# email: None
# phone: None
# password_hash: "!deleted!"
# deleted_at: 2025-10-07 15:30:00
# previous_username: "paolo" (preserved for records)

# User is_active = False (Flask-Login)
# User excluded from soft_delete_filter queries
```

---

## Important Notes

### Business Rules

**Role Hierarchy:**
- **Admin**: Can manage ALL campionatos, gare, venues
- **Director**: Can manage assigned campionatos/gare only
- **Player**: Can inscribe to competitions, propose matches, request promotions

**Director Promotion:**
- Only players can request promotion (directors/admins cannot)
- Only one pending request allowed per user
- Approval creates DirectorRequest with status="approved"
- User.role changes to "director" on approval

**Venue Management:**
- Admin can manage all venues
- Venue managers can manage only assigned venues
- Multiple managers per venue allowed
- VenueManagement.is_active for soft deactivation

**Soft Delete:**
- User.deleted_at != None marks user as deleted
- Soft delete filter excludes from queries automatically
- anonymize() method handles PII removal (GDPR)
- previous_username preserved for audit trail

### Encrypted Fields

**PII Encryption** (using EncryptedString):
- `User.email`: Encrypted at rest
- `User.phone`: Encrypted at rest
- Query by encrypted fields requires decryption
- See `models/fields.py` for EncryptedString implementation

**Example:**
```python
# Creating user with encrypted email
user = User(
    username="paolo",
    email="paolo@example.com",  # Stored encrypted
    phone="+39123456789"  # Stored encrypted
)
db.session.add(user)
db.session.commit()

# Querying - automatic decryption
user = User.query.filter_by(email="paolo@example.com").first()
# EncryptedString handles encryption/decryption transparently
```

### Phase 4 Rating Refactoring

**Key Changes:**
- ✅ `User.fargo_rating` and `User.elo_rating` added (player skill)
- ✅ `Campionato.scoring_policy` remains (classification calculation method)
- ❌ `Gara.rating_type` REMOVED (was architectural mistake)

**Rationale:**
- Rating is a **player property** (skill level)
- Scoring policy is a **campionato configuration** (how to calculate rankings)
- Gara should not have rating_type (it's a round, not a tournament)

**Migration:**
- All Amalfi strategies use `User.fargo_rating` or `User.elo_rating` directly
- No breaking changes - backward compatible

### Gotchas & Edge Cases

**1. Role Properties Are Computed**
```python
# ❌ Wrong - cannot set computed property
user.is_admin = True  # AttributeError

# ✅ Correct - set role field
user.role = UserRole.ADMIN.value
```

**2. Soft Delete Filter**
```python
# Soft delete filter excludes deleted users automatically
users = User.query.all()  # Only active users

# Include deleted users
from sqlalchemy import inspect
session = inspect(User).session
users = session.query(User).filter(User.id > 0).all()
```

**3. DirectorAssignment Composite Key**
```python
# Query requires all PK fields
assignment = DirectorAssignment.query.filter_by(
    user_id=user.id,
    entity_type="campionato",
    entity_id=campionato.id
).first()

# Or use get with tuple
assignment = db.session.get(
    DirectorAssignment,
    (user.id, "campionato", campionato.id)
)
```

**4. Permission Checks Need Fresh Data**
```python
# After promoting user, session may have stale data
user = User.query.get(user_id)  # Fresh fetch
if user.is_director:
    # Now reflects promotion
```

**5. Event Emission in Services**
```python
# Always emit events AFTER db.session.flush()
db.session.flush()  # Ensure entity has ID

from models.events.base import EventBus
EventBus.publish(DirectorRequestCreatedEvent(...))
```

---

## Cross-References

**Documentation:**
- [models/CLAUDE.md](../CLAUDE.md): Complete domain index
- [models/competition/CLAUDE.md](../competition/CLAUDE.md): Inscription, director assignments
- [models/notification/CLAUDE.md](../notification/CLAUDE.md): User notifications
- [models/individual_match/CLAUDE.md](../individual_match/CLAUDE.md): Match proposals

**Code References:**
- `models/user/permissions.py`: Permission decorators and checkers
- `models/events/user_events.py`: User domain events
- `routes/auth.py`: Authentication routes
- `routes/admin/user.py`: User management routes
- `utils/__init__.py`: create_admin_if_not_exists utility

**Related Enums:**
- `models/user/role_enum.py`: UserRole enum
- `models/status_enum.py`: DirectorRequestStatus enum
