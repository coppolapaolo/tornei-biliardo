"""
Notification Factory for standardizing notification creation patterns.

This module provides a centralized factory for creating notifications with
standardized error handling, logging, and common patterns used throughout
the application.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any, Union

from .services import NotificationService
from .models import NotificationType, NotificationPriority

logger = logging.getLogger(__name__)


class NotificationFactory:
    """
    Factory for creating notifications with standardized patterns.

    This factory centralizes notification creation logic and provides
    standardized error handling, logging, and bulk operation support
    to reduce code duplication across the application.
    """

    @staticmethod
    def create_admin_notification(
        admin_user_ids: List[int],
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        related_entities: Optional[Dict[str, Any]] = None,
        action_url: Optional[str] = None,
        action_text: Optional[str] = None,
    ) -> List[Optional]:
        """
        Create notifications for multiple admin users.

        Args:
            admin_user_ids: List of admin user IDs to notify
            title: Notification title
            message: Notification message
            priority: Notification priority level
            related_entities: Optional related data
            action_url: Optional action URL
            action_text: Optional action button text

        Returns:
            List of created notifications (or None for failed notifications)
        """
        notifications = []

        for admin_id in admin_user_ids:
            try:
                notification = NotificationService.create_notification(
                    user_id=admin_id,
                    notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                    title=title,
                    message=message,
                    priority=priority,
                    related_entities=related_entities,
                    action_url=action_url,
                    action_text=action_text,
                )
                notifications.append(notification)
                logger.debug(f"Created admin notification for user {admin_id}: {title}")
            except Exception as e:
                logger.error(f"Failed to create admin notification for user {admin_id}: {e}", exc_info=True)
                notifications.append(None)

        return notifications

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
    ) -> List[Optional]:
        """
        Create notifications for multiple users with error handling.

        Args:
            user_ids: List of user IDs to notify
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            priority: Notification priority level
            related_entities: Optional related data
            action_url: Optional action URL
            action_text: Optional action button text
            continue_on_error: Whether to continue if individual notifications fail

        Returns:
            List of created notifications (or None for failed notifications)
        """
        notifications = []
        failed_count = 0

        for user_id in user_ids:
            try:
                notification = NotificationService.create_notification(
                    user_id=user_id,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    priority=priority,
                    related_entities=related_entities,
                    action_url=action_url,
                    action_text=action_text,
                )
                notifications.append(notification)
                logger.debug(f"Created notification for user {user_id}: {title}")
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to create notification for user {user_id}: {e}", exc_info=True)
                notifications.append(None)

                if not continue_on_error:
                    logger.error(f"Stopping bulk notification creation after error for user {user_id}")
                    break

        if failed_count > 0:
            logger.warning(f"Bulk notification completed with {failed_count} failures out of {len(user_ids)} users")
        else:
            logger.info(f"Successfully created notifications for all {len(user_ids)} users")

        return notifications

    @staticmethod
    def create_tournament_notification(
        user_ids: List[int],
        tournament_name: str,
        message_template: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        tournament_id: Optional[int] = None,
    ) -> List[Optional]:
        """
        Create tournament-related notifications for multiple users.

        Args:
            user_ids: List of user IDs to notify
            tournament_name: Name of the tournament
            message_template: Message template (will be formatted with tournament_name)
            priority: Notification priority level
            tournament_id: Optional tournament ID for action URL

        Returns:
            List of created notifications
        """
        message = message_template.format(tournament_name=tournament_name)
        action_url = f"/gare/{tournament_id}" if tournament_id else None

        return NotificationFactory.create_bulk_notification(
            user_ids=user_ids,
            notification_type=NotificationType.TOURNAMENT_REGISTRATION,
            title="Aggiornamento Torneo",
            message=message,
            priority=priority,
            related_entities={"tournament_id": tournament_id, "tournament_name": tournament_name} if tournament_id else None,
            action_url=action_url,
            action_text="Visualizza Torneo" if action_url else None,
        )

    @staticmethod
    def create_match_notification(
        user_id: int,
        match_type: str,  # "proposal", "accepted", "completed", etc.
        player_names: List[str],
        location_name: Optional[str] = None,
        scheduled_time: Optional[str] = None,
        notes: Optional[str] = None,
        match_id: Optional[int] = None,
        proposal_id: Optional[int] = None,
    ) -> Optional:
        """
        Create match-related notification with standardized content.

        Args:
            user_id: User ID to notify
            match_type: Type of match event ("proposal", "accepted", "completed")
            player_names: Names of players involved
            location_name: Optional location name
            scheduled_time: Optional scheduled time
            notes: Optional additional notes
            match_id: Optional match ID for action URL
            proposal_id: Optional proposal ID for action URL

        Returns:
            Created notification or None if failed
        """
        # Determine notification type and content based on match_type
        type_map = {
            "proposal": NotificationType.MATCH_PROPOSAL,
            "accepted": NotificationType.MATCH_ACCEPTED,
            "completed": NotificationType.TOURNAMENT_RESULTS,  # closest available
        }

        title_map = {
            "proposal": "Nuova Proposta di Partita",
            "accepted": "Proposta Accettata!",
            "completed": "Partita Completata",
        }

        notification_type = type_map.get(match_type, NotificationType.MATCH_PROPOSAL)
        title = title_map.get(match_type, "Aggiornamento Partita")

        # Build message
        players_text = " vs ".join(player_names) if len(player_names) > 1 else player_names[0]
        location_text = f" presso {location_name}" if location_name else ""
        time_text = f" il {scheduled_time}" if scheduled_time else ""

        message = f"{players_text}{location_text}{time_text}"
        if notes:
            message += f". {notes}"

        # Determine action URL
        action_url = None
        action_text = None
        if match_id:
            action_url = f"/player/matches/{match_id}"
            action_text = "Visualizza Partita"
        elif proposal_id:
            action_url = f"/player/proposals/{proposal_id}"
            action_text = "Visualizza Proposta"

        try:
            return NotificationService.create_notification(
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                message=message,
                priority=NotificationPriority.NORMAL,
                related_entities={
                    "match_type": match_type,
                    "player_names": player_names,
                    "location_name": location_name,
                    "match_id": match_id,
                    "proposal_id": proposal_id,
                },
                action_url=action_url,
                action_text=action_text,
            )
        except Exception as e:
            logger.error(f"Failed to create match notification for user {user_id}: {e}", exc_info=True)
            return None

    @staticmethod
    def create_account_update_notification(
        user_id: int,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        update_type: Optional[str] = None,
        related_entities: Optional[Dict[str, Any]] = None,
    ) -> Optional:
        """
        Create account update notification with standardized error handling.

        Args:
            user_id: User ID to notify
            title: Notification title
            message: Notification message
            priority: Notification priority level
            update_type: Type of account update
            related_entities: Optional related data

        Returns:
            Created notification or None if failed
        """
        try:
            entities = related_entities or {}
            if update_type:
                entities["update_type"] = update_type

            return NotificationService.create_notification(
                user_id=user_id,
                notification_type=NotificationType.ACCOUNT_UPDATE,
                title=title,
                message=message,
                priority=priority,
                related_entities=entities,
            )
        except Exception as e:
            logger.error(f"Failed to create account update notification for user {user_id}: {e}", exc_info=True)
            return None

    @staticmethod
    def create_system_announcement(
        user_ids: List[int],
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        action_url: Optional[str] = None,
        action_text: Optional[str] = None,
    ) -> List[Optional]:
        """
        Create system announcement for multiple users.

        Args:
            user_ids: List of user IDs to notify
            title: Announcement title
            message: Announcement message
            priority: Notification priority level
            action_url: Optional action URL
            action_text: Optional action button text

        Returns:
            List of created notifications
        """
        return NotificationFactory.create_bulk_notification(
            user_ids=user_ids,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            title=title,
            message=message,
            priority=priority,
            action_url=action_url,
            action_text=action_text,
        )

    @staticmethod
    def get_notification_stats(notifications: List[Optional]) -> Dict[str, int]:
        """
        Get statistics from a list of notification creation results.

        Args:
            notifications: List of notifications (with None for failures)

        Returns:
            Dict with success/failure statistics
        """
        successful = sum(1 for n in notifications if n is not None)
        failed = sum(1 for n in notifications if n is None)

        return {
            "total": len(notifications),
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / len(notifications) * 100) if notifications else 0,
        }