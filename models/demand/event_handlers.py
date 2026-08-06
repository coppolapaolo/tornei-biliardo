"""Event handler del segnale-domanda (ADR-036).

Chiude il loop domanda→offerta: quando un director apre una gara con una sala
dotata di coordinate, consuma i segnali di domanda attivi nella zona e notifica
i giocatori. Decoupled via EventBus (errori isolati per-handler).
"""

from __future__ import annotations

import logging

from models.events.base import EventBus
from models.events.competition_events import CompetitionCreatedEvent

logger = logging.getLogger(__name__)


class DemandSignalEventHandlers:
    """Registra gli handler del dominio demand con l'EventBus."""

    @staticmethod
    def register_all_handlers() -> None:
        EventBus.register_handler(
            CompetitionCreatedEvent,
            DemandSignalEventHandlers.handle_gara_created_consume_signals,
        )

    @staticmethod
    def handle_gara_created_consume_signals(event: CompetitionCreatedEvent) -> None:
        """Consuma i segnali vicini alla sala della gara appena creata."""
        if not event.location_id:
            return

        from models.base import db
        from models.location.models import BilliardHall
        from models.demand.service import DemandSignalService

        venue = db.session.get(BilliardHall, event.location_id)
        if not venue or venue.latitude is None or venue.longitude is None:
            # Senza coordinate sala non c'è prossimità: niente da consumare.
            return

        consumed = DemandSignalService.consume_signals_for_gara(
            gara_id=event.gara_id,
            venue_lat=venue.latitude,
            venue_lng=venue.longitude,
        )
        if consumed:
            logger.info(
                "Demand: consumati %s segnali per la gara %s",
                consumed,
                event.gara_id,
            )


# Auto-registrazione all'import del modulo (cfr. gamification).
DemandSignalEventHandlers.register_all_handlers()
