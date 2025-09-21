"""
Module: models/notification/services.py
Purpose: Notification domain services for community notification management
Requirements: SPECIFICHE.md - Notification system for match proposals, campionato updates, and community engagement

Business Logic:
- Handles notification lifecycle from creation to cleanup
- Respects user preferences including quiet hours and rate limiting
- Supports template-based notifications for consistency
- Provides transaction safety for all notification operations
- Manages community-wide notifications for tournaments and system announcements

Architecture:
- All write operations use @transactional(domain="notification") for data integrity
- Template system ensures consistent messaging across notification types
- User preference engine prevents notification spam and respects user settings
- Automatic expiration and cleanup maintain database performance

Integrations:
- Individual Match System: Match proposals, acceptances, cancellations
- Tournament System: Registration alerts, playoff invitations, results
- Challenge System: Skill challenges and exam notifications
- Community Features: System announcements and account updates
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from ..base import db
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
    """Service for community notification management and delivery.

    Core service for the platform's notification system, handling all aspects
    of user notifications from creation to cleanup. Ensures notifications respect
    user preferences and provide a non-intrusive community experience.

    Key Features:
    - Template-based notification creation for consistency
    - User preference enforcement (quiet hours, rate limiting)
    - Automatic expiration and cleanup for database efficiency
    - Transactional safety for all notification operations
    - Community-wide broadcast capabilities for tournaments
    """

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
    ) -> Optional[Notification]:
        """Create a new notification with user preference validation.

        Core notification creation method that respects user preferences and
        rate limiting rules. Returns None if user has disabled this notification
        type or if rate limits would be exceeded.

        Args:
            user_id: Target user for the notification
            notification_type: Type of notification (match_proposal, tournament_registration, etc.)
            title: Notification headline
            message: Detailed notification content
            priority: Notification importance level
            related_entities: JSON data for notification context (match_id, tournament_id, etc.)
            action_url: Optional URL for notification action button
            action_text: Optional text for action button
            expires_at: Optional expiration datetime for time-sensitive notifications

        Returns:
            Notification instance if created, None if blocked by user preferences

        Business Rules:
        - Checks user notification preferences before creation
        - Enforces rate limiting (max_per_day, min_interval_minutes)
        - Respects quiet hours settings
        - Automatically sets PENDING status for new notifications
        """

        # Enforce user notification preferences - respects community member privacy settings
        if not NotificationPreference.is_notification_enabled(
            user_id, notification_type
        ):
            return None  # User has disabled this notification type

        # Check rate limiting and quiet hours - prevents notification spam
        preference = NotificationPreference.get_user_preference(
            user_id, notification_type
        )
        if preference and not preference.can_send_notification():
            return None  # Rate limited or in quiet hours

        # Create notification with PENDING status - transaction managed by decorator
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            action_url=action_url,
            action_text=action_text,
            expires_at=expires_at,
            # status defaults to PENDING in model
        )

        # Store context data for notification rendering and business logic
        if related_entities:
            notification.set_related_entities(related_entities)

        db.session.add(notification)
        return notification

    @staticmethod
    def create_from_template(
        user_id: int,
        notification_type: NotificationType,
        context: Dict[str, Any],
        priority_override: Optional[NotificationPriority] = None,
        expires_override: Optional[datetime] = None,
    ) -> Optional[Notification]:
        """Create notification from template with dynamic content rendering.

        Template-based notification creation ensures consistent messaging across
        the platform while allowing dynamic content personalization.

        Args:
            user_id: Target user for notification
            notification_type: Template type to use
            context: Template variables (player names, match details, etc.)
            priority_override: Override template default priority
            expires_override: Override template default expiration

        Returns:
            Notification if created successfully, None if no template or user preferences block

        Business Logic:
        - Uses NotificationTemplate for consistent community messaging
        - Renders dynamic content using Jinja2-style templates
        - Falls back gracefully if template not found
        - Preserves context data for future reference
        """

        # Fetch template for consistent community messaging
        template = NotificationTemplate.query.filter_by(
            notification_type=notification_type
        ).first()

        if not template:
            # Graceful degradation - no template available for this notification type
            return None

        # Render dynamic content using template engine (Jinja2-style)
        rendered = template.render_notification(context)

        # Apply priority and expiration rules - template defaults with override capability
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
        """Retrieve user notifications with filtering options.

        Provides filtered access to user notifications for dashboard display
        and notification management interfaces.

        Args:
            user_id: User to fetch notifications for
            unread_only: If True, only return unread notifications (PENDING/SENT status)
            limit: Maximum number of notifications to return

        Returns:
            List of notifications ordered by creation date (newest first)

        Business Logic:
        - Excludes dismissed and expired notifications from unread filter
        - Orders by creation date for chronological display
        - Supports pagination through limit parameter
        """

        # Base query for user's notifications
        query = Notification.query.filter_by(user_id=user_id)

        # Filter for unread notifications - excludes read, dismissed, and expired
        if unread_only:
            query = query.filter(
                Notification.status.in_(  # type: ignore[attr-defined]
                    [
                        NotificationStatus.PENDING,  # Not yet delivered
                        NotificationStatus.SENT,  # Delivered but not read
                    ]
                )
            )

        # Order by creation date - newest notifications first for user experience
        query = query.order_by(Notification.created_at.desc())

        # Apply pagination limit if requested
        if limit:
            query = query.limit(limit)

        return query.all()

    @staticmethod
    @transactional(domain="notification")
    def mark_notification_read(notification_id: int, user_id: int) -> bool:
        """Mark notification as read by user.

        Updates notification status to READ and sets read timestamp.
        Includes user_id validation for security.

        Args:
            notification_id: Notification to mark as read
            user_id: User attempting to mark notification (security validation)

        Returns:
            True if notification was marked as read, False if not found or access denied

        Security:
        - Validates user_id matches notification owner to prevent unauthorized access
        - Transaction safety through @transactional decorator
        """
        # Security check - ensure user owns this notification
        notification = Notification.query.filter_by(
            id=notification_id, user_id=user_id
        ).first()

        if not notification:
            return False  # Notification not found or access denied

        # Update status and timestamp - business logic in model method
        notification.mark_as_read()
        return True

    @staticmethod
    @transactional(domain="notification")
    def dismiss_notification(notification_id: int, user_id: int) -> bool:
        """Dismiss notification without reading.

        Allows users to dismiss notifications they're not interested in,
        removing them from unread counts and notification displays.

        Args:
            notification_id: Notification to dismiss
            user_id: User attempting to dismiss notification (security validation)

        Returns:
            True if notification was dismissed, False if not found or access denied

        Business Logic:
        - Dismissed notifications don't appear in unread counts
        - Different from read status - indicates user actively dismissed
        - Provides user control over notification visibility
        """
        # Security validation - user must own notification to dismiss
        notification = Notification.query.filter_by(
            id=notification_id, user_id=user_id
        ).first()

        if not notification:
            return False  # Not found or unauthorized access

        # Set dismissed status - removes from user's active notifications
        notification.dismiss()
        return True

    @staticmethod
    @transactional(domain="notification")
    def mark_all_read(user_id: int) -> int:
        """Mark all unread notifications as read for user.

        Bulk operation to clear all unread notifications, typically used
        for "mark all as read" functionality in notification interfaces.

        Args:
            user_id: User whose notifications to mark as read

        Returns:
            Number of notifications that were marked as read

        Business Logic:
        - Only affects PENDING and SENT notifications (already unread)
        - Preserves dismissed and expired notifications in their current state
        - Efficient bulk operation for user experience
        """
        # Fetch all unread notifications for user
        notifications = (
            Notification.query.filter_by(user_id=user_id)
            .filter(
                Notification.status.in_(  # type: ignore[attr-defined]
                    [
                        NotificationStatus.PENDING,  # Not yet delivered
                        NotificationStatus.SENT,  # Delivered but unread
                    ]
                )
            )
            .all()
        )

        # Bulk mark as read - transaction safety from decorator
        count = 0
        for notification in notifications:
            notification.mark_as_read()  # Sets READ status and read_at timestamp
            count += 1

        return count

    @staticmethod
    def get_unread_count(user_id: int) -> int:
        """Get count of unread notifications for user dashboard.

        Provides unread notification count for UI badge displays and
        user notification status indicators.

        Args:
            user_id: User to count unread notifications for

        Returns:
            Number of unread notifications (PENDING + SENT status)

        Performance:
        - Uses COUNT query for efficiency (no data transfer)
        - Commonly used for real-time dashboard updates
        """
        # Efficient count query for unread notifications
        return (
            Notification.query.filter_by(user_id=user_id)
            .filter(
                Notification.status.in_(  # type: ignore[attr-defined]
                    [
                        NotificationStatus.PENDING,  # Newly created notifications
                        NotificationStatus.SENT,  # Delivered but not read
                    ]
                )
            )
            .count()  # Database-level count for performance
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
    ) -> NotificationPreference:
        """Configure user notification preferences for a specific type.

        Manages user notification settings including rate limiting, quiet hours,
        and delivery preferences. Creates or updates existing preferences.

        Args:
            user_id: User setting preferences
            notification_type: Type of notification to configure
            enabled: Whether notifications of this type are enabled
            email_enabled: Whether to send email notifications (future feature)
            quiet_hours_start: Start time for quiet hours (HH:MM format)
            quiet_hours_end: End time for quiet hours (HH:MM format)
            max_per_day: Maximum notifications per day (rate limiting)
            min_interval_minutes: Minimum minutes between notifications

        Returns:
            NotificationPreference instance (created or updated)

        Business Logic:
        - Creates new preference if none exists, updates existing otherwise
        - Validates time format for quiet hours
        - Gracefully handles invalid time strings
        - Supports community-friendly notification management
        """

        # Update existing preference or create new one
        preference = NotificationPreference.get_user_preference(
            user_id, notification_type
        )

        if preference:
            # Update existing preference - preserve settings not being changed
            preference.enabled = enabled
            preference.email_enabled = email_enabled
            if max_per_day is not None:
                preference.max_per_day = max_per_day
            if min_interval_minutes is not None:
                preference.min_interval_minutes = min_interval_minutes
        else:
            # Create new preference with provided settings
            preference = NotificationPreference(
                user_id=user_id,
                notification_type=notification_type,
                enabled=enabled,
                email_enabled=email_enabled,
                max_per_day=max_per_day,
                min_interval_minutes=min_interval_minutes,
            )
            db.session.add(preference)

        # Parse and validate quiet hours time strings - graceful error handling
        if quiet_hours_start:
            try:
                preference.quiet_hours_start = datetime.strptime(
                    quiet_hours_start, "%H:%M"
                ).time()
            except ValueError:
                # Invalid time format - silently ignore to preserve user experience
                pass

        if quiet_hours_end:
            try:
                preference.quiet_hours_end = datetime.strptime(
                    quiet_hours_end, "%H:%M"
                ).time()
            except ValueError:
                # Invalid time format - silently ignore to preserve user experience
                pass

        return preference

    @staticmethod
    def get_user_preferences(user_id: int) -> Dict[str, NotificationPreference]:
        """Retrieve all notification preferences for user settings interface.

        Returns comprehensive preference settings for displaying in user
        notification management interfaces.

        Args:
            user_id: User to fetch preferences for

        Returns:
            Dictionary mapping notification type values to preference objects

        Usage:
        - Used for populating user notification settings forms
        - Provides complete preference state for frontend management
        """
        # Fetch all user preferences for settings interface
        preferences = NotificationPreference.query.filter_by(user_id=user_id).all()
        # Return as dictionary keyed by notification type for easy lookup
        return {pref.notification_type.value: pref for pref in preferences}

    @staticmethod
    @transactional(domain="notification")
    def expire_old_notifications() -> int:
        """Expire notifications that have passed their expiry time.

        System maintenance operation to automatically expire time-sensitive
        notifications that are no longer relevant (match proposals, tournament
        registrations, etc.).

        Returns:
            Number of notifications that were expired

        Business Logic:
        - Only affects PENDING and SENT notifications (still active)
        - Sets EXPIRED status for notifications past their expiry time
        - Maintains data integrity for audit trails
        - Should be run periodically (cron job or background task)
        """
        # Find notifications that have exceeded their expiry time
        expired_notifications = Notification.query.filter(
            Notification.expires_at <= datetime.utcnow(),  # Past expiry time
            Notification.status.in_(  # type: ignore[attr-defined]
                [NotificationStatus.PENDING, NotificationStatus.SENT]  # Still active
            ),
        ).all()

        # Mark each notification as expired
        count = 0
        for notification in expired_notifications:
            notification.expire()  # Sets EXPIRED status
            count += 1

        return count

    @staticmethod
    @transactional(domain="notification")
    def cleanup_old_notifications(days_old: int = 30) -> int:
        """Delete old processed notifications for database maintenance.

        Removes old notifications that have been read, dismissed, or expired
        to prevent unlimited database growth while preserving active notifications.

        Args:
            days_old: Age threshold in days for deletion (default: 30 days)

        Returns:
            Number of notifications that were deleted

        Business Logic:
        - Only deletes processed notifications (READ, DISMISSED, EXPIRED)
        - Preserves active notifications (PENDING, SENT)
        - Maintains audit trail for recent activity
        - Conservative default of 30 days for data retention
        """
        # Calculate cutoff date for cleanup
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)

        # Find old processed notifications safe for deletion
        old_notifications = Notification.query.filter(
            Notification.created_at <= cutoff_date,  # Older than threshold
            Notification.status.in_(  # type: ignore[attr-defined]
                [
                    NotificationStatus.READ,  # User has read
                    NotificationStatus.DISMISSED,  # User has dismissed
                    NotificationStatus.EXPIRED,  # System expired
                ]
            ),
        ).all()

        # Delete old notifications - preserve active ones
        count = len(old_notifications)
        for notification in old_notifications:
            db.session.delete(notification)  # Hard delete for cleanup

        return count

    # ============================================================================
    # DOMAIN-SPECIFIC NOTIFICATION CREATORS
    # ============================================================================
    # These methods provide convenient interfaces for creating notifications
    # for common community platform scenarios. They use templates for consistency
    # and handle domain-specific context data formatting.
    # ============================================================================

    @staticmethod
    def notify_match_proposal(
        proposer_id: int, target_user_id: int, match_details: Dict[str, Any]
    ) -> Optional[Notification]:
        """Notify user about incoming individual match proposal.

        Community feature that alerts users when another player proposes
        a casual match, fostering social interaction and gameplay.

        Args:
            proposer_id: User who made the proposal (for context)
            target_user_id: User receiving the proposal notification
            match_details: Match context (proposer_name, location, time, proposal_id)

        Returns:
            Notification if created, None if user has disabled match proposal notifications

        Integration:
        - Used by Individual Match System when proposals are created
        - Template-based for consistent community messaging
        - Includes action button linking to proposal details
        """
        # Create match proposal notification with community context
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
        """Notify proposer that their match proposal was accepted.

        Confirms successful match arrangement, enabling community members
        to coordinate gameplay and build social connections.

        Args:
            proposer_id: Original match proposer to notify
            accepter_name: Name of user who accepted the proposal
            match_details: Match context (location, time, match_id)

        Returns:
            Notification if created, None if user has disabled acceptance notifications

        Community Impact:
        - Facilitates match coordination between community members
        - Provides confirmation of successful match arrangements
        - Links to match details for planning and execution
        """
        # Notify proposer of successful match arrangement
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
        """Broadcast campionato registration opening to community members.

        Community-wide notification for tournament registration, enabling
        mass communication to interested players about upcoming events.

        Args:
            user_ids: List of users to notify (targeted audience)
            campionato_name: Tournament name for notification content
            campionato_id: Tournament ID for action button linking

        Returns:
            List of created notifications (excludes users who have disabled tournament notifications)

        Business Logic:
        - Respects individual user notification preferences
        - Enables selective community communication
        - Supports tournament marketing and player engagement
        - Template-based for consistent tournament messaging
        """
        # Broadcast to selected community members - respects individual preferences
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
            if notification:  # Only add if user preferences allow
                notifications.append(notification)

        return notifications

    @staticmethod
    def notify_playoff_invitation(
        user_id: int, playoff_name: str, campionato_name: str, deadline: datetime
    ) -> Optional[Notification]:
        """Notify qualified player about playoff invitation.

        Time-sensitive notification for tournament advancement, ensuring
        qualified players are aware of playoff opportunities and deadlines.

        Args:
            user_id: Qualified player to notify
            playoff_name: Name of playoff tournament
            campionato_name: Original tournament name for context
            deadline: Response deadline for automatic expiration

        Returns:
            Notification if created, None if user has disabled playoff notifications

        Business Logic:
        - Automatically expires at response deadline
        - High priority for tournament progression
        - Links to playoff response interface
        - Maintains tournament flow and player engagement
        """
        # Create time-sensitive playoff invitation with automatic expiration
        return NotificationService.create_from_template(
            user_id=user_id,
            notification_type=NotificationType.PLAYOFF_INVITATION,
            context={
                "playoff_name": playoff_name,
                "campionato_name": campionato_name,
                "deadline": deadline.strftime(
                    "%Y-%m-%d %H:%M"
                ),  # Formatted for display
            },
            expires_override=deadline,  # Auto-expire at response deadline
        )

    @staticmethod
    @transactional(domain="notification")
    def create_default_templates() -> List[NotificationTemplate]:
        """Initialize default notification templates for community platform.

        Creates standard templates for consistent notification messaging
        across the platform. Should be run during application setup.

        Returns:
            List of created templates (only new ones, skips existing)

        Template Coverage:
        - Individual Match System: proposals, acceptances
        - Tournament System: registration, playoff invitations
        - Community Features: announcements, system updates

        Design Principles:
        - Clear, actionable messaging
        - Appropriate expiration times for urgency
        - Consistent community tone and branding
        """
        # Define default templates for consistent community messaging
        templates_data = [
            {
                "type": NotificationType.MATCH_PROPOSAL,
                "title": "New Match Proposal",
                "message": "{proposer_name} has proposed a match at {location} on {scheduled_time}",
                "action_text": "View Proposal",
                "action_url": "/player/proposals/{proposal_id}",
                "expires_hours": 48,  # 2 days to respond to match proposals
            },
            {
                "type": NotificationType.MATCH_ACCEPTED,
                "title": "Match Accepted!",
                "message": "{accepter_name} has accepted your match proposal for {location} on {scheduled_time}",
                "action_text": "View Match",
                "action_url": "/player/matches/{match_id}",
                "expires_hours": 24,  # 1 day - less urgent than proposals
            },
            {
                "type": NotificationType.TOURNAMENT_REGISTRATION,
                "title": "Campionato Registration Open",
                "message": "Registration is now open for {campionato_name}",
                "action_text": "Register Now",
                "action_url": "/campionati/{campionato_id}",
                "expires_hours": 168,  # 1 week for tournament registration
            },
            {
                "type": NotificationType.PLAYOFF_INVITATION,
                "title": "Playoff Invitation",
                "message": "You've qualified for {playoff_name} in {campionato_name}! Please respond by {deadline}",
                "action_text": "Respond",
                "action_url": "/playoffs/respond",
                "priority": NotificationPriority.HIGH,  # High priority for tournament progression
                # No default expiry - set dynamically based on tournament deadline
            },
        ]

        # Create templates if they don't already exist
        templates = []
        for template_data in templates_data:
            # Check for existing template to avoid duplicates
            existing = NotificationTemplate.query.filter_by(
                notification_type=template_data["type"]
            ).first()

            if not existing:
                # Create new template with default settings
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
