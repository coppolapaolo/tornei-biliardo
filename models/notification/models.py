"""
Module: models/notification/models.py
Purpose: Notification domain models for user notifications
Requirements: SPECIFICHE.md - Notification system for match proposals and tournament updates
Data Structures: Notification, NotificationPreference
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, TYPE_CHECKING
from enum import Enum


from ..base import db, BaseModel, TimestampMixin

if TYPE_CHECKING:
    pass


class NotificationType(Enum):
    """Types of notifications."""

    MATCH_PROPOSAL = "match_proposal"  # Individual match proposal received
    MATCH_ACCEPTED = "match_accepted"  # Your match proposal was accepted
    MATCH_DECLINED = "match_declined"  # Your match proposal was declined
    MATCH_CANCELLED = "match_cancelled"  # Match was cancelled
    MATCH_REMINDER = "match_reminder"  # Upcoming match reminder

    TOURNAMENT_INVITATION = "tournament_invitation"  # Invited to tournament
    TOURNAMENT_REGISTRATION = (
        "tournament_registration"  # Tournament registration opened
    )
    TOURNAMENT_STARTING = "tournament_starting"  # Tournament is starting
    TOURNAMENT_RESULTS = "tournament_results"  # Tournament results available

    PLAYOFF_INVITATION = "playoff_invitation"  # Invited to playoffs
    PLAYOFF_DEADLINE = "playoff_deadline"  # Playoff response deadline approaching

    CHALLENGE_ASSIGNED = "challenge_assigned"  # New challenge available
    EXAM_AVAILABLE = "exam_available"  # New exam available

    SYSTEM_ANNOUNCEMENT = "system_announcement"  # System-wide announcement
    ACCOUNT_UPDATE = "account_update"  # Account-related updates


class NotificationPriority(Enum):
    """Notification priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationStatus(Enum):
    """Notification status."""

    PENDING = "pending"  # Not yet delivered
    SENT = "sent"  # Delivered to user
    READ = "read"  # Read by user
    DISMISSED = "dismissed"  # Dismissed by user
    EXPIRED = "expired"  # Expired without being read


