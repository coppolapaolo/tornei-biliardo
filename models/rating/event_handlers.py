"""
Event Handlers for Rating System.
Listens to domain events to trigger rating updates.
"""

from models.events import MatchCompletedEvent, MatchReopenedEvent
from models.events.match_events import IndividualMatchCompletedEvent
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

        Handicap matches (effective_has_handicap, ereditato da gara/campionato)
        non aggiornano i rating (né Elo né, in futuro, Fargo): il risultato è
        falsato dall'handicap e non riflette la skill.
        """
        from models.match.models import Match

        match = db.session.get(Match, event.match_id)
        if not match:
            logger.warning(f"Match {event.match_id} not found for rating update")
            return

        if match.is_walkover:
            logger.info(f"Skipping rating update for walkover match {match.id}")
            return

        if match.effective_has_handicap:
            logger.info(
                f"Skipping rating update for handicap match {match.id} "
                f"(effective_has_handicap)"
            )
            return

        logger.info(f"Handling rating update for completed match {match.id}")

        try:
            RatingCalculationService.process_match_result(match)
        except Exception as e:
            logger.error(
                f"Error updating ratings for match {match.id}: {str(e)}", exc_info=True
            )

    @staticmethod
    def handle_individual_match_completed(
        event: IndividualMatchCompletedEvent,
    ) -> None:
        """Match individuale/casual VALIDATO → aggiorna SOLO il pool ELO_GLOBAL.

        Il casual non tocca l'ELO competitivo. Niente walkover/handicap qui: il
        forfait non emette questo evento (solo VALIDATED). I pareggi (winner_id
        None) non aggiornano il rating.
        """
        from models.individual_match.models import IndividualMatch

        im = db.session.get(IndividualMatch, event.match_id)
        if not im:
            logger.warning(
                f"IndividualMatch {event.match_id} not found for rating update"
            )
            return

        if not im.winner_id:
            logger.info(f"Skipping ELO_GLOBAL for casual {im.id} without winner (tie)")
            return

        try:
            RatingCalculationService.process_individual_match_result(im)
        except Exception as e:
            logger.error(
                f"Error updating ELO_GLOBAL for casual {im.id}: {str(e)}",
                exc_info=True,
            )

    @staticmethod
    def handle_match_reopened(event: MatchReopenedEvent) -> None:
        """
        Triggered when a completed match is reopened/reset.

        Annulla i delta Elo applicati per quel match (revert), così che il
        ricalcolo successivo (alla ricompletazione) riparta da uno stato
        coerente. No-op se non c'è history da annullare.
        """
        from models.match.models import Match

        match = db.session.get(Match, event.match_id)
        if not match:
            logger.warning(f"Match {event.match_id} not found for rating revert")
            return

        try:
            RatingCalculationService.revert_match_result(match)
        except Exception as e:
            logger.error(
                f"Error reverting ratings for match {match.id}: {str(e)}",
                exc_info=True,
            )
