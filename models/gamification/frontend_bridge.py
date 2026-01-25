"""
Gamification Frontend Bridge - Connects Backend Events to Frontend Animations

This module listens to gamification domain events and creates temporary
frontend events (via Flask flash mechanism) that trigger animations in the browser.

It acts as the "Transmission" between the Python backend engine and the
JavaScript frontend display.
"""

from __future__ import annotations
import json
import logging
from typing import Dict, Any, Optional

from flask import flash, has_request_context
from flask_login import current_user

from models.events.base import EventBus
from models.gamification.events import (
    XPGainedEvent,
    LevelUpEvent,
    AchievementUnlockedEvent,
    StreakMilestoneEvent,
    StreakBrokenEvent,
    QuestCompletedEvent,
)
from models.notification.templates import (
    DIFFICULTY_LABELS,
    STREAK_TYPE_LABELS,
    QUEST_TYPE_LABELS,
)

class GamificationEventType:
    """Enum for frontend event types."""
    XP = "xp"
    LEVEL_UP = "levelup"
    ACHIEVEMENT = "achievement"
    STREAK = "streak"
    STREAK_LOST = "streak_lost"
    QUEST = "quest"
    WELCOME = "welcome"

logger = logging.getLogger(__name__)


class GamificationFrontendBridge:
    """
    Bridge that translates domain events into frontend flash messages.
    
    These messages are consumed by base.html and passed to 
    gamification.js via showGamificationEvent().
    """

    @staticmethod
    def register_all_handlers() -> None:
        """Register all bridge handlers with the EventBus."""
        EventBus.register_handler(
            XPGainedEvent,
            GamificationFrontendBridge.handle_xp_gained,
            priority=0  # Low priority, UI only
        )
        
        EventBus.register_handler(
            LevelUpEvent,
            GamificationFrontendBridge.handle_level_up,
            priority=0
        )
        
        EventBus.register_handler(
            AchievementUnlockedEvent,
            GamificationFrontendBridge.handle_achievement_unlocked,
            priority=0
        )
        
        EventBus.register_handler(
            StreakMilestoneEvent,
            GamificationFrontendBridge.handle_streak_milestone,
            priority=0
        )
        
        EventBus.register_handler(
            StreakBrokenEvent,
            GamificationFrontendBridge.handle_streak_broken,
            priority=0
        )
        
        EventBus.register_handler(
            QuestCompletedEvent,
            GamificationFrontendBridge.handle_quest_completed,
            priority=0
        )

        logger.info("Registered gamification frontend bridge handlers")

    @staticmethod
    def _flash_gamification_event(event_type: str, data: Dict[str, Any], user_id: int) -> None:
        """
        Helper to flash event if suitable for current context.
        
        Only flashes if:
        1. We are in a Flask request context
        2. There is a logged-in user
        3. The event belongs to the current user (don't animate for others)
        """
        if not has_request_context():
            return
            
        if not current_user.is_authenticated:
            return
            
        if current_user.id != user_id:
            # Event is for another user, don't show animation to this user
            return

        if current_user.is_admin:
            # Admin users don't see gamification animations
            return
            
        try:
            payload = {
                "type": event_type,
                "data": data
            }
            # Use 'gamification_event' category to separate from normal alerts
            flash(json.dumps(payload), category="gamification_event")
            logger.debug(f"Flashed gamification event: {event_type}")
        except Exception as e:
            logger.error(f"Error flashing gamification event: {e}")

    @staticmethod
    def handle_xp_gained(event: XPGainedEvent) -> None:
        """Send XP gain event to frontend."""
        # Only flash significant XP gains to avoid spam (e.g., > 0)
        if event.xp_amount <= 0:
            return

        # Improved reason formatting
        reason = "XP Ottenuti"
        if event.related_entities:
            if "match_id" in event.related_entities:
                reason = f"Partita #{event.related_entities['match_id']}"
            elif "gara_id" in event.related_entities:
                reason = f"Torneo #{event.related_entities['gara_id']}"

        GamificationFrontendBridge._flash_gamification_event(
            "xp",
            {
                "amount": event.xp_amount,
                "reason": reason
            },
            event.user_id
        )

    @staticmethod
    def handle_level_up(event: LevelUpEvent) -> None:
        """Send level up event to frontend."""
        GamificationFrontendBridge._flash_gamification_event(
            "levelup",
            {
                "level": event.new_level,
                "title": f"Livello {event.new_level}"  # Could be enhanced with rank titles
            },
            event.user_id
        )

    @staticmethod
    def handle_achievement_unlocked(event: AchievementUnlockedEvent) -> None:
        """Send achievement event to frontend."""
        GamificationFrontendBridge._flash_gamification_event(
            "achievement",
            {
                "name": event.achievement_name,
                "description": _get_achievement_description(event), # Helper needed or simple text
                "rarity": event.achievement_difficulty.lower(), # common, rare, epic, legendary
                "icon": "🏆" # Placeholder, JS handles images based on rarity
            },
            event.user_id
        )

    @staticmethod
    def handle_streak_milestone(event: StreakMilestoneEvent) -> None:
        """Send streak milestone event to frontend."""
        GamificationFrontendBridge._flash_gamification_event(
            "streak",
            {
                "count": event.current_streak,
                "type": event.streak_type,
                "hasFreeze": event.freeze_earned > 0
            },
            event.user_id
        )

    @staticmethod
    def handle_streak_broken(event: StreakBrokenEvent) -> None:
        """Send streak lost event to frontend."""
        GamificationFrontendBridge._flash_gamification_event(
            "streak_lost",
            {
                "message": f"Hai perso uno streak di {event.streak_length} settimane!"
            },
            event.user_id
        )

    @staticmethod
    def handle_quest_completed(event: QuestCompletedEvent) -> None:
        """Send quest completion event to frontend."""
        GamificationFrontendBridge._flash_gamification_event(
            "quest",
            {
                "name": event.quest_name,
                "description": "Quest completata!" 
            },
            event.user_id
        )


    @staticmethod
    def handle_nudge_event(user_id: int, feature_config: Any) -> None:
        """
        Send nudge event to frontend.
        feature_config is expected to be a FeatureConfig model instance.
        """
        # I18n should be handled by the frontend or pre-translated here.
        # Ensure we pass keys or English text that can be translated.
        GamificationFrontendBridge._flash_gamification_event(
            "nudge",
            {
                "code": feature_config.code,
                "name": feature_config.name,
                "description": feature_config.description,
                "badge": feature_config.badge_slug
            },
            user_id
        )

    @staticmethod
    def handle_feature_unlock_event(user_id: int, feature_config: Any) -> None:
        """
        Send feature unlock event to frontend.
        Typically triggered via manual flash or specific domain event.
        """
        GamificationFrontendBridge._flash_gamification_event(
            "unlock",
            {
                "code": feature_config.code,
                "name": feature_config.name,
                "description": feature_config.description,
                "icon": "🔓"
            },
            user_id
        )

def _get_achievement_description(event: AchievementUnlockedEvent) -> str:
    """Helper to get a simple description properly formatted."""
    # Ideally should fetch from DB or translation, but for animation simple is fine
    return f"+{event.xp_awarded} XP - {event.achievement_category.capitalize()}"


# Auto-register handlers
GamificationFrontendBridge.register_all_handlers()


def flash_gamification_event(event_type: str, data: Dict[str, Any]) -> None:
    """
    Public API to trigger a gamification frontend event manually.
    Useful for events not triggered by domain events, like "Welcome".
    """
    if not has_request_context() or not current_user.is_authenticated:
        return

    if current_user.is_admin:
        return

    try:
        payload = {
            "type": event_type,
            "data": data
        }
        flash(json.dumps(payload), category="gamification_event")
        logger.debug(f"Manually flashed gamification event: {event_type}")
    except Exception as e:
        logger.error(f"Error manually flashing gamification event: {e}")