class Notification(BaseModel, TimestampMixin):
    """User notification for various system events."""

    __tablename__ = "notification"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # Notification content
    notification_type = db.Column(db.Enum(NotificationType), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    priority = db.Column(
        db.Enum(NotificationPriority),
        nullable=False,
        default=NotificationPriority.NORMAL,
    )

    # Status and timing
    status = db.Column(
        db.Enum(NotificationStatus), nullable=False, default=NotificationStatus.PENDING
    )
    sent_at = db.Column(db.DateTime, nullable=True)
    read_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    # Related entities (JSON to store references)
    related_entities = db.Column(db.Text, nullable=True)  # JSON string

    # Action information
    action_url = db.Column(db.String(255), nullable=True)  # URL for action button
    action_text = db.Column(db.String(100), nullable=True)  # Text for action button

    # Delivery tracking
    delivery_attempts = db.Column(db.Integer, nullable=False, default=0)
    last_attempt_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])

    def get_related_entities(self) -> Dict[str, Any]:
        """Parse related entities from JSON."""
        if not self.related_entities:
            return {}
        try:
            return json.loads(self.related_entities)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_related_entities(self, entities: Dict[str, Any]) -> None:
        """Set related entities as JSON."""
        self.related_entities = json.dumps(entities) if entities else None

    def mark_as_sent(self) -> None:
        """Mark notification as sent."""
        if self.status == NotificationStatus.PENDING:
            self.status = NotificationStatus.SENT
            self.sent_at = datetime.utcnow()
            self.delivery_attempts += 1
            self.last_attempt_at = datetime.utcnow()

    def mark_as_read(self) -> None:
        """Mark notification as read."""
        if self.status in [NotificationStatus.SENT, NotificationStatus.PENDING]:
            self.status = NotificationStatus.READ
            self.read_at = datetime.utcnow()

    def dismiss(self) -> None:
        """Dismiss notification."""
        if self.status in [
            NotificationStatus.SENT,
            NotificationStatus.PENDING,
            NotificationStatus.READ,
        ]:
            self.status = NotificationStatus.DISMISSED

    def is_expired(self) -> bool:
        """Check if notification is expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    def expire(self) -> None:
        """Mark notification as expired."""
        if self.status in [NotificationStatus.PENDING, NotificationStatus.SENT]:
            self.status = NotificationStatus.EXPIRED

    def can_be_delivered(self) -> bool:
        """Check if notification can be delivered."""
        return (
            self.status == NotificationStatus.PENDING
            and not self.is_expired()
            and self.delivery_attempts < 3
        )

    def __repr__(self) -> str:
        return f"<Notification {self.user_id}: {self.notification_type.value}>"


class NotificationPreference(BaseModel, TimestampMixin):
    """User preferences for notification types."""

    __tablename__ = "notification_preference"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    notification_type = db.Column(db.Enum(NotificationType), nullable=False)

    # Preferences
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    email_enabled = db.Column(
        db.Boolean, nullable=False, default=False
    )  # Future: email notifications
    push_enabled = db.Column(
        db.Boolean, nullable=False, default=True
    )  # Future: push notifications

    # Timing preferences
    quiet_hours_start = db.Column(db.Time, nullable=True)  # Start of quiet hours
    quiet_hours_end = db.Column(db.Time, nullable=True)  # End of quiet hours

    # Frequency limits
    max_per_day = db.Column(
        db.Integer, nullable=True
    )  # Max notifications per day for this type
    min_interval_minutes = db.Column(
        db.Integer, nullable=True
    )  # Minimum interval between notifications

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])

    # Unique constraint: one preference per user per type
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "notification_type", name="uq_user_notification_preference"
        ),
    )

    @classmethod
    def get_user_preference(
        cls, user_id: int, notification_type: NotificationType
    ) -> Optional["NotificationPreference"]:
        """Get user preference for a notification type."""
        return cls.query.filter_by(
            user_id=user_id, notification_type=notification_type
        ).first()

    @classmethod
    def is_notification_enabled(
        cls, user_id: int, notification_type: NotificationType
    ) -> bool:
        """Check if notification type is enabled for user."""
        preference = cls.get_user_preference(user_id, notification_type)
        return preference.enabled if preference else True  # Default: enabled

    def is_in_quiet_hours(self) -> bool:
        """Check if current time is in user's quiet hours."""
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False

        now = datetime.utcnow().time()

        if self.quiet_hours_start <= self.quiet_hours_end:
            # Normal case: 22:00 - 08:00
            return self.quiet_hours_start <= now <= self.quiet_hours_end
        else:
            # Overnight case: 22:00 - 08:00 (crosses midnight)
            return now >= self.quiet_hours_start or now <= self.quiet_hours_end

    def has_reached_daily_limit(self) -> bool:
        """Check if daily notification limit has been reached."""
        if not self.max_per_day:
            return False

        today_start = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_count = Notification.query.filter(
            Notification.user_id == self.user_id,
            Notification.notification_type == self.notification_type,
            Notification.created_at >= today_start,
            Notification.status != NotificationStatus.DISMISSED,
        ).count()

        return today_count >= self.max_per_day

    def has_violated_interval(self) -> bool:
        """Check if minimum interval has been violated."""
        if not self.min_interval_minutes:
            return False

        cutoff_time = datetime.utcnow() - timedelta(minutes=self.min_interval_minutes)
        recent_notification = Notification.query.filter(
            Notification.user_id == self.user_id,
            Notification.notification_type == self.notification_type,
            Notification.created_at >= cutoff_time,
        ).first()

        return recent_notification is not None

    def can_send_notification(self) -> bool:
        """Check if notification can be sent based on preferences."""
        return (
            self.enabled
            and not self.is_in_quiet_hours()
            and not self.has_reached_daily_limit()
            and not self.has_violated_interval()
        )

    def __repr__(self) -> str:
        return f"<NotificationPreference {self.user_id}: {self.notification_type.value}={self.enabled}>"


class NotificationTemplate(BaseModel, TimestampMixin):
    """Templates for notification messages."""

    __tablename__ = "notification_template"

    id = db.Column(db.Integer, primary_key=True)
    notification_type = db.Column(
        db.Enum(NotificationType), nullable=False, unique=True
    )

    # Template content
    title_template = db.Column(db.String(255), nullable=False)
    message_template = db.Column(db.Text, nullable=False)

    # Default settings
    default_priority = db.Column(
        db.Enum(NotificationPriority),
        nullable=False,
        default=NotificationPriority.NORMAL,
    )
    default_expires_hours = db.Column(
        db.Integer, nullable=True
    )  # Hours until expiration

    # Action settings
    action_text_template = db.Column(db.String(100), nullable=True)
    action_url_template = db.Column(db.String(255), nullable=True)

    def render_notification(self, context: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """Render notification content using context variables."""
        import re

        def replace_vars(template: str) -> str:
            if not template:
                return ""

            # Simple variable replacement: {variable_name}
            def replace_func(match):
                var_name = match.group(1)
                return str(context.get(var_name, f"{{{var_name}}}"))

            return re.sub(r"\{(\w+)\}", replace_func, template)

        return {
            "title": replace_vars(self.title_template),
            "message": replace_vars(self.message_template),
            "action_text": replace_vars(self.action_text_template)
            if self.action_text_template
            else None,
            "action_url": replace_vars(self.action_url_template)
            if self.action_url_template
            else None,
        }

    def get_expiry_datetime(self) -> Optional[datetime]:
        """Get expiry datetime based on default hours."""
        if not self.default_expires_hours:
            return None
        return datetime.utcnow() + timedelta(hours=self.default_expires_hours)

    def __repr__(self) -> str:
        return f"<NotificationTemplate {self.notification_type.value}>"
