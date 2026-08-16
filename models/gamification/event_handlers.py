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
from models.events.match_events import (
    MatchCompletedEvent,
    IndividualMatchCompletedEvent,
)
from models.events.competition_events import (
    InscriptionCreatedEvent,
    CompetitionCompletedEvent,
    CompetitionCreatedEvent,
    CampionatoCreatedEvent,
)
from models.challenge.events import ChallengeAttemptCompletedEvent
from models.exam.events import ExamAttemptCompletedEvent
from models.gamification.level_service import LevelService
from models.gamification.achievement_service import AchievementService
from models.gamification.streak_service import StreakService
from models.gamification.quest_service import QuestService
from models.gamification.config_service import (
    GamificationConfigService as ConfigService,
)
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
        EventBus.register_handler(
            IndividualMatchCompletedEvent,
            GamificationEventHandlers.handle_individual_match_completed_for_xp,
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

        # Drill (catalogo e gara)
        EventBus.register_handler(
            ChallengeAttemptCompletedEvent,
            GamificationEventHandlers.handle_challenge_attempt_completed_for_xp,
            priority=10,
        )

        # Esame (ADR-042)
        EventBus.register_handler(
            ExamAttemptCompletedEvent,
            GamificationEventHandlers.handle_exam_attempt_completed_for_xp,
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
                win_xp = ConfigService.get_xp_rate(XPTransactionType.MATCH_WIN)
                LevelService.award_xp(
                    user_id=event.winner_id,
                    xp_amount=win_xp,
                    transaction_type=XPTransactionType.MATCH_WIN,
                    reason=f"Won match {event.match_id}",
                    related_entities={"match_id": event.match_id},
                )
                logger.info(
                    f"Awarded {win_xp} XP to user {event.winner_id} for match win"
                )

            # Award loser participation XP (skip if loser is a forfeit)
            if loser_id and loser_id not in forfeit_ids:
                loss_xp = ConfigService.get_xp_rate(XPTransactionType.MATCH_LOSS)
                LevelService.award_xp(
                    user_id=loser_id,
                    xp_amount=loss_xp,
                    transaction_type=XPTransactionType.MATCH_LOSS,
                    reason=f"Participated in match {event.match_id}",
                    related_entities={"match_id": event.match_id},
                )
                logger.info(
                    f"Awarded {loss_xp} XP to user {loser_id} for match participation"
                )

            # Iterate the full participant roster so trio p3 is not skipped.
            all_player_ids = event.get_all_player_ids()

            # Achievement: riconcilia ogni partecipante non forfait. Metric-driven
            # → un'unica chiamata copre vittorie (first_blood/veteran/...),
            # serie di vittorie e avversari unici. Isolata per-utente: un errore
            # non blocca gli altri né gli effetti collaterali sotto.
            for player_id in all_player_ids:
                if player_id and player_id not in forfeit_ids:
                    try:
                        AchievementService.reconcile_achievements(player_id)
                    except Exception as ach_error:
                        logger.warning(
                            f"Error reconciling achievements for user {player_id}: {ach_error}"
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
                            f"Error recording streak for user "
                            f"{player_id}: {streak_error}"
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
                            f"Error updating quest progress for user "
                            f"{player_id}: {quest_error}"
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
                        f"Error updating matches_won quest for user "
                        f"{event.winner_id}: {quest_error}"
                    )

        except Exception as e:
            logger.error(
                f"Error handling match completed event for XP: {e}", exc_info=True
            )

    @staticmethod
    def handle_individual_match_completed_for_xp(
        event: IndividualMatchCompletedEvent,
    ) -> None:
        """Award XP per un match individuale/casual VALIDATO.

        Versione "gated" di handle_match_completed_for_xp:
        - XP RIDOTTO (CASUAL_MATCH_WIN/LOSS, 20/5 vs 50/20 torneo).
        - Nessun walkover-lookup: l'evento è emesso SOLO alla validazione
          bilaterale (mai forfait), quindi non esistono forfeiters da escludere.
        - Streak/quest/achievement-vittorie identici al torneo: il rischio
          farming è mitigato dalla conferma bilaterale.

        Tie free-format (`winner_id=None`): nessun XP/achievement (coerente col
        torneo, che salta i match senza vincitore).

        Args:
            event: IndividualMatchCompletedEvent (sempre 1v1, senza gara).
        """
        if not event.winner_id:
            logger.info(
                f"Casual match {event.match_id} validato senza vincitore (pari) "
                f"- nessun XP assegnato"
            )
            return

        try:
            loser_id: Optional[int] = None
            if event.player1_id and event.player2_id:
                loser_id = (
                    event.player2_id
                    if event.player1_id == event.winner_id
                    else event.player1_id
                )

            # XP vincitore (ridotto)
            LevelService.award_xp(
                user_id=event.winner_id,
                xp_amount=ConfigService.get_xp_rate(XPTransactionType.CASUAL_MATCH_WIN),
                transaction_type=XPTransactionType.CASUAL_MATCH_WIN,
                reason=f"Won casual match {event.match_id}",
                related_entities={"individual_match_id": event.match_id},
            )

            # XP partecipazione perdente (ridotto)
            if loser_id:
                LevelService.award_xp(
                    user_id=loser_id,
                    xp_amount=ConfigService.get_xp_rate(
                        XPTransactionType.CASUAL_MATCH_LOSS
                    ),
                    transaction_type=XPTransactionType.CASUAL_MATCH_LOSS,
                    reason=f"Participated in casual match {event.match_id}",
                    related_entities={"individual_match_id": event.match_id},
                )

            # Achievement: riconcilia entrambi i giocatori. Metric-driven → una
            # sola chiamata copre vittorie, serie e avversari unici (come nel
            # torneo). Isolata per-utente: un errore non blocca gli altri.
            for player_id in (event.player1_id, event.player2_id):
                if player_id:
                    try:
                        AchievementService.reconcile_achievements(player_id)
                    except Exception as ach_error:
                        logger.warning(
                            f"Error reconciling achievements for user "
                            f"{player_id}: {ach_error}"
                        )

            # Streak settimanali per entrambi
            for player_id in (event.player1_id, event.player2_id):
                if player_id:
                    try:
                        StreakService.record_activity(
                            user_id=player_id, streak_type=StreakType.WEEKLY_MATCH
                        )
                        StreakService.record_activity(
                            user_id=player_id, streak_type=StreakType.WEEKLY_ACTIVITY
                        )
                    except Exception as streak_error:
                        logger.warning(
                            f"Error recording streak for user {player_id}: "
                            f"{streak_error}"
                        )

            # Quest progress per entrambi (matches_played) + vincitore (matches_won)
            for player_id in (event.player1_id, event.player2_id):
                if player_id:
                    try:
                        QuestService.record_activity_for_quests(
                            user_id=player_id,
                            activity_type="matches_played",
                            activity_count=1,
                        )
                    except Exception as quest_error:
                        logger.warning(
                            f"Error updating quest progress for user {player_id}: "
                            f"{quest_error}"
                        )
            try:
                QuestService.record_activity_for_quests(
                    user_id=event.winner_id,
                    activity_type="matches_won",
                    activity_count=1,
                )
            except Exception as quest_error:
                logger.warning(
                    f"Error updating matches_won quest for user "
                    f"{event.winner_id}: {quest_error}"
                )

        except Exception as e:
            logger.error(
                f"Error handling individual match completed event for XP: {e}",
                exc_info=True,
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
            inscription_xp = ConfigService.get_xp_rate(
                XPTransactionType.TOURNAMENT_INSCRIPTION
            )
            LevelService.award_xp(
                user_id=event.user_id,
                xp_amount=inscription_xp,
                transaction_type=XPTransactionType.TOURNAMENT_INSCRIPTION,
                reason=f"Registered for tournament {event.gara_id}",
                related_entities={"gara_id": event.gara_id},
            )
            logger.info(
                f"Awarded {inscription_xp} XP to user {event.user_id} for tournament inscription"
            )

            # Achievement: riconcilia (tournament_participation + strategie provate)
            try:
                AchievementService.reconcile_achievements(event.user_id)
            except Exception as ach_error:
                logger.warning(
                    f"Error reconciling achievements for user {event.user_id}: {ach_error}"
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
                    f"Error updating quest progress for user "
                    f"{event.user_id}: {quest_error}"
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
            completion_xp = ConfigService.get_xp_rate(
                XPTransactionType.TOURNAMENT_COMPLETION
            )
            for participant_id in participant_ids:
                LevelService.award_xp(
                    user_id=participant_id,
                    xp_amount=completion_xp,
                    transaction_type=XPTransactionType.TOURNAMENT_COMPLETION,
                    reason=f"Completed tournament {event.gara_id}",
                    related_entities={"gara_id": event.gara_id},
                )

            logger.info(
                f"Awarded {completion_xp} XP "
                f"to {len(participant_ids)} participants for tournament {event.gara_id} completion"
            )

            # Bonus for winner
            if event.winner_id:
                win_xp = ConfigService.get_xp_rate(XPTransactionType.TOURNAMENT_WIN)
                LevelService.award_xp(
                    user_id=event.winner_id,
                    xp_amount=win_xp,
                    transaction_type=XPTransactionType.TOURNAMENT_WIN,
                    reason=f"Won tournament {event.gara_id}",
                    related_entities={"gara_id": event.gara_id, "position": 1},
                )
                logger.info(f"Awarded {win_xp} XP to winner {event.winner_id}")

            # Bonus for podium (top 3, excluding winner who already got bonus)
            if event.final_standings and len(event.final_standings) >= 2:
                podium_xp = ConfigService.get_xp_rate(
                    XPTransactionType.TOURNAMENT_PODIUM
                )
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
                            xp_amount=podium_xp,
                            transaction_type=XPTransactionType.TOURNAMENT_PODIUM,
                            reason=f"Finished {position} in tournament {event.gara_id}",
                            related_entities={
                                "gara_id": event.gara_id,
                                "position": position,
                            },
                        )

                logger.info(f"Awarded podium bonuses to {len(podium)} players")

            # Achievement: riconcilia lo stato di ogni partecipante. I premi di
            # piazzamento (TOURNAMENT_WIN/PODIUM) sono già a ledger sopra, quindi
            # champion/podium_finish/tournament_dominator si sbloccano qui.
            # `aspiring_director` (director_eligibility) è escluso dalla
            # riconciliazione (costoso) e va controllato a parte.
            for participant_id in participant_ids:
                try:
                    AchievementService.reconcile_achievements(participant_id)
                except Exception as ach_error:
                    logger.warning(
                        f"Error reconciling achievements for user {participant_id}: {ach_error}"
                    )
                try:
                    AchievementService.check_and_award_achievement(
                        participant_id, "aspiring_director"
                    )
                except Exception as ach_error:
                    logger.warning(
                        f"Error checking aspiring_director achievement "
                        f"for user {participant_id}: {ach_error}"
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
                        f"Error updating quest progress for user "
                        f"{participant_id}: {quest_error}"
                    )

        except Exception as e:
            logger.error(
                f"Error handling competition completed event for XP: {e}", exc_info=True
            )

    @staticmethod
    def handle_competition_created_for_xp(event: CompetitionCreatedEvent) -> None:
        """Award XP for creating a competition (Gara)."""
        try:
            gara_xp = ConfigService.get_xp_rate(XPTransactionType.GARA_CREATION)
            LevelService.award_xp(
                user_id=event.creator_id,
                xp_amount=gara_xp,
                transaction_type=XPTransactionType.GARA_CREATION,
                reason=f"Created competition {event.name}",
                related_entities={"gara_id": event.gara_id},
            )
            logger.info(
                f"Awarded {gara_xp} XP to user {event.creator_id} for creating Gara"
            )
        except Exception as e:
            logger.error(
                f"Error handling competition created event for XP: {e}", exc_info=True
            )

    @staticmethod
    def handle_campionato_created_for_xp(event: CampionatoCreatedEvent) -> None:
        """Award XP for creating a Campionato."""
        try:
            campionato_xp = ConfigService.get_xp_rate(
                XPTransactionType.CAMPIONATO_CREATION
            )
            LevelService.award_xp(
                user_id=event.creator_id,
                xp_amount=campionato_xp,
                transaction_type=XPTransactionType.CAMPIONATO_CREATION,
                reason=f"Created campionato {event.name}",
                related_entities={"campionato_id": event.campionato_id},
            )
            logger.info(
                f"Awarded {campionato_xp} XP to user {event.creator_id} for creating Campionato"
            )
        except Exception as e:
            logger.error(
                f"Error handling campionato created event for XP: {e}", exc_info=True
            )

    # ========================================
    # Challenge (drill) Domain Handlers
    # ========================================

    @staticmethod
    def handle_challenge_attempt_completed_for_xp(
        event: ChallengeAttemptCompletedEvent,
    ) -> None:
        """XP e streak alla chiusura di un drill.

        **Il drill conta da entrambe le parti.** Un allenamento fatto dal
        catalogo e uno fatto durante una gara sono la stessa abitudine: la
        ``WEEKLY_DRILL`` scatta per tutt'e due, come per l'esame — che è a sua
        volta una sequenza di drill (ADR-042). Distinguerli avrebbe voluto dire
        dire al giocatore che allenarsi in gara non è allenarsi.

        **L'XP invece guarda l'origine**, perché «un drill» vuol dire due cose
        diverse nei due posti. Dal catalogo un tentativo è una sessione: si
        sceglie la prova, la si fa, la si chiude. In gara la stessa prova si
        ripete fino a ``max_attempts`` nello stesso turno, e il direttore
        registra spesso i tentativi in blocco: pagarli tutti significherebbe
        moltiplicare l'XP di un allenamento per il numero di tiri. Paga quindi
        solo il primo — che è il drill — e i successivi sono lo stesso drill,
        riprovato.

        L'esito non entra nel conto: come per l'esame in autonomia, quello che
        si premia è essersi allenati. Un drill sbagliato è comunque un drill.
        """
        try:
            if not event.is_a_retry:
                LevelService.award_xp(
                    user_id=event.user_id,
                    xp_amount=ConfigService.get_xp_rate(
                        XPTransactionType.CHALLENGE_COMPLETION
                    ),
                    transaction_type=XPTransactionType.CHALLENGE_COMPLETION,
                    reason=f"Completed drill {event.challenge_name}",
                    related_entities={
                        "challenge_id": event.challenge_id,
                        "challenge_attempt_id": event.attempt_id,
                        "gara_id": event.gara_id,
                    },
                )

            # La streak è settimanale e idempotente: un secondo tentativo non
            # la muove, quindi si registra comunque senza doverlo verificare.
            for streak_type in (StreakType.WEEKLY_DRILL, StreakType.WEEKLY_ACTIVITY):
                try:
                    StreakService.record_activity(
                        user_id=event.user_id, streak_type=streak_type
                    )
                except Exception as streak_error:
                    logger.warning(
                        f"Error recording {streak_type} for user "
                        f"{event.user_id}: {streak_error}"
                    )
        except Exception as e:
            logger.error(
                f"Error handling challenge attempt completed event: {e}", exc_info=True
            )

    # ========================================
    # Exam Domain Handlers (ADR-042)
    # ========================================

    @staticmethod
    def handle_exam_attempt_completed_for_xp(
        event: ExamAttemptCompletedEvent,
    ) -> None:
        """XP, streak e achievement alla chiusura di un tentativo d'esame.

        La regola del dominio in una riga: **solo la sessione certificata e
        superata vale una certificazione.**

        - *In autonomia* → XP di allenamento e streak ``WEEKLY_DRILL``. È un
          allenamento, e come tale conta per l'abitudine, non per il curriculum:
          nessun achievement di certificazione.
        - *Certificato e superato* → XP pieno e riconciliazione degli
          achievement, perché ``exams_certified`` è appena cambiata.
        - *Certificato e non superato* → nessun XP. Non è una punizione: è che
          il tentativo si ripete, e pagarlo comunque renderebbe conveniente
          farsi bocciare in serie. La streak d'allenamento invece scatta lo
          stesso — presentarsi a un esame è attività, quale che sia l'esito.

        Un tentativo abbandonato non arriva neanche qui: il dominio non
        pubblica l'evento per chi non si è presentato.
        """
        try:
            certification = event.is_certification

            if certification:
                xp_type = XPTransactionType.EXAM_CERTIFIED
                reason = f"Passed certified exam {event.exam_name}"
            elif event.is_certified:
                xp_type = None  # bocciato: nessun XP, il tentativo si ripete
                reason = ""
            else:
                xp_type = XPTransactionType.EXAM_PRACTICE
                reason = f"Practised exam {event.exam_name}"

            if xp_type is not None:
                LevelService.award_xp(
                    user_id=event.user_id,
                    xp_amount=ConfigService.get_xp_rate(xp_type),
                    transaction_type=xp_type,
                    reason=reason,
                    related_entities={
                        "exam_id": event.exam_id,
                        "exam_attempt_id": event.attempt_id,
                    },
                )

            # L'esame è una sequenza di drill: allenarsi conta per la stessa
            # abitudine settimanale, sia da soli sia davanti a un esaminatore.
            for streak_type in (StreakType.WEEKLY_DRILL, StreakType.WEEKLY_ACTIVITY):
                try:
                    StreakService.record_activity(
                        user_id=event.user_id, streak_type=streak_type
                    )
                except Exception as streak_error:
                    logger.warning(
                        f"Error recording {streak_type} for user "
                        f"{event.user_id}: {streak_error}"
                    )

            # Solo la certificazione muove il curriculum: riconciliare a ogni
            # allenamento sarebbe lavoro sprecato su una metrica ferma.
            if certification:
                try:
                    AchievementService.reconcile_achievements(event.user_id)
                except Exception as ach_error:
                    logger.warning(
                        f"Error reconciling achievements for user "
                        f"{event.user_id}: {ach_error}"
                    )
        except Exception as e:
            logger.error(
                f"Error handling exam attempt completed event: {e}", exc_info=True
            )


# Auto-register handlers when module is imported
GamificationEventHandlers.register_all_handlers()
