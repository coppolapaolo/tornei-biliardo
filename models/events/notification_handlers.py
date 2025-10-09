"""
Event handlers for notification generation.

This module contains event handlers that listen to domain events and
generate appropriate notifications using the NotificationService.
This decouples domains from direct notification dependencies.
"""

from __future__ import annotations

import logging

from ..notification.services import NotificationService
from ..notification.models import NotificationType, NotificationPriority
from .base import EventBus
from .user_events import (
    DirectorRequestCreatedEvent,
    DirectorRequestProcessedEvent,
    VenueManagerRequestCreatedEvent,
    VenueManagerRequestProcessedEvent,
)
from .match_events import (
    MatchProposalCreatedEvent,
    MatchAcceptedEvent,
    MatchCompletedEvent,
)
from .competition_events import (
    CompetitionRegistrationOpenedEvent,
    InscriptionCreatedEvent,
    DirectorAssignmentAddedEvent,
    DirectorAssignmentRemovedEvent,
)
from .availability_events import (
    AvailabilityNotificationEvent,
)

logger = logging.getLogger(__name__)


class NotificationEventHandlers:
    """
    Event handlers for generating notifications from domain events.

    This class centralizes all notification logic and removes the need
    for individual services to directly import NotificationService.
    """

    @staticmethod
    def register_all_handlers() -> None:
        """Register all notification event handlers with the EventBus."""
        # User domain handlers
        EventBus.register_handler(
            DirectorRequestCreatedEvent,
            NotificationEventHandlers.handle_director_request_created,
            priority=10
        )
        EventBus.register_handler(
            DirectorRequestProcessedEvent,
            NotificationEventHandlers.handle_director_request_processed,
            priority=10
        )
        EventBus.register_handler(
            VenueManagerRequestCreatedEvent,
            NotificationEventHandlers.handle_venue_manager_request_created,
            priority=10
        )
        EventBus.register_handler(
            VenueManagerRequestProcessedEvent,
            NotificationEventHandlers.handle_venue_manager_request_processed,
            priority=10
        )

        # Match domain handlers
        EventBus.register_handler(
            MatchProposalCreatedEvent,
            NotificationEventHandlers.handle_match_proposal_created,
            priority=10
        )
        EventBus.register_handler(
            MatchAcceptedEvent,
            NotificationEventHandlers.handle_match_accepted,
            priority=10
        )

        # Competition domain handlers
        EventBus.register_handler(
            CompetitionRegistrationOpenedEvent,
            NotificationEventHandlers.handle_competition_registration_opened,
            priority=10
        )
        EventBus.register_handler(
            DirectorAssignmentAddedEvent,
            NotificationEventHandlers.handle_director_assignment_added,
            priority=10
        )
        EventBus.register_handler(
            DirectorAssignmentRemovedEvent,
            NotificationEventHandlers.handle_director_assignment_removed,
            priority=10
        )

        # Availability domain handlers
        EventBus.register_handler(
            AvailabilityNotificationEvent,
            NotificationEventHandlers.handle_availability_notification,
            priority=10
        )

        logger.info("Registered all notification event handlers")

    # User domain notification handlers

    @staticmethod
    def handle_director_request_created(event: DirectorRequestCreatedEvent) -> None:
        """Handle director request created by notifying admins."""
        try:
            # Notify all admins about the new director request
            for admin_id in event.admin_user_ids:
                NotificationService.create_notification(
                    user_id=admin_id,
                    notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                    title="Nuova Richiesta Direttore",
                    message=f"L'utente {event.username} ha richiesto di diventare direttore.",
                    priority=NotificationPriority.HIGH,
                    related_entities={
                        "request_id": event.request_id,
                        "user_id": event.user_id,
                        "username": event.username
                    },
                    action_url="/admin/director_requests",
                    action_text="Gestisci Richiesta"
                )
            logger.info(f"Sent director request notifications for request {event.request_id}")
        except Exception as e:
            logger.error(f"Error handling director request created event: {e}", exc_info=True)

    @staticmethod
    def handle_director_request_processed(event: DirectorRequestProcessedEvent) -> None:
        """Handle director request processed by notifying the requester."""
        try:
            from models.status_enum import DirectorRequestStatus

            if event.status == DirectorRequestStatus.APPROVED.value:
                title = "Richiesta Direttore Approvata"
                message = f"Congratulazioni! La tua richiesta di diventare direttore è stata approvata."
                if event.notes:
                    message += f" Note: {event.notes}"
                priority = NotificationPriority.HIGH
            else:  # rejected
                title = "Richiesta Direttore Rifiutata"
                message = "La tua richiesta di diventare direttore è stata rifiutata."
                if event.notes:
                    message += f" Motivo: {event.notes}"
                message += " Per maggiori informazioni, contatta l'amministratore."
                priority = NotificationPriority.NORMAL

            NotificationService.create_notification(
                user_id=event.user_id,
                notification_type=NotificationType.ACCOUNT_UPDATE,
                title=title,
                message=message,
                priority=priority,
                related_entities={
                    "request_id": event.request_id,
                    "status": event.status,
                    "processed_by_id": event.processed_by_id
                }
            )
            logger.info(f"Sent director request {event.status} notification to user {event.user_id}")
        except Exception as e:
            logger.error(f"Error handling director request processed event: {e}", exc_info=True)

    @staticmethod
    def handle_venue_manager_request_created(event: VenueManagerRequestCreatedEvent) -> None:
        """Handle venue manager request created by notifying admins."""
        try:
            priority = NotificationPriority.HIGH if event.is_contested else NotificationPriority.NORMAL
            title = "Nuova Richiesta Gestore"
            if event.is_contested:
                title += " (CONTESA)"

            message = f"L'utente {event.username} ha richiesto di gestire la sede '{event.venue_name}'. "
            message += f"Motivazione: {event.motivation}"

            if event.is_contested:
                message += " ATTENZIONE: Questa richiesta è contesa da altri gestori esistenti."

            # Notify all admins about the new venue manager request
            for admin_id in event.admin_user_ids:
                NotificationService.create_notification(
                    user_id=admin_id,
                    notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                    title=title,
                    message=message,
                    priority=priority,
                    related_entities={
                        "request_id": event.request_id,
                        "user_id": event.user_id,
                        "username": event.username,
                        "venue_id": event.venue_id,
                        "venue_name": event.venue_name,
                        "is_contested": event.is_contested
                    },
                    action_url="/admin/manager-requests",
                    action_text="Gestisci Richiesta"
                )
            logger.info(f"Sent venue manager request notifications for request {event.request_id}")
        except Exception as e:
            logger.error(f"Error handling venue manager request created event: {e}", exc_info=True)

    @staticmethod
    def handle_venue_manager_request_processed(event: VenueManagerRequestProcessedEvent) -> None:
        """Handle venue manager request processed by notifying the requester."""
        try:
            if event.status == "approved":
                title = f"Richiesta Gestore '{event.venue_name}' Approvata"
                message = f"Congratulazioni! La tua richiesta di gestire la sede '{event.venue_name}' è stata approvata."
                if event.notes:
                    message += f" Note: {event.notes}"
                priority = NotificationPriority.HIGH
            else:  # rejected
                title = f"Richiesta Gestore '{event.venue_name}' Rifiutata"
                message = f"La tua richiesta di gestire la sede '{event.venue_name}' è stata rifiutata."
                if event.notes:
                    message += f" Motivo: {event.notes}"
                message += " Per maggiori informazioni, contatta l'amministratore."
                priority = NotificationPriority.NORMAL

            NotificationService.create_notification(
                user_id=event.user_id,
                notification_type=NotificationType.ACCOUNT_UPDATE,
                title=title,
                message=message,
                priority=priority,
                related_entities={
                    "request_id": event.request_id,
                    "venue_id": event.venue_id,
                    "venue_name": event.venue_name,
                    "status": event.status,
                    "processed_by_id": event.processed_by_id
                }
            )
            logger.info(f"Sent venue manager request {event.status} notification to user {event.user_id}")
        except Exception as e:
            logger.error(f"Error handling venue manager request processed event: {e}", exc_info=True)

    # Match domain notification handlers

    @staticmethod
    def handle_match_proposal_created(event: MatchProposalCreatedEvent) -> None:
        """Handle match proposal created by notifying the target user."""
        if not event.target_user_id:
            # Public proposal, no specific target to notify
            return

        try:
            location_text = f" presso {event.location_name}" if event.location_name else ""
            time_text = f" il {event.scheduled_time.strftime('%d/%m/%Y alle %H:%M')}" if event.scheduled_time else ""

            message = f"{event.proposer_name} ti ha proposto una partita{location_text}{time_text}."
            if event.notes:
                message += f" Note: {event.notes}"

            NotificationService.create_notification(
                user_id=event.target_user_id,
                notification_type=NotificationType.MATCH_PROPOSAL,
                title="Nuova Proposta di Partita",
                message=message,
                priority=NotificationPriority.NORMAL,
                related_entities={
                    "proposal_id": event.proposal_id,
                    "proposer_id": event.proposer_id,
                    "proposer_name": event.proposer_name,
                    "location_id": event.location_id,
                    "location_name": event.location_name
                },
                action_url=f"/player/proposals/{event.proposal_id}",
                action_text="Visualizza Proposta"
            )
            logger.info(f"Sent match proposal notification to user {event.target_user_id}")
        except Exception as e:
            logger.error(f"Error handling match proposal created event: {e}", exc_info=True)

    @staticmethod
    def handle_match_accepted(event: MatchAcceptedEvent) -> None:
        """Handle match accepted by notifying the proposer."""
        try:
            location_text = f" presso {event.location_name}" if event.location_name else ""
            time_text = f" per il {event.scheduled_time.strftime('%d/%m/%Y alle %H:%M')}" if event.scheduled_time else ""

            message = f"{event.accepter_name} ha accettato la tua proposta di partita{location_text}{time_text}."

            NotificationService.create_notification(
                user_id=event.proposer_id,
                notification_type=NotificationType.MATCH_ACCEPTED,
                title="Proposta di Partita Accettata!",
                message=message,
                priority=NotificationPriority.NORMAL,
                related_entities={
                    "proposal_id": event.proposal_id,
                    "match_id": event.match_id,
                    "accepter_id": event.accepter_id,
                    "accepter_name": event.accepter_name,
                    "location_id": event.location_id,
                    "location_name": event.location_name
                },
                action_url=f"/player/matches/{event.match_id}",
                action_text="Visualizza Partita"
            )
            logger.info(f"Sent match accepted notification to user {event.proposer_id}")
        except Exception as e:
            logger.error(f"Error handling match accepted event: {e}", exc_info=True)

    # Competition domain notification handlers

    @staticmethod
    def handle_competition_registration_opened(event: CompetitionRegistrationOpenedEvent) -> None:
        """Handle competition registration opened by notifying eligible users."""
        if not event.eligible_user_ids:
            # No specific users to notify
            return

        try:
            location_text = f" presso {event.location_name}" if event.location_name else ""
            time_text = f" il {event.scheduled_time.strftime('%d/%m/%Y alle %H:%M')}" if event.scheduled_time else ""
            deadline_text = ""
            if event.registration_deadline:
                deadline_text = f" Scadenza iscrizioni: {event.registration_deadline.strftime('%d/%m/%Y alle %H:%M')}."

            message = f"Le iscrizioni per '{event.name}'{location_text}{time_text} sono ora aperte!{deadline_text}"

            # Notify eligible users
            for user_id in event.eligible_user_ids:
                NotificationService.create_notification(
                    user_id=user_id,
                    notification_type=NotificationType.TOURNAMENT_REGISTRATION,
                    title="Iscrizioni Aperte",
                    message=message,
                    priority=NotificationPriority.NORMAL,
                    related_entities={
                        "gara_id": event.gara_id,
                        "name": event.name,
                        "location_id": event.location_id,
                        "location_name": event.location_name
                    },
                    action_url=f"/gare/{event.gara_id}",
                    action_text="Iscriviti Ora"
                )
            logger.info(f"Sent competition registration notifications for gara {event.gara_id}")
        except Exception as e:
            logger.error(f"Error handling competition registration opened event: {e}", exc_info=True)

    # Competition domain notification handlers (continued)

    @staticmethod
    def handle_director_assignment_added(
        event: DirectorAssignmentAddedEvent
    ) -> None:
        """Handle director assignment added by notifying the director."""
        try:
            entity_label = (
                "gara" if event.entity_type == "gara" else "campionato"
            )
            title = "Nominato co-direttore"
            message = (
                f"Sei stato nominato co-direttore "
                f"della {entity_label} '{event.entity_name}'"
            )

            NotificationService.create_notification(
                user_id=event.user_id,
                notification_type=NotificationType.ACCOUNT_UPDATE,
                title=title,
                message=message,
                priority=NotificationPriority.NORMAL,
                related_entities={
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "entity_name": event.entity_name,
                    "assigned_by_id": event.assigned_by_id
                }
            )
            logger.info(
                f"Sent director assignment added notification "
                f"to user {event.user_id}"
            )
        except Exception as e:
            logger.error(
                f"Error handling director assignment added event: {e}",
                exc_info=True
            )

    @staticmethod
    def handle_director_assignment_removed(
        event: DirectorAssignmentRemovedEvent
    ) -> None:
        """Handle director assignment removed by notifying the director."""
        try:
            entity_label = (
                "gara" if event.entity_type == "gara" else "campionato"
            )
            title = "Rimosso da co-direttore"
            message = (
                f"Sei stato rimosso dal ruolo di co-direttore "
                f"della {entity_label} '{event.entity_name}'"
            )

            NotificationService.create_notification(
                user_id=event.user_id,
                notification_type=NotificationType.ACCOUNT_UPDATE,
                title=title,
                message=message,
                priority=NotificationPriority.NORMAL,
                related_entities={
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "entity_name": event.entity_name,
                    "removed_by_id": event.removed_by_id
                }
            )
            logger.info(
                f"Sent director assignment removed notification "
                f"to user {event.user_id}"
            )
        except Exception as e:
            logger.error(
                f"Error handling director assignment removed event: {e}",
                exc_info=True
            )

    # Availability domain notification handlers

    @staticmethod
    def handle_availability_notification(event: AvailabilityNotificationEvent) -> None:
        """Handle availability notification by notifying relevant users."""
        try:
            # Send notifications to all specified users
            for user_id in event.notification_user_ids:
                NotificationService.create_notification(
                    user_id=user_id,
                    notification_type=NotificationType.MATCH_PROPOSAL,
                    title="Giocatore Disponibile",
                    message=event.notification_message,
                    priority=NotificationPriority.NORMAL,
                    related_entities=event.notification_context,
                    action_url=f"/player/availability/{event.location_id}",
                    action_text="Visualizza Disponibilità"
                )
            logger.info(f"Sent availability notifications for location {event.location_id}")
        except Exception as e:
            logger.error(f"Error handling availability notification event: {e}", exc_info=True)


# Auto-register handlers when module is imported
NotificationEventHandlers.register_all_handlers()