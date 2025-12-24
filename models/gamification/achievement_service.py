"""
Achievement Service - Achievement Unlock and Progress Tracking

Service for checking achievement eligibility and awarding achievements.

Key Methods:
- check_and_award_achievement(): Check if user meets requirements and award if eligible
- get_user_achievements(): Get user's achievements with progress
- check_achievement_progress(): Update progress for progressive achievements
"""

from __future__ import annotations
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime
import json
import logging

from models.base import db
from models.transaction.manager import transactional
from models.gamification.models import (
    Achievement,
    UserAchievement,
)
from models.gamification.events import AchievementUnlockedEvent
from models.gamification.level_service import LevelService
from models.gamification.xp_config import XP_RATES
from models.gamification.models import XPTransactionType
from models.events.base import EventBus

logger = logging.getLogger(__name__)


class AchievementService:
    """
    Service for achievement unlock and progress tracking.
    
    Handles:
    - Checking if user meets achievement requirements
    - Updating progress for progressive achievements
    - Awarding achievements and XP bonuses
    - Emitting AchievementUnlockedEvent
    """

    @staticmethod
    @transactional(domain="gamification")
    def check_and_award_achievement(
        user_id: int,
        achievement_slug: str,
        progress_increment: int = 1,
        force_check: bool = False
    ) -> Tuple[Optional[UserAchievement], bool]:
        """
        Check if user meets requirements and award achievement if eligible.
        
        For progressive achievements:
        - Increments current_progress by progress_increment
        - Checks if total progress meets requirements
        - Awards if requirements met
        
        For non-progressive achievements:
        - Checks current stats against requirements
        - Awards if requirements met
        
        Args:
            user_id: User ID
            achievement_slug: Achievement slug (e.g., "first_blood")
            progress_increment: Amount to increment progress (for progressive)
            force_check: Force requirement check even if already unlocked
            
        Returns:
            Tuple of (UserAchievement or None, was_newly_unlocked: bool)
            
        Emits:
            AchievementUnlockedEvent if newly unlocked
            
        Example:
            # Progressive achievement (veteran_player: 50 wins)
            user_achievement, unlocked = AchievementService.check_and_award_achievement(
                user_id=42,
                achievement_slug="veteran_player",
                progress_increment=1  # Each win increments by 1
            )
            
            # Non-progressive achievement (first_blood: 1 win)
            user_achievement, unlocked = AchievementService.check_and_award_achievement(
                user_id=42,
                achievement_slug="first_blood"
            )
        """
        # Get achievement
        achievement = Achievement.query.filter_by(slug=achievement_slug).first()
        
        if not achievement or not achievement.is_active:
            logger.warning(f"Achievement {achievement_slug} not found or inactive")
            return None, False
        
        # Get or create UserAchievement
        user_achievement = UserAchievement.query.filter_by(
            user_id=user_id,
            achievement_id=achievement.id
        ).first()
        
        if user_achievement is None:
            user_achievement = UserAchievement(
                user_id=user_id,
                achievement_id=achievement.id,
                current_progress=0  # Explicit init before flush
            )
            db.session.add(user_achievement)
        
        # Skip if already unlocked (unless force_check)
        if user_achievement.is_unlocked and not force_check:
            return user_achievement, False
        
        # Parse requirements
        requirements = json.loads(achievement.requirements)
        requirement_type = requirements.get("type")
        
        # Update progress for progressive achievements
        if achievement.is_progressive:
            user_achievement.current_progress += progress_increment
        
        # Check if requirements met
        is_eligible = AchievementService._check_requirements(
            user_id=user_id,
            requirement_type=requirement_type,
            requirements=requirements,
            current_progress=user_achievement.current_progress if achievement.is_progressive else None
        )
        
        if not is_eligible:
            return user_achievement, False
        
        # Already unlocked
        if user_achievement.is_unlocked:
            return user_achievement, False
        
        # Award achievement!
        user_achievement.is_unlocked = True
        user_achievement.unlocked_at = datetime.utcnow()
        
        # Award XP bonus
        if achievement.xp_reward > 0:
            LevelService.award_xp(
                user_id=user_id,
                xp_amount=achievement.xp_reward,
                transaction_type=XPTransactionType.ACHIEVEMENT_UNLOCK,
                reason=f"Unlocked achievement: {achievement.name}",
                related_entities={"achievement_id": achievement.id, "achievement_slug": achievement.slug}
            )
        
        # Emit event
        EventBus.publish(AchievementUnlockedEvent(
            user_id=user_id,
            achievement_id=achievement.id,
            achievement_slug=achievement.slug,
            achievement_name=achievement.name,
            achievement_category=achievement.category.value,
            achievement_difficulty=achievement.difficulty.value,
            xp_awarded=achievement.xp_reward
        ))
        
        logger.info(
            f"User {user_id} unlocked achievement '{achievement.slug}' "
            f"(+{achievement.xp_reward} XP)"
        )
        
        return user_achievement, True

    @staticmethod
    def _check_requirements(
        user_id: int,
        requirement_type: str,
        requirements: Dict[str, Any],
        current_progress: Optional[int] = None
    ) -> bool:
        """
        Check if user meets achievement requirements.
        
        Requirement types:
        - match_wins: Total match wins >= count
        - tournament_participation: Total tournaments >= count
        - tournament_podium: Top 3 finishes >= count
        - tournament_wins: Tournament wins >= count
        - win_rate: Win percentage >= percentage (with min_matches)
        - level_reached: Current level >= level
        - weekly_streak: Current streak >= weeks
        - challenges_completed: Challenges completed >= count
        - unique_opponents: Unique opponents played >= count
        
        Args:
            user_id: User ID
            requirement_type: Type of requirement
            requirements: Full requirements dict
            current_progress: Current progress (for progressive achievements)
            
        Returns:
            True if requirements are met
        """
        if requirement_type == "match_wins":
            required_count = requirements["count"]
            if current_progress is not None:
                # Progressive achievement - use tracked progress
                return current_progress >= required_count
            else:
                # Non-progressive - query actual stats
                from models.user.services import UserStatsService
                stats = UserStatsService.get_user_stats(user_id)
                return stats.get("won_matches", 0) >= required_count
        
        elif requirement_type == "tournament_participation":
            required_count = requirements["count"]
            if current_progress is not None:
                return current_progress >= required_count
            else:
                from models.user.services import UserStatsService
                stats = UserStatsService.get_user_stats(user_id)
                return stats.get("tournaments_played", 0) >= required_count
        
        elif requirement_type == "tournament_podium":
            # Check classification for top 3 finishes
            required_count = requirements["count"]
            # For now, use simplified check (would need Classification query)
            if current_progress is not None:
                return current_progress >= required_count
            return False
        
        elif requirement_type == "tournament_wins":
            required_count = requirements["count"]
            if current_progress is not None:
                return current_progress >= required_count
            return False
        
        elif requirement_type == "win_rate":
            required_percentage = requirements["percentage"]
            min_matches = requirements["min_matches"]
            
            from models.user.services import UserStatsService
            stats = UserStatsService.get_user_stats(user_id)
            total_matches = stats.get("total_matches", 0)
            win_percentage = stats.get("win_percentage", 0)
            
            return total_matches >= min_matches and win_percentage >= required_percentage
        
        elif requirement_type == "level_reached":
            required_level = requirements["level"]
            from models.gamification.models import UserLevel
            user_level = db.session.get(UserLevel, user_id)
            current_level = user_level.current_level if user_level else 1
            return current_level >= required_level
        
        elif requirement_type == "weekly_streak":
            required_weeks = requirements["weeks"]
            from models.gamification.models import StreakTracker, StreakType
            streak = StreakTracker.query.filter_by(
                user_id=user_id,
                streak_type=StreakType.WEEKLY_ACTIVITY
            ).first()
            current_streak = streak.current_streak if streak else 0
            return current_streak >= required_weeks
        
        elif requirement_type == "challenges_completed":
            required_count = requirements["count"]
            if current_progress is not None:
                return current_progress >= required_count
            return False
        
        elif requirement_type == "win_streak":
            # Check current win streak (would need separate tracking)
            required_count = requirements["count"]
            # Placeholder - would need win streak tracking
            return False
        
        elif requirement_type == "unique_opponents":
            required_count = requirements["count"]
            # Placeholder - would need opponent tracking
            if current_progress is not None:
                return current_progress >= required_count
            return False
        
        else:
            logger.warning(f"Unknown requirement type: {requirement_type}")
            return False

    @staticmethod
    def get_user_achievements(
        user_id: int,
        unlocked_only: bool = False,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get user's achievements with progress.
        
        Args:
            user_id: User ID
            unlocked_only: If True, only return unlocked achievements
            category: Filter by category (e.g., "MATCH")
            
        Returns:
            List of dicts with achievement and progress info:
            [
                {
                    "achievement": Achievement,
                    "is_unlocked": bool,
                    "current_progress": int,
                    "progress_percentage": float,
                    "unlocked_at": datetime or None
                },
                ...
            ]
        """
        # Build query
        query = Achievement.query.filter_by(is_active=True)
        
        if category:
            from models.gamification.models import AchievementCategory
            try:
                category_enum = AchievementCategory[category.upper()]
                query = query.filter_by(category=category_enum)
            except KeyError:
                logger.warning(f"Invalid category: {category}")
        
        achievements = query.all()
        
        result = []
        for achievement in achievements:
            # Get user progress
            user_achievement = UserAchievement.query.filter_by(
                user_id=user_id,
                achievement_id=achievement.id
            ).first()
            
            is_unlocked = user_achievement.is_unlocked if user_achievement else False
            current_progress = user_achievement.current_progress if user_achievement else 0
            unlocked_at = user_achievement.unlocked_at if user_achievement else None
            
            # Skip locked achievements if unlocked_only
            if unlocked_only and not is_unlocked:
                continue
            
            # Calculate progress percentage
            if achievement.is_progressive:
                requirements = json.loads(achievement.requirements)
                target = requirements.get("count", 100)
                progress_percentage = min(100.0, (current_progress / target * 100))
            else:
                progress_percentage = 100.0 if is_unlocked else 0.0
            
            result.append({
                "achievement": achievement,
                "is_unlocked": is_unlocked,
                "current_progress": current_progress,
                "progress_percentage": round(progress_percentage, 1),
                "unlocked_at": unlocked_at
            })
        
        return result

    @staticmethod
    def get_achievement_stats(user_id: int) -> Dict[str, Any]:
        """
        Get achievement statistics for user profile.
        
        Returns:
            {
                "total_unlocked": int,
                "total_achievements": int,
                "completion_percentage": float,
                "by_category": {
                    "MATCH": {"unlocked": int, "total": int},
                    ...
                },
                "by_difficulty": {
                    "COMMON": {"unlocked": int, "total": int},
                    ...
                },
                "recent_unlocks": [Achievement, ...]
            }
        """
        from models.gamification.models import AchievementCategory, AchievementDifficulty
        
        all_achievements = Achievement.query.filter_by(is_active=True).all()
        unlocked = UserAchievement.query.filter_by(
            user_id=user_id,
            is_unlocked=True
        ).all()
        
        # By category
        by_category = {}
        for category in AchievementCategory:
            cat_total = len([a for a in all_achievements if a.category == category])
            cat_unlocked = len([ua for ua in unlocked if ua.achievement.category == category])
            by_category[category.value] = {
                "unlocked": cat_unlocked,
                "total": cat_total
            }
        
        # By difficulty
        by_difficulty = {}
        for difficulty in AchievementDifficulty:
            diff_total = len([a for a in all_achievements if a.difficulty == difficulty])
            diff_unlocked = len([ua for ua in unlocked if ua.achievement.difficulty == difficulty])
            by_difficulty[difficulty.value] = {
                "unlocked": diff_unlocked,
                "total": diff_total
            }
        
        # Recent unlocks (last 5)
        recent_unlocks = UserAchievement.query.filter_by(
            user_id=user_id,
            is_unlocked=True
        ).order_by(
            UserAchievement.unlocked_at.desc()
        ).limit(5).all()
        
        return {
            "total_unlocked": len(unlocked),
            "total_achievements": len(all_achievements),
            "completion_percentage": round((len(unlocked) / len(all_achievements) * 100), 1) if all_achievements else 0.0,
            "by_category": by_category,
            "by_difficulty": by_difficulty,
            "recent_unlocks": [ua.achievement for ua in recent_unlocks]
        }
