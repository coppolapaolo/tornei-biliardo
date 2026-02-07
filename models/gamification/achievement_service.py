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
import json
import logging

from models.base import db, utc_now
from models.transaction.manager import transactional
from models.gamification.models import (
    Achievement,
    UserAchievement,
    AchievementCategory,
    AchievementDifficulty,
)
from models.gamification.events import AchievementUnlockedEvent
from models.gamification.level_service import LevelService
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
        # Skip gamification for admin users
        from models.user.models import User
        user = db.session.get(User, user_id)
        if user and user.is_admin:
            logger.debug(f"Skipping achievement check for admin user {user_id}")
            return None, False

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
        user_achievement.unlocked_at = utc_now()
        
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

        elif requirement_type == "director_eligibility":
            # Check if user has enough experience to become a director
            # Requirements: 10+ gare participations OR 1+ complete campionato
            min_gare = requirements.get("min_gare", 10)
            min_campionati = requirements.get("min_campionati_completi", 1)

            return AchievementService._check_director_eligibility(
                user_id=user_id,
                min_gare=min_gare,
                min_campionati=min_campionati
            )

        elif requirement_type == "category_reached":
            # Check if user has reached a specific player category
            required_category = requirements.get("category", "B")
            # Would need player category tracking - placeholder for now
            return False

        elif requirement_type == "strategies_tried":
            # Check if user has played with multiple matchmaking strategies
            required_count = requirements.get("count", 5)
            if current_progress is not None:
                return current_progress >= required_count
            return False

        elif requirement_type == "perfect_challenges":
            # Check perfect score on challenges
            required_count = requirements.get("count", 5)
            if current_progress is not None:
                return current_progress >= required_count
            return False

        elif requirement_type == "match_proposals_created":
            # Social: match proposals created
            required_count = requirements.get("count", 5)
            if current_progress is not None:
                return current_progress >= required_count
            return False

        elif requirement_type == "match_proposals_accepted":
            # Social: invitations accepted
            required_count = requirements.get("count", 10)
            if current_progress is not None:
                return current_progress >= required_count
            return False

        elif requirement_type == "gaming_data_shared":
            # Check if user has shared at least one gaming data type publicly
            from models.user.privacy_models import UserPrivacySetting

            settings = UserPrivacySetting.query.filter_by(user_id=user_id).first()
            if not settings:
                return False

            # Gaming data fields (excluding personal contact info)
            return any([
                settings.show_statistics,
                settings.show_recent_matches,
                settings.show_classifications,
                settings.show_challenge_stats,
            ])

        else:
            logger.warning(f"Unknown requirement type: {requirement_type}")
            return False

    @staticmethod
    def _check_director_eligibility(
        user_id: int,
        min_gare: int = 10,
        min_campionati: int = 1
    ) -> bool:
        """
        Check if user has enough experience for director eligibility achievement.

        Requirements (OR logic):
        - Participated in min_gare completed gare
        - Participated in ALL gare of at least min_campionati campionati

        Args:
            user_id: User ID to check
            min_gare: Minimum completed gare participations
            min_campionati: Minimum complete campionati

        Returns:
            True if either condition is met
        """
        from models.competition.models import Inscription, Gara
        from models.campionato.models import Campionato
        from models.status_enum import GaraStatus
        from sqlalchemy import func

        # Count gare where user participated (inscription not withdrawn)
        # in gare that are completed
        gare_count = (
            db.session.query(Inscription)
            .join(Gara, Inscription.gara_id == Gara.id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,  # noqa: E712
                Gara.status == GaraStatus.COMPLETED.value
            )
            .count()
        )

        if gare_count >= min_gare:
            logger.debug(
                f"User {user_id} eligible for director: {gare_count} gare >= {min_gare}"
            )
            return True

        # Check complete campionati (user participated in ALL gare of a campionato)
        # Get campionati where user has at least one inscription
        user_campionati = (
            db.session.query(Campionato.id)
            .join(Gara, Gara.campionato_id == Campionato.id)
            .join(Inscription, Inscription.gara_id == Gara.id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,  # noqa: E712
                Campionato.is_deleted == False  # noqa: E712
            )
            .distinct()
            .all()
        )

        complete_campionati_count = 0

        for (campionato_id,) in user_campionati:
            # Count total completed gare in this campionato
            total_gare = (
                db.session.query(func.count(Gara.id))
                .filter(
                    Gara.campionato_id == campionato_id,
                    Gara.status == GaraStatus.COMPLETED.value
                )
                .scalar()
            ) or 0

            if total_gare == 0:
                continue  # Campionato has no completed gare yet

            # Count gare where user participated in this campionato
            user_gare = (
                db.session.query(func.count(Inscription.id))
                .join(Gara, Inscription.gara_id == Gara.id)
                .filter(
                    Gara.campionato_id == campionato_id,
                    Gara.status == GaraStatus.COMPLETED.value,
                    Inscription.user_id == user_id,
                    Inscription.is_withdrawn == False  # noqa: E712
                )
                .scalar()
            ) or 0

            if user_gare >= total_gare:
                complete_campionati_count += 1
                if complete_campionati_count >= min_campionati:
                    logger.debug(
                        f"User {user_id} eligible for director: "
                        f"{complete_campionati_count} complete campionati >= {min_campionati}"
                    )
                    return True

        logger.debug(
            f"User {user_id} not eligible for director: "
            f"{gare_count} gare (need {min_gare}), "
            f"{complete_campionati_count} campionati (need {min_campionati})"
        )
        return False

    @staticmethod
    def has_achievement(user_id: int, achievement_slug: str) -> bool:
        """
        Check if user has unlocked a specific achievement.

        Args:
            user_id: User ID
            achievement_slug: Achievement slug to check

        Returns:
            True if achievement is unlocked
        """
        achievement = Achievement.query.filter_by(slug=achievement_slug).first()
        if not achievement:
            return False

        user_achievement = UserAchievement.query.filter_by(
            user_id=user_id,
            achievement_id=achievement.id,
            is_unlocked=True
        ).first()

        return user_achievement is not None

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

    # ========================================
    # Admin Operations
    # ========================================

    @staticmethod
    @transactional(domain="gamification")
    def create_achievement(
        slug: str,
        name: str,
        description: str,
        category: str,
        difficulty: str,
        icon_path: Optional[str],
        xp_reward: int,
        is_hidden: bool,
        is_progressive: bool,
        requirement_type: str,
        requirement_value: int,
    ) -> Achievement:
        """Create a new achievement definition.

        Raises:
            ValueError: If slug/name empty or slug already exists.
        """
        if not slug or not name:
            raise ValueError("Slug e nome sono obbligatori")
        if Achievement.query.filter_by(slug=slug).first():
            raise ValueError("Un achievement con questo slug esiste già")

        requirements = json.dumps({"type": requirement_type, "count": requirement_value})
        achievement = Achievement(
            slug=slug,
            name=name,
            description=description,
            category=AchievementCategory[category.upper()],
            difficulty=AchievementDifficulty[difficulty.upper()],
            icon_path=icon_path,
            xp_reward=xp_reward,
            is_hidden=is_hidden,
            is_progressive=is_progressive,
            requirements=requirements,
        )
        db.session.add(achievement)
        logger.info(f"Created achievement '{slug}'")
        return achievement

    @staticmethod
    @transactional(domain="gamification")
    def toggle_hidden(achievement_id: int) -> Achievement:
        """Toggle achievement hidden status.

        Raises:
            ValueError: If achievement not found.
        """
        achievement = db.session.get(Achievement, achievement_id)
        if not achievement:
            raise ValueError("Achievement non trovato")
        achievement.is_hidden = not achievement.is_hidden
        logger.info(f"Achievement '{achievement.slug}' hidden={achievement.is_hidden}")
        return achievement
