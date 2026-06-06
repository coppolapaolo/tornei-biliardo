"""
Streak Service - Weekly Streak Tracking with Freeze Mechanics

Core service for tracking user activity streaks on a WEEKLY basis.
Designed for casual billiards players who play weekly, not daily.

Key Features:
- Weekly streak tracking using ISO week numbers (1-53)
- Freeze mechanics earned at milestones (4/12/52 weeks)
- Automatic freeze application when missing 1 week
- Streak break detection when missing 2+ weeks
- XP bonuses for streak milestones

All methods use @transactional decorator for automatic commit/rollback.
"""

from __future__ import annotations
from typing import Tuple, Optional, Dict, Any
from datetime import date
import logging

from models.base import db
from models.transaction.manager import transactional
from models.gamification.models import (
    StreakTracker,
    StreakType,
    XPTransactionType,
)
from models.gamification.xp_config import (
    FREEZE_MILESTONES_WEEKLY,
    MAX_FREEZE_COUNT,
)
from models.gamification.config_service import (
    GamificationConfigService as ConfigService,
)
from models.gamification.events import (
    StreakMilestoneEvent,
    StreakBrokenEvent,
    StreakFreezeUsedEvent,
)
from models.gamification.level_service import LevelService
from models.events.base import EventBus

logger = logging.getLogger(__name__)


