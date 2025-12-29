"""
Gamification Notification Handlers

Event handlers that create notifications when gamification events occur.
Listens to LevelUpEvent, AchievementUnlockedEvent, StreakMilestoneEvent, etc.

Uses NotificationService to respect user preferences automatically.
All notifications support i18n with Flask-Babel via template_key + template_params.
"""

from __future__ import annotations
import logging
from datetime import datetime, timedelta

from flask_babel import gettext as _

from models.events.base import EventBus
from models.gamification.events import (
    LevelUpEvent,
    AchievementUnlockedEvent,
    StreakMilestoneEvent,
    StreakBrokenEvent,
    QuestCompletedEvent,
)
from models.notification.services import NotificationService
from models.notification.models import NotificationType, NotificationPriority
from models.notification.templates import (
    DIFFICULTY_LABELS,
    STREAK_TYPE_LABELS,
    QUEST_TYPE_LABELS,
)

logger = logging.getLogger(__name__)


class GamificationNotificationHandlers:
    """
    Event handlers for gamification notifications.
    
    Creates notifications when:
    - User levels up (with feature unlocks)
    - User unlocks achievement
    - User reaches streak milestone
    - User's streak is about to break (warning)
    - User completes quest
    """

    @staticmethod
    def register_all_handlers() -> None:
        """Register all notification handlers with EventBus."""
        EventBus.register_handler(
            LevelUpEvent,
            GamificationNotificationHandlers.handle_level_up_notification,
            priority=5  # Lower priority than gamification logic (priority 10)
        )
        
        EventBus.register_handler(
            AchievementUnlockedEvent,
            GamificationNotificationHandlers.handle_achievement_unlocked_notification,
            priority=5
        )
        
        EventBus.register_handler(
            StreakMilestoneEvent,
            GamificationNotificationHandlers.handle_streak_milestone_notification,
            priority=5
        )
        
        EventBus.register_handler(
            QuestCompletedEvent,
            GamificationNotificationHandlers.handle_quest_completed_notification,
            priority=5
        )

        logger.info("Registered all gamification notification handlers")

    @staticmethod
    def handle_level_up_notification(event: LevelUpEvent) -> None:
        """
        Send notification on level up.

        Notification includes:
        - New level reached
        - Feature unlocks (if any)
        - Total XP milestone

        Priority: HIGH (celebrate achievement!)

        Uses template_key for i18n support - translation happens at display time.
        """
        try:
            # Build unlock text
            unlocks_text = ""
            if event.unlocks:
                unlock_descriptions = [u["description"] for u in event.unlocks]
                unlocks_text = " " + _("Hai sbloccato: ") + ", ".join(unlock_descriptions)

            title = _("Livello %(level)d Raggiunto!", level=event.new_level)
            message = _(
                "Congratulazioni! Hai raggiunto il livello %(level)d!%(unlocks)s",
                level=event.new_level,
                unlocks=unlocks_text
            )

            # Template params for dynamic i18n at display time
            template_params = {
                "level": event.new_level,
                "unlocks": unlocks_text,
            }

            NotificationService.create_notification(
                user_id=event.user_id,
                notification_type=NotificationType.LEVEL_UP,
                title=title,
                message=message,
                priority=NotificationPriority.HIGH,
                related_entities={
                    "old_level": event.old_level,
                    "new_level": event.new_level,
                    "total_xp": event.total_xp,
                    "unlocks": event.unlocks
                },
                action_url="/gamification/dashboard",
                action_text=_("Visualizza Progressi"),
                template_key="gamification.level_up",
                template_params=template_params,
            )

            logger.info(f"Sent level up notification to user {event.user_id} (level {event.new_level})")

        except Exception as e:
            logger.error(f"Error sending level up notification: {e}", exc_info=True)

    @staticmethod
    def handle_achievement_unlocked_notification(event: AchievementUnlockedEvent) -> None:
        """
        Send notification on achievement unlock.

        Notification includes:
        - Achievement name and description
        - XP awarded
        - Achievement category and difficulty

        Priority: NORMAL (frequent, but still exciting)

        Uses template_key for i18n support - translation happens at display time.
        The difficulty key is stored raw (e.g., "common") and translated at display time.
        """
        try:
            # Get translated label for fallback message only
            difficulty_label = DIFFICULTY_LABELS.get(
                event.achievement_difficulty, event.achievement_difficulty
            )

            # Static fallback values (for backwards compatibility)
            title = _("Achievement Sbloccato!")
            message = _(
                "Hai ottenuto '%(name)s' (%(difficulty)s)! +%(xp)d XP",
                name=event.achievement_name,
                difficulty=difficulty_label,
                xp=event.xp_awarded
            )

            # Template params for dynamic i18n at display time
            # Store raw difficulty key - gets translated via DIFFICULTY_LABELS at display time
            template_params = {
                "name": event.achievement_name,
                "difficulty_key": event.achievement_difficulty,  # Raw key, not translated
                "xp": event.xp_awarded,
            }

            NotificationService.create_notification(
                user_id=event.user_id,
                notification_type=NotificationType.ACHIEVEMENT_UNLOCKED,
                title=title,
                message=message,
                priority=NotificationPriority.NORMAL,
                related_entities={
                    "achievement_id": event.achievement_id,
                    "achievement_slug": event.achievement_slug,
                    "category": event.achievement_category,
                    "difficulty": event.achievement_difficulty,
                    "xp_awarded": event.xp_awarded
                },
                action_url="/gamification/achievements",
                action_text=_("Visualizza Achievement"),
                template_key="achievement.unlocked",
                template_params=template_params,
            )

            logger.info(f"Sent achievement notification to user {event.user_id} ({event.achievement_slug})")

        except Exception as e:
            logger.error(f"Error sending achievement notification: {e}", exc_info=True)

    @staticmethod
    def handle_streak_milestone_notification(event: StreakMilestoneEvent) -> None:
        """
        Send notification on streak milestone.

        Milestones: 4, 12, 52 weeks

        Notification includes:
        - Milestone reached (e.g., "4 Settimane Consecutive!")
        - Freeze earned (if applicable)
        - XP bonus awarded

        Priority: HIGH (celebrate consistency!)

        Uses template_key for i18n support - translation happens at display time.
        The type_key is stored raw and translated via STREAK_TYPE_LABELS at display time.
        """
        try:
            # Get streak type label for fallback message only
            streak_type_display = STREAK_TYPE_LABELS.get(
                event.streak_type, event.streak_type
            )

            # Build freeze text
            freeze_text = ""
            if event.freeze_earned > 0:
                freeze_text = " " + _(
                    "Hai guadagnato %(count)d freeze!",
                    count=event.freeze_earned
                )

            title = _("Streak di %(weeks)d Settimane!", weeks=event.milestone)
            message = _(
                "Incredibile! Hai mantenuto il tuo streak di %(type)s per %(weeks)d settimane consecutive!%(freeze)s +%(xp)d XP",
                type=streak_type_display,
                weeks=event.milestone,
                freeze=freeze_text,
                xp=event.xp_bonus
            )

            # Template params for dynamic i18n at display time
            # Store raw type_key - gets translated via STREAK_TYPE_LABELS at display time
            template_params = {
                "type_key": event.streak_type,  # Raw key, not translated
                "weeks": event.milestone,
                "freeze": freeze_text,
                "xp": event.xp_bonus,
            }

            NotificationService.create_notification(
                user_id=event.user_id,
                notification_type=NotificationType.STREAK_MILESTONE,
                title=title,
                message=message,
                priority=NotificationPriority.HIGH,
                related_entities={
                    "streak_type": event.streak_type,
                    "milestone": event.milestone,
                    "current_streak": event.current_streak,
                    "freeze_earned": event.freeze_earned,
                    "xp_bonus": event.xp_bonus
                },
                action_url="/gamification/dashboard",
                action_text=_("Visualizza Streak"),
                template_key="gamification.streak_milestone",
                template_params=template_params,
            )

            logger.info(f"Sent streak milestone notification to user {event.user_id} ({event.milestone} weeks)")

        except Exception as e:
            logger.error(f"Error sending streak milestone notification: {e}", exc_info=True)

    @staticmethod
    def handle_quest_completed_notification(event: QuestCompletedEvent) -> None:
        """
        Send notification on quest completion.

        Notification includes:
        - Quest name
        - Quest type (weekly/monthly)
        - XP awarded

        Priority: NORMAL

        Uses template_key for i18n support - translation happens at display time.
        The type_key is stored raw and translated via QUEST_TYPE_LABELS at display time.
        """
        try:
            # Get quest type label for fallback message only
            quest_type_display = QUEST_TYPE_LABELS.get(
                event.quest_type, event.quest_type
            )

            title = _("Quest Completata!")
            message = _(
                "Hai completato la quest %(type)s '%(name)s'! +%(xp)d XP",
                type=quest_type_display,
                name=event.quest_name,
                xp=event.xp_awarded
            )

            # Template params for dynamic i18n at display time
            # Store raw type_key - gets translated via QUEST_TYPE_LABELS at display time
            template_params = {
                "type_key": event.quest_type,  # Raw key, not translated
                "name": event.quest_name,
                "xp": event.xp_awarded,
            }

            NotificationService.create_notification(
                user_id=event.user_id,
                notification_type=NotificationType.QUEST_COMPLETED,
                title=title,
                message=message,
                priority=NotificationPriority.NORMAL,
                related_entities={
                    "quest_id": event.quest_id,
                    "quest_name": event.quest_name,
                    "quest_type": event.quest_type,
                    "xp_awarded": event.xp_awarded,
                    "completion_percentage": event.completion_percentage
                },
                action_url="/gamification/quests",
                action_text=_("Visualizza Quests"),
                template_key="gamification.quest_completed",
                template_params=template_params,
            )

            logger.info(f"Sent quest completed notification to user {event.user_id} ({event.quest_name})")

        except Exception as e:
            logger.error(f"Error sending quest completed notification: {e}", exc_info=True)


# Auto-register handlers when module is imported
GamificationNotificationHandlers.register_all_handlers()
