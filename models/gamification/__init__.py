"""
Gamification Domain - XP, Levels, Achievements, Streaks, Leaderboards

This domain implements an advanced gamification system to create habits
and encourage community engagement through:
- XP and level progression with tangible unlocks
- Achievement system with 20+ categorized badges
- Weekly streak tracking with freeze mechanics
- Multiple leaderboards with caching
- Weekly/monthly quest system
- Integration with existing Challenge (drill) system

Architecture:
- Event-driven: Hooks into existing domain events (MatchCompletedEvent, etc.)
- @transactional: All write operations use transaction decorator
- i18n: Full Flask-Babel internationalization support
- Performance: Materialized view pattern for leaderboards

Components:
- models.py: UserLevel, XPTransaction, Achievement, UserAchievement, StreakTracker, etc.
- xp_config.py: XP rates, level progression curve, feature unlocks
- level_service.py: XP award logic with automatic level up detection
- achievement_service.py: Achievement eligibility and unlock logic
- streak_service.py: Weekly streak tracking with ISO week numbers
- leaderboard_service.py: Cached leaderboard calculation
- quest_service.py: Weekly/monthly goal management
- events.py: Gamification domain events (XPGainedEvent, LevelUpEvent, etc.)
- event_handlers.py: Handlers for existing domain events
- notification_handlers.py: Notification creation for gamification events
"""

from .models import (
    UserLevel,
    XPTransaction,
    XPTransactionType,
    Achievement,
    AchievementCategory,
    AchievementDifficulty,
    UserAchievement,
    StreakTracker,
    StreakType,
    LeaderboardEntry,
    LeaderboardType,
    Quest,
    QuestType,
    QuestStatus,
    QuestParticipation,
)

__all__ = [
    # Models
    "UserLevel",
    "XPTransaction",
    "XPTransactionType",
    "Achievement",
    "AchievementCategory",
    "AchievementDifficulty",
    "UserAchievement",
    "StreakTracker",
    "StreakType",
    "LeaderboardEntry",
    "LeaderboardType",
    "Quest",
    "QuestType",
    "QuestStatus",
    "QuestParticipation",
]
