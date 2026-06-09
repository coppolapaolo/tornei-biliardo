"""
Module: models/notification/services.py
Purpose: Notification domain services for notification management
Requirements: SPECIFICHE.md - Notification system for matches and campionati
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from ..base import db, utc_now
from ..transaction.manager import transactional
from .models import (
    Notification,
    NotificationPreference,
    NotificationTemplate,
    NotificationType,
    NotificationPriority,
    NotificationStatus,
)


class NotificationService:
    """Service for notification management and delivery."""

    # Default global auto-delete window (giorni) applicato quando l'utente
    # non ha mai configurato la preferenza. Vedi bug 16 docs/debug20260528.md.
    DEFAULT_AUTO_DELETE_DAYS = 30

    @staticmethod
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
        template_key: Optional[str] = None,
        template_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Notification]:
        """Create a new notification if user preferences allow it.

        Args:
            template_key: Optional key to NOTIFICATION_TEMPLATES for i18n support.
                         If provided, title/message will be translated at display time.
            template_params: Optional params dict for template substitution.
        """

        # Check user preferences
        if not NotificationPreference.is_notification_enabled(
            user_id, notification_type
        ):
            return None

        preference = NotificationPreference.get_user_preference(
            user_id, notification_type
        )
        if preference and not preference.can_send_notification():
            return None

        # Create notification
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            action_url=action_url,
            action_text=action_text,
            expires_at=expires_at,
            template_key=template_key,
        )

        if related_entities:
            notification.set_related_entities(related_entities)

        if template_params:
            notification.set_template_params(template_params)

        db.session.add(notification)

        # Emit SSE event for real-time badge update
        # Import here to avoid circular imports
        from routes.sse import emit_user_event

        # Count unread notifications (PENDING or SENT status)
        new_count = (
            Notification.query.filter_by(user_id=user_id)
            .filter(
                Notification.status.in_(  # type: ignore[attr-defined]
                    [NotificationStatus.PENDING, NotificationStatus.SENT]
                )
            )
            .count()
        )
        emit_user_event(user_id, "notification", {"unread_count": new_count})

        return notification

    @staticmethod
    def create_from_template(
        user_id: int,
        notification_type: NotificationType,
        context: Dict[str, Any],
        priority_override: Optional[NotificationPriority] = None,
        expires_override: Optional[datetime] = None,
    ) -> Optional[Notification]:
        """Create notification from template with context variables."""

        template = NotificationTemplate.query.filter_by(
            notification_type=notification_type
        ).first()

        if not template:
            # No template found, cannot create notification
            return None

        # Render content
        rendered = template.render_notification(context)

        # Use template defaults or overrides
        priority = priority_override or template.default_priority
        expires_at = expires_override or template.get_expiry_datetime()

        return NotificationService.create_notification(
            user_id=user_id,
            notification_type=notification_type,
            title=rendered["title"],
            message=rendered["message"],
            priority=priority,
            related_entities=context,
            action_url=rendered["action_url"],
            action_text=rendered["action_text"],
            expires_at=expires_at,
        )

    @staticmethod
    def get_user_notifications(
        user_id: int, unread_only: bool = False, limit: Optional[int] = None
    ) -> List[Notification]:
        """Get notifications for a user."""

        query = Notification.query.filter_by(user_id=user_id)

        if unread_only:
            query = query.filter(
                Notification.status.in_(  # type: ignore[attr-defined]
                    [
                        NotificationStatus.PENDING,
                        NotificationStatus.SENT,
                    ]
                )
            )

        query = query.order_by(Notification.created_at.desc())

        if limit:
            query = query.limit(limit)

        return query.all()

    @staticmethod
    @transactional(domain="notification")
    def mark_notification_read(
        notification_id: int, user_id: int
    ) -> Optional[Notification]:
        """Mark a notification as read.

        Returns the notification if found, None otherwise.
        Backward compatible: truthy when found, falsy when not.
        """
        notification = Notification.query.filter_by(
            id=notification_id, user_id=user_id
        ).first()

        if not notification:
            return None

        notification.mark_as_read()
        return notification

    @staticmethod
    @transactional(domain="notification")
    def dismiss_notification(notification_id: int, user_id: int) -> bool:
        """Dismiss a notification."""
        notification = Notification.query.filter_by(
            id=notification_id, user_id=user_id
        ).first()

        if not notification:
            return False

        notification.dismiss()
        return True

    @staticmethod
    @transactional(domain="notification")
    def mark_all_read(user_id: int) -> int:
        """Mark all notifications as read for a user."""
        notifications = (
            Notification.query.filter_by(user_id=user_id)
            .filter(
                Notification.status.in_(  # type: ignore[attr-defined]
                    [
                        NotificationStatus.PENDING,
                        NotificationStatus.SENT,
                    ]
                )
            )
            .all()
        )

        count = 0
        for notification in notifications:
            notification.mark_as_read()
            count += 1

        return count

    @staticmethod
    @transactional(domain="notification")
    def mark_pending_as_sent(user_id: int) -> int:
        """Mark all PENDING notifications as SENT for a user.

        Called when the user views the notifications page.
        Returns the number of notifications updated.
        """
        notifications = Notification.query.filter_by(
            user_id=user_id, status=NotificationStatus.PENDING
        ).all()

        count = 0
        for notification in notifications:
            notification.status = NotificationStatus.SENT
            notification.sent_at = utc_now()
            count += 1

        return count

    @staticmethod
    def get_unread_count(user_id: int) -> int:
        """Get count of unread notifications for user."""
        return (
            Notification.query.filter_by(user_id=user_id)
            .filter(
                Notification.status.in_(  # type: ignore[attr-defined]
                    [
                        NotificationStatus.PENDING,
                        NotificationStatus.SENT,
                    ]
                )
            )
            .count()
        )

    @staticmethod
    @transactional(domain="notification")
    def set_user_preference(
        user_id: int,
        notification_type: NotificationType,
        enabled: bool = True,
        email_enabled: bool = False,
        quiet_hours_start: Optional[str] = None,
        quiet_hours_end: Optional[str] = None,
        max_per_day: Optional[int] = None,
        min_interval_minutes: Optional[int] = None,
        auto_delete_days: Optional[int] = None,
    ) -> NotificationPreference:
        """Set user preference for a notification type."""

        preference = NotificationPreference.get_user_preference(
            user_id, notification_type
        )

        if preference:
            preference.enabled = enabled
            preference.email_enabled = email_enabled
            if max_per_day is not None:
                preference.max_per_day = max_per_day
            if min_interval_minutes is not None:
                preference.min_interval_minutes = min_interval_minutes
            if auto_delete_days is not None:
                preference.auto_delete_days = auto_delete_days
        else:
            preference = NotificationPreference(
                user_id=user_id,
                notification_type=notification_type,
                enabled=enabled,
                email_enabled=email_enabled,
                max_per_day=max_per_day,
                min_interval_minutes=min_interval_minutes,
                auto_delete_days=auto_delete_days,
            )
            db.session.add(preference)

        # Parse time strings
        if quiet_hours_start:
            try:
                preference.quiet_hours_start = datetime.strptime(
                    quiet_hours_start, "%H:%M"
                ).time()
            except ValueError:
                pass

        if quiet_hours_end:
            try:
                preference.quiet_hours_end = datetime.strptime(
                    quiet_hours_end, "%H:%M"
                ).time()
            except ValueError:
                pass

        return preference

    @staticmethod
    def get_user_preferences(user_id: int) -> Dict[str, NotificationPreference]:
        """Get all notification preferences for a user."""
        preferences = NotificationPreference.query.filter_by(user_id=user_id).all()
        return {pref.notification_type.value: pref for pref in preferences}

    @staticmethod
    @transactional(domain="notification")
    def expire_old_notifications() -> int:
        """Expire old notifications that have passed their expiry time."""
        expired_notifications = Notification.query.filter(
            Notification.expires_at <= utc_now(),
            Notification.status.in_(  # type: ignore[attr-defined]
                [NotificationStatus.PENDING, NotificationStatus.SENT]
            ),
        ).all()

        count = 0
        for notification in expired_notifications:
            notification.expire()
            count += 1

        return count

    @staticmethod
    @transactional(domain="notification")
    def cleanup_old_notifications(days_old: int = 30) -> int:
        """Delete old notifications to keep database clean."""
        cutoff_date = utc_now() - timedelta(days=days_old)

        old_notifications = Notification.query.filter(
            Notification.created_at <= cutoff_date,
            Notification.status.in_(  # type: ignore[attr-defined]
                [
                    NotificationStatus.READ,
                    NotificationStatus.DISMISSED,
                    NotificationStatus.EXPIRED,
                ]
            ),
        ).all()

        count = len(old_notifications)
        for notification in old_notifications:
            db.session.delete(notification)

        return count

    @staticmethod
    @transactional(domain="notification")
    def delete_notifications_bulk(notification_ids: List[int], user_id: int) -> int:
        """Delete multiple notifications by IDs for a specific user."""
        notifications = Notification.query.filter(
            Notification.id.in_(notification_ids),  # type: ignore[attr-defined]
            Notification.user_id == user_id,
        ).all()

        count = len(notifications)
        for notification in notifications:
            db.session.delete(notification)

        return count

    @staticmethod
    @transactional(domain="notification")
    def auto_delete_by_user_preferences(user_id: Optional[int] = None) -> int:
        """Auto-delete old notifications based on user preferences.

        If user_id is provided, only that user's preferences are processed
        (used for just-in-time cleanup on notification page access). If None,
        all users are processed (cron/scheduled job mode).
        """
        from sqlalchemy import and_

        total_deleted = 0

        query = NotificationPreference.query.filter(
            NotificationPreference.auto_delete_days.isnot(  # type: ignore[attr-defined]
                None
            )
        )
        if user_id is not None:
            query = query.filter(NotificationPreference.user_id == user_id)
        preferences = query.all()

        for preference in preferences:
            if not preference.auto_delete_days:
                continue

            cutoff_date = utc_now() - timedelta(days=preference.auto_delete_days)

            # Bulk DELETE invece di SELECT .all() + db.session.delete per riga:
            # un solo statement per preferenza, niente materializzazione in
            # memoria. Ritorna il numero di righe eliminate.
            deleted = Notification.query.filter(
                and_(
                    Notification.user_id == preference.user_id,
                    Notification.notification_type == preference.notification_type,
                    Notification.created_at <= cutoff_date,
                    Notification.status.in_(  # type: ignore[attr-defined]
                        [
                            NotificationStatus.READ,
                            NotificationStatus.DISMISSED,
                            NotificationStatus.EXPIRED,
                        ]
                    ),
                )
            ).delete(synchronize_session=False)
            total_deleted += deleted

        return total_deleted

    @staticmethod
    def get_global_auto_delete_days(user_id: int) -> Optional[int]:
        """Finestra di auto-cancellazione globale (giorni) dell'utente.

        Convenzione (bug 16):
        - nessuna preferenza configurata → DEFAULT (30 giorni, attivo);
        - preferenza con `auto_delete_days = N` → N giorni;
        - preferenza con `auto_delete_days = None` → disattivata esplicitamente.

        La preferenza globale è memorizzata sulla riga `SYSTEM_ANNOUNCEMENT`.
        """
        preference = NotificationPreference.get_user_preference(
            user_id, NotificationType.SYSTEM_ANNOUNCEMENT
        )
        if preference is None:
            return NotificationService.DEFAULT_AUTO_DELETE_DAYS
        return preference.auto_delete_days

    @staticmethod
    @transactional(domain="notification")
    def set_global_auto_delete_days(
        user_id: int, days: Optional[int]
    ) -> NotificationPreference:
        """Imposta la finestra globale di auto-cancellazione (giorni).

        `days=None` disattiva esplicitamente l'auto-cancellazione. A
        differenza di `set_user_preference`, scrive sempre il valore (anche
        None), così la disattivazione persiste su una preferenza esistente.
        """
        preference = NotificationPreference.get_user_preference(
            user_id, NotificationType.SYSTEM_ANNOUNCEMENT
        )
        if preference is None:
            preference = NotificationPreference(
                user_id=user_id,
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                enabled=True,
            )
            db.session.add(preference)
        preference.auto_delete_days = days
        return preference

    @staticmethod
    @transactional(domain="notification")
    def auto_delete_for_user(user_id: int, default_days: Optional[int] = None) -> int:
        """Cancella TUTTE le notifiche scadute dell'utente (qualsiasi tipo).

        "Scadute" = lette/dismissed/expired più vecchie della finestra di
        auto-cancellazione globale (vedi `get_global_auto_delete_days`).
        Se l'utente non ha mai configurato nulla si applica il default
        (30 giorni); se l'ha disattivata esplicitamente non cancella nulla.

        A differenza di `auto_delete_by_user_preferences` (per-tipo), qui la
        finestra globale si applica a tutti i tipi di notifica (bug 16:
        "cancella tutte quelle scadute").
        """
        days = NotificationService.get_global_auto_delete_days(user_id)
        if days is None:
            days = default_days
        if not days or days <= 0:
            return 0

        cutoff_date = utc_now() - timedelta(days=days)
        old_notifications = Notification.query.filter(
            Notification.user_id == user_id,
            Notification.created_at <= cutoff_date,
            Notification.status.in_(  # type: ignore[attr-defined]
                [
                    NotificationStatus.READ,
                    NotificationStatus.DISMISSED,
                    NotificationStatus.EXPIRED,
                ]
            ),
        ).all()

        count = len(old_notifications)
        for notification in old_notifications:
            db.session.delete(notification)

        return count

    # Specific notification creators for common use cases

    @staticmethod
    def notify_match_proposal(
        proposer_id: int, target_user_id: int, match_details: Dict[str, Any]
    ) -> Optional[Notification]:
        """Notify user about a match proposal."""
        return NotificationService.create_from_template(
            user_id=target_user_id,
            notification_type=NotificationType.MATCH_PROPOSAL,
            context={
                "proposer_name": match_details.get("proposer_name", "Someone"),
                "location": match_details.get("location", "TBD"),
                "scheduled_time": match_details.get("scheduled_time", "TBD"),
                "proposal_id": match_details.get("proposal_id"),
            },
        )

    @staticmethod
    def notify_match_accepted(
        proposer_id: int, accepter_name: str, match_details: Dict[str, Any]
    ) -> Optional[Notification]:
        """Notify proposer that their match was accepted."""
        return NotificationService.create_from_template(
            user_id=proposer_id,
            notification_type=NotificationType.MATCH_ACCEPTED,
            context={
                "accepter_name": accepter_name,
                "location": match_details.get("location", "TBD"),
                "scheduled_time": match_details.get("scheduled_time", "TBD"),
                "match_id": match_details.get("match_id"),
            },
        )

    @staticmethod
    def notify_campionato_registration(
        user_ids: List[int], campionato_name: str, campionato_id: int
    ) -> List[Notification]:
        """Notify multiple users about campionato registration opening."""
        notifications = []

        for user_id in user_ids:
            notification = NotificationService.create_from_template(
                user_id=user_id,
                notification_type=NotificationType.TOURNAMENT_REGISTRATION,
                context={
                    "campionato_name": campionato_name,
                    "campionato_id": campionato_id,
                },
            )
            if notification:
                notifications.append(notification)

        return notifications

    @staticmethod
    def notify_playoff_invitation(
        user_id: int, playoff_name: str, campionato_name: str, deadline: datetime
    ) -> Optional[Notification]:
        """Notify user about playoff invitation."""
        return NotificationService.create_from_template(
            user_id=user_id,
            notification_type=NotificationType.PLAYOFF_INVITATION,
            context={
                "playoff_name": playoff_name,
                "campionato_name": campionato_name,
                "deadline": deadline.strftime("%Y-%m-%d %H:%M"),
            },
            expires_override=deadline,
        )

    @staticmethod
    @transactional(domain="notification")
    def create_default_templates() -> List[NotificationTemplate]:
        """Create default notification templates."""
        templates_data = [
            {
                "type": NotificationType.MATCH_PROPOSAL,
                "title": "New Match Proposal",
                "message": (
                    "{proposer_name} has proposed a match at {location} "
                    "on {scheduled_time}"
                ),
                "action_text": "View Proposal",
                "action_url": "/player/proposals/{proposal_id}",
                "expires_hours": 48,
            },
            {
                "type": NotificationType.MATCH_ACCEPTED,
                "title": "Match Accepted!",
                "message": (
                    "{accepter_name} has accepted your match proposal for "
                    "{location} on {scheduled_time}"
                ),
                "action_text": "View Match",
                "action_url": "/player/matches/{match_id}",
                "expires_hours": 24,
            },
            {
                "type": NotificationType.TOURNAMENT_REGISTRATION,
                "title": "Campionato Registration Open",
                "message": "Registration is now open for {campionato_name}",
                "action_text": "Register Now",
                "action_url": "/campionati/{campionato_id}",
                "expires_hours": 168,  # 1 week
            },
            {
                "type": NotificationType.PLAYOFF_INVITATION,
                "title": "Playoff Invitation",
                "message": (
                    "You've qualified for {playoff_name} in {campionato_name}! "
                    "Please respond by {deadline}"
                ),
                "action_text": "Respond",
                "action_url": "/playoffs/respond",
                "priority": NotificationPriority.HIGH,
            },
        ]

        templates = []
        for template_data in templates_data:
            existing = NotificationTemplate.query.filter_by(
                notification_type=template_data["type"]
            ).first()

            if not existing:
                template = NotificationTemplate(
                    notification_type=template_data["type"],
                    title_template=template_data["title"],
                    message_template=template_data["message"],
                    action_text_template=template_data.get("action_text"),
                    action_url_template=template_data.get("action_url"),
                    default_priority=template_data.get(
                        "priority", NotificationPriority.NORMAL
                    ),
                    default_expires_hours=template_data.get("expires_hours"),
                )
                db.session.add(template)
                templates.append(template)

        return templates
