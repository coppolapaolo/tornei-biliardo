# Notification Domain

## Purpose

Event-driven notification system for user communications across all domains.

**Key Features:**
- Event-driven: Listens to domain events via `@event_handler`
- User preferences: Quiet hours, frequency limits, notification types
- Bulk operations: Multi-user notifications with error handling
- Priority levels: LOW, NORMAL, HIGH, URGENT
- Expiration management: Auto-cleanup of old notifications

---

## Quick Reference

```python
from models.notification.models import (
    Notification, NotificationPreference, NotificationTemplate,
    NotificationType, NotificationPriority, NotificationStatus,
)
from models.notification.services import NotificationService
from models.notification.factory import NotificationFactory

# Create notification (respects user preferences)
notification = NotificationService.create_notification(
    user_id=user.id,
    notification_type=NotificationType.MATCH_PROPOSAL,
    title="Nuova Proposta",
    message="Paolo ti ha invitato a giocare",
    priority=NotificationPriority.NORMAL,
    action_url="/player/proposals/123"
)

# Bulk notifications
notifications = NotificationFactory.create_bulk_notification(
    user_ids=[1, 2, 3],
    notification_type=NotificationType.TOURNAMENT_STARTING,
    title="Torneo in Partenza",
    message="Il torneo sta per iniziare!",
    priority=NotificationPriority.HIGH
)

# Check stats
stats = NotificationFactory.get_notification_stats(notifications)
# {"total": 3, "successful": 2, "failed": 1, "success_rate": 66.67}

# Mark as read
NotificationService.mark_notification_read(notification.id, user.id)

# Set user preferences
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

## Key Models

### Notification
**Key Fields:** `user_id`, `notification_type`, `title`, `message`, `priority`, `status`, `action_url`, `related_entities` (JSON), `expires_at`

**Status Flow:** PENDING → SENT → READ / DISMISSED / EXPIRED

**Key Methods:**
- `get_related_entities()` / `set_related_entities(dict)` - JSON handling
- `mark_as_read()`, `dismiss()`, `expire()` - Status updates
- `can_be_delivered()` - Check delivery constraints

### NotificationPreference
Per-user settings for each notification type.

**Key Fields:** `user_id`, `notification_type`, `enabled`, `quiet_hours_start/end`, `max_per_day`, `min_interval_minutes`

### NotificationType (Enum)
`MATCH_PROPOSAL`, `MATCH_ACCEPTED`, `MATCH_DECLINED`, `TOURNAMENT_INVITATION`, `TOURNAMENT_REGISTRATION`, `PLAYOFF_INVITATION`, `SYSTEM_ANNOUNCEMENT`, etc.

### NotificationPriority (Enum)
`LOW` (gray), `NORMAL` (blue), `HIGH` (orange), `URGENT` (red)

---

## Services

### NotificationService
- `create_notification(...)` - Single notification (respects preferences)
- `create_from_template(...)` - Template-based creation
- `get_user_notifications(user_id, unread_only, limit)` - Query notifications
- `mark_notification_read()`, `mark_all_read()`, `dismiss_notification()`
- `set_user_preference(...)` - Configure user settings
- `expire_old_notifications()`, `cleanup_old_notifications(days)` - Maintenance

### NotificationFactory
- `create_bulk_notification(...)` - Multi-user with error handling
- `create_admin_notification(...)` - Notify admins
- `get_notification_stats(notifications)` - Success/failure counts

---

## Do Not

- **Do not call `db.session.commit()`** - All methods use `@transactional`
- **Do not manipulate `related_entities` JSON directly** - Use `get_related_entities()` / `set_related_entities()`
- **Do not skip preference checks** - `create_notification()` returns `None` if user disabled type
- **Do not assume bulk success** - Check `None` values in returned list
- **Do not forget cleanup** - Run `expire_old_notifications()` and `cleanup_old_notifications()` periodically

---

## Preference Hierarchy

`create_notification()` automatically checks (returns `None` if blocked):
1. Is notification type enabled?
2. Is user in quiet hours?
3. Has daily limit been reached?
4. Has minimum interval been violated?

---

## Cross-References

- **User Domain**: FK to User for `user_id`
- **Events Domain**: `@event_handler` for automatic notifications
- Used by: competition, match, individual_match, challenge, playoff domains
