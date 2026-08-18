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
- Achievement eligibility is metric-driven (``AchievementMetrics``): every
  ``requirement_type`` now derives its value from the domain source of truth, so
  the rebuild is self-correcting. Existing unlocks are always preserved.
- ``WEEKLY_DRILL`` **is** rebuilt (since 2026-08-18) from drill attempts —
  catalogue, gara and exam — because those are the same three sources the live
  handlers record from.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

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
        (the unlock XP, if any, is already in the reassigned ledger). Eligibility
        is metric-driven: ``_check_requirements`` derives the current value from
        the domain source of truth (``AchievementMetrics``), so no progress
        counter is threaded in from here.
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

            if AchievementService._check_requirements(
                user_id=user_id,
                requirement_type=requirement_type,
                requirements=requirements,
            ):
                ua.is_unlocked = True
                ua.unlocked_at = utc_now()
                newly_unlocked += 1

        db.session.flush()
        return newly_unlocked

    # ------------------------------------------------- dopo una prova tolta

    #: Le metriche che dipendono dalle prove di un esercizio. Solo queste si
    #: rivalutano al ribasso: su un requisito booleano o legato a un evento
    #: irripetibile «non idoneo adesso» non vuol dire «non e' mai successo».
    DRILL_DEPENDENT_METRICS = ("challenges_completed", "perfect_challenges")

    @staticmethod
    @transactional(domain="gamification")
    def recompute_after_drill_removed(user_id: int) -> Dict[str, Any]:
        """Rimette in riga cio' che dipendeva da una prova appena cancellata.

        **Ricalcola, non sottrae.** La differenza e' tutto il punto: se altri
        esercizi reggono comunque la serie o il traguardo, non cambia niente.
        Sottrarre uno alla serie avrebbe punito chi si allena tutti i giorni per
        un tocco sbagliato, che e' il contrario di quello che serve.

        Due cose si toccano e una no:

        - **le serie settimanali** ``WEEKLY_DRILL`` e ``WEEKLY_ACTIVITY`` si
          ricostruiscono dalle settimane in cui l'attivita' c'e' *davvero*.
          ``WEEKLY_ACTIVITY`` si nutre anche di partite e iscrizioni: se la
          settimana resta viva per quelle, resta viva;
        - **i traguardi legati agli esercizi** si rivalutano, e cadono solo se
          il conto non li regge piu';
        - **congelamenti e traguardi di serie gia' raggiunti** restano dove
          sono. Un congelamento speso non si puo' rimettere nel cassetto, e
          ``milestone_*_reached`` serve a non riassegnarlo due volte: azzerarlo
          per un annulla aprirebbe un modo di guadagnarne uno nuovo.

        Ed e' anche il motivo per cui questo metodo non e' ``_rebuild_streaks``,
        che i congelamenti invece li azzera: quello ricostruisce un account dopo
        una fusione, qui si sta correggendo un tocco sbagliato.
        """
        per_type = GamificationRecalcService._activity_dates_by_streak(user_id)
        toccate = []

        for streak_type in (StreakType.WEEKLY_DRILL, StreakType.WEEKLY_ACTIVITY):
            tracker = StreakTracker.query.filter_by(
                user_id=user_id, streak_type=streak_type
            ).first()
            if tracker is None:
                continue  # non c'era niente da correggere

            current, longest, last_date = GamificationRecalcService._streak_from_dates(
                per_type.get(streak_type, [])
            )
            prima = tracker.current_streak
            tracker.current_streak = current
            # `longest_streak` puo' solo scendere fino al valore ricostruito: e'
            # un massimo storico, e qui la storia e' cambiata davvero.
            tracker.longest_streak = longest
            if last_date is not None:
                iso = last_date.isocalendar()
                tracker.last_activity_year = iso[0]
                tracker.last_activity_week = iso[1]
            else:
                tracker.last_activity_year = None
                tracker.last_activity_week = None
            if prima != current:
                toccate.append((streak_type.value, prima, current))

        from models.gamification.achievement_service import AchievementService

        tolti = AchievementService.revoke_no_longer_earned(
            user_id, GamificationRecalcService.DRILL_DEPENDENT_METRICS
        )

        db.session.flush()
        if toccate or tolti:
            logger.info(
                "Dopo una prova tolta (user %s): serie %s, traguardi tolti %s",
                user_id,
                toccate,
                tolti,
            )
        return {"streaks_changed": toccate, "achievements_revoked": tolti}

    # ----------------------------------------------------------------- streaks

    @staticmethod
    def _activity_dates_by_streak(user_id: int) -> Dict:
        """Le date che alimentano ciascuna serie, dalle fonti di verita'.

        Deve rispecchiare **esattamente** chi chiama
        ``StreakService.record_activity`` negli event handler: una sorgente
        dimenticata qui non produce un errore, produce una serie piu' corta di
        quella vera — e chi la guarda non ha modo di accorgersene.
        """
        match_dates = GamificationRecalcService._match_activity_dates(user_id)
        tournament_dates = GamificationRecalcService._inscription_activity_dates(
            user_id
        )
        drill_dates = GamificationRecalcService._drill_activity_dates(user_id)

        return {
            StreakType.WEEKLY_MATCH: match_dates,
            StreakType.WEEKLY_TOURNAMENT: tournament_dates,
            StreakType.WEEKLY_DRILL: drill_dates,
            StreakType.WEEKLY_ACTIVITY: match_dates + tournament_dates + drill_dates,
        }

    @staticmethod
    def _rebuild_streaks(user_id: int) -> int:
        """Rebuild current/longest streaks from activity timestamps.

        Reconstructs the set of ISO weeks (keyed by their Monday date) in which
        the user had a qualifying activity, then derives the longest consecutive
        run and the run ending at the most recent activity. ``freeze_count`` is
        reset (no freeze ledger exists).
        """
        per_type = GamificationRecalcService._activity_dates_by_streak(user_id)

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
    def _drill_activity_dates(user_id: int) -> List:
        """I giorni in cui l'utente ha completato un esercizio.

        Tre sorgenti, perche' «allenarsi» succede in tre posti e per la serie
        settimanale contano allo stesso modo: il catalogo, la gara (l'esercizio
        al posto dell'X) e l'esame — che e' a sua volta una sequenza di
        esercizi (ADR-042). Tenerne fuori uno vorrebbe dire dire al giocatore
        che allenarsi li' non e' allenarsi.
        """
        from models.challenge.models import ChallengeAttempt
        from models.competition.gara_challenge import GaraChallengeAttempt

        dates: List = []

        for attempt in ChallengeAttempt.query.filter(
            ChallengeAttempt.user_id == user_id,
            ChallengeAttempt.completed.is_(True),
        ).all():
            if attempt.attempted_at is not None:
                dates.append(attempt.attempted_at.date())

        for attempt in GaraChallengeAttempt.query.filter(
            GaraChallengeAttempt.user_id == user_id,
            GaraChallengeAttempt.completed.is_(True),
        ).all():
            when = getattr(attempt, "attempted_at", None) or getattr(
                attempt, "created_at", None
            )
            if when is not None:
                dates.append(when.date())

        return dates + GamificationRecalcService._exam_activity_dates(user_id)

    @staticmethod
    def _exam_activity_dates(user_id: int) -> List:
        """I giorni in cui l'utente ha concluso un esame."""
        from models.exam.models import ExamAttempt
        from models.status_enum import ExamAttemptStatus

        rows = ExamAttempt.query.filter(
            ExamAttempt.user_id == user_id,
            ExamAttempt.status == ExamAttemptStatus.COMPLETED.value,
        ).all()
        return [a.completed_at.date() for a in rows if a.completed_at is not None]

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
