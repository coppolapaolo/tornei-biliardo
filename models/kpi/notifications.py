"""
Module: models/kpi/notifications.py
Purpose: KPI notification service for admin alerts
"""

from __future__ import annotations

from typing import List, Tuple
import logging

from flask_babel import _

from ..notification.models import NotificationType, NotificationPriority
from ..notification.services import NotificationService
from ..user.models import User
from .enums import MilestoneType, AlertType

logger = logging.getLogger(__name__)


class KpiNotificationService:
    """Service for sending KPI-related notifications to admins."""

    @staticmethod
    def get_admin_user_ids() -> List[int]:
        """Get all admin user IDs."""
        admins = User.query.filter_by(role="admin", is_deleted=False).all()
        return [admin.id for admin in admins]

    @staticmethod
    def notify_milestone(milestone_type: MilestoneType, value: int) -> List[int]:
        """
        Send milestone notification to all admins.

        Returns list of admin IDs who received the notification.
        """
        admin_ids = KpiNotificationService.get_admin_user_ids()

        if not admin_ids:
            logger.warning("No admin users found for milestone notification")
            return []

        # Build notification content based on milestone type
        if milestone_type == MilestoneType.USERS_TOTAL:
            title = _("Milestone: %(value)s utenti!", value=value)
            message = _(
                "La community ha raggiunto %(value)s utenti registrati. "
                "Congratulazioni!",
                value=value,
            )
        elif milestone_type == MilestoneType.MATCHES_TOTAL:
            title = _("Milestone: %(value)s partite!", value=value)
            message = _(
                "Sono state giocate %(value)s partite sulla piattaforma. "
                "La community cresce!",
                value=value,
            )
        elif milestone_type == MilestoneType.GARE_COMPLETED:
            title = _("Milestone: %(value)s gare completate!", value=value)
            message = _(
                "Sono state completate %(value)s gare. " "Ottimo lavoro!",
                value=value,
            )
        else:
            title = _("Milestone raggiunta!")
            message = _(
                "Una nuova milestone e stata raggiunta: %(type)s = %(value)s",
                type=milestone_type.value,
                value=value,
            )

        notified_ids = []
        for admin_id in admin_ids:
            try:
                notification = NotificationService.create_notification(
                    user_id=admin_id,
                    notification_type=NotificationType.KPI_MILESTONE,
                    title=title,
                    message=message,
                    priority=NotificationPriority.NORMAL,
                    related_entities={
                        "milestone_type": milestone_type.value,
                        "milestone_value": value,
                    },
                    action_url="/admin/kpi",
                    action_text=_("Visualizza KPI"),
                )
                if notification:
                    notified_ids.append(admin_id)
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id} of milestone: {e}")

        logger.info(
            f"Sent milestone notification ({milestone_type.value}={value}) "
            f"to {len(notified_ids)}/{len(admin_ids)} admins"
        )
        return notified_ids

    @staticmethod
    def notify_activity_alert(alert_type: AlertType) -> List[int]:
        """
        Send activity alert notification to all admins.

        Returns list of admin IDs who received the notification.
        """
        admin_ids = KpiNotificationService.get_admin_user_ids()

        if not admin_ids:
            logger.warning("No admin users found for activity alert")
            return []

        # Build notification content based on alert type
        if alert_type == AlertType.NO_MATCH_3_DAYS:
            title = _("Attenzione: calo attivita")
            message = _(
                "Non sono state giocate partite negli ultimi 3 giorni. "
                "Potrebbe essere utile stimolare la community."
            )
            priority = NotificationPriority.NORMAL
        elif alert_type == AlertType.NO_MATCH_7_DAYS:
            title = _("Attenzione: nessuna partita da 7 giorni")
            message = _(
                "Non sono state giocate partite negli ultimi 7 giorni. "
                "La community potrebbe aver bisogno di attenzione."
            )
            priority = NotificationPriority.HIGH
        elif alert_type == AlertType.NO_REGISTRATION_7_DAYS:
            title = _("Attenzione: nessuna registrazione")
            message = _(
                "Non ci sono state nuove registrazioni negli ultimi 7 giorni. "
                "Considera strategie di promozione."
            )
            priority = NotificationPriority.NORMAL
        else:
            title = _("Alert attivita")
            message = _("Si e verificato un calo di attivita sulla piattaforma.")
            priority = NotificationPriority.NORMAL

        notified_ids = []
        for admin_id in admin_ids:
            try:
                notification = NotificationService.create_notification(
                    user_id=admin_id,
                    notification_type=NotificationType.KPI_ACTIVITY_ALERT,
                    title=title,
                    message=message,
                    priority=priority,
                    related_entities={"alert_type": alert_type.value},
                    action_url="/admin/kpi",
                    action_text=_("Visualizza KPI"),
                )
                if notification:
                    notified_ids.append(admin_id)
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id} of alert: {e}")

        logger.info(
            f"Sent activity alert ({alert_type.value}) "
            f"to {len(notified_ids)}/{len(admin_ids)} admins"
        )
        return notified_ids

    @staticmethod
    def notify_milestones_batch(milestones: List[Tuple[MilestoneType, int]]) -> int:
        """
        Send notifications for multiple milestones.

        Returns total count of notifications sent.
        """
        total_sent = 0
        for milestone_type, value in milestones:
            sent = KpiNotificationService.notify_milestone(milestone_type, value)
            total_sent += len(sent)
        return total_sent

    @staticmethod
    def notify_alerts_batch(alerts: List[AlertType]) -> int:
        """
        Send notifications for multiple alerts.

        Returns total count of notifications sent.
        """
        total_sent = 0
        for alert_type in alerts:
            sent = KpiNotificationService.notify_activity_alert(alert_type)
            total_sent += len(sent)
        return total_sent
