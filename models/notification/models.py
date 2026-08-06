"""
Module: models/notification/models.py
Purpose: Notification domain models for user notifications
Requirements: SPECIFICHE.md - Notification system for match proposals and
              campionato updates
Data Structures: Notification, NotificationPreference
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, TYPE_CHECKING
from enum import Enum


from ..base import db, BaseModel, utc_now

if TYPE_CHECKING:
    pass


class NotificationType(Enum):
    """Types of notifications."""

    MATCH_PROPOSAL = "match_proposal"  # Individual match proposal received
    MATCH_ACCEPTED = "match_accepted"  # Your match proposal was accepted
    MATCH_DECLINED = "match_declined"  # Your match proposal was declined
    MATCH_CANCELLED = "match_cancelled"  # Match was cancelled
    MATCH_REMINDER = "match_reminder"  # Upcoming match reminder

    TOURNAMENT_INVITATION = "campionato_invitation"  # Invited to campionato
    TOURNAMENT_REGISTRATION = (
        "campionato_registration"  # Campionato registration opened
    )
    TOURNAMENT_STARTING = "campionato_starting"  # Campionato is starting
    TOURNAMENT_RESULTS = "campionato_results"  # Campionato results available

    PLAYOFF_INVITATION = "playoff_invitation"  # Invited to playoffs
    PLAYOFF_DEADLINE = "playoff_deadline"  # Playoff response deadline approaching

    CHALLENGE_ASSIGNED = "challenge_assigned"  # New challenge available
    EXAM_AVAILABLE = "exam_available"  # New exam available

    SYSTEM_ANNOUNCEMENT = "system_announcement"  # System-wide announcement
    ACCOUNT_UPDATE = "account_update"  # Account-related updates
    ADMIN_ACTION_REQUIRED = "admin_action_required"  # Action required by admin

    # Demand signal → director (ADR-036)
    DEMAND_THRESHOLD_REACHED = "demand_threshold_reached"  # Director: domanda ≥ soglia
    DEMAND_GARA_NEARBY = "demand_gara_nearby"  # Player: gara aperta nella tua zona
    DEMAND_ZONE_NO_DIRECTOR = (
        "demand_zone_no_director"  # Admin: domanda in zona senza director
    )
    DEMAND_SIGNAL_EXPIRING = (
        "demand_signal_expiring"  # Player: la tua richiesta sta per scadere
    )

    # Gamification
    ACHIEVEMENT_UNLOCKED = "achievement_unlocked"  # Achievement earned
    LEVEL_UP = "level_up"  # Level up with unlocks
    STREAK_WARNING = "streak_warning"  # Streak about to break
    STREAK_MILESTONE = "streak_milestone"  # Reached 4/12/52 week milestone
    QUEST_COMPLETED = "quest_completed"  # Quest finished
    QUEST_NEW = "quest_new"  # New quest available

    # KPI (Admin only)
    KPI_MILESTONE = "kpi_milestone"  # Community milestone reached
    KPI_ACTIVITY_ALERT = "kpi_activity_alert"  # Activity drop alert


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


class Notification(BaseModel):
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

    # i18n support: store template key + params instead of pre-translated strings
    # This enables proper language switching at display time
    template_key = db.Column(
        db.String(100), nullable=True
    )  # e.g., "achievement.unlocked"
    template_params = db.Column(db.Text, nullable=True)  # JSON params for template

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
            self.sent_at = utc_now()
            self.delivery_attempts += 1
            self.last_attempt_at = utc_now()

    def mark_as_read(self) -> None:
        """Mark notification as read."""
        if self.status in [NotificationStatus.SENT, NotificationStatus.PENDING]:
            self.status = NotificationStatus.READ
            self.read_at = utc_now()

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
        return utc_now() > self.expires_at

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

    def get_template_params(self) -> Dict[str, Any]:
        """Parse template params from JSON."""
        if not self.template_params:
            return {}
        try:
            return json.loads(self.template_params)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_template_params(self, params: Dict[str, Any]) -> None:
        """Set template params as JSON."""
        self.template_params = json.dumps(params) if params else None

    def get_translated_content(self) -> Dict[str, str]:
        """Get translated notification content based on current locale.

        If template_key is set, translates the template at display time.
        Otherwise, falls back to static title/message fields.

        Handles special param keys that need translation:
        - difficulty_key -> difficulty (via DIFFICULTY_LABELS)
        - type_key -> type (via STREAK_TYPE_LABELS or QUEST_TYPE_LABELS)

        Returns:
            Dict with 'title', 'message', 'action_text' keys
        """
        if self.template_key:
            from flask_babel import gettext as _
            from models.notification.templates import (
                NOTIFICATION_TEMPLATES,
                DIFFICULTY_LABELS,
                STREAK_TYPE_LABELS,
                QUEST_TYPE_LABELS,
            )

            template = NOTIFICATION_TEMPLATES.get(self.template_key, {})
            params = (
                self.get_template_params().copy()
            )  # Copy to avoid mutating original

            # Translate special keys that need runtime translation
            if "difficulty_key" in params:
                difficulty_key = params.pop("difficulty_key")
                # DIFFICULTY_LABELS values are lazy_gettext, convert to string
                # for current locale
                params["difficulty"] = str(
                    DIFFICULTY_LABELS.get(difficulty_key, difficulty_key)
                )

            if "type_key" in params:
                type_key = params.pop("type_key")
                # Try streak types first, then quest types
                label = STREAK_TYPE_LABELS.get(type_key) or QUEST_TYPE_LABELS.get(
                    type_key, type_key
                )
                params["type"] = str(label)

            # Translate template strings and substitute params
            title_template = template.get("title", self.title or "")
            message_template = template.get("message", self.message or "")
            action_template = template.get("action_text", self.action_text or "")

            try:
                return {
                    "title": (
                        _(title_template) % params if params else _(title_template)
                    ),
                    "message": (
                        _(message_template) % params if params else _(message_template)
                    ),
                    "action_text": (
                        _(action_template) % params
                        if params and action_template
                        else _(action_template) if action_template else ""
                    ),
                }
            except (KeyError, TypeError):
                # Substituzione fallita (param mancante o tipo errato): usa i
                # campi statici gia' renderizzati alla creazione invece del
                # template grezzo, per non mostrare placeholder tipo %(name)s.
                return {
                    "title": self.title or _(title_template),
                    "message": self.message or _(message_template),
                    "action_text": self.action_text
                    or (_(action_template) if action_template else ""),
                }

        # Fallback to static fields (backward compatibility)
        return {
            "title": self.title or "",
            "message": self.message or "",
            "action_text": self.action_text or "",
        }

    def __repr__(self) -> str:
        return f"<Notification {self.user_id}: {self.notification_type.value}>"


class NotificationPreference(BaseModel):
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

    # Auto-deletion settings
    auto_delete_days = db.Column(
        db.Integer, nullable=True
    )  # Auto-delete notifications older than N days (NULL = no auto-delete)

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

        # Le quiet hours sono impostate dall'utente in ora locale italiana:
        # converti il naive-UTC di utc_now() in Europe/Rome (DST incluso)
        # prima del confronto, come fa format_datetime_local per il display.
        from zoneinfo import ZoneInfo

        now = (
            utc_now()
            .replace(tzinfo=ZoneInfo("UTC"))
            .astimezone(ZoneInfo("Europe/Rome"))
            .time()
        )

        if self.quiet_hours_start <= self.quiet_hours_end:
            # Normal case: e.g. 13:00 - 15:00 (same day)
            return self.quiet_hours_start <= now <= self.quiet_hours_end
        else:
            # Overnight case: 22:00 - 08:00 (crosses midnight)
            return now >= self.quiet_hours_start or now <= self.quiet_hours_end

    def has_reached_daily_limit(self) -> bool:
        """Check if daily notification limit has been reached."""
        if not self.max_per_day:
            return False

        today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
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

        cutoff_time = utc_now() - timedelta(minutes=self.min_interval_minutes)
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
        return (
            f"<NotificationPreference {self.user_id}: "
            f"{self.notification_type.value}={self.enabled}>"
        )


class NotificationTemplate(BaseModel):
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
            "action_text": (
                replace_vars(self.action_text_template)
                if self.action_text_template
                else None
            ),
            "action_url": (
                replace_vars(self.action_url_template)
                if self.action_url_template
                else None
            ),
        }

    def get_expiry_datetime(self) -> Optional[datetime]:
        """Get expiry datetime based on default hours."""
        if not self.default_expires_hours:
            return None
        return utc_now() + timedelta(hours=self.default_expires_hours)

    def __repr__(self) -> str:
        return f"<NotificationTemplate {self.notification_type.value}>"
