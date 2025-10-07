# Notification Domain - Event-Driven Communication System

## Purpose and Core Responsibilities

The Notification domain provides a **centralized, event-driven communication system** for the pool community platform. It handles all user notifications across domains including match proposals, tournament updates, administrative actions, and community events.

**Key Features:**
- **Event-driven architecture**: Listens to domain events and automatically creates notifications
- **User preference management**: Respects quiet hours, frequency limits, and notification types
- **Delivery tracking**: Monitors sent, read, and dismissed statuses with retry logic
- **Template system**: Standardized notification content with variable substitution
- **Bulk operations**: Efficient multi-user notification with error handling
- **Priority levels**: LOW, NORMAL, HIGH, URGENT for critical communications
- **Expiration management**: Automatic cleanup of old notifications

**Cross-Domain Integration:**
- Used by: user, competition, match, individual_match, challenge, exam, playoff domains
- Triggered by: DomainEvents via @event_handler decorator
- Factory patterns: NotificationFactory for standardized notification creation

---

## Domain Structure

**Files** (4 files, ~1,231 lines total):
```
models/notification/
├── models.py              (~357 lines) - Core notification models and enums
├── factory.py             (~351 lines) - NotificationFactory with standardized patterns
├── services.py            (~497 lines) - NotificationService with @transactional methods
└── __init__.py            (~26 lines)  - Domain exports
```

---

## Quick Reference

### Common Imports

```python
# Models and Enums
from models.notification.models import (
    Notification,
    NotificationPreference,
    NotificationTemplate,
    NotificationType,
    NotificationPriority,
    NotificationStatus,
)

# Services
from models.notification.services import NotificationService

# Factory
from models.notification.factory import NotificationFactory
```

### Common Operations

```python
# Create notification (respects user preferences automatically)
notification = NotificationService.create_notification(
    user_id=user.id,
    notification_type=NotificationType.MATCH_PROPOSAL,
    title="Nuova Proposta di Partita",
    message="Paolo ti ha invitato a una partita presso Sala Biliardo",
    priority=NotificationPriority.NORMAL,
    action_url="/player/proposals/123",
    action_text="Visualizza Proposta"
)

# Bulk notifications (with error handling)
notifications = NotificationFactory.create_bulk_notification(
    user_ids=[1, 2, 3, 4],
    notification_type=NotificationType.TOURNAMENT_REGISTRATION,
    title="Torneo Aperto",
    message="Le iscrizioni per il torneo sono aperte!",
    priority=NotificationPriority.HIGH
)

# Get user's unread notifications
unread = NotificationService.get_user_notifications(
    user_id=user.id,
    unread_only=True,
    limit=10
)

# Mark as read
NotificationService.mark_notification_read(notification.id, user.id)

# User preference management
NotificationService.set_user_preference(
    user_id=user.id,
    notification_type=NotificationType.MATCH_PROPOSAL,
    enabled=True,
    quiet_hours_start="22:00",
    quiet_hours_end="08:00",
    max_per_day=10
)
```

---

## Key Classes

### Notification Model

**Purpose**: Core notification entity with delivery tracking and user actions.

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

# Related Entities (JSON storage)
related_entities: text - nullable (JSON string)

# Action Information
action_url: str(255) - nullable (e.g., "/player/proposals/123")
action_text: str(100) - nullable (e.g., "Visualizza Proposta")

# Delivery Tracking
delivery_attempts: int - default 0
last_attempt_at: datetime - nullable

# Timestamps
created_at: datetime (from TimestampMixin)
updated_at: datetime (from TimestampMixin)
```

**Relationships:**
```python
user: User - foreign key relationship
```

**Key Methods:**
```python
# JSON handling
get_related_entities() -> Dict[str, Any]:
    """Parse related entities from JSON."""
    # Returns: {"gara_id": 123, "user_id": 456, ...}

set_related_entities(entities: Dict[str, Any]) -> None:
    """Set related entities as JSON."""

# Status management
mark_as_sent() -> None:
    """Update status to SENT, increment delivery_attempts."""

mark_as_read() -> None:
    """Update status to READ, set read_at timestamp."""

dismiss() -> None:
    """Update status to DISMISSED."""

# Expiration
is_expired() -> bool:
    """Check if notification has passed expires_at."""

expire() -> None:
    """Mark as EXPIRED if pending or sent."""

# Delivery validation
can_be_delivered() -> bool:
    """Returns True if:
    - status == PENDING
    - not expired
    - delivery_attempts < 3
    """
```

**Usage Example:**
```python
# Create notification with related data
notification = Notification(
    user_id=user.id,
    notification_type=NotificationType.MATCH_PROPOSAL,
    title="Nuova Proposta",
    message="Paolo ti ha invitato a giocare",
    priority=NotificationPriority.NORMAL,
    action_url="/player/proposals/123",
    action_text="Visualizza"
)
notification.set_related_entities({
    "proposal_id": 123,
    "proposer_name": "Paolo",
    "location": "Sala Biliardo"
})
db.session.add(notification)