class StreakService:
    """
    Service for weekly streak tracking and freeze management.

    Streak rules (WEEKLY, not daily):
    - Streak increments when activity occurs in consecutive weeks
    - Missing 1 week: auto-use freeze if available, streak preserved
    - Missing 2+ weeks: streak breaks regardless of freezes
    - Freeze earned at 4-week, 12-week (recurring), and 52-week milestones
    - Max 3 freezes can be held at once
    """

    @staticmethod
    def get_current_iso_week(for_date: Optional[date] = None) -> Tuple[int, int]:
        """
        Get ISO week number and year for a date.

        ISO week numbering:
        - Week 1 is the first week with at least 4 days in the new year
        - Week numbers range 1-53
        - Year may differ from calendar year at edges (Dec/Jan)

        Args:
            for_date: Date to check (defaults to today)

        Returns:
            Tuple of (iso_week_number, iso_year)

        Example:
            # December 31, 2024 may be week 1 of 2025 in ISO calendar
            week, year = StreakService.get_current_iso_week(date(2024, 12, 31))
        """
        check_date = for_date or date.today()
        iso_calendar = check_date.isocalendar()
        return iso_calendar.week, iso_calendar.year

    @staticmethod
    def weeks_between(
        week1: int, year1: int,
        week2: int, year2: int
    ) -> int:
        """
        Calculate weeks between two ISO week/year pairs.

        Handles year transitions correctly.

        Args:
            week1, year1: First ISO week/year (earlier date)
            week2, year2: Second ISO week/year (later date)

        Returns:
            Number of weeks between the dates

        Example:
            # Week 52 of 2023 to Week 1 of 2024 = 1 week
            diff = StreakService.weeks_between(52, 2023, 1, 2024)  # = 1
        """
        # Handle same year case
        if year1 == year2:
            return week2 - week1

        # Handle year transition
        # Week 52/53 to Week 1 of next year
        if year2 == year1 + 1:
            # Get last week of year1 (52 or 53)
            last_week_year1 = date(year1, 12, 28).isocalendar().week
            weeks_to_year_end = last_week_year1 - week1
            return weeks_to_year_end + week2

        # More than 1 year difference - calculate properly
        # This is rare but handles edge cases
        total_weeks = 0
        current_year = year1
        current_week = week1

        while current_year < year2:
            last_week = date(current_year, 12, 28).isocalendar().week
            total_weeks += last_week - current_week
            current_week = 0  # Reset for next year
            current_year += 1

        total_weeks += week2
        return total_weeks

    @staticmethod
    @transactional(domain="gamification")
    def record_activity(
        user_id: int,
        streak_type: StreakType,
        activity_date: Optional[date] = None
    ) -> Tuple[StreakTracker, Dict[str, Any]]:
        """
        Record weekly activity and update streak.

        This is the main entry point called when a user performs
        a trackable activity (match, tournament, drill).

        Logic:
        1. Get current ISO week
        2. If same week as last activity: no change (already counted)
        3. If consecutive week: increment streak
        4. If missed 1 week: use freeze if available
        5. If missed 2+ weeks: break streak
        6. Check for milestone rewards

        Args:
            user_id: User performing activity
            streak_type: Type of streak (WEEKLY_ACTIVITY, WEEKLY_MATCH, etc.)
            activity_date: Optional date (defaults to today)

        Returns:
            Tuple of (StreakTracker, result_info dict)

        Result info dict contains:
            - "action": "continued" | "incremented" | "freeze_used" | "broken" | "started"
            - "current_streak": int
            - "longest_streak": int
            - "milestone_reached": Optional[int] (4, 12, or 52 weeks)
            - "freeze_earned": int (0, 1, or 2)
            - "xp_bonus": int (XP awarded for milestone)

        Example:
            tracker, result = StreakService.record_activity(
                user_id=42,
                streak_type=StreakType.WEEKLY_MATCH
            )

            if result["action"] == "incremented":
                print(f"Streak now {result['current_streak']} weeks!")
        """
        # Skip gamification for admin users
        from models.user.models import User
        user = db.session.get(User, user_id)
        if user and user.is_admin:
            logger.debug(f"Skipping streak record for admin user {user_id}")
            return None, {"action": "skipped", "reason": "admin_user"}  # type: ignore

        current_week, current_year = StreakService.get_current_iso_week(activity_date)

        # Get or create streak tracker
        tracker = StreakTracker.query.filter_by(
            user_id=user_id,
            streak_type=streak_type
        ).first()

        if tracker is None:
            tracker = StreakTracker(
                user_id=user_id,
                streak_type=streak_type,
                current_streak=0,
                longest_streak=0,
                freeze_count=0,
                total_freeze_earned=0  # Explicit init before flush
            )
            db.session.add(tracker)
            db.session.flush()

        result = {
            "action": "started",
            "current_streak": 0,
            "longest_streak": 0,
            "milestone_reached": None,
            "freeze_earned": 0,
            "xp_bonus": 0,
        }

        # Case 1: First activity ever (no last_activity_week)
        if tracker.last_activity_week is None:
            tracker.current_streak = 1
            tracker.longest_streak = 1
            tracker.last_activity_week = current_week
            tracker.last_activity_year = current_year

            result["action"] = "started"
            result["current_streak"] = 1
            result["longest_streak"] = 1

            logger.info(f"User {user_id} started {streak_type.value} streak")
            return tracker, result

        # Calculate weeks since last activity
        weeks_diff = StreakService.weeks_between(
            tracker.last_activity_week,
            tracker.last_activity_year,
            current_week,
            current_year
        )

        # Case 2: Same week - already counted
        if weeks_diff == 0:
            result["action"] = "continued"
            result["current_streak"] = tracker.current_streak
            result["longest_streak"] = tracker.longest_streak
            return tracker, result

        # Case 3: Consecutive week - increment streak
        if weeks_diff == 1:
            tracker.current_streak += 1
            tracker.last_activity_week = current_week
            tracker.last_activity_year = current_year

            # Update longest streak
            if tracker.current_streak > tracker.longest_streak:
                tracker.longest_streak = tracker.current_streak

            result["action"] = "incremented"
            result["current_streak"] = tracker.current_streak
            result["longest_streak"] = tracker.longest_streak

            # Check for milestones
            milestone_result = StreakService._check_milestone_rewards(tracker)
            if milestone_result:
                result["milestone_reached"] = milestone_result["milestone"]
                result["freeze_earned"] = milestone_result["freeze_earned"]
                result["xp_bonus"] = milestone_result["xp_bonus"]

            logger.info(
                f"User {user_id} {streak_type.value} streak incremented to "
                f"{tracker.current_streak} weeks"
            )
            return tracker, result

        # Case 4: Missed exactly 1 week - try to use freeze
        if weeks_diff == 2:  # 2 weeks diff means 1 week gap
            if tracker.freeze_count > 0:
                # Use freeze
                tracker.freeze_count -= 1
                tracker.last_freeze_used_at = activity_date or date.today()
                tracker.current_streak += 1
                tracker.last_activity_week = current_week
                tracker.last_activity_year = current_year

                # Update longest streak
                if tracker.current_streak > tracker.longest_streak:
                    tracker.longest_streak = tracker.current_streak

                result["action"] = "freeze_used"
                result["current_streak"] = tracker.current_streak
                result["longest_streak"] = tracker.longest_streak

                # Emit freeze used event
                EventBus.publish(StreakFreezeUsedEvent(
                    user_id=user_id,
                    streak_type=streak_type.value,
                    current_streak=tracker.current_streak,
                    freezes_remaining=tracker.freeze_count
                ))

                # Check for milestones (streak still continued)
                milestone_result = StreakService._check_milestone_rewards(tracker)
                if milestone_result:
                    result["milestone_reached"] = milestone_result["milestone"]
                    result["freeze_earned"] = milestone_result["freeze_earned"]
                    result["xp_bonus"] = milestone_result["xp_bonus"]

                logger.info(
                    f"User {user_id} used freeze for {streak_type.value} streak, "
                    f"now {tracker.current_streak} weeks, {tracker.freeze_count} freezes left"
                )
                return tracker, result

        # Case 5: Missed 2+ weeks (or no freeze available) - break streak
        old_streak = tracker.current_streak
        tracker.current_streak = 1  # Start fresh
        tracker.last_activity_week = current_week
        tracker.last_activity_year = current_year

        result["action"] = "broken"
        result["current_streak"] = 1
        result["longest_streak"] = tracker.longest_streak

        # Emit streak broken event
        EventBus.publish(StreakBrokenEvent(
            user_id=user_id,
            streak_type=streak_type.value,
            streak_length=old_streak,
            no_freeze_available=tracker.freeze_count == 0
        ))

        logger.info(
            f"User {user_id} {streak_type.value} streak broken after "
            f"{old_streak} weeks (missed {weeks_diff - 1} weeks)"
        )
        return tracker, result

    @staticmethod
    def _check_milestone_rewards(tracker: StreakTracker) -> Optional[Dict[str, Any]]:
        """
        Check and award milestone rewards for streak.

        Milestones:
        - 4 weeks: 1 freeze (one-time)
        - 12 weeks: 1 freeze (first time + every 12 weeks)
        - 52 weeks: 2 freezes (one-time)

        Also awards XP bonus for milestones.

        Args:
            tracker: StreakTracker to check

        Returns:
            Dict with milestone info if milestone reached, None otherwise
        """
        current_streak = tracker.current_streak
        result = None

        # Check 4-week milestone (one-time)
        if current_streak >= 4 and not tracker.milestone_4_reached:
            tracker.milestone_4_reached = True
            freeze_earned = min(
                FREEZE_MILESTONES_WEEKLY[4]["freezes"],
                MAX_FREEZE_COUNT - tracker.freeze_count
            )
            tracker.freeze_count += freeze_earned
            tracker.total_freeze_earned += freeze_earned
            tracker.last_freeze_earned_at = date.today()

            # Award XP bonus
            xp_bonus = ConfigService.get_xp_rate(XPTransactionType.STREAK_BONUS) * 4  # 30 * 4 = 120 XP
            LevelService.award_xp(
                user_id=tracker.user_id,
                xp_amount=xp_bonus,
                transaction_type=XPTransactionType.STREAK_BONUS,
                reason=f"4-week streak milestone ({tracker.streak_type.value})"
            )

            result = {
                "milestone": 4,
                "freeze_earned": freeze_earned,
                "xp_bonus": xp_bonus,
            }

            # Emit milestone event
            EventBus.publish(StreakMilestoneEvent(
                user_id=tracker.user_id,
                streak_type=tracker.streak_type.value,
                milestone=4,
                current_streak=current_streak,
                freeze_earned=freeze_earned,
                xp_bonus=xp_bonus
            ))

            logger.info(
                f"User {tracker.user_id} reached 4-week milestone, "
                f"earned {freeze_earned} freeze(s) + {xp_bonus} XP"
            )

        # Check 12-week milestone (recurring)
        if current_streak >= 12 and not tracker.milestone_12_reached:
            tracker.milestone_12_reached = True
            freeze_earned = min(
                FREEZE_MILESTONES_WEEKLY[12]["freezes"],
                MAX_FREEZE_COUNT - tracker.freeze_count
            )
            tracker.freeze_count += freeze_earned
            tracker.total_freeze_earned += freeze_earned
            tracker.last_freeze_earned_at = date.today()

            xp_bonus = ConfigService.get_xp_rate(XPTransactionType.STREAK_BONUS) * 12  # 30 * 12 = 360 XP
            LevelService.award_xp(
                user_id=tracker.user_id,
                xp_amount=xp_bonus,
                transaction_type=XPTransactionType.STREAK_BONUS,
                reason=f"12-week streak milestone ({tracker.streak_type.value})"
            )

            result = {
                "milestone": 12,
                "freeze_earned": freeze_earned,
                "xp_bonus": xp_bonus,
            }

            EventBus.publish(StreakMilestoneEvent(
                user_id=tracker.user_id,
                streak_type=tracker.streak_type.value,
                milestone=12,
                current_streak=current_streak,
                freeze_earned=freeze_earned,
                xp_bonus=xp_bonus
            ))

        # Check recurring 12-week milestones (24, 36, 48, 60, etc.)
        if current_streak > 12 and current_streak % 12 == 0:
            freeze_earned = min(
                FREEZE_MILESTONES_WEEKLY[12]["freezes"],
                MAX_FREEZE_COUNT - tracker.freeze_count
            )
            if freeze_earned > 0:
                tracker.freeze_count += freeze_earned
                tracker.total_freeze_earned += freeze_earned
                tracker.last_freeze_earned_at = date.today()

            xp_bonus = ConfigService.get_xp_rate(XPTransactionType.STREAK_BONUS) * 12
            LevelService.award_xp(
                user_id=tracker.user_id,
                xp_amount=xp_bonus,
                transaction_type=XPTransactionType.STREAK_BONUS,
                reason=f"{current_streak}-week streak milestone ({tracker.streak_type.value})"
            )

            result = {
                "milestone": current_streak,
                "freeze_earned": freeze_earned,
                "xp_bonus": xp_bonus,
            }

            EventBus.publish(StreakMilestoneEvent(
                user_id=tracker.user_id,
                streak_type=tracker.streak_type.value,
                milestone=current_streak,
                current_streak=current_streak,
                freeze_earned=freeze_earned,
                xp_bonus=xp_bonus
            ))

        # Check 52-week milestone (one-time)
        if current_streak >= 52 and not tracker.milestone_52_reached:
            tracker.milestone_52_reached = True
            freeze_earned = min(
                FREEZE_MILESTONES_WEEKLY[52]["freezes"],
                MAX_FREEZE_COUNT - tracker.freeze_count
            )
            tracker.freeze_count += freeze_earned
            tracker.total_freeze_earned += freeze_earned
            tracker.last_freeze_earned_at = date.today()

            xp_bonus = ConfigService.get_xp_rate(XPTransactionType.STREAK_BONUS) * 52  # 30 * 52 = 1560 XP
            LevelService.award_xp(
                user_id=tracker.user_id,
                xp_amount=xp_bonus,
                transaction_type=XPTransactionType.STREAK_BONUS,
                reason=f"52-week streak milestone ({tracker.streak_type.value})"
            )

            result = {
                "milestone": 52,
                "freeze_earned": freeze_earned,
                "xp_bonus": xp_bonus,
            }

            EventBus.publish(StreakMilestoneEvent(
                user_id=tracker.user_id,
                streak_type=tracker.streak_type.value,
                milestone=52,
                current_streak=current_streak,
                freeze_earned=freeze_earned,
                xp_bonus=xp_bonus
            ))

            logger.info(
                f"User {tracker.user_id} reached 52-week milestone! "
                f"Earned {freeze_earned} freeze(s) + {xp_bonus} XP"
            )

        return result

    @staticmethod
    def get_streak_info(
        user_id: int,
        streak_type: StreakType
    ) -> Dict[str, Any]:
        """
        Get streak information for display.

        Args:
            user_id: User ID
            streak_type: Type of streak

        Returns:
            Dict with streak display data:
            {
                "current_streak": int,
                "longest_streak": int,
                "freeze_count": int,
                "last_activity_week": int or None,
                "last_activity_year": int or None,
                "is_at_risk": bool (True if 1 week from breaking),
                "weeks_until_break": int (0 if already needs activity this week),
                "next_milestone": int or None,
                "milestones_reached": List[int]
            }
        """
        tracker = StreakTracker.query.filter_by(
            user_id=user_id,
            streak_type=streak_type
        ).first()

        if tracker is None:
            return {
                "current_streak": 0,
                "longest_streak": 0,
                "freeze_count": 0,
                "last_activity_week": None,
                "last_activity_year": None,
                "is_at_risk": False,
                "weeks_until_break": 0,
                "next_milestone": 4,
                "milestones_reached": []
            }

        current_week, current_year = StreakService.get_current_iso_week()

        # Calculate weeks since last activity
        weeks_since = 0
        if tracker.last_activity_week is not None:
            weeks_since = StreakService.weeks_between(
                tracker.last_activity_week,
                tracker.last_activity_year,
                current_week,
                current_year
            )

        # Determine risk status
        is_at_risk = weeks_since >= 1 and tracker.freeze_count == 0
        weeks_until_break = max(0, 2 - weeks_since)  # Break at 2 weeks gap
        if tracker.freeze_count > 0:
            weeks_until_break = max(0, 2 - weeks_since)  # Freeze buys 1 extra week

        # Calculate next milestone
        current_streak = tracker.current_streak
        milestones = [4, 12, 24, 36, 48, 52, 60, 72]  # Continue pattern
        next_milestone = None
        for m in milestones:
            if m > current_streak:
                next_milestone = m
                break

        # Collect reached milestones
        milestones_reached = []
        if tracker.milestone_4_reached:
            milestones_reached.append(4)
        if tracker.milestone_12_reached:
            milestones_reached.append(12)
        if tracker.milestone_52_reached:
            milestones_reached.append(52)

        return {
            "current_streak": tracker.current_streak,
            "longest_streak": tracker.longest_streak,
            "freeze_count": tracker.freeze_count,
            "last_activity_week": tracker.last_activity_week,
            "last_activity_year": tracker.last_activity_year,
            "is_at_risk": is_at_risk,
            "weeks_until_break": weeks_until_break,
            "next_milestone": next_milestone,
            "milestones_reached": milestones_reached
        }

    @staticmethod
    def get_all_streaks(user_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Get all streak types for a user.

        Args:
            user_id: User ID

        Returns:
            Dict mapping streak type value to streak info

        Example:
            streaks = StreakService.get_all_streaks(user_id=42)
            # {
            #     "weekly_activity": {"current_streak": 5, ...},
            #     "weekly_match": {"current_streak": 3, ...},
            #     ...
            # }
        """
        result = {}
        for streak_type in StreakType:
            result[streak_type.value] = StreakService.get_streak_info(
                user_id=user_id,
                streak_type=streak_type
            )
        return result

    @staticmethod
    @transactional(domain="gamification")
    def admin_grant_freeze(
        user_id: int,
        streak_type: StreakType,
        freeze_count: int = 1,
        reason: str = "Admin grant"
    ) -> Tuple[StreakTracker, bool]:
        """
        Admin method to manually grant freezes.

        Args:
            user_id: User ID
            streak_type: Type of streak
            freeze_count: Number of freezes to grant
            reason: Reason for grant (audit trail)

        Returns:
            Tuple of (StreakTracker, success: bool)
        """
        tracker = StreakTracker.query.filter_by(
            user_id=user_id,
            streak_type=streak_type
        ).first()

        if tracker is None:
            tracker = StreakTracker(
                user_id=user_id,
                streak_type=streak_type,
                current_streak=0,
                longest_streak=0,
                freeze_count=0,
                total_freeze_earned=0  # Explicit init before flush
            )
            db.session.add(tracker)
            db.session.flush()  # Apply defaults before arithmetic

        freezes_to_add = min(freeze_count, MAX_FREEZE_COUNT - tracker.freeze_count)
        if freezes_to_add <= 0:
            logger.warning(
                f"User {user_id} already at max freezes ({MAX_FREEZE_COUNT})"
            )
            return tracker, False

        tracker.freeze_count += freezes_to_add
        tracker.total_freeze_earned += freezes_to_add
        tracker.last_freeze_earned_at = date.today()

        logger.info(
            f"Admin granted {freezes_to_add} freeze(s) to user {user_id} "
            f"for {streak_type.value}: {reason}"
        )

        return tracker, True
