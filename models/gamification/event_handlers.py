"""
Gamification Event Handlers - Automatic XP Awards and Streak Tracking

Event handlers that listen to domain events and award XP automatically.
This decouples gamification from other domains - no direct dependencies.

Handlers for:
- Match completion (winner/loser XP + weekly match streak)
- Tournament inscription (participation XP + weekly tournament streak)
- Tournament completion (completion + podium + winner bonuses)
- Challenge (drill) completion (training XP + weekly drill streak)

All handlers use LevelService.award_xp() which emits LevelUpEvent if applicable.
Streak tracking uses StreakService.record_activity() for weekly streaks.
"""

from __future__ import annotations
import logging
from typing import Optional

from models.events.base import EventBus
from models.events.match_events import MatchCompletedEvent
from models.events.competition_events import (
    InscriptionCreatedEvent,
    CompetitionCompletedEvent,
    CompetitionCreatedEvent,
    CampionatoCreatedEvent,
)
from models.gamification.level_service import LevelService
from models.gamification.achievement_service import AchievementService
from models.gamification.streak_service import StreakService
from models.gamification.quest_service import QuestService
from models.gamification.xp_config import XP_RATES
from models.gamification.models import XPTransactionType, StreakType

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
            priority=10,
        )

        # Competition domain handlers
        EventBus.register_handler(
            InscriptionCreatedEvent,
            GamificationEventHandlers.handle_inscription_for_xp,
            priority=10,
        )
        EventBus.register_handler(
            CompetitionCompletedEvent,
            GamificationEventHandlers.handle_competition_completed_for_xp,
            priority=10,
        )
        EventBus.register_handler(
            CompetitionCreatedEvent,
            GamificationEventHandlers.handle_competition_created_for_xp,
            priority=10,
        )
        EventBus.register_handler(
            CampionatoCreatedEvent,
            GamificationEventHandlers.handle_campionato_created_for_xp,
            priority=10,
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

        Walkover handling: a match completed with no racks played (2-player forfeit,
        trio 2/3 or 3/3 walkover) grants no XP/quest/streak/achievement side effects
        to any player in the gara's forfeit set — the nominal 3/3 winner included.

        Error handling policy:
        - Walkover detection (match lookup + forfeit set) runs OUTSIDE the
          broad except: a failure here would leave `forfeit_ids` empty and
          silently route XP to forfeiters, so we let EventBus catch and
          report the error.
        - Each AchievementService call is isolated: a single achievement
          failure must not block the remaining three nor the streak/quest
          side effects that follow.

        Args:
            event: MatchCompletedEvent with match_id, winner_id, player1_id, player2_id
        """
        if not event.winner_id:
            logger.warning(
                f"Match {event.match_id} completed without winner - no XP awarded"
            )
            return

        # Walkover detection: load match and gather forfeit set once.
        # Intentionally outside the broad try/except below — see docstring.
        from models.match.models import Match
        from models.base import db as _db

        match = _db.session.get(Match, event.match_id)
        forfeit_ids: set[int] = set()
        if match is not None and match.is_walkover and match.gara_id:
            from models.competition.withdraw_policy_service import (
                WithdrawPolicyService,
            )

            forfeit_ids = WithdrawPolicyService.get_forfeit_user_ids(match.gara_id)

        try:
            # Determine loser
            loser_id: Optional[int] = None
            if event.player1_id and event.player2_id:
                loser_id = (
                    event.player2_id
                    if event.player1_id == event.winner_id
                    else event.player1_id
                )

            # Award winner XP (skip if winner is a forfeit — covers trio 3/3 walkover)
            if event.winner_id not in forfeit_ids:
                LevelService.award_xp(
                    user_id=event.winner_id,
                    xp_amount=XP_RATES[XPTransactionType.MATCH_WIN],
                    transaction_type=XPTransactionType.MATCH_WIN,
                    reason=f"Won match {event.match_id}",
                    related_entities={"match_id": event.match_id},
                )
                logger.info(
                    f"Awarded {XP_RATES[XPTransactionType.MATCH_WIN]} XP to user {event.winner_id} for match win"
                )

            # Award loser participation XP (skip if loser is a forfeit)
            if loser_id and loser_id not in forfeit_ids:
                LevelService.award_xp(
                    user_id=loser_id,
                    xp_amount=XP_RATES[XPTransactionType.MATCH_LOSS],
                    transaction_type=XPTransactionType.MATCH_LOSS,
                    reason=f"Participated in match {event.match_id}",
                    related_entities={"match_id": event.match_id},
                )
                logger.info(
                    f"Awarded {XP_RATES[XPTransactionType.MATCH_LOSS]} XP to user {loser_id} for match participation"
                )

            # Win-based achievements for winner (skip if winner is a forfeit).
            # Each call isolated: failure in one must not block the others.
            # L'idoneità è metric-driven (won_matches reali), quindi basta
            # richiedere la rivalutazione — niente increment manuale.
            if event.winner_id not in forfeit_ids:
                for code in (
                    "first_blood",
                    "veteran_player",
                    "century_club",
                    "match_marathon",
                ):
                    try:
                        AchievementService.check_and_award_achievement(
                            event.winner_id, code
                        )
                    except Exception as ach_error:
                        logger.warning(
                            f"Error checking achievement '{code}' for user {event.winner_id}: {ach_error}"
                        )

            # Iterate the full participant roster so trio p3 is not skipped.
            all_player_ids = event.get_all_player_ids()

            # Opponent-based achievements for ALL participants (skip forfeiters):
            # aver giocato questa partita può aver aumentato gli avversari unici.
            for player_id in all_player_ids:
                if player_id and player_id not in forfeit_ids:
                    for code in ("diverse_competitor", "community_pillar"):
                        try:
                            AchievementService.check_and_award_achievement(
                                player_id, code
                            )
                        except Exception as ach_error:
                            logger.warning(
                                f"Error checking achievement '{code}' for user {player_id}: {ach_error}"
                            )

            # Record weekly streaks for all participants (skip forfeiters)
            # WEEKLY_MATCH: At least 1 match per week
            # WEEKLY_ACTIVITY: Any activity per week
            for player_id in all_player_ids:
                if player_id and player_id not in forfeit_ids:
                    try:
                        StreakService.record_activity(
                            user_id=player_id, streak_type=StreakType.WEEKLY_MATCH
                        )
                        StreakService.record_activity(
                            user_id=player_id, streak_type=StreakType.WEEKLY_ACTIVITY
                        )
                    except Exception as streak_error:
                        logger.warning(
                            f"Error recording streak for user {player_id}: {streak_error}"
                        )

            # Update quest progress for all participants (skip forfeiters)
            # "matches_played": Any match completed
            # "matches_won": Match won (winner only)
            for player_id in all_player_ids:
                if player_id and player_id not in forfeit_ids:
                    try:
                        QuestService.record_activity_for_quests(
                            user_id=player_id,
                            activity_type="matches_played",
                            activity_count=1,
                        )
                    except Exception as quest_error:
                        logger.warning(
                            f"Error updating quest progress for user {player_id}: {quest_error}"
                        )

            # Winner gets "matches_won" quest progress (skip if winner is a forfeit)
            if event.winner_id and event.winner_id not in forfeit_ids:
                try:
                    QuestService.record_activity_for_quests(
                        user_id=event.winner_id,
                        activity_type="matches_won",
                        activity_count=1,
                    )
                except Exception as quest_error:
                    logger.warning(
                        f"Error updating matches_won quest for user {event.winner_id}: {quest_error}"
                    )

        except Exception as e:
            logger.error(
                f"Error handling match completed event for XP: {e}", exc_info=True
            )

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
                related_entities={"gara_id": event.gara_id},
            )
            logger.info(
                f"Awarded {XP_RATES[XPTransactionType.TOURNAMENT_INSCRIPTION]} XP to user {event.user_id} for tournament inscription"
            )

            # Check tournament participation achievements (metric-driven)
            AchievementService.check_and_award_achievement(
                event.user_id, "tournament_debut"
            )
            AchievementService.check_and_award_achievement(
                event.user_id, "tournament_regular"
            )

            # Record weekly streaks
            # WEEKLY_TOURNAMENT: At least 1 tournament registration per week
            # WEEKLY_ACTIVITY: Any activity per week
            try:
                StreakService.record_activity(
                    user_id=event.user_id, streak_type=StreakType.WEEKLY_TOURNAMENT
                )
                StreakService.record_activity(
                    user_id=event.user_id, streak_type=StreakType.WEEKLY_ACTIVITY
                )
            except Exception as streak_error:
                logger.warning(
                    f"Error recording streak for user {event.user_id}: {streak_error}"
                )

            # Update quest progress for tournament registration
            try:
                QuestService.record_activity_for_quests(
                    user_id=event.user_id,
                    activity_type="tournaments_registered",
                    activity_count=1,
                )
            except Exception as quest_error:
                logger.warning(
                    f"Error updating quest progress for user {event.user_id}: {quest_error}"
                )

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
            event: CompetitionCompletedEvent with gara_id, winner_id, final_standings
        """
        try:
            # Extract participant IDs from final_standings
            participant_ids = []
            if event.final_standings:
                participant_ids = [
                    s.get("user_id")
                    for s in event.final_standings
                    if s.get("user_id") is not None
                ]

            # Award all participants completion XP
            for participant_id in participant_ids:
                LevelService.award_xp(
                    user_id=participant_id,
                    xp_amount=XP_RATES[XPTransactionType.TOURNAMENT_COMPLETION],
                    transaction_type=XPTransactionType.TOURNAMENT_COMPLETION,
                    reason=f"Completed tournament {event.gara_id}",
                    related_entities={"gara_id": event.gara_id},
                )

            logger.info(
                f"Awarded {XP_RATES[XPTransactionType.TOURNAMENT_COMPLETION]} XP "
                f"to {len(participant_ids)} participants for tournament {event.gara_id} completion"
            )

            # Bonus for winner
            if event.winner_id:
                LevelService.award_xp(
                    user_id=event.winner_id,
                    xp_amount=XP_RATES[XPTransactionType.TOURNAMENT_WIN],
                    transaction_type=XPTransactionType.TOURNAMENT_WIN,
                    reason=f"Won tournament {event.gara_id}",
                    related_entities={"gara_id": event.gara_id, "position": 1},
                )
                logger.info(
                    f"Awarded {XP_RATES[XPTransactionType.TOURNAMENT_WIN]} XP to winner {event.winner_id}"
                )

            # Bonus for podium (top 3, excluding winner who already got bonus)
            if event.final_standings and len(event.final_standings) >= 2:
                # Get top 3 (positions 1, 2, 3)
                podium = [
                    s
                    for s in event.final_standings[:3]
                    if s.get("user_id") != event.winner_id
                ]

                for standing in podium:
                    user_id = standing.get("user_id")
                    position = standing.get("position")

                    if user_id:
                        LevelService.award_xp(
                            user_id=user_id,
                            xp_amount=XP_RATES[XPTransactionType.TOURNAMENT_PODIUM],
                            transaction_type=XPTransactionType.TOURNAMENT_PODIUM,
                            reason=f"Finished {position} in tournament {event.gara_id}",
                            related_entities={
                                "gara_id": event.gara_id,
                                "position": position,
                            },
                        )

                logger.info(f"Awarded podium bonuses to {len(podium)} players")

            # Check tournament completion achievements
            for participant_id in participant_ids:
                # Everyone who completes gets checked (they all finished the tournament)
                # Check "Aspirante Direttore" achievement (director eligibility)
                # This requires 10+ completed gare OR 1+ complete campionato
                try:
                    AchievementService.check_and_award_achievement(
                        participant_id, "aspiring_director"
                    )
                except Exception as ach_error:
                    logger.warning(
                        f"Error checking aspiring_director achievement for user {participant_id}: {ach_error}"
                    )

            # Check winner achievement
            if event.winner_id:
                AchievementService.check_and_award_achievement(
                    event.winner_id, "champion"
                )
                AchievementService.check_and_award_achievement(
                    event.winner_id, "tournament_dominator"
                )

            # Check podium achievements (top 3)
            if event.final_standings and len(event.final_standings) >= 3:
                for standing in event.final_standings[:3]:
                    user_id = standing.get("user_id")
                    if user_id:
                        AchievementService.check_and_award_achievement(
                            user_id, "podium_finish"
                        )

            # Update quest progress for all participants
            # "tournaments_completed": Finished a tournament
            for participant_id in participant_ids:
                try:
                    QuestService.record_activity_for_quests(
                        user_id=participant_id,
                        activity_type="tournaments_completed",
                        activity_count=1,
                    )
                except Exception as quest_error:
                    logger.warning(
                        f"Error updating quest progress for user {participant_id}: {quest_error}"
                    )

        except Exception as e:
            logger.error(
                f"Error handling competition completed event for XP: {e}", exc_info=True
            )

    @staticmethod
    def handle_competition_created_for_xp(event: CompetitionCreatedEvent) -> None:
        """Award XP for creating a competition (Gara)."""
        try:
            LevelService.award_xp(
                user_id=event.creator_id,
                xp_amount=XP_RATES[XPTransactionType.GARA_CREATION],
                transaction_type=XPTransactionType.GARA_CREATION,
                reason=f"Created competition {event.name}",
                related_entities={"gara_id": event.gara_id},
            )
            logger.info(
                f"Awarded {XP_RATES[XPTransactionType.GARA_CREATION]} XP to user {event.creator_id} for creating Gara"
            )
        except Exception as e:
            logger.error(
                f"Error handling competition created event for XP: {e}", exc_info=True
            )

    @staticmethod
    def handle_campionato_created_for_xp(event: CampionatoCreatedEvent) -> None:
        """Award XP for creating a Campionato."""
        try:
            LevelService.award_xp(
                user_id=event.creator_id,
                xp_amount=XP_RATES[XPTransactionType.CAMPIONATO_CREATION],
                transaction_type=XPTransactionType.CAMPIONATO_CREATION,
                reason=f"Created campionato {event.name}",
                related_entities={"campionato_id": event.campionato_id},
            )
            logger.info(
                f"Awarded {XP_RATES[XPTransactionType.CAMPIONATO_CREATION]} XP to user {event.creator_id} for creating Campionato"
            )
        except Exception as e:
            logger.error(
                f"Error handling campionato created event for XP: {e}", exc_info=True
            )


# Auto-register handlers when module is imported
GamificationEventHandlers.register_all_handlers()
