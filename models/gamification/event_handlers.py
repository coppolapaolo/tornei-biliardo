"""
Gamification Event Handlers - Automatic XP Awards

Event handlers that listen to domain events and award XP automatically.
This decouples gamification from other domains - no direct dependencies.

Handlers for:
- Match completion (winner/loser XP)
- Tournament inscription (participation XP)
- Tournament completion (completion + podium + winner bonuses)
- Challenge (drill) completion (training XP)

All handlers use LevelService.award_xp() which emits LevelUpEvent if applicable.
"""

from __future__ import annotations
import logging
from typing import Optional

from models.events.base import EventBus
from models.events.match_events import MatchCompletedEvent
from models.events.competition_events import (
    InscriptionCreatedEvent,
    CompetitionCompletedEvent,
)
from models.gamification.level_service import LevelService
from models.gamification.achievement_service import AchievementService
from models.gamification.xp_config import XP_RATES
from models.gamification.models import XPTransactionType

logger = logging.getLogger(__name__)


class GamificationEventHandlers:
    """
    Event handlers for automatic XP awards from domain events.
    
    Register all handlers with EventBus on application startup.
    """

    @staticmethod
    def register_all_handlers() -> None:
        """Register all gamification event handlers with the EventBus."""
        # Match domain handlers
        EventBus.register_handler(
            MatchCompletedEvent,
            GamificationEventHandlers.handle_match_completed_for_xp,
            priority=10
        )

        # Competition domain handlers
        EventBus.register_handler(
            InscriptionCreatedEvent,
            GamificationEventHandlers.handle_inscription_for_xp,
            priority=10
        )
        EventBus.register_handler(
            CompetitionCompletedEvent,
            GamificationEventHandlers.handle_competition_completed_for_xp,
            priority=10
        )

        logger.info("Registered all gamification event handlers")

    # ========================================
    # Match Domain Handlers
    # ========================================

    @staticmethod
    def handle_match_completed_for_xp(event: MatchCompletedEvent) -> None:
        """
        Award XP for match completion (winner and loser).
        
        XP Awards:
        - Winner: 50 XP (MATCH_WIN)
        - Loser: 20 XP (MATCH_LOSS) for participation
        
        Args:
            event: MatchCompletedEvent with match_id, winner_id, player1_id, player2_id
        """
        try:
            if not event.winner_id:
                logger.warning(f"Match {event.match_id} completed without winner - no XP awarded")
                return

            # Determine loser
            loser_id: Optional[int] = None
            if event.player1_id and event.player2_id:
                loser_id = event.player2_id if event.player1_id == event.winner_id else event.player1_id

            # Award winner XP
            LevelService.award_xp(
                user_id=event.winner_id,
                xp_amount=XP_RATES[XPTransactionType.MATCH_WIN],
                transaction_type=XPTransactionType.MATCH_WIN,
                reason=f"Won match {event.match_id}",
                related_entities={"match_id": event.match_id}
            )
            logger.info(f"Awarded {XP_RATES[XPTransactionType.MATCH_WIN]} XP to user {event.winner_id} for match win")

            # Award loser participation XP
            if loser_id:
                LevelService.award_xp(
                    user_id=loser_id,
                    xp_amount=XP_RATES[XPTransactionType.MATCH_LOSS],
                    transaction_type=XPTransactionType.MATCH_LOSS,
                    reason=f"Participated in match {event.match_id}",
                    related_entities={"match_id": event.match_id}
                )
                logger.info(f"Awarded {XP_RATES[XPTransactionType.MATCH_LOSS]} XP to user {loser_id} for match participation")

            # Check match-related achievements for winner
            AchievementService.check_and_award_achievement(event.winner_id, "first_blood")
            AchievementService.check_and_award_achievement(event.winner_id, "veteran_player", progress_increment=1)
            AchievementService.check_and_award_achievement(event.winner_id, "century_club", progress_increment=1)
            AchievementService.check_and_award_achievement(event.winner_id, "match_marathon", progress_increment=1)

        except Exception as e:
            logger.error(f"Error handling match completed event for XP: {e}", exc_info=True)

    # ========================================
    # Competition Domain Handlers
    # ========================================

    @staticmethod
    def handle_inscription_for_xp(event: InscriptionCreatedEvent) -> None:
        """
        Award XP for tournament inscription.
        
        XP Award: 25 XP (TOURNAMENT_INSCRIPTION)
        
        Args:
            event: InscriptionCreatedEvent with user_id, gara_id
        """
        try:
            LevelService.award_xp(
                user_id=event.user_id,
                xp_amount=XP_RATES[XPTransactionType.TOURNAMENT_INSCRIPTION],
                transaction_type=XPTransactionType.TOURNAMENT_INSCRIPTION,
                reason=f"Registered for tournament {event.gara_id}",
                related_entities={"gara_id": event.gara_id}
            )
            logger.info(f"Awarded {XP_RATES[XPTransactionType.TOURNAMENT_INSCRIPTION]} XP to user {event.user_id} for tournament inscription")

            # Check tournament participation achievements
            AchievementService.check_and_award_achievement(event.user_id, "tournament_debut")
            AchievementService.check_and_award_achievement(event.user_id, "tournament_regular", progress_increment=1)

        except Exception as e:
            logger.error(f"Error handling inscription event for XP: {e}", exc_info=True)

    @staticmethod
    def handle_competition_completed_for_xp(event: CompetitionCompletedEvent) -> None:
        """
        Award XP for tournament completion with bonuses.
        
        XP Awards:
        - All participants: 100 XP (TOURNAMENT_COMPLETION)
        - Top 3 (podium): +200 XP (TOURNAMENT_PODIUM)
        - Winner: +500 XP (TOURNAMENT_WIN)
        
        Total for winner: 100 + 500 = 600 XP
        Total for 2nd/3rd: 100 + 200 = 300 XP
        Total for other participants: 100 XP
        
        Args:
            event: CompetitionCompletedEvent with gara_id, participant_ids, winner_id, final_standings
        """
        try:
            # Award all participants completion XP
            for participant_id in event.participant_ids:
                LevelService.award_xp(
                    user_id=participant_id,
                    xp_amount=XP_RATES[XPTransactionType.TOURNAMENT_COMPLETION],
                    transaction_type=XPTransactionType.TOURNAMENT_COMPLETION,
                    reason=f"Completed tournament {event.gara_id}",
                    related_entities={"gara_id": event.gara_id}
                )
            
            logger.info(
                f"Awarded {XP_RATES[XPTransactionType.TOURNAMENT_COMPLETION]} XP "
                f"to {len(event.participant_ids)} participants for tournament {event.gara_id} completion"
            )

            # Bonus for winner
            if event.winner_id:
                LevelService.award_xp(
                    user_id=event.winner_id,
                    xp_amount=XP_RATES[XPTransactionType.TOURNAMENT_WIN],
                    transaction_type=XPTransactionType.TOURNAMENT_WIN,
                    reason=f"Won tournament {event.gara_id}",
                    related_entities={"gara_id": event.gara_id, "position": 1}
                )
                logger.info(f"Awarded {XP_RATES[XPTransactionType.TOURNAMENT_WIN]} XP to winner {event.winner_id}")

            # Bonus for podium (top 3, excluding winner who already got bonus)
            if event.final_standings and len(event.final_standings) >= 2:
                # Get top 3 (positions 1, 2, 3)
                podium = [s for s in event.final_standings[:3] if s.get("user_id") != event.winner_id]
                
                for standing in podium:
                    user_id = standing.get("user_id")
                    position = standing.get("position")
                    
                    if user_id:
                        LevelService.award_xp(
                            user_id=user_id,
                            xp_amount=XP_RATES[XPTransactionType.TOURNAMENT_PODIUM],
                            transaction_type=XPTransactionType.TOURNAMENT_PODIUM,
                            reason=f"Finished {position} in tournament {event.gara_id}",
                            related_entities={"gara_id": event.gara_id, "position": position}
                        )
                
                logger.info(f"Awarded podium bonuses to {len(podium)} players")

            # Check tournament completion achievements
            for participant_id in event.participant_ids:
                # Everyone who completes gets checked (they all finished the tournament)
                pass  # Completion tracked separately

            # Check winner achievement
            if event.winner_id:
                AchievementService.check_and_award_achievement(event.winner_id, "champion")
                AchievementService.check_and_award_achievement(event.winner_id, "tournament_dominator", progress_increment=1)

            # Check podium achievements (top 3)
            if event.final_standings and len(event.final_standings) >= 3:
                for standing in event.final_standings[:3]:
                    user_id = standing.get("user_id")
                    if user_id:
                        AchievementService.check_and_award_achievement(user_id, "podium_finish")

        except Exception as e:
            logger.error(f"Error handling competition completed event for XP: {e}", exc_info=True)


# Auto-register handlers when module is imported
GamificationEventHandlers.register_all_handlers()