# Later: mark as read
notification.mark_as_read()
# Now: status=READ, read_at=datetime.utcnow()
```

---

### NotificationType Enum

**Purpose**: Categorize notifications by type for preference management.

**Values:**
```python
# Individual Match System
MATCH_PROPOSAL = "match_proposal"           # Received match proposal
MATCH_ACCEPTED = "match_accepted"           # Your proposal was accepted
MATCH_DECLINED = "match_declined"           # Your proposal was declined
MATCH_CANCELLED = "match_cancelled"         # Match was cancelled
MATCH_REMINDER = "match_reminder"           # Upcoming match reminder

# Tournament System
TOURNAMENT_INVITATION = "campionato_invitation"      # Invited to campionato
TOURNAMENT_REGISTRATION = "campionato_registration"  # Registration opened
TOURNAMENT_STARTING = "campionato_starting"          # Campionato starting
TOURNAMENT_RESULTS = "campionato_results"            # Results available

# Playoffs
PLAYOFF_INVITATION = "playoff_invitation"    # Invited to playoffs
PLAYOFF_DEADLINE = "playoff_deadline"        # Response deadline approaching

# Challenges & Exams
CHALLENGE_ASSIGNED = "challenge_assigned"    # New challenge available
EXAM_AVAILABLE = "exam_available"            # New exam available

# System & Administrative
SYSTEM_ANNOUNCEMENT = "system_announcement"  # System-wide announcement
ACCOUNT_UPDATE = "account_update"            # Account-related updates
ADMIN_ACTION_REQUIRED = "admin_action_required"  # Admin action needed
```

**Usage:**
```python
# Always use enum values
notification_type = NotificationType.MATCH_PROPOSAL

# In filters
notifications = Notification.query.filter_by(
    notification_type=NotificationType.MATCH_PROPOSAL
).all()
```

---

### NotificationPriority Enum

**Purpose**: Indicate urgency level for UI display and sorting.

**Values:**
```python
LOW = "low"           # Non-urgent information
NORMAL = "normal"     # Standard priority (default)
HIGH = "high"         # Important but not urgent
URGENT = "urgent"     # Requires immediate attention
```

**UI Implications:**
- **URGENT**: Red badge, push to top of list, sound/vibration (future)
- **HIGH**: Orange badge, prominent display
- **NORMAL**: Blue badge, standard display
- **LOW**: Gray badge, can be collapsed

---

### NotificationStatus Enum

**Purpose**: Track notification lifecycle and user actions.

**Values:**
```python
PENDING = "pending"       # Created but not yet delivered
SENT = "sent"             # Delivered to user
READ = "read"             # User has read it
DISMISSED = "dismissed"   # User dismissed it
EXPIRED = "expired"       # Expired without being read
```

**State Transitions:**
```
PENDING → SENT → READ
              ↘ DISMISSED
        ↘ EXPIRED
```

---

### NotificationPreference Model

**Purpose**: User-specific preferences for notification delivery and frequency.

**Database Fields:**
```python
id: int (PK)
user_id: int (FK to user.id, cascade delete) - not null
notification_type: NotificationType (enum) - not null

# Preferences
enabled: bool - default True
email_enabled: bool - default False (future: email delivery)
push_enabled: bool - default True (future: push notifications)

# Timing Preferences
quiet_hours_start: time - nullable (e.g., 22:00)
quiet_hours_end: time - nullable (e.g., 08:00)

# Frequency Limits
max_per_day: int - nullable (max notifications per day for this type)
min_interval_minutes: int - nullable (minimum time between notifications)

# Auto-deletion
auto_delete_days: int - nullable (auto-delete after N days)

# Timestamps
created_at: datetime
updated_at: datetime
```

**Constraints:**
```python
UNIQUE(user_id, notification_type) - one preference per user per type
```

**Relationships:**
```python
user: User
```

**Key Methods:**
```python
# Class methods (query helpers)
@classmethod
get_user_preference(user_id: int, notification_type: NotificationType) -> Optional[NotificationPreference]:
    """Get preference for specific type."""

@classmethod
is_notification_enabled(user_id: int, notification_type: NotificationType) -> bool:
    """Check if notification type is enabled (defaults to True)."""

# Instance methods (validation)
is_in_quiet_hours() -> bool:
    """Check if current time is in user's quiet hours."""
    # Handles overnight spans (e.g., 22:00-08:00)

has_reached_daily_limit() -> bool:
    """Check if max_per_day has been reached."""

has_violated_interval() -> bool:
    """Check if min_interval_minutes has been violated."""

can_send_notification() -> bool:
    """Comprehensive check: enabled AND not quiet hours AND not daily limit AND not interval violation."""
