"""
Gamification Recalc Service - rebuild a user's gamification state from scratch.

Primary use case: **user merge** (an account absorbs another). After the factual
records (matches, inscriptions, XP ledger, ...) have been reassigned to the kept
account, this service rebuilds the *derived* gamification state for that account.

Design choices (deliberate):

- **No domain events / notifications**. The gamification award path
  (``LevelService.award_xp`` / ``AchievementService.check_and_award_achievement``)
  emits ``XPGainedEvent`` / ``LevelUpEvent`` / ``AchievementUnlockedEvent`` which
  drive toasts and notifications. Replaying history through it would spam the
  user (and the admin doing the merge) with "level up!" toasts. So we recompute
  the models directly, reusing only the *pure* eligibility logic
  (``AchievementService._check_requirements``).

- **XP/level is exact** because the ``XPTransaction`` ledger is append-only and
  includes admin grants/adjustments that are NOT derivable from facts. We sum the
  ledger and derive level from the XP curve.

Known limitations (documented):

- **Streak freeze count is not reconstructible** (there is no freeze ledger), so
  ``freeze_count`` is reset to 0 on rebuild. ``current_streak`` reflects the run
  up to the last recorded activity (not decayed to "now"); the live service
  corrects it on the next activity.
- A few achievement ``requirement_type`` values are unimplemented placeholders in
  ``_check_requirements`` (e.g. ``win_streak``, ``unique_opponents``,
  ``category_reached``): those achievements won't auto-unlock on rebuild unless
  already unlocked (existing unlocks are preserved).
- ``WEEKLY_DRILL`` streaks are not rebuilt (challenge activity is not derived
  here) and are left untouched.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, or_

from models.base import db, utc_now
from models.transaction.manager import transactional
from models.gamification.models import (
    UserLevel,
    XPTransaction,
    Achievement,
    UserAchievement,
    StreakTracker,
    StreakType,
    QuestParticipation,
)
from models.gamification.xp_config import (
    get_level_from_total_xp,
    get_xp_for_level,
)
from models.gamification.achievement_service import AchievementService

logger = logging.getLogger(__name__)


class GamificationRecalcService:
    """Rebuild a user's derived gamification state from canonical data."""

    @staticmethod
    @transactional(domain="gamification")
    def rebuild_for_user(user_id: int) -> Dict[str, int]:
        """Rebuild level, achievements, streaks and quests for a single user.

        Runs without emitting domain events (see module docstring). Intended to
        be called inside a larger transaction (e.g. the user-merge flow); the
        ``@transactional`` decorator makes it a savepoint when nested.

        Returns a small report dict with counters.
        """
        # Order matters: level + streaks first, because some achievement
        # requirements read UserLevel (level_reached) and StreakTracker
        # (weekly_streak).
        level = GamificationRecalcService._rebuild_level(user_id)
        streaks = GamificationRecalcService._rebuild_streaks(user_id)
        unlocked = GamificationRecalcService._rebuild_achievements(user_id)
        quests = GamificationRecalcService._rebuild_quests(user_id)

        logger.info(
            "Gamification rebuild for user %s: level=%s, achievements_unlocked=%s, "
            "streaks=%s, quests=%s",
            user_id,
            level,
            unlocked,
            streaks,
            quests,
        )
        return {
            "current_level": level,
            "achievements_unlocked": unlocked,
            "streaks_rebuilt": streaks,
            "quests_recomputed": quests,
        }

    # ------------------------------------------------------------------ level

    @staticmethod
    def _rebuild_level(user_id: int) -> int:
        """Recompute UserLevel from the XPTransaction ledger (exact)."""
        total = (
            db.session.query(func.coalesce(func.sum(XPTransaction.xp_amount), 0))
            .filter(XPTransaction.user_id == user_id)
            .scalar()
        ) or 0
        total = max(0, int(total))

        level = get_level_from_total_xp(total)
        current_xp = total - get_xp_for_level(level)

        # Highest level ever reached: best signal is the max level_after in the
        # ledger (records the level after each award), floored at the current.
        max_after = (
            db.session.query(func.max(XPTransaction.level_after))
            .filter(XPTransaction.user_id == user_id)
            .scalar()
        ) or level

        user_level = db.session.get(UserLevel, user_id)
        if user_level is None:
            user_level = UserLevel(user_id=user_id)
            db.session.add(user_level)

        user_level.total_xp = total
        user_level.current_level = level
        user_level.current_xp = current_xp
        user_level.highest_level_reached = max(level, int(max_after), 1)
        db.session.flush()
        return level

    # ------------------------------------------------------------- achievements

    @staticmethod
    def _rebuild_achievements(user_id: int) -> int:
        """Re-evaluate achievement eligibility; unlock newly-qualifying ones.

        Existing unlocks are preserved. No XP is awarded and no event is emitted
        (the unlock XP, if any, is already in the reassigned ledger). Progressive
        achievements use their tracked ``current_progress``.
        """
        newly_unlocked = 0
        for ach in Achievement.query.filter_by(is_active=True).all():
            ua = UserAchievement.query.filter_by(
                user_id=user_id, achievement_id=ach.id
            ).first()
            if ua is None:
                ua = UserAchievement(
                    user_id=user_id, achievement_id=ach.id, current_progress=0
                )
                db.session.add(ua)

            if ua.is_unlocked:
                continue

            try:
                requirements = json.loads(ach.requirements)
            except (ValueError, TypeError):
                continue
            requirement_type = requirements.get("type")
            current_progress = ua.current_progress if ach.is_progressive else None

            if AchievementService._check_requirements(
                user_id=user_id,
                requirement_type=requirement_type,
                requirements=requirements,
                current_progress=current_progress,
            ):
                ua.is_unlocked = True
                ua.unlocked_at = utc_now()
                newly_unlocked += 1

        db.session.flush()
        return newly_unlocked

    # ----------------------------------------------------------------- streaks

    @staticmethod
    def _rebuild_streaks(user_id: int) -> int:
        """Rebuild current/longest streaks from activity timestamps.

        Reconstructs the set of ISO weeks (keyed by their Monday date) in which
        the user had a qualifying activity, then derives the longest consecutive
        run and the run ending at the most recent activity. ``freeze_count`` is
        reset (no freeze ledger exists). ``WEEKLY_DRILL`` is left untouched.
        """
        match_dates = GamificationRecalcService._match_activity_dates(user_id)
        tournament_dates = GamificationRecalcService._inscription_activity_dates(
            user_id
        )

        per_type = {
            StreakType.WEEKLY_MATCH: match_dates,
            StreakType.WEEKLY_TOURNAMENT: tournament_dates,
            StreakType.WEEKLY_ACTIVITY: match_dates + tournament_dates,
        }

        rebuilt = 0
        for streak_type, dates in per_type.items():
            current, longest, last_date = GamificationRecalcService._streak_from_dates(
                dates
            )
            tracker = StreakTracker.query.filter_by(
                user_id=user_id, streak_type=streak_type
            ).first()
            if tracker is None:
                if current == 0 and longest == 0:
                    continue  # nothing to record
                tracker = StreakTracker(user_id=user_id, streak_type=streak_type)
                db.session.add(tracker)

            tracker.current_streak = current
            tracker.longest_streak = longest
            tracker.freeze_count = 0
            tracker.total_freeze_earned = 0
            tracker.last_freeze_earned_at = None
            tracker.last_freeze_used_at = None
            tracker.milestone_4_reached = longest >= 4
            tracker.milestone_12_reached = longest >= 12
            tracker.milestone_52_reached = longest >= 52
            if last_date is not None:
                iso = last_date.isocalendar()
                tracker.last_activity_year = iso[0]
                tracker.last_activity_week = iso[1]
            else:
                tracker.last_activity_year = None
                tracker.last_activity_week = None
            rebuilt += 1

        db.session.flush()
        return rebuilt

    @staticmethod
    def _streak_from_dates(dates: List):
        """Return (current_streak, longest_streak, last_activity_date).

        ``current_streak`` is the run of consecutive weeks ending at the most
        recent activity week (not decayed to "now"; the live service corrects it
        on next activity).
        """
        if not dates:
            return 0, 0, None

        # Canonical week key = Monday of that date's week.
        weeks = sorted({d - timedelta(days=d.weekday()) for d in dates})
        last_date = max(dates)

        longest = 1
        run = 1
        for i in range(1, len(weeks)):
            if weeks[i] - weeks[i - 1] == timedelta(days=7):
                run += 1
            else:
                run = 1
            longest = max(longest, run)

        current = 1
        for i in range(len(weeks) - 1, 0, -1):
            if weeks[i] - weeks[i - 1] == timedelta(days=7):
                current += 1
            else:
                break

        return current, longest, last_date

    # ------------------------------------------------------------------ quests

    @staticmethod
    def _rebuild_quests(user_id: int) -> int:
        """Recompute progress of the user's quest participations from facts.

        For each participation, count the user's qualifying activity within the
        quest window ``[start_date, end_date]``. ``xp_awarded`` is left as-is (the
        award is already in the reassigned XP ledger).
        """
        recomputed = 0
        participations = QuestParticipation.query.filter_by(user_id=user_id).all()
        for qp in participations:
            quest = qp.quest
            if quest is None:
                continue
            try:
                requirements = json.loads(quest.requirements)
            except (ValueError, TypeError):
                continue
            activity_type = requirements.get("type")
            count = GamificationRecalcService._count_activity(
                user_id, activity_type, quest.start_date, quest.end_date
            )
            qp.current_progress = count
            if count >= qp.target_progress:
                if not qp.is_completed:
                    qp.is_completed = True
                    qp.completed_at = utc_now()
            else:
                qp.is_completed = False
                qp.completed_at = None
            recomputed += 1

        db.session.flush()
        return recomputed

    # --------------------------------------------------------------- factual data

    @staticmethod
    def _finished_matches(user_id: int):
        from models.match.models import Match
        from models.status_enum import MatchStatus

        return Match.query.filter(
            Match.status.in_(MatchStatus.finished_values()),
            or_(Match.player1_id == user_id, Match.player2_id == user_id),
        ).all()

    @staticmethod
    def _match_activity_dates(user_id: int) -> List:
        return [
            m.ended_at.date()
            for m in GamificationRecalcService._finished_matches(user_id)
            if m.ended_at is not None
        ]

    @staticmethod
    def _inscription_activity_dates(user_id: int) -> List:
        from models.competition.models import Inscription

        rows = Inscription.query.filter(Inscription.user_id == user_id).all()
        return [i.created_at.date() for i in rows if i.created_at is not None]

    @staticmethod
    def _count_activity(user_id: int, activity_type: Optional[str], start, end) -> int:
        """Count qualifying activity within ``[start, end]`` for a quest type.

        ``tournaments_completed`` uses the gara's ``updated_at`` as a proxy for
        its completion time (best-effort; there is no dedicated completion
        timestamp).
        """
        from models.match.models import Match
        from models.competition.models import Inscription, Gara
        from models.status_enum import MatchStatus, GaraStatus

        if activity_type in ("matches_played", "matches_won"):
            q = Match.query.filter(
                Match.status.in_(MatchStatus.finished_values()),
                Match.ended_at.isnot(None),
                Match.ended_at >= start,
                Match.ended_at <= end,
                or_(Match.player1_id == user_id, Match.player2_id == user_id),
            )
            if activity_type == "matches_won":
                q = q.filter(Match.winner_id == user_id)
            return q.count()

        if activity_type == "tournaments_registered":
            return Inscription.query.filter(
                Inscription.user_id == user_id,
                Inscription.created_at >= start,
                Inscription.created_at <= end,
            ).count()

        if activity_type == "tournaments_completed":
            return (
                db.session.query(Inscription)
                .join(Gara, Inscription.gara_id == Gara.id)
                .filter(
                    Inscription.user_id == user_id,
                    Inscription.is_withdrawn == False,  # noqa: E712
                    Gara.status == GaraStatus.COMPLETED.value,
                    Gara.updated_at >= start,
                    Gara.updated_at <= end,
                )
                .count()
            )

        return 0
