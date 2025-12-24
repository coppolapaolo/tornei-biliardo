"""
Quest Service - Weekly/Monthly Community Goals

Service for managing quests (community goals) and player participation.
NOT to be confused with Challenge (drill/training) domain.

Key Features:
- Quest lifecycle management (upcoming → active → completed/expired)
- Player participation and progress tracking
- Automatic XP award on completion
- Quest statistics and completion rates

Quest Types:
- WEEKLY: 7-day goals (e.g., "Play 5 matches this week")
- MONTHLY: 30-day goals (e.g., "Win 20 matches this month")
- SPECIAL_EVENT: Limited-time events (e.g., "Tournament participation")

All methods use @transactional decorator for automatic commit/rollback.
"""

from __future__ import annotations
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime
import json
import logging

from models.base import db
from models.transaction.manager import transactional
from models.gamification.models import (
    Quest,
    QuestParticipation,
    QuestType,
    QuestStatus,
    XPTransactionType,
)
from models.gamification.xp_config import QUEST_XP_REWARDS
from models.gamification.level_service import LevelService
from models.gamification.events import QuestCompletedEvent
from models.events.base import EventBus

logger = logging.getLogger(__name__)


class QuestService:
    """
    Service for quest management and participation tracking.

    Quest Lifecycle:
    1. UPCOMING: Quest created but not yet started
    2. ACTIVE: Quest is running, players can participate
    3. COMPLETED: Quest ended with successful completion
    4. EXPIRED: Quest ended without completion (time ran out)

    Progress Tracking:
    - Players join quests automatically or manually
    - Progress increments based on quest requirements
    - XP awarded on completion
    """

    # ========================================
    # Quest Lifecycle Management
    # ========================================

    @staticmethod
    @transactional(domain="gamification")
    def create_quest(
        name: str,
        description: str,
        quest_type: QuestType,
        start_date: datetime,
        end_date: datetime,
        requirements: Dict[str, Any],
        xp_reward: Optional[int] = None,
        badge_icon: Optional[str] = None
    ) -> Quest:
        """
        Create a new quest.

        Args:
            name: Quest name (e.g., "Weekly Warrior")
            description: Quest description
            quest_type: WEEKLY, MONTHLY, or SPECIAL_EVENT
            start_date: When quest becomes active
            end_date: When quest expires
            requirements: Dict with "type" and "target"
                e.g., {"type": "matches_played", "target": 10}
            xp_reward: XP reward (defaults to type-based reward)
            badge_icon: Optional badge icon path

        Returns:
            Created Quest

        Example:
            quest = QuestService.create_quest(
                name="Weekly Warrior",
                description="Play 5 matches this week",
                quest_type=QuestType.WEEKLY,
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 1, 7, 23, 59, 59),
                requirements={"type": "matches_played", "target": 5}
            )
        """
        # Determine status based on dates
        now = datetime.utcnow()
        if now < start_date:
            status = QuestStatus.UPCOMING
        elif now <= end_date:
            status = QuestStatus.ACTIVE
        else:
            status = QuestStatus.EXPIRED

        # Default XP reward based on type
        if xp_reward is None:
            xp_reward = QUEST_XP_REWARDS.get(quest_type.value, 150)

        quest = Quest(
            name=name,
            description=description,
            quest_type=quest_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
            requirements=json.dumps(requirements),
            xp_reward=xp_reward,
            badge_icon=badge_icon,
            participant_count=0,
            completion_count=0
        )
        db.session.add(quest)
        db.session.flush()

        logger.info(f"Created quest '{name}' (type: {quest_type.value}, status: {status.value})")
        return quest

    @staticmethod
    @transactional(domain="gamification")
    def update_quest_statuses() -> Dict[str, int]:
        """
        Update quest statuses based on current time.

        Called periodically (e.g., via cron job) to:
        - Activate UPCOMING quests that have started
        - Expire ACTIVE quests that have ended

        Returns:
            Dict with counts: {"activated": int, "expired": int}
        """
        now = datetime.utcnow()
        activated = 0
        expired = 0

        # Activate upcoming quests
        upcoming_quests = Quest.query.filter_by(status=QuestStatus.UPCOMING).filter(
            Quest.start_date <= now
        ).all()

        for quest in upcoming_quests:
            if now <= quest.end_date:
                quest.status = QuestStatus.ACTIVE
                activated += 1
                logger.info(f"Quest '{quest.name}' activated")
            else:
                quest.status = QuestStatus.EXPIRED
                expired += 1
                logger.info(f"Quest '{quest.name}' expired (missed activation window)")

        # Expire active quests
        active_quests = Quest.query.filter_by(status=QuestStatus.ACTIVE).filter(
            Quest.end_date < now
        ).all()

        for quest in active_quests:
            quest.status = QuestStatus.EXPIRED
            expired += 1
            logger.info(f"Quest '{quest.name}' expired")

        return {"activated": activated, "expired": expired}

    @staticmethod
    def get_active_quests() -> List[Quest]:
        """
        Get all currently active quests.

        Returns:
            List of active Quest objects
        """
        return Quest.query.filter_by(status=QuestStatus.ACTIVE).all()

    @staticmethod
    def get_quest_by_id(quest_id: int) -> Optional[Quest]:
        """
        Get quest by ID.

        Args:
            quest_id: Quest ID

        Returns:
            Quest or None
        """
        return db.session.get(Quest, quest_id)

    # ========================================
    # Participation Management
    # ========================================

    @staticmethod
    @transactional(domain="gamification")
    def join_quest(user_id: int, quest_id: int) -> Tuple[QuestParticipation, bool]:
        """
        Join a quest (create participation record).

        Args:
            user_id: User ID
            quest_id: Quest ID

        Returns:
            Tuple of (QuestParticipation, is_new: bool)

        Raises:
            ValueError: If quest is not active
        """
        quest = db.session.get(Quest, quest_id)
        if quest is None:
            raise ValueError(f"Quest {quest_id} not found")

        if quest.status != QuestStatus.ACTIVE:
            raise ValueError(f"Quest '{quest.name}' is not active (status: {quest.status.value})")

        # Check existing participation
        existing = QuestParticipation.query.filter_by(
            user_id=user_id,
            quest_id=quest_id
        ).first()

        if existing:
            return existing, False

        # Parse requirements to get target
        requirements = json.loads(quest.requirements)
        target = requirements.get("target", 100)

        participation = QuestParticipation(
            user_id=user_id,
            quest_id=quest_id,
            current_progress=0,
            target_progress=target,
            is_completed=False,
            xp_awarded=0
        )
        db.session.add(participation)

        # Update quest stats
        quest.participant_count += 1

        logger.info(f"User {user_id} joined quest '{quest.name}'")
        return participation, True

    @staticmethod
    @transactional(domain="gamification")
    def update_progress(
        user_id: int,
        quest_id: int,
        progress_increment: int = 1
    ) -> Tuple[QuestParticipation, bool]:
        """
        Update player's progress on a quest.

        Args:
            user_id: User ID
            quest_id: Quest ID
            progress_increment: Amount to add to progress

        Returns:
            Tuple of (QuestParticipation, just_completed: bool)

        Raises:
            ValueError: If not participating in quest
        """
        participation = QuestParticipation.query.filter_by(
            user_id=user_id,
            quest_id=quest_id
        ).first()

        if participation is None:
            raise ValueError(f"User {user_id} not participating in quest {quest_id}")

        # Already completed
        if participation.is_completed:
            return participation, False

        # Update progress
        participation.current_progress += progress_increment

        # Check completion
        just_completed = False
        if participation.current_progress >= participation.target_progress:
            just_completed = QuestService._complete_quest(participation)

        return participation, just_completed

    @staticmethod
    def _complete_quest(participation: QuestParticipation) -> bool:
        """
        Complete a quest and award XP.

        Args:
            participation: QuestParticipation to complete

        Returns:
            True if newly completed
        """
        if participation.is_completed:
            return False

        quest = participation.quest
        participation.is_completed = True
        participation.completed_at = datetime.utcnow()
        participation.xp_awarded = quest.xp_reward

        # Update quest stats
        quest.completion_count += 1

        # Award XP
        LevelService.award_xp(
            user_id=participation.user_id,
            xp_amount=quest.xp_reward,
            transaction_type=XPTransactionType.CHALLENGE_COMPLETION,
            reason=f"Completed quest: {quest.name}",
            related_entities={"quest_id": quest.id, "quest_name": quest.name}
        )

        # Calculate completion percentage for event
        completion_percentage = (
            (quest.completion_count / quest.participant_count * 100)
            if quest.participant_count > 0 else 0.0
        )

        # Emit event
        EventBus.publish(QuestCompletedEvent(
            user_id=participation.user_id,
            quest_id=quest.id,
            quest_name=quest.name,
            quest_type=quest.quest_type.value,
            xp_awarded=quest.xp_reward,
            completion_percentage=completion_percentage
        ))

        logger.info(
            f"User {participation.user_id} completed quest '{quest.name}' "
            f"(+{quest.xp_reward} XP)"
        )

        return True

    @staticmethod
    @transactional(domain="gamification")
    def record_activity_for_quests(
        user_id: int,
        activity_type: str,
        activity_count: int = 1
    ) -> List[Tuple[Quest, bool]]:
        """
        Record activity that may progress multiple quests.

        This is the main entry point called when a user performs
        a trackable activity (match, tournament, etc.).

        Args:
            user_id: User ID
            activity_type: Type of activity (e.g., "matches_played", "matches_won")
            activity_count: Number of activities (default 1)

        Returns:
            List of (Quest, just_completed) tuples for affected quests

        Example:
            # After a match is completed
            results = QuestService.record_activity_for_quests(
                user_id=42,
                activity_type="matches_played",
                activity_count=1
            )
            for quest, completed in results:
                if completed:
                    print(f"Completed quest: {quest.name}")
        """
        # Skip gamification for admin users
        from models.user.models import User
        user = db.session.get(User, user_id)
        if user and user.is_admin:
            logger.debug(f"Skipping quest progress for admin user {user_id}")
            return []

        results = []

        # Find active quests that match this activity type
        active_quests = Quest.query.filter_by(status=QuestStatus.ACTIVE).all()

        for quest in active_quests:
            requirements = json.loads(quest.requirements)
            req_type = requirements.get("type")

            if req_type != activity_type:
                continue

            # Get or create participation
            participation = QuestParticipation.query.filter_by(
                user_id=user_id,
                quest_id=quest.id
            ).first()

            if participation is None:
                # Auto-join quest
                participation, _ = QuestService.join_quest(user_id, quest.id)

            # Update progress
            if not participation.is_completed:
                participation.current_progress += activity_count

                just_completed = False
                if participation.current_progress >= participation.target_progress:
                    just_completed = QuestService._complete_quest(participation)

                results.append((quest, just_completed))

        return results

    # ========================================
    # Query Methods
    # ========================================

    @staticmethod
    def get_user_quests(
        user_id: int,
        include_completed: bool = True,
        active_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get quests for a user with participation status.

        Args:
            user_id: User ID
            include_completed: Include completed participations
            active_only: Only include active quests

        Returns:
            List of dicts with quest and participation info:
            [
                {
                    "quest": Quest,
                    "participation": QuestParticipation or None,
                    "is_participating": bool,
                    "is_completed": bool,
                    "progress_percentage": float
                },
                ...
            ]
        """
        query = Quest.query
        if active_only:
            query = query.filter_by(status=QuestStatus.ACTIVE)

        quests = query.order_by(Quest.end_date.asc()).all()

        results = []
        for quest in quests:
            participation = QuestParticipation.query.filter_by(
                user_id=user_id,
                quest_id=quest.id
            ).first()

            is_participating = participation is not None
            is_completed = participation.is_completed if participation else False

            if not include_completed and is_completed:
                continue

            # Calculate progress
            if participation:
                progress_percentage = min(100.0, (
                    participation.current_progress / participation.target_progress * 100
                ))
            else:
                progress_percentage = 0.0

            results.append({
                "quest": quest,
                "participation": participation,
                "is_participating": is_participating,
                "is_completed": is_completed,
                "progress_percentage": round(progress_percentage, 1)
            })

        return results

    @staticmethod
    def get_user_quest_stats(user_id: int) -> Dict[str, Any]:
        """
        Get quest statistics for user profile.

        Args:
            user_id: User ID

        Returns:
            {
                "total_participated": int,
                "total_completed": int,
                "completion_rate": float,
                "total_xp_earned": int,
                "quests_by_type": {
                    "weekly": {"participated": int, "completed": int},
                    "monthly": {"participated": int, "completed": int},
                    "special_event": {"participated": int, "completed": int}
                },
                "recent_completions": [Quest, ...]
            }
        """
        participations = QuestParticipation.query.filter_by(user_id=user_id).all()

        total_participated = len(participations)
        total_completed = sum(1 for p in participations if p.is_completed)
        total_xp_earned = sum(p.xp_awarded for p in participations)

        # By type
        quests_by_type = {}
        for quest_type in QuestType:
            type_participations = [
                p for p in participations
                if p.quest.quest_type == quest_type
            ]
            quests_by_type[quest_type.value] = {
                "participated": len(type_participations),
                "completed": sum(1 for p in type_participations if p.is_completed)
            }

        # Recent completions
        recent_completions = QuestParticipation.query.filter_by(
            user_id=user_id,
            is_completed=True
        ).order_by(
            QuestParticipation.completed_at.desc()
        ).limit(5).all()

        return {
            "total_participated": total_participated,
            "total_completed": total_completed,
            "completion_rate": (
                (total_completed / total_participated * 100)
                if total_participated > 0 else 0.0
            ),
            "total_xp_earned": total_xp_earned,
            "quests_by_type": quests_by_type,
            "recent_completions": [p.quest for p in recent_completions]
        }

    @staticmethod
    def get_quest_leaderboard(quest_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get leaderboard for a specific quest.

        Args:
            quest_id: Quest ID
            limit: Max number of entries

        Returns:
            List of dicts with user progress:
            [
                {
                    "rank": int,
                    "user_id": int,
                    "username": str,
                    "progress": int,
                    "target": int,
                    "is_completed": bool
                },
                ...
            ]
        """
        participations = QuestParticipation.query.filter_by(
            quest_id=quest_id
        ).order_by(
            QuestParticipation.is_completed.desc(),
            QuestParticipation.current_progress.desc(),
            QuestParticipation.created_at.asc()
        ).limit(limit).all()

        results = []
        for rank, participation in enumerate(participations, 1):
            results.append({
                "rank": rank,
                "user_id": participation.user_id,
                "username": participation.user.username if participation.user else "Unknown",
                "progress": participation.current_progress,
                "target": participation.target_progress,
                "is_completed": participation.is_completed
            })

        return results

    @staticmethod
    def get_quest_statistics(quest_id: int) -> Dict[str, Any]:
        """
        Get detailed statistics for a quest.

        Args:
            quest_id: Quest ID

        Returns:
            {
                "quest": Quest,
                "participant_count": int,
                "completion_count": int,
                "completion_rate": float,
                "average_progress": float,
                "time_remaining": timedelta or None,
                "is_expired": bool
            }
        """
        quest = db.session.get(Quest, quest_id)
        if quest is None:
            raise ValueError(f"Quest {quest_id} not found")

        participations = QuestParticipation.query.filter_by(quest_id=quest_id).all()

        average_progress = 0.0
        if participations:
            total_progress_percentage = sum(
                min(100.0, p.current_progress / p.target_progress * 100)
                for p in participations
            )
            average_progress = total_progress_percentage / len(participations)

        now = datetime.utcnow()
        time_remaining = quest.end_date - now if quest.end_date > now else None
        is_expired = quest.status == QuestStatus.EXPIRED or quest.end_date < now

        return {
            "quest": quest,
            "participant_count": quest.participant_count,
            "completion_count": quest.completion_count,
            "completion_rate": (
                (quest.completion_count / quest.participant_count * 100)
                if quest.participant_count > 0 else 0.0
            ),
            "average_progress": round(average_progress, 1),
            "time_remaining": time_remaining,
            "is_expired": is_expired
        }
