"""
Module: models/notification/services.py
Purpose: Notification domain services for notification management
Requirements: SPECIFICHE.md - Notification system for matches and tournaments
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from ..base import db
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

    @staticmethod
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
        """Create a new notification if user preferences allow it."""

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
        )

        if related_entities:
            notification.set_related_entities(related_entities)

        db.session.add(notification)
        db.session.commit()

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
                Notification.status.in_(
                    [  # type: ignore
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
    def mark_notification_read(notification_id: int, user_id: int) -> bool:
        """Mark a notification as read."""
        notification = Notification.query.filter_by(
            id=notification_id, user_id=user_id
        ).first()

        if not notification:
            return False

        notification.mark_as_read()
        db.session.commit()
        return True

    @staticmethod
    def dismiss_notification(notification_id: int, user_id: int) -> bool:
        """Dismiss a notification."""
        notification = Notification.query.filter_by(
            id=notification_id, user_id=user_id
        ).first()

        if not notification:
            return False

        notification.dismiss()
        db.session.commit()
        return True

    @staticmethod
    def mark_all_read(user_id: int) -> int:
        """Mark all notifications as read for a user."""
        notifications = (
            Notification.query.filter_by(user_id=user_id)
            .filter(
                Notification.status.in_(
                    [  # type: ignore
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

        db.session.commit()
        return count

    @staticmethod
    def get_unread_count(user_id: int) -> int:
        """Get count of unread notifications for user."""
        return (
            Notification.query.filter_by(user_id=user_id)
            .filter(
                Notification.status.in_(
                    [  # type: ignore
                        NotificationStatus.PENDING,
                        NotificationStatus.SENT,
                    ]
                )
            )
            .count()
        )

    @staticmethod
    def set_user_preference(
        user_id: int,
        notification_type: NotificationType,
        enabled: bool = True,
        email_enabled: bool = False,
        quiet_hours_start: Optional[str] = None,
        quiet_hours_end: Optional[str] = None,
        max_per_day: Optional[int] = None,
        min_interval_minutes: Optional[int] = None,
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
        else:
            preference = NotificationPreference(
                user_id=user_id,
                notification_type=notification_type,
                enabled=enabled,
                email_enabled=email_enabled,
                max_per_day=max_per_day,
                min_interval_minutes=min_interval_minutes,
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

        db.session.commit()
        return preference

    @staticmethod
    def get_user_preferences(user_id: int) -> Dict[str, NotificationPreference]:
        """Get all notification preferences for a user."""
        preferences = NotificationPreference.query.filter_by(user_id=user_id).all()
        return {pref.notification_type.value: pref for pref in preferences}

    @staticmethod
    def expire_old_notifications() -> int:
        """Expire old notifications that have passed their expiry time."""
        expired_notifications = Notification.query.filter(
            Notification.expires_at <= datetime.utcnow(),
            Notification.status.in_(
                [NotificationStatus.PENDING, NotificationStatus.SENT]  # type: ignore
            ),
        ).all()

        count = 0
        for notification in expired_notifications:
            notification.expire()
            count += 1

        db.session.commit()
        return count

    @staticmethod
    def cleanup_old_notifications(days_old: int = 30) -> int:
        """Delete old notifications to keep database clean."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)

        old_notifications = Notification.query.filter(
            Notification.created_at <= cutoff_date,
            Notification.status.in_(
                [  # type: ignore
                    NotificationStatus.READ,
                    NotificationStatus.DISMISSED,
                    NotificationStatus.EXPIRED,
                ]
            ),
        ).all()

        count = len(old_notifications)
        for notification in old_notifications:
            db.session.delete(notification)

        db.session.commit()
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
    def notify_tournament_registration(
        user_ids: List[int], tournament_name: str, tournament_id: int
    ) -> List[Notification]:
        """Notify multiple users about tournament registration opening."""
        notifications = []

        for user_id in user_ids:
            notification = NotificationService.create_from_template(
                user_id=user_id,
                notification_type=NotificationType.TOURNAMENT_REGISTRATION,
                context={
                    "tournament_name": tournament_name,
                    "tournament_id": tournament_id,
                },
            )
            if notification:
                notifications.append(notification)

        return notifications

    @staticmethod
    def notify_playoff_invitation(
        user_id: int, playoff_name: str, tournament_name: str, deadline: datetime
    ) -> Optional[Notification]:
        """Notify user about playoff invitation."""
        return NotificationService.create_from_template(
            user_id=user_id,
            notification_type=NotificationType.PLAYOFF_INVITATION,
            context={
                "playoff_name": playoff_name,
                "tournament_name": tournament_name,
                "deadline": deadline.strftime("%Y-%m-%d %H:%M"),
            },
            expires_override=deadline,
        )

    @staticmethod
    def create_default_templates() -> List[NotificationTemplate]:
        """Create default notification templates."""
        templates_data = [
            {
                "type": NotificationType.MATCH_PROPOSAL,
                "title": "New Match Proposal",
                "message": "{proposer_name} has proposed a match at {location} on {scheduled_time}",
                "action_text": "View Proposal",
                "action_url": "/player/proposals/{proposal_id}",
                "expires_hours": 48,
            },
            {
                "type": NotificationType.MATCH_ACCEPTED,
                "title": "Match Accepted!",
                "message": "{accepter_name} has accepted your match proposal for {location} on {scheduled_time}",
                "action_text": "View Match",
                "action_url": "/player/matches/{match_id}",
                "expires_hours": 24,
            },
            {
                "type": NotificationType.TOURNAMENT_REGISTRATION,
                "title": "Tournament Registration Open",
                "message": "Registration is now open for {tournament_name}",
                "action_text": "Register Now",
                "action_url": "/tournaments/{tournament_id}",
                "expires_hours": 168,  # 1 week
            },
            {
                "type": NotificationType.PLAYOFF_INVITATION,
                "title": "Playoff Invitation",
                "message": "You've qualified for {playoff_name} in {tournament_name}! Please respond by {deadline}",
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

        db.session.commit()
        return templates
