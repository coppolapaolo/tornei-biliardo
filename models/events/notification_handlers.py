"""
Event handlers for notification generation.

This module contains event handlers that listen to domain events and
generate appropriate notifications using the NotificationService.
This decouples domains from direct notification dependencies.

I testi si compongono nella lingua del destinatario (ADR-062): titoli e
pulsanti sono pigri, i messaggi fatti di pezzi sono funzioni che il servizio
delle notifiche chiama dentro quella lingua. Un orario si mostra nel fuso del
destinatario (ADR-043).
"""

from __future__ import annotations

import logging

from flask_babel import gettext as _, lazy_gettext as _l

from utils.lingua import data_ora_per

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
)
from .competition_events import (
    CompetitionRegistrationOpenedEvent,
    DirectorAssignmentAddedEvent,
    DirectorAssignmentRemovedEvent,
)
from .availability_events import (
    AvailabilityNotificationEvent,
)

logger = logging.getLogger(__name__)


def _iscrizioni_aperte(event: CompetitionRegistrationOpenedEvent, user_id: int) -> str:
    """Il messaggio delle iscrizioni aperte, per un destinatario preciso."""
    dove = (
        " " + _("presso %(luogo)s", luogo=event.location_name)
        if event.location_name
        else ""
    )
    quando = (
        " " + _("il %(quando)s", quando=data_ora_per(user_id, event.scheduled_time))
        if event.scheduled_time
        else ""
    )
    testo = _(
        "Le iscrizioni per '%(nome)s'%(dove)s%(quando)s sono ora aperte!",
        nome=event.name,
        dove=dove,
        quando=quando,
    )
    if event.registration_deadline:
        testo += " " + _(
            "Scadenza iscrizioni: %(scadenza)s.",
            scadenza=data_ora_per(user_id, event.registration_deadline),
        )
    return testo


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
            priority=10,
        )
        EventBus.register_handler(
            DirectorRequestProcessedEvent,
            NotificationEventHandlers.handle_director_request_processed,
            priority=10,
        )
        EventBus.register_handler(
            VenueManagerRequestCreatedEvent,
            NotificationEventHandlers.handle_venue_manager_request_created,
            priority=10,
        )
        EventBus.register_handler(
            VenueManagerRequestProcessedEvent,
            NotificationEventHandlers.handle_venue_manager_request_processed,
            priority=10,
        )

        # Match domain handlers
        EventBus.register_handler(
            MatchProposalCreatedEvent,
            NotificationEventHandlers.handle_match_proposal_created,
            priority=10,
        )
        EventBus.register_handler(
            MatchAcceptedEvent,
            NotificationEventHandlers.handle_match_accepted,
            priority=10,
        )

        # Competition domain handlers
        EventBus.register_handler(
            CompetitionRegistrationOpenedEvent,
            NotificationEventHandlers.handle_competition_registration_opened,
            priority=10,
        )
        EventBus.register_handler(
            DirectorAssignmentAddedEvent,
            NotificationEventHandlers.handle_director_assignment_added,
            priority=10,
        )
        EventBus.register_handler(
            DirectorAssignmentRemovedEvent,
            NotificationEventHandlers.handle_director_assignment_removed,
            priority=10,
        )

        # Availability domain handlers
        EventBus.register_handler(
            AvailabilityNotificationEvent,
            NotificationEventHandlers.handle_availability_notification,
            priority=10,
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
                    title=_l("Nuova Richiesta Direttore"),
                    message=_l(
                        "L'utente %(username)s ha richiesto di diventare direttore.",
                        username=event.username,
                    ),
                    priority=NotificationPriority.HIGH,
                    related_entities={
                        "request_id": event.request_id,
                        "user_id": event.user_id,
                        "username": event.username,
                    },
                    action_url="/admin/director_requests",
                    action_text=_l("Gestisci Richiesta"),
                )
            logger.info(
                f"Sent director request notifications for request {event.request_id}"
            )
        except Exception as e:
            logger.error(
                f"Error handling director request created event: {e}", exc_info=True
            )

    @staticmethod
    def handle_director_request_processed(event: DirectorRequestProcessedEvent) -> None:
        """Handle director request processed by notifying the requester."""
        try:
            from models.status_enum import DirectorRequestStatus

            approvata = event.status == DirectorRequestStatus.APPROVED.value
            if approvata:
                title = _l("Richiesta Direttore Approvata")
                priority = NotificationPriority.HIGH
            else:  # rejected
                title = _l("Richiesta Direttore Rifiutata")
                priority = NotificationPriority.NORMAL

            def message() -> str:
                if approvata:
                    testo = _(
                        "Congratulazioni! La tua richiesta di diventare "
                        "direttore è stata approvata."
                    )
                    if event.notes:
                        testo += " " + _("Note: %(note)s", note=event.notes)
                    return testo
                testo = _("La tua richiesta di diventare direttore è stata rifiutata.")
                if event.notes:
                    testo += " " + _("Motivo: %(motivo)s", motivo=event.notes)
                return (
                    testo
                    + " "
                    + _("Per maggiori informazioni, contatta l'amministratore.")
                )

            NotificationService.create_notification(
                user_id=event.user_id,
                notification_type=NotificationType.ACCOUNT_UPDATE,
                title=title,
                message=message,
                priority=priority,
                related_entities={
                    "request_id": event.request_id,
                    "status": event.status,
                    "processed_by_id": event.processed_by_id,
                },
            )
            logger.info(
                f"Sent director request {event.status} notification "
                f"to user {event.user_id}"
            )
        except Exception as e:
            logger.error(
                f"Error handling director request processed event: {e}", exc_info=True
            )

    @staticmethod
    def handle_venue_manager_request_created(
        event: VenueManagerRequestCreatedEvent,
    ) -> None:
        """Handle venue manager request created by notifying admins."""
        try:
            priority = (
                NotificationPriority.HIGH
                if event.is_contested
                else NotificationPriority.NORMAL
            )
            title = (
                _l("Nuova Richiesta Gestore (CONTESA)")
                if event.is_contested
                else _l("Nuova Richiesta Gestore")
            )

            def message() -> str:
                testo = _(
                    "L'utente %(username)s ha richiesto di gestire la sede "
                    "'%(sede)s'.",
                    username=event.username,
                    sede=event.venue_name,
                )
                testo += " " + _(
                    "Motivazione: %(motivazione)s", motivazione=event.motivation
                )
                if event.is_contested:
                    testo += " " + _(
                        "ATTENZIONE: Questa richiesta è contesa da altri "
                        "gestori esistenti."
                    )
                return testo

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
                        "is_contested": event.is_contested,
                    },
                    action_url="/admin/manager-requests",
                    action_text=_l("Gestisci Richiesta"),
                )
            logger.info(
                f"Sent venue manager request notifications for request "
                f"{event.request_id}"
            )
        except Exception as e:
            logger.error(
                f"Error handling venue manager request created event: {e}",
                exc_info=True,
            )

    @staticmethod
    def handle_venue_manager_request_processed(
        event: VenueManagerRequestProcessedEvent,
    ) -> None:
        """Handle venue manager request processed by notifying the requester."""
        try:
            sede = event.venue_name
            if event.status == "approved":
                title = _l("Richiesta Gestore '%(sede)s' Approvata", sede=sede)
                priority = NotificationPriority.HIGH
            elif event.status == "revoked":
                # Revoca di una gestione già attiva (non un rifiuto di richiesta):
                # VenueManagerService.revoke_venue_manager pubblica
                # status="revoked". Prima cadeva nell'else "rejected" → messaggio
                # fuorviante "richiesta ... rifiutata".
                title = _l("Gestione Sede '%(sede)s' Revocata", sede=sede)
                priority = NotificationPriority.NORMAL
            else:  # rejected
                title = _l("Richiesta Gestore '%(sede)s' Rifiutata", sede=sede)
                priority = NotificationPriority.NORMAL

            def message() -> str:
                contatta = _("Per maggiori informazioni, contatta l'amministratore.")
                if event.status == "approved":
                    testo = _(
                        "Congratulazioni! La tua richiesta di gestire la sede "
                        "'%(sede)s' è stata approvata.",
                        sede=sede,
                    )
                    if event.notes:
                        testo += " " + _("Note: %(note)s", note=event.notes)
                    return testo
                if event.status == "revoked":
                    testo = _(
                        "La gestione della sede '%(sede)s' ti è stata revocata.",
                        sede=sede,
                    )
                else:
                    testo = _(
                        "La tua richiesta di gestire la sede '%(sede)s' è stata "
                        "rifiutata.",
                        sede=sede,
                    )
                if event.notes:
                    testo += " " + _("Motivo: %(motivo)s", motivo=event.notes)
                return testo + " " + contatta

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
                    "processed_by_id": event.processed_by_id,
                },
            )
            logger.info(
                f"Sent venue manager request {event.status} notification "
                f"to user {event.user_id}"
            )
        except Exception as e:
            logger.error(
                f"Error handling venue manager request processed event: {e}",
                exc_info=True,
            )

    # Match domain notification handlers

    @staticmethod
    def handle_match_proposal_created(event: MatchProposalCreatedEvent) -> None:
        """Handle match proposal created by notifying the target user."""
        if not event.target_user_id:
            # Public proposal, no specific target to notify
            return

        destinatario = event.target_user_id

        def message() -> str:
            dove = (
                " " + _("presso %(luogo)s", luogo=event.location_name)
                if event.location_name
                else ""
            )
            quando = (
                " "
                + _(
                    "il %(quando)s",
                    quando=data_ora_per(destinatario, event.scheduled_time),
                )
                if event.scheduled_time
                else ""
            )
            testo = _(
                "%(proposer)s ti ha proposto una partita%(dove)s%(quando)s.",
                proposer=event.proposer_name,
                dove=dove,
                quando=quando,
            )
            if event.notes:
                testo += " " + _("Note: %(note)s", note=event.notes)
            return testo

        try:
            NotificationService.create_notification(
                user_id=destinatario,
                notification_type=NotificationType.MATCH_PROPOSAL,
                title=_l("Nuova Proposta di Partita"),
                message=message,
                priority=NotificationPriority.NORMAL,
                related_entities={
                    "proposal_id": event.proposal_id,
                    "proposer_id": event.proposer_id,
                    "proposer_name": event.proposer_name,
                    "location_id": event.location_id,
                    "location_name": event.location_name,
                },
                action_url=f"/player/proposals/{event.proposal_id}",
                action_text=_l("Visualizza Proposta"),
            )
            logger.info(f"Sent match proposal notification to user {destinatario}")
        except Exception as e:
            logger.error(
                f"Error handling match proposal created event: {e}", exc_info=True
            )

    @staticmethod
    def handle_match_accepted(event: MatchAcceptedEvent) -> None:
        """Handle match accepted by notifying the proposer."""
        destinatario = event.proposer_id

        def message() -> str:
            dove = (
                " " + _("presso %(luogo)s", luogo=event.location_name)
                if event.location_name
                else ""
            )
            quando = (
                " "
                + _(
                    "per il %(quando)s",
                    quando=data_ora_per(destinatario, event.scheduled_time),
                )
                if event.scheduled_time
                else ""
            )
            return _(
                "%(accepter)s ha accettato la tua proposta di partita"
                "%(dove)s%(quando)s.",
                accepter=event.accepter_name,
                dove=dove,
                quando=quando,
            )

        try:
            NotificationService.create_notification(
                user_id=destinatario,
                notification_type=NotificationType.MATCH_ACCEPTED,
                title=_l("Proposta di Partita Accettata!"),
                message=message,
                priority=NotificationPriority.NORMAL,
                related_entities={
                    "proposal_id": event.proposal_id,
                    "match_id": event.match_id,
                    "accepter_id": event.accepter_id,
                    "accepter_name": event.accepter_name,
                    "location_id": event.location_id,
                    "location_name": event.location_name,
                },
                action_url=f"/player/matches/{event.match_id}",
                action_text=_l("Visualizza Partita"),
            )
            logger.info(f"Sent match accepted notification to user {destinatario}")
        except Exception as e:
            logger.error(f"Error handling match accepted event: {e}", exc_info=True)

    # Competition domain notification handlers

    @staticmethod
    def handle_competition_registration_opened(
        event: CompetitionRegistrationOpenedEvent,
    ) -> None:
        """Handle competition registration opened by notifying eligible users."""
        if not event.eligible_user_ids:
            # No specific users to notify
            return

        try:
            # Notify eligible users: un messaggio per ciascuno, nella sua lingua
            # e con gli orari nel suo fuso.
            for user_id in event.eligible_user_ids:
                NotificationService.create_notification(
                    user_id=user_id,
                    notification_type=NotificationType.TOURNAMENT_REGISTRATION,
                    title=_l("Iscrizioni Aperte"),
                    message=lambda uid=user_id: _iscrizioni_aperte(event, uid),
                    priority=NotificationPriority.NORMAL,
                    related_entities={
                        "gara_id": event.gara_id,
                        "name": event.name,
                        "location_id": event.location_id,
                        "location_name": event.location_name,
                    },
                    action_url=f"/gara/{event.gara_id}",
                    action_text=_l("Iscriviti Ora"),
                )
            logger.info(
                f"Sent competition registration notifications for gara {event.gara_id}"
            )
        except Exception as e:
            logger.error(
                f"Error handling competition registration opened event: {e}",
                exc_info=True,
            )

    # Competition domain notification handlers (continued)

    @staticmethod
    def handle_director_assignment_added(event: DirectorAssignmentAddedEvent) -> None:
        """Handle director assignment added by notifying the director."""
        try:
            # Due frasi e non un'etichetta inserita: «della gara», ma «del
            # campionato». Prima usciva «della campionato».
            if event.entity_type == "gara":
                message = _l(
                    "Sei stato nominato co-direttore della gara '%(nome)s'",
                    nome=event.entity_name,
                )
                # Co-directors have admin access, so link to admin routes
                action_url = f"/admin/gara/{event.entity_id}"
                action_text = _l("Gestisci Gara")
            else:
                message = _l(
                    "Sei stato nominato co-direttore del campionato '%(nome)s'",
                    nome=event.entity_name,
                )
                action_url = f"/admin/campionato/{event.entity_id}"
                action_text = _l("Gestisci Campionato")

            NotificationService.create_notification(
                user_id=event.user_id,
                notification_type=NotificationType.ACCOUNT_UPDATE,
                title=_l("Nominato co-direttore"),
                message=message,
                priority=NotificationPriority.NORMAL,
                related_entities={
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "entity_name": event.entity_name,
                    "assigned_by_id": event.assigned_by_id,
                },
                action_url=action_url,
                action_text=action_text,
            )
            logger.info(
                f"Sent director assignment added notification "
                f"to user {event.user_id}"
            )
        except Exception as e:
            logger.error(
                f"Error handling director assignment added event: {e}", exc_info=True
            )

    @staticmethod
    def handle_director_assignment_removed(
        event: DirectorAssignmentRemovedEvent,
    ) -> None:
        """Handle director assignment removed by notifying the director."""
        try:
            if event.entity_type == "gara":
                message = _l(
                    "Sei stato rimosso dal ruolo di co-direttore della gara '%(nome)s'",
                    nome=event.entity_name,
                )
                # Link to public view since user no longer has admin access
                action_url = f"/gara/{event.entity_id}"
                action_text = _l("Visualizza Gara")
            else:
                message = _l(
                    "Sei stato rimosso dal ruolo di co-direttore del campionato "
                    "'%(nome)s'",
                    nome=event.entity_name,
                )
                action_url = f"/campionato/{event.entity_id}"
                action_text = _l("Visualizza Campionato")

            NotificationService.create_notification(
                user_id=event.user_id,
                notification_type=NotificationType.ACCOUNT_UPDATE,
                title=_l("Rimosso da co-direttore"),
                message=message,
                priority=NotificationPriority.NORMAL,
                related_entities={
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "entity_name": event.entity_name,
                    "removed_by_id": event.removed_by_id,
                },
                action_url=action_url,
                action_text=action_text,
            )
            logger.info(
                f"Sent director assignment removed notification "
                f"to user {event.user_id}"
            )
        except Exception as e:
            logger.error(
                f"Error handling director assignment removed event: {e}", exc_info=True
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
                    title=_l("Giocatore Disponibile"),
                    message=event.notification_message,
                    priority=NotificationPriority.NORMAL,
                    related_entities=event.notification_context,
                    action_url=f"/player/availability/{event.location_id}",
                    action_text=_l("Visualizza Disponibilità"),
                )
            logger.info(
                f"Sent availability notifications for location {event.location_id}"
            )
        except Exception as e:
            logger.error(
                f"Error handling availability notification event: {e}", exc_info=True
            )


# Auto-register handlers when module is imported
NotificationEventHandlers.register_all_handlers()
