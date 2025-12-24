"""
Gamification Domain Events

Events emitted by the gamification system for cross-domain integration:
- XPGainedEvent: Triggered when user earns XP (for analytics, notifications)
- LevelUpEvent: Triggered when user levels up (for notifications, unlocks)
- AchievementUnlockedEvent: Triggered when achievement is unlocked
- StreakMilestoneEvent: Triggered on weekly streak milestones (4/12/52 weeks)
- StreakBrokenEvent: Triggered when streak is broken
- StreakFreezeUsedEvent: Triggered when freeze is used to save streak
- QuestCompletedEvent: Triggered when user completes a quest

All events follow the DomainEvent pattern with @dataclass and type hints.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from models.events.base import DomainEvent
from models.gamification.models import XPTransactionType


@dataclass
class XPGainedEvent(DomainEvent):
    """
    Event emitted when user gains XP.
    
    Used for:
    - Analytics tracking
    - Real-time UI updates
    - Third-party integrations
    """
    user_id: int
    xp_amount: int
    transaction_type: XPTransactionType
    new_total_xp: int
    level_before: int
    level_after: int
    related_entities: Optional[Dict[str, Any]] = None

    @property
    def domain(self) -> str:
        return "gamification"

    def get_event_type(self) -> str:
        return "xp_gained"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "xp_amount": self.xp_amount,
            "transaction_type": self.transaction_type.value,
            "new_total_xp": self.new_total_xp,
            "level_before": self.level_before,
            "level_after": self.level_after,
            "related_entities": self.related_entities,
        }


@dataclass
class LevelUpEvent(DomainEvent):
    """
    Event emitted when user levels up.
    
    Used for:
    - Notification creation (celebrate level up!)
    - Feature unlock checks
    - Analytics tracking
    """
    user_id: int
    old_level: int
    new_level: int
    unlocks: List[Dict[str, str]]  # [{"feature": "tournament_creation", "description": "..."}]
    total_xp: int

    @property
    def domain(self) -> str:
        return "gamification"

    def get_event_type(self) -> str:
        return "level_up"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "old_level": self.old_level,
            "new_level": self.new_level,
            "unlocks": self.unlocks,
            "total_xp": self.total_xp,
        }


@dataclass
class AchievementUnlockedEvent(DomainEvent):
    """
    Event emitted when user unlocks an achievement.
    
    Used for:
    - Notification creation (celebrate achievement!)
    - XP award (achievement.xp_reward)
    - Social sharing (future)
    """
    user_id: int
    achievement_id: int
    achievement_slug: str
    achievement_name: str
    achievement_category: str
    achievement_difficulty: str
    xp_awarded: int

    @property
    def domain(self) -> str:
        return "gamification"

    def get_event_type(self) -> str:
        return "achievement_unlocked"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "achievement_id": self.achievement_id,
            "achievement_slug": self.achievement_slug,
            "achievement_name": self.achievement_name,
            "achievement_category": self.achievement_category,
            "achievement_difficulty": self.achievement_difficulty,
            "xp_awarded": self.xp_awarded,
        }


@dataclass
class StreakMilestoneEvent(DomainEvent):
    """
    Event emitted when user reaches a weekly streak milestone.
    
    Milestones: 4 weeks (1 month), 12 weeks (3 months), 52 weeks (1 year)
    
    Used for:
    - Notification creation (celebrate milestone!)
    - Freeze award (if applicable)
    - XP bonus award
    """
    user_id: int
    streak_type: str  # "weekly_activity", "weekly_match", etc.
    milestone: int  # 4, 12, 52 (weeks)
    current_streak: int
    freeze_earned: int  # 0, 1, or 2
    xp_bonus: int

    @property
    def domain(self) -> str:
        return "gamification"

    def get_event_type(self) -> str:
        return "streak_milestone"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "streak_type": self.streak_type,
            "milestone": self.milestone,
            "current_streak": self.current_streak,
            "freeze_earned": self.freeze_earned,
            "xp_bonus": self.xp_bonus,
        }


@dataclass
class StreakBrokenEvent(DomainEvent):
    """
    Event emitted when streak is broken (missed 2+ weeks).
    
    Used for:
    - Analytics (track streak loss)
    - Encouragement notifications (future)
    """
    user_id: int
    streak_type: str
    streak_length: int  # How many weeks were lost
    no_freeze_available: bool

    @property
    def domain(self) -> str:
        return "gamification"

    def get_event_type(self) -> str:
        return "streak_broken"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "streak_type": self.streak_type,
            "streak_length": self.streak_length,
            "no_freeze_available": self.no_freeze_available,
        }


@dataclass
class StreakFreezeUsedEvent(DomainEvent):
    """
    Event emitted when freeze is used to save a streak.
    
    Used for:
    - Analytics (track freeze usage)
    - UI updates (show freeze count)
    """
    user_id: int
    streak_type: str
    current_streak: int
    freezes_remaining: int

    @property
    def domain(self) -> str:
        return "gamification"

    def get_event_type(self) -> str:
        return "streak_freeze_used"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "streak_type": self.streak_type,
            "current_streak": self.current_streak,
            "freezes_remaining": self.freezes_remaining,
        }


@dataclass
class QuestCompletedEvent(DomainEvent):
    """
    Event emitted when user completes a quest.
    
    Used for:
    - Notification creation (celebrate quest completion!)
    - XP award
    - Quest statistics update
    """
    user_id: int
    quest_id: int
    quest_name: str
    quest_type: str  # "weekly", "monthly", "special_event"
    xp_awarded: int
    completion_percentage: float  # For quest-wide stats

    @property
    def domain(self) -> str:
        return "gamification"

    def get_event_type(self) -> str:
        return "quest_completed"

    def _get_event_data(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "quest_id": self.quest_id,
            "quest_name": self.quest_name,
            "quest_type": self.quest_type,
            "xp_awarded": self.xp_awarded,
            "completion_percentage": self.completion_percentage,
        }