```

**Usage Example:**
```python
# Set user preferences
NotificationService.set_user_preference(
    user_id=user.id,
    notification_type=NotificationType.MATCH_PROPOSAL,
    enabled=True,
    quiet_hours_start="22:00",
    quiet_hours_end="08:00",
    max_per_day=5,
    min_interval_minutes=30,
    auto_delete_days=7
)

# Check before sending (done automatically by NotificationService)
preference = NotificationPreference.get_user_preference(
    user.id, NotificationType.MATCH_PROPOSAL
)
if preference and preference.can_send_notification():
    # Send notification
```

---

### NotificationTemplate Model

**Purpose**: Standardized notification content with variable substitution.

**Database Fields:**
```python
id: int (PK)
notification_type: NotificationType (enum) - unique, not null

# Template Content
title_template: str(255) - not null
message_template: text - not null

# Default Settings
default_priority: NotificationPriority - default NORMAL
default_expires_hours: int - nullable (hours until expiration)

# Action Settings
action_text_template: str(100) - nullable
action_url_template: str(255) - nullable

# Timestamps
created_at: datetime
updated_at: datetime
```

**Key Methods:**
```python
render_notification(context: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Render notification content using context variables.

    Template syntax: {variable_name}

    Returns:
        {
            "title": str,
            "message": str,
            "action_text": Optional[str],
            "action_url": Optional[str]
        }
    """

get_expiry_datetime() -> Optional[datetime]:
    """Get expiry datetime based on default_expires_hours."""
```

**Usage Example:**
```python
# Create template
template = NotificationTemplate(
    notification_type=NotificationType.MATCH_PROPOSAL,
    title_template="Nuova Proposta da {proposer_name}",
    message_template="{proposer_name} ti ha invitato a {location} il {scheduled_time}",
    action_text_template="Visualizza Proposta",
    action_url_template="/player/proposals/{proposal_id}",
    default_priority=NotificationPriority.NORMAL,
    default_expires_hours=48
)

# Render notification
rendered = template.render_notification({
    "proposer_name": "Paolo",
    "location": "Sala Biliardo",
    "scheduled_time": "2025-10-15 alle 19:00",
    "proposal_id": 123
})
# Result:
# {
#     "title": "Nuova Proposta da Paolo",
#     "message": "Paolo ti ha invitato a Sala Biliardo il 2025-10-15 alle 19:00",
#     "action_text": "Visualizza Proposta",
#     "action_url": "/player/proposals/123"
# }
```

---

## Services

### NotificationService

**Purpose**: Core notification CRUD operations with transaction management.

**All methods use `@transactional(domain="notification")` for automatic commit/rollback.**

#### Core Methods

```python
@transactional(domain="notification")
def create_notification(
    user_id: int,
    notification_type: NotificationType,
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.NORMAL,
    related_entities: Optional[Dict[str, Any]] = None,
    action_url: Optional[str] = None,
    action_text: Optional[str] = None,
    expires_at: Optional[datetime] = None,
) -> Optional[Notification]:
    """Create a new notification (respects user preferences).

    Returns None if user has disabled this notification type.

    Automatically checks:
    - Is notification type enabled?
    - Is user in quiet hours?
    - Has daily limit been reached?
    - Has interval been violated?
    """
```

**Important**: This is the primary method for creating notifications. It automatically:
1. Checks user preferences via `NotificationPreference.is_notification_enabled()`
2. Validates delivery constraints via `preference.can_send_notification()`
3. Creates notification with proper JSON encoding for `related_entities`
4. Handles transaction commit/rollback

#### Template-Based Creation

```python
def create_from_template(
    user_id: int,
    notification_type: NotificationType,
    context: Dict[str, Any],
    priority_override: Optional[NotificationPriority] = None,
    expires_override: Optional[datetime] = None,
) -> Optional[Notification]:
    """Create notification from template with context variables.

    Looks up NotificationTemplate by notification_type.
    Renders content using context.
    Uses template defaults unless overridden.

    Returns None if template doesn't exist or user preferences block.
    """
```

**Usage Example:**
```python
notification = NotificationService.create_from_template(
    user_id=user.id,
    notification_type=NotificationType.MATCH_PROPOSAL,
    context={
        "proposer_name": "Paolo",
        "location": "Sala Biliardo",
        "scheduled_time": "2025-10-15 alle 19:00",
        "proposal_id": 123
    },
    priority_override=NotificationPriority.HIGH
)
```

#### Query Methods

```python
def get_user_notifications(
    user_id: int,
    unread_only: bool = False,
    limit: Optional[int] = None
) -> List[Notification]:
    """Get notifications for a user.

    Args:
        user_id: User ID
        unread_only: If True, only return PENDING or SENT notifications
        limit: Max number of notifications to return

    Returns: List ordered by created_at DESC
    """

def get_unread_count(user_id: int) -> int:
    """Get count of unread notifications (PENDING or SENT)."""
```

#### Status Management

```python
@transactional(domain="notification")
def mark_notification_read(notification_id: int, user_id: int) -> bool:
    """Mark notification as read.

    Validates user_id matches notification.user_id.
    Returns False if notification not found or user mismatch.
    """

@transactional(domain="notification")
def dismiss_notification(notification_id: int, user_id: int) -> bool:
    """Dismiss a notification."""

@transactional(domain="notification")
def mark_all_read(user_id: int) -> int:
    """Mark all unread notifications as read.

    Returns: Count of notifications marked as read.
    """
```

#### Preference Management

```python
@transactional(domain="notification")
def set_user_preference(
    user_id: int,
    notification_type: NotificationType,
    enabled: bool = True,
    email_enabled: bool = False,
    quiet_hours_start: Optional[str] = None,  # Format: "HH:MM"
    quiet_hours_end: Optional[str] = None,    # Format: "HH:MM"
    max_per_day: Optional[int] = None,
    min_interval_minutes: Optional[int] = None,
    auto_delete_days: Optional[int] = None,
) -> NotificationPreference:
    """Set or update user preference for a notification type.

    Creates new preference if doesn't exist.
    Updates existing preference if found.
    Parses time strings to time objects.
    """

def get_user_preferences(user_id: int) -> Dict[str, NotificationPreference]:
    """Get all notification preferences for a user.

    Returns: {notification_type.value: NotificationPreference}
    """
```

#### Cleanup & Maintenance

```python
@transactional(domain="notification")
def expire_old_notifications() -> int:
    """Expire notifications that have passed their expiry time.

    Updates PENDING and SENT notifications with expires_at <= now.
    Returns: Count of expired notifications.
    """

@transactional(domain="notification")
def cleanup_old_notifications(days_old: int = 30) -> int:
    """Delete old READ, DISMISSED, EXPIRED notifications.

    Args:
        days_old: Delete notifications older than this many days

    Returns: Count of deleted notifications.
    """

@transactional(domain="notification")
def auto_delete_by_user_preferences() -> int:
    """Auto-delete based on user preference auto_delete_days.

    Respects individual user preferences for each notification type.
    Returns: Total count of deleted notifications.
    """

@transactional(domain="notification")
def delete_notifications_bulk(notification_ids: List[int], user_id: int) -> int:
    """Delete multiple notifications for a specific user.

    Validates user_id matches for all notifications.
    Returns: Count of deleted notifications.
    """
```

#### Domain-Specific Notification Creators

```python
def notify_match_proposal(
    proposer_id: int,
    target_user_id: int,
    match_details: Dict[str, Any]
) -> Optional[Notification]:
    """Notify user about a match proposal.

    Uses template with context: proposer_name, location, scheduled_time, proposal_id.
    """

def notify_match_accepted(
    proposer_id: int,
    accepter_name: str,
    match_details: Dict[str, Any]
) -> Optional[Notification]:
    """Notify proposer that their match was accepted.

    Uses template with context: accepter_name, location, scheduled_time, match_id.
    """

def notify_campionato_registration(
    user_ids: List[int],
    campionato_name: str,
    campionato_id: int
) -> List[Notification]:
    """Notify multiple users about campionato registration opening.

    Uses template with context: campionato_name, campionato_id.
    """

def notify_playoff_invitation(
    user_id: int,
    playoff_name: str,
    campionato_name: str,
    deadline: datetime
) -> Optional[Notification]:
    """Notify user about playoff invitation.

    Sets expires_at to deadline.
    Uses template with context: playoff_name, campionato_name, deadline.
    """
```

#### Template Management

```python
@transactional(domain="notification")
def create_default_templates() -> List[NotificationTemplate]:
    """Create default notification templates.

    Creates templates for:
    - MATCH_PROPOSAL (expires 48h)
    - MATCH_ACCEPTED (expires 24h)
    - TOURNAMENT_REGISTRATION (expires 168h / 1 week)
    - PLAYOFF_INVITATION (expires at deadline, priority HIGH)

    Skips templates that already exist.
    Returns: List of newly created templates.
    """
```

---

### NotificationFactory

**Purpose**: Standardized notification creation patterns with bulk operations and error handling.

**All factory methods use NotificationService internally and handle errors gracefully.**

#### Bulk Operations

```python
@staticmethod
def create_bulk_notification(
    user_ids: List[int],
    notification_type: NotificationType,
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.NORMAL,
    related_entities: Optional[Dict[str, Any]] = None,
    action_url: Optional[str] = None,
    action_text: Optional[str] = None,
    continue_on_error: bool = True,
) -> List[Optional[Notification]]:
    """Create notifications for multiple users with error handling.

    Args:
        user_ids: List of user IDs to notify
        continue_on_error: If True, continue creating notifications even if some fail

    Returns: List of notifications (or None for failed notifications)

    Logging:
        - Logs each successful creation at DEBUG level
        - Logs each failure at ERROR level with exc_info
        - Logs summary at INFO (all success) or WARNING (some failures)
    """
```

**Usage Example:**
```python
# Notify all gara participants
user_ids = [i.user_id for i in gara.inscriptions if not i.is_withdrawn]
notifications = NotificationFactory.create_bulk_notification(
    user_ids=user_ids,
    notification_type=NotificationType.TOURNAMENT_STARTING,
    title="Torneo in Partenza",
    message=f"Il torneo {gara.name} sta per iniziare!",
    priority=NotificationPriority.HIGH,
    action_url=f"/gare/{gara.id}",
    action_text="Visualizza Torneo"
)

# Check results
stats = NotificationFactory.get_notification_stats(notifications)
print(f"Sent: {stats['successful']}/{stats['total']}")
```

#### Admin Notifications

```python
@staticmethod
def create_admin_notification(
    admin_user_ids: List[int],
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.NORMAL,
    related_entities: Optional[Dict[str, Any]] = None,
    action_url: Optional[str] = None,
    action_text: Optional[str] = None,
) -> List[Optional[Notification]]:
    """Create notifications for multiple admin users.

    Always uses SYSTEM_ANNOUNCEMENT notification type.
    Returns: List of notifications (or None for failures).
    """
```

#### Domain-Specific Factories

```python
@staticmethod
def create_tournament_notification(
    user_ids: List[int],
    tournament_name: str,
    message_template: str,
    priority: NotificationPriority = NotificationPriority.NORMAL,
    tournament_id: Optional[int] = None,
) -> List[Optional[Notification]]:
    """Create tournament-related notifications for multiple users.

    Args:
        message_template: Format string with {tournament_name} placeholder

    Example:
        NotificationFactory.create_tournament_notification(
            user_ids=[1, 2, 3],
            tournament_name="Torneo Autunno 2025",
            message_template="Il torneo {tournament_name} è stato annullato.",
            priority=NotificationPriority.HIGH,
            tournament_id=gara.id
        )
    """

@staticmethod
def create_match_notification(
    user_id: int,
    match_type: str,  # "proposal", "accepted", "completed"
    player_names: List[str],
    location_name: Optional[str] = None,
    scheduled_time: Optional[str] = None,
    notes: Optional[str] = None,
    match_id: Optional[int] = None,
    proposal_id: Optional[int] = None,
) -> Optional[Notification]:
    """Create match-related notification with standardized content.

    Args:
        match_type: One of "proposal", "accepted", "completed"
        player_names: List of player names (joined with " vs ")

    Returns: Notification or None if creation failed
    """

@staticmethod
def create_account_update_notification(
    user_id: int,
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.NORMAL,
    update_type: Optional[str] = None,
    related_entities: Optional[Dict[str, Any]] = None,
) -> Optional[Notification]:
    """Create account update notification with error handling."""

@staticmethod
def create_system_announcement(
    user_ids: List[int],
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.NORMAL,
    action_url: Optional[str] = None,
    action_text: Optional[str] = None,
) -> List[Optional[Notification]]:
    """Create system announcement for multiple users.

    Equivalent to create_admin_notification but can target any users.
    """
```

#### Statistics

```python
@staticmethod
def get_notification_stats(notifications: List[Optional[Notification]]) -> Dict[str, Union[int, float]]:
    """Get statistics from notification creation results.

    Args:
        notifications: List of notifications (with None for failures)

    Returns:
        {
            "total": int,
            "successful": int,
            "failed": int,
            "success_rate": float (percentage)
        }
    """
```

---

## Common Workflows

### Workflow 1: Create Notification with Preferences Check

```python
from models.notification.services import NotificationService
from models.notification.models import NotificationType, NotificationPriority

# Service automatically checks user preferences
notification = NotificationService.create_notification(
    user_id=target_user.id,
    notification_type=NotificationType.MATCH_PROPOSAL,
    title="Nuova Proposta di Partita",
    message="Paolo ti ha invitato a giocare presso Sala Biliardo",
    priority=NotificationPriority.NORMAL,
    related_entities={
        "proposal_id": 123,
        "proposer_id": proposer.id,
        "location": "Sala Biliardo"
    },
    action_url=f"/player/proposals/123",
    action_text="Visualizza Proposta"
)

if notification:
    # Notification created successfully
    # It respects user's quiet hours, frequency limits, etc.
    pass
else:
    # User has disabled this notification type or frequency limits reached
    pass
```

**Key Points:**
- `create_notification()` returns `None` if user preferences block delivery
- `related_entities` automatically converted to JSON
- Transaction handled by `@transactional` decorator

---

### Workflow 2: Bulk Notification with Error Handling

```python
from models.notification.factory import NotificationFactory
from models.notification.models import NotificationType, NotificationPriority

# Get all gara participants
user_ids = [i.user_id for i in gara.inscriptions if not i.is_withdrawn]

# Send bulk notification
notifications = NotificationFactory.create_bulk_notification(
    user_ids=user_ids,
    notification_type=NotificationType.TOURNAMENT_STARTING,
    title="Torneo in Partenza",
    message=f"Il torneo {gara.name} sta per iniziare! Presentarsi entro 15 minuti.",
    priority=NotificationPriority.HIGH,
    related_entities={"gara_id": gara.id},
    action_url=f"/gare/{gara.id}",
    action_text="Visualizza Torneo",
    continue_on_error=True  # Continue even if some fail
)

# Check results
stats = NotificationFactory.get_notification_stats(notifications)
print(f"Notifiche inviate: {stats['successful']}/{stats['total']}")
print(f"Tasso di successo: {stats['success_rate']:.1f}%")

# Handle failures (notifications contains None for failures)
for i, notification in enumerate(notifications):
    if notification is None:
        failed_user_id = user_ids[i]
        print(f"Failed to notify user {failed_user_id}")
```

**Key Points:**
- `create_bulk_notification()` continues on error by default
- Returns list with `None` for failed notifications
- Logs errors automatically at ERROR level
- Use `get_notification_stats()` for summary

---

### Workflow 3: Event-Driven Notification (from Domain Events)

```python
from models.events.base import event_handler, EventType
from models.notification.factory import NotificationFactory
from models.notification.models import NotificationType, NotificationPriority

@event_handler(EventType.INSCRIPTION_CREATED)
def notify_on_inscription(event):
    """Send notification when user joins a gara."""
    gara_id = event.data.get("gara_id")
    user_id = event.data.get("user_id")

    gara = db.session.get(Gara, gara_id)
    user = db.session.get(User, user_id)

    if not gara or not user:
        return

    # Notify user of successful inscription
    NotificationFactory.create_account_update_notification(
        user_id=user.id,
        title="Iscrizione Confermata",
        message=f"Ti sei iscritto con successo al torneo {gara.name}.",
        priority=NotificationPriority.NORMAL,
        update_type="inscription_confirmed",
        related_entities={"gara_id": gara.id}
    )

    # Notify directors of new inscription
    director_ids = [d.id for d in gara.directors]
    if director_ids:
        NotificationFactory.create_bulk_notification(
            user_ids=director_ids,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="Nuova Iscrizione",
            message=f"{user.username} si è iscritto a {gara.name}.",
            priority=NotificationPriority.LOW,
            related_entities={"gara_id": gara.id, "user_id": user.id}
        )
```

**Key Points:**
- Use `@event_handler` decorator to listen to domain events
- NotificationFactory handles all errors gracefully
- Separate notifications for user and directors
- Different priority levels (NORMAL for user, LOW for directors)

---

### Workflow 4: Template-Based Notification

```python
from models.notification.services import NotificationService
from models.notification.models import NotificationType, NotificationPriority

# Create notification from template
notification = NotificationService.create_from_template(
    user_id=target_user.id,
    notification_type=NotificationType.PLAYOFF_INVITATION,
    context={
        "playoff_name": "Finali 2025",
        "campionato_name": "Campionato Autunno",
        "deadline": "2025-10-20 23:59"
    },
    priority_override=NotificationPriority.HIGH,
    expires_override=datetime(2025, 10, 20, 23, 59)
)

# Template automatically renders:
# title: "Playoff Invitation"
# message: "You've qualified for Finali 2025 in Campionato Autunno! Please respond by 2025-10-20 23:59"
# action_text: "Respond"
# action_url: "/playoffs/respond"
```

**Prerequisites:**
- NotificationTemplate must exist for the notification_type
- Create default templates with `NotificationService.create_default_templates()`

---

### Workflow 5: User Preference Management

```python
from models.notification.services import NotificationService
from models.notification.models import NotificationType

# User sets quiet hours for all notifications
for notification_type in NotificationType:
    NotificationService.set_user_preference(
        user_id=user.id,
        notification_type=notification_type,
        enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="08:00"
    )

# User disables specific notification type
NotificationService.set_user_preference(
    user_id=user.id,
    notification_type=NotificationType.MATCH_REMINDER,
    enabled=False
)

# User sets frequency limits for match proposals
NotificationService.set_user_preference(
    user_id=user.id,
    notification_type=NotificationType.MATCH_PROPOSAL,
    enabled=True,
    max_per_day=10,  # Max 10 per day
    min_interval_minutes=30,  # At least 30 min between notifications
    auto_delete_days=7  # Auto-delete after 7 days
)

# Get all user preferences
preferences = NotificationService.get_user_preferences(user.id)
for type_value, pref in preferences.items():
    print(f"{type_value}: enabled={pref.enabled}")
```

---

### Workflow 6: Cleanup & Maintenance

```python
from models.notification.services import NotificationService

# Expire old notifications (should run periodically, e.g., cron job)
expired_count = NotificationService.expire_old_notifications()
print(f"Expired {expired_count} notifications")

# Delete old read/dismissed notifications (run monthly)
deleted_count = NotificationService.cleanup_old_notifications(days_old=30)
print(f"Deleted {deleted_count} old notifications")

# Auto-delete based on user preferences (run daily)
auto_deleted = NotificationService.auto_delete_by_user_preferences()
print(f"Auto-deleted {auto_deleted} notifications per user preferences")
```

**Best Practice**: Set up periodic tasks (cron jobs or Celery tasks) to:
- Run `expire_old_notifications()` every hour
- Run `cleanup_old_notifications()` every day
- Run `auto_delete_by_user_preferences()` every day

---

## Important Notes

### Transaction Management

**All service methods use `@transactional` decorator:**
```python
@transactional(domain="notification")
def create_notification(...) -> Optional[Notification]:
    # No need for db.session.commit()
    # Decorator handles commit on success, rollback on error
```

**Never call `db.session.commit()` directly in notification code.**

---

### User Preference Hierarchy

**Notification delivery respects this hierarchy:**

1. **Is notification type enabled?** (`NotificationPreference.enabled`)
   - If False, notification is not created

2. **Is user in quiet hours?** (`preference.is_in_quiet_hours()`)
   - If True, notification is not created

3. **Has daily limit been reached?** (`preference.has_reached_daily_limit()`)
   - If True, notification is not created

4. **Has interval been violated?** (`preference.has_violated_interval()`)
   - If True, notification is not created

**All checks are performed automatically by `NotificationService.create_notification()`.**

---

### Error Handling in Factory

**NotificationFactory methods never raise exceptions:**
```python
# If notification creation fails, None is returned
notification = NotificationFactory.create_match_notification(...)
if notification is None:
    # Creation failed (logged at ERROR level)
    pass

# Bulk operations continue on error by default
notifications = NotificationFactory.create_bulk_notification(
    user_ids=[1, 2, 3, 999999],  # 999999 doesn't exist
    ...,
    continue_on_error=True  # Default
)
# Returns [Notification, Notification, Notification, None]
```

**Always check for None and use `get_notification_stats()` for bulk operations.**

---

### JSON Storage in related_entities

**Always use model methods for JSON handling:**
```python
# ✅ Correct
notification.set_related_entities({"gara_id": 123, "user_id": 456})
entities = notification.get_related_entities()  # Returns dict

# ❌ Wrong - don't manipulate JSON directly
notification.related_entities = '{"gara_id": 123}'  # Manual JSON string
```

**Methods handle JSON encoding/decoding and error handling automatically.**

---

### Notification Expiration

**Two ways to set expiration:**

1. **Explicit `expires_at` parameter:**
```python
NotificationService.create_notification(
    ...,
    expires_at=datetime.utcnow() + timedelta(hours=24)
)
```

2. **Template default:**
```python
# Template has default_expires_hours=48
NotificationService.create_from_template(...)
# Expires 48 hours from now
```

**Expired notifications:**
- Status becomes EXPIRED (if PENDING or SENT)
- Can be cleaned up with `cleanup_old_notifications()`
- Run `expire_old_notifications()` periodically

---

### Priority Levels and UI

**Recommended UI behavior:**

```python
# URGENT (red badge, top of list, sound)
NotificationPriority.URGENT
# Use for: Match starting in 5 minutes, playoff deadline in 1 hour

# HIGH (orange badge, prominent display)
NotificationPriority.HIGH
# Use for: Tournament starting soon, playoff invitation

# NORMAL (blue badge, standard display)
NotificationPriority.NORMAL
# Use for: Match proposals, tournament registration, general updates

# LOW (gray badge, collapsible)
NotificationPriority.LOW
# Use for: New inscriptions (for directors), system info
```

---

### Template Variable Substitution

**Template syntax:**
```
{variable_name}
```

**Example:**
```python
title_template = "Proposta da {proposer_name}"
message_template = "{proposer_name} ti ha invitato a {location} il {scheduled_time}"

# Rendered with context:
context = {
    "proposer_name": "Paolo",
    "location": "Sala Biliardo",
    "scheduled_time": "2025-10-15 alle 19:00"
}

# Result:
# title: "Proposta da Paolo"
# message: "Paolo ti ha invitato a Sala Biliardo il 2025-10-15 alle 19:00"
```

**Missing variables are left as `{variable_name}` in output.**

---

## Cross-References

### Used By (Domains that create notifications)

- **User Domain** (`models/user/`): Account updates, role changes, director requests
- **Competition Domain** (`models/competition/`): Tournament updates, inscription confirmations, gara status changes
- **Match Domain** (`models/match/`): Match assignments, results posted
- **Individual Match Domain** (`models/individual_match/`): Match proposals, acceptances, availability alerts
- **Challenge Domain** (`models/challenge/`): New challenges, exam availability
- **Playoff Domain** (`models/playoff/`): Playoff invitations, deadline reminders

### Depends On (External dependencies)

- **User Domain** (`models/user/models.py`): User model for foreign key
- **Events Domain** (`models/events/`): DomainEvent for event-driven notifications
- **Transaction Domain** (`models/transaction/`): @transactional decorator

### Related Documentation

- **[models/user/CLAUDE.md](../user/CLAUDE.md)**: User model and permissions
- **[models/individual_match/CLAUDE.md](../individual_match/CLAUDE.md)**: Match proposal notifications
- **[models/competition/CLAUDE.md](../competition/CLAUDE.md)**: Tournament notifications
- **[models/events/](../events/)**: Event system for automatic notifications

---

## Testing Notifications

### Unit Tests

```python
from models.notification.services import NotificationService
from models.notification.models import NotificationType, NotificationPriority

def test_create_notification_respects_preferences():
    # Disable notification type
    NotificationService.set_user_preference(
        user_id=user.id,
        notification_type=NotificationType.MATCH_PROPOSAL,
        enabled=False
    )

    # Try to create notification
    notification = NotificationService.create_notification(
        user_id=user.id,
        notification_type=NotificationType.MATCH_PROPOSAL,
        title="Test",
        message="Test message"
    )

    # Should return None (user has disabled this type)
    assert notification is None

def test_quiet_hours():
    # Set quiet hours: 22:00-08:00
    NotificationService.set_user_preference(
        user_id=user.id,
        notification_type=NotificationType.MATCH_PROPOSAL,
        enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="08:00"
    )

    # Mock current time to 23:00 (in quiet hours)
    with freeze_time("2025-10-15 23:00:00"):
        notification = NotificationService.create_notification(
            user_id=user.id,
            notification_type=NotificationType.MATCH_PROPOSAL,
            title="Test",
            message="Test"
        )
        assert notification is None  # Blocked by quiet hours
```

### Integration Tests

```python
def test_bulk_notification_with_failures(db_session):
    # Create 3 users
    users = [create_user(f"user{i}") for i in range(3)]

    # Set user2 to disable match proposals
    NotificationService.set_user_preference(
        user_id=users[1].id,
        notification_type=NotificationType.MATCH_PROPOSAL,
        enabled=False
    )

    # Send bulk notification
    user_ids = [u.id for u in users]
    notifications = NotificationFactory.create_bulk_notification(
        user_ids=user_ids,
        notification_type=NotificationType.MATCH_PROPOSAL,
        title="Test",
        message="Test message",
        continue_on_error=True
    )

    # Should have 3 results: [Notification, None, Notification]
    assert len(notifications) == 3
    assert notifications[0] is not None  # user1 got notification
    assert notifications[1] is None      # user2 blocked
    assert notifications[2] is not None  # user3 got notification

    # Check stats
    stats = NotificationFactory.get_notification_stats(notifications)
    assert stats["successful"] == 2
    assert stats["failed"] == 1
    assert stats["success_rate"] == 66.67  # Approximately
```

---

## Performance Considerations

### Batch Operations

**Always use bulk methods for multiple users:**
```python
# ✅ Efficient - single factory call
NotificationFactory.create_bulk_notification(
    user_ids=[1, 2, 3, 4, 5],
    notification_type=...,
    title=...,
    message=...
)

# ❌ Inefficient - multiple service calls
for user_id in [1, 2, 3, 4, 5]:
    NotificationService.create_notification(
        user_id=user_id,
        notification_type=...,
        title=...,
        message=...
    )
```

**Bulk operations use a single transaction and better error handling.**

---

### Cleanup Queries

**Run cleanup periodically to prevent database bloat:**
```python
# Daily cleanup (e.g., 2 AM cron job)
NotificationService.expire_old_notifications()
NotificationService.cleanup_old_notifications(days_old=30)
NotificationService.auto_delete_by_user_preferences()
```

**Cleanup operations use indexed queries and are optimized for large datasets.**

---

## Future Enhancements

### Email Notifications
- `NotificationPreference.email_enabled` is prepared but not implemented
- Future: Send email for HIGH and URGENT priority notifications
- Future: Digest emails for LOW priority notifications

### Push Notifications
- `NotificationPreference.push_enabled` is prepared but not implemented
- Future: Browser push notifications for real-time alerts
- Future: Mobile app push notifications

### Advanced Templates
- Current: Simple `{variable}` substitution
- Future: Conditional blocks, loops, filters (Jinja2-style)

### Notification Channels
- Current: In-app only
- Future: Email, SMS, Push, Webhook channels
- Future: Channel preferences per notification type
