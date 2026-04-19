"""
Event Handlers for Rating System.
Listens to domain events to trigger rating updates.
"""

from models.events import MatchCompletedEvent
from models.rating.calculation_service import RatingCalculationService
from models.base import db
import logging

logger = logging.getLogger(__name__)


class RatingEventHandlers:
    """Handlers for rating-related events."""

    @staticmethod
    def handle_match_completed(event: MatchCompletedEvent) -> None:
        """
        Triggered when a match is completed.
        Calculates and updates Elo ratings for the players involved.

        Walkover matches (no racks played) do not trigger a rating update — an
        Elo delta from a forfeit would punish skill blindly and distort the
        rating signal.
        """
        from models.match.models import Match

        match = db.session.get(Match, event.match_id)
        if not match:
            logger.warning(f"Match {event.match_id} not found for rating update")
            return

        if match.is_walkover:
            logger.info(f"Skipping rating update for walkover match {match.id}")
            return

        logger.info(f"Handling rating update for completed match {match.id}")

        try:
            RatingCalculationService.process_match_result(match)
        except Exception as e:
            logger.error(
                f"Error updating ratings for match {match.id}: {str(e)}", exc_info=True
            )
