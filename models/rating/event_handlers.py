"""
Event Handlers for Rating System.
Listens to domain events to trigger rating updates.
"""
from models.events import MatchCompletedEvent
from models.rating.calculation_service import RatingCalculationService
import logging

logger = logging.getLogger(__name__)

class RatingEventHandlers:
    """Handlers for rating-related events."""

    @staticmethod
    def handle_match_completed(event: MatchCompletedEvent) -> None:
        """
        Triggered when a match is completed.
        Calculates and updates Elo ratings for the players involved.
        """
        match = event.match
        logger.info(f"Handling rating update for completed match {match.id}")
        
        try:
            RatingCalculationService.process_match_result(match)
        except Exception as e:
            logger.error(f"Error updating ratings for match {match.id}: {str(e)}", exc_info=True)
