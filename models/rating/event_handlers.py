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

        Nelle gare con handicap l'aggiornamento dipende dalle categorie: fra
        due giocatori della **stessa** categoria l'handicap non è in gioco e
        il risultato riflette la forza, quindi l'ELO si aggiorna; fra
        categorie diverse — o quando manca — no. La regola sta tutta in
        ``RatingEligibility``, mai duplicata qui (ADR-049).
        """
        from models.match.models import Match
        from .eligibility import RatingEligibility

        match = db.session.get(Match, event.match_id)
        if not match:
            logger.warning(f"Match {event.match_id} not found for rating update")
            return

        motivo = RatingEligibility.exclusion_reason(match)
        if motivo is not None:
            logger.info(
                f"Skipping rating update for match {match.id} — "
                f"{motivo.description}"
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
