"""
Module: models/kpi/services.py
Purpose: KPI calculation and metrics service
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from sqlalchemy import func, and_, or_

from ..base import db
from ..transaction.manager import transactional
from .models import KpiFeatureUsage, KpiDailySnapshot, KpiMilestone
from .enums import (
    FeatureName,
    MilestoneType,
    AlertType,
    USER_MILESTONES,
    MATCH_MILESTONES,
    GARA_MILESTONES,
)


@dataclass
class MetricWithTrend:
    """A metric value with trend comparison."""

    current: int | float
    previous: int | float
    trend_percent: float
    trend_direction: str  # "up", "down", "stable"


@dataclass
class DateRange:
    """Date range for queries. None means unbounded in that direction."""

    start: Optional[date]
    end: Optional[date]

    @classmethod
    def last_n_days(cls, days: int) -> "DateRange":
        """Create a date range for the last N days."""
        end = date.today()
        start = end - timedelta(days=days - 1)
        return cls(start=start, end=end)

    @classmethod
    def custom(
        cls, start: Optional[date] = None, end: Optional[date] = None
    ) -> "DateRange":
        """Create a custom date range. None means unbounded."""
        return cls(start=start, end=end)

    @classmethod
    def previous_period(cls, current: "DateRange") -> "DateRange":
        """Get the previous period of same length."""
        if current.start is None or current.end is None:
            # Can't calculate previous period without bounds
            return cls(start=None, end=None)
        length = (current.end - current.start).days + 1
        end = current.start - timedelta(days=1)
        start = end - timedelta(days=length - 1)
        return cls(start=start, end=end)

    @property
    def is_bounded(self) -> bool:
        """Check if both start and end are defined."""
        return self.start is not None and self.end is not None

    def get_display_label(self) -> str:
        """Get human-readable label for this range."""
        if self.start is None and self.end is None:
            return "Tutto"
        elif self.start is None:
            return f"Fino al {self.end.strftime('%d/%m/%Y')}" if self.end else "Tutto"
        elif self.end is None:
            return f"Dal {self.start.strftime('%d/%m/%Y')}"
        else:
            return f"{self.start.strftime('%d/%m/%Y')} - {self.end.strftime('%d/%m/%Y')}"


def _build_date_filters(
    date_column: Any, date_range: Optional[DateRange]
) -> List[Any]:
    """Build SQLAlchemy filter conditions for date range.

    Handles Optional dates - returns empty list if no filters needed.
    """
    filters = []
    if date_range:
        if date_range.start is not None:
            filters.append(date_column >= date_range.start)
        if date_range.end is not None:
            filters.append(date_column <= date_range.end)
    return filters


class KpiService:
    """Service for calculating and retrieving KPI metrics."""

    # ========== ACQUISITION METRICS ==========

    @staticmethod
    def get_total_users() -> int:
        """Get total registered users (excluding deleted)."""
        from ..user.models import User

        return User.query.filter(User.deleted_at.is_(None)).count()

    @staticmethod
    def get_new_users(date_range: Optional[DateRange]) -> int:
        """Get count of new users in date range."""
        from ..user.models import User

        filters = [User.deleted_at.is_(None)]  # noqa: E712
        filters.extend(_build_date_filters(func.date(User.created_at), date_range))
        return User.query.filter(and_(*filters)).count()

    @staticmethod
    def get_new_users_trend(date_range: Optional[DateRange]) -> MetricWithTrend:
        """Get new users with trend comparison."""
        current = KpiService.get_new_users(date_range)
        if date_range and date_range.is_bounded:
            prev_range = DateRange.previous_period(date_range)
            previous = KpiService.get_new_users(prev_range)
        else:
            previous = 0  # No trend comparison for unbounded ranges
        return KpiService._calculate_trend(current, previous)

    @staticmethod
    def get_daily_registrations(date_range: Optional[DateRange]) -> List[Dict[str, Any]]:
        """Get daily registration counts for charting."""
        from ..user.models import User

        filters = [User.deleted_at.is_(None)]  # noqa: E712
        filters.extend(_build_date_filters(func.date(User.created_at), date_range))

        results = (
            db.session.query(
                func.date(User.created_at).label("date"),
                func.count(User.id).label("count"),
            )
            .filter(and_(*filters))
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
            .all()
        )

        return [{"date": str(r.date), "count": r.count} for r in results]

    # ========== ACTIVATION METRICS ==========

    @staticmethod
    def get_activation_rate() -> float:
        """Get % of users who have played at least 1 match."""
        from ..user.models import User
        from ..match.models import Match

        total_users = User.query.filter(User.deleted_at.is_(None)).count()
        if total_users == 0:
            return 0.0

        users_with_matches = (
            db.session.query(func.count(func.distinct(Match.player1_id)))
            .filter(Match.status == "completed")
            .scalar()
            or 0
        )

        users_with_matches_p2 = (
            db.session.query(func.count(func.distinct(Match.player2_id)))
            .filter(Match.status == "completed")
            .scalar()
            or 0
        )

        # Approximate unique players (not perfect but fast)
        unique_players = min(users_with_matches + users_with_matches_p2, total_users)
        return round((unique_players / total_users) * 100, 1)

    @staticmethod
    def get_dormant_users_count() -> int:
        """Get count of users registered but never played a match."""
        from ..user.models import User
        from ..match.models import Match

        # Get all user IDs who have played at least one match
        player_ids = set()

        players_as_p1 = (
            db.session.query(Match.player1_id)
            .filter(Match.player1_id.isnot(None))
            .distinct()
            .all()
        )
        players_as_p2 = (
            db.session.query(Match.player2_id)
            .filter(Match.player2_id.isnot(None))
            .distinct()
            .all()
        )

        for (pid,) in players_as_p1:
            player_ids.add(pid)
        for (pid,) in players_as_p2:
            player_ids.add(pid)

        total_users = User.query.filter(User.deleted_at.is_(None)).count()
        return total_users - len(player_ids)

    # ========== RETENTION METRICS ==========

    @staticmethod
    def get_active_users_count(days: int) -> int:
        """Get count of users active in last N days (based on match activity)."""
        from ..match.models import Match

        cutoff = datetime.utcnow() - timedelta(days=days)

        # Users who played a match in the period
        active_p1 = (
            db.session.query(func.count(func.distinct(Match.player1_id)))
            .filter(
                and_(
                    Match.updated_at >= cutoff,
                    Match.status == "completed",
                    Match.player1_id.isnot(None),
                )
            )
            .scalar()
            or 0
        )

        active_p2 = (
            db.session.query(func.count(func.distinct(Match.player2_id)))
            .filter(
                and_(
                    Match.updated_at >= cutoff,
                    Match.status == "completed",
                    Match.player2_id.isnot(None),
                )
            )
            .scalar()
            or 0
        )

        return active_p1 + active_p2

    @staticmethod
    def get_dau() -> int:
        """Get Daily Active Users."""
        return KpiService.get_active_users_count(1)

    @staticmethod
    def get_wau() -> int:
        """Get Weekly Active Users."""
        return KpiService.get_active_users_count(7)

    @staticmethod
    def get_mau() -> int:
        """Get Monthly Active Users."""
        return KpiService.get_active_users_count(30)

    @staticmethod
    def get_retention_rate(days: int) -> float:
        """Get retention rate: % of users who returned after N days from registration."""
        from ..user.models import User
        from ..match.models import Match

        cutoff_registration = datetime.utcnow() - timedelta(days=days * 2)
        cutoff_activity = datetime.utcnow() - timedelta(days=days)

        # Users registered before cutoff_registration
        eligible_users = User.query.filter(
            and_(
                User.deleted_at.is_(None),
                User.created_at <= cutoff_registration,
            )
        ).all()

        if not eligible_users:
            return 0.0

        eligible_ids = [u.id for u in eligible_users]

        # Count how many have activity after their registration + N days
        retained_count = 0
        for user in eligible_users:
            activity_after = user.created_at + timedelta(days=days)
            has_activity = Match.query.filter(
                and_(
                    or_(Match.player1_id == user.id, Match.player2_id == user.id),
                    Match.updated_at >= activity_after,
                    Match.status == "completed",
                )
            ).first()
            if has_activity:
                retained_count += 1

        return round((retained_count / len(eligible_ids)) * 100, 1)

    # ========== ENGAGEMENT METRICS ==========

    @staticmethod
    def get_total_matches() -> int:
        """Get total completed matches."""
        from ..match.models import Match

        return Match.query.filter_by(status="completed").count()

    @staticmethod
    def get_matches_in_period(date_range: Optional[DateRange]) -> int:
        """Get matches completed in date range."""
        from ..match.models import Match

        filters = [Match.status == "completed"]
        filters.extend(_build_date_filters(func.date(Match.updated_at), date_range))
        return Match.query.filter(and_(*filters)).count()

    @staticmethod
    def get_matches_trend(date_range: Optional[DateRange]) -> MetricWithTrend:
        """Get matches with trend comparison."""
        current = KpiService.get_matches_in_period(date_range)
        if date_range and date_range.is_bounded:
            prev_range = DateRange.previous_period(date_range)
            previous = KpiService.get_matches_in_period(prev_range)
        else:
            previous = 0  # No trend comparison for unbounded ranges
        return KpiService._calculate_trend(current, previous)

    @staticmethod
    def get_daily_matches(date_range: Optional[DateRange]) -> List[Dict[str, Any]]:
        """Get daily match counts for charting."""
        from ..match.models import Match

        filters = [Match.status == "completed"]
        filters.extend(_build_date_filters(func.date(Match.updated_at), date_range))

        results = (
            db.session.query(
                func.date(Match.updated_at).label("date"),
                func.count(Match.id).label("count"),
            )
            .filter(and_(*filters))
            .group_by(func.date(Match.updated_at))
            .order_by(func.date(Match.updated_at))
            .all()
        )

        return [{"date": str(r.date), "count": r.count} for r in results]

    @staticmethod
    def get_active_gare_count() -> int:
        """Get count of currently active gare (status = playing)."""
        from ..competition.models import Gara

        return Gara.query.filter_by(status="playing").count()

    @staticmethod
    def get_completed_gare_count(date_range: Optional[DateRange] = None) -> int:
        """Get count of completed gare."""
        from ..competition.models import Gara

        filters = [Gara.status == "completed"]
        filters.extend(_build_date_filters(Gara.date, date_range))
        return Gara.query.filter(and_(*filters)).count()

    @staticmethod
    def get_avg_user_level() -> float:
        """Get average user level (gamification)."""
        from ..gamification.models import UserLevel

        result = db.session.query(func.avg(UserLevel.current_level)).scalar()
        return round(result or 1.0, 1)

    @staticmethod
    def get_total_xp_in_period(date_range: Optional[DateRange]) -> int:
        """Get total XP awarded in period."""
        from ..gamification.models import XPTransaction

        filters = _build_date_filters(func.date(XPTransaction.created_at), date_range)
        query = db.session.query(func.sum(XPTransaction.xp_amount))
        if filters:
            query = query.filter(and_(*filters))
        result = query.scalar()
        return result or 0

    @staticmethod
    def get_matches_per_active_user(date_range: Optional[DateRange]) -> float:
        """Get average matches per active user."""
        matches = KpiService.get_matches_in_period(date_range)
        # Calculate days for active user query
        if date_range and date_range.is_bounded:
            days = (date_range.end - date_range.start).days + 1  # type: ignore
        else:
            days = 30  # Default to 30 days for unbounded ranges
        active_users = KpiService.get_active_users_count(days)
        if active_users == 0:
            return 0.0
        return round(matches / active_users, 1)

    # ========== FEATURE ADOPTION ==========

    @staticmethod
    def get_feature_usage(date_range: Optional[DateRange]) -> List[Dict[str, Any]]:
        """Get feature usage stats for all features."""
        results = []

        # Get current period usage
        filters = _build_date_filters(KpiFeatureUsage.date, date_range)
        query = db.session.query(
            KpiFeatureUsage.feature_name,
            func.sum(KpiFeatureUsage.usage_count).label("usage"),
            func.sum(KpiFeatureUsage.unique_users).label("unique"),
        )
        if filters:
            query = query.filter(and_(*filters))
        current_usage = query.group_by(KpiFeatureUsage.feature_name).all()

        usage_map = {r.feature_name: (r.usage or 0, r.unique or 0) for r in current_usage}

        # Get previous period for trend (only if bounded range)
        prev_map: Dict[str, int] = {}
        if date_range and date_range.is_bounded:
            prev_range = DateRange.previous_period(date_range)
            prev_filters = _build_date_filters(KpiFeatureUsage.date, prev_range)
            prev_query = db.session.query(
                KpiFeatureUsage.feature_name,
                func.sum(KpiFeatureUsage.usage_count).label("usage"),
            )
            if prev_filters:
                prev_query = prev_query.filter(and_(*prev_filters))
            prev_usage = prev_query.group_by(KpiFeatureUsage.feature_name).all()
            prev_map = {r.feature_name: r.usage or 0 for r in prev_usage}

        # Calculate total for percentage
        total_usage = sum(u for u, _ in usage_map.values())

        # Build results for all features
        for feature in FeatureName:
            current, unique = usage_map.get(feature.value, (0, 0))
            previous = prev_map.get(feature.value, 0)
            trend = KpiService._calculate_trend(current, previous)

            results.append(
                {
                    "feature_name": feature.value,
                    "feature_label": KpiService._get_feature_label(feature),
                    "usage_count": current,
                    "unique_users": unique,
                    "trend_percent": trend.trend_percent,
                    "trend_direction": trend.trend_direction,
                    "percentage": round((current / total_usage * 100), 1)
                    if total_usage > 0
                    else 0,
                }
            )

        # Sort by usage descending
        results.sort(key=lambda x: x["usage_count"], reverse=True)
        return results

    # ========== PANORAMICA (OVERVIEW) ==========

    @staticmethod
    def get_overview_metrics(date_range: Optional[DateRange]) -> Dict[str, Any]:
        """Get all overview metrics for the dashboard."""
        return {
            "total_users": KpiService.get_total_users(),
            "new_users": KpiService.get_new_users_trend(date_range),
            "matches_played": KpiService.get_matches_trend(date_range),
            "active_gare": KpiService.get_active_gare_count(),
            "activation_rate": KpiService.get_activation_rate(),
            "mau": KpiService.get_mau(),
        }

    # ========== MILESTONE CHECKING ==========

    @staticmethod
    @transactional(domain="kpi")
    def check_and_record_milestones() -> List[Tuple[MilestoneType, int]]:
        """Check for new milestones and record them. Returns newly reached milestones."""
        newly_reached = []

        # Check user milestones
        total_users = KpiService.get_total_users()
        for threshold in USER_MILESTONES:
            if total_users >= threshold and not KpiMilestone.is_reached(
                MilestoneType.USERS_TOTAL, threshold
            ):
                KpiMilestone.mark_reached(MilestoneType.USERS_TOTAL, threshold)
                newly_reached.append((MilestoneType.USERS_TOTAL, threshold))

        # Check match milestones
        total_matches = KpiService.get_total_matches()
        for threshold in MATCH_MILESTONES:
            if total_matches >= threshold and not KpiMilestone.is_reached(
                MilestoneType.MATCHES_TOTAL, threshold
            ):
                KpiMilestone.mark_reached(MilestoneType.MATCHES_TOTAL, threshold)
                newly_reached.append((MilestoneType.MATCHES_TOTAL, threshold))

        # Check gara milestones
        from ..competition.models import Gara

        completed_gare = Gara.query.filter_by(status="completed").count()
        for threshold in GARA_MILESTONES:
            if completed_gare >= threshold and not KpiMilestone.is_reached(
                MilestoneType.GARE_COMPLETED, threshold
            ):
                KpiMilestone.mark_reached(MilestoneType.GARE_COMPLETED, threshold)
                newly_reached.append((MilestoneType.GARE_COMPLETED, threshold))

        return newly_reached

    # ========== ACTIVITY ALERTS ==========

    @staticmethod
    def check_activity_alerts() -> List[AlertType]:
        """Check for activity drop alerts. Returns triggered alerts."""
        from ..match.models import Match
        from ..user.models import User

        alerts = []

        # Check last match date
        last_match = (
            Match.query.filter_by(status="completed")
            .order_by(Match.updated_at.desc())
            .first()
        )

        if last_match:
            days_since_match = (datetime.utcnow() - last_match.updated_at).days
            if days_since_match >= 7:
                alerts.append(AlertType.NO_MATCH_7_DAYS)
            elif days_since_match >= 3:
                alerts.append(AlertType.NO_MATCH_3_DAYS)

        # Check last registration
        last_user = (
            User.query.filter(User.deleted_at.is_(None))
            .order_by(User.created_at.desc())
            .first()
        )

        if last_user:
            days_since_registration = (datetime.utcnow() - last_user.created_at).days
            if days_since_registration >= 7:
                alerts.append(AlertType.NO_REGISTRATION_7_DAYS)

        return alerts

    # ========== HELPER METHODS ==========

    @staticmethod
    def _calculate_trend(current: int | float, previous: int | float) -> MetricWithTrend:
        """Calculate trend between two values."""
        if previous == 0:
            if current > 0:
                trend_percent = 100.0
                trend_direction = "up"
            else:
                trend_percent = 0.0
                trend_direction = "stable"
        else:
            trend_percent = round(((current - previous) / previous) * 100, 1)
            if trend_percent > 5:
                trend_direction = "up"
            elif trend_percent < -5:
                trend_direction = "down"
            else:
                trend_direction = "stable"

        return MetricWithTrend(
            current=current,
            previous=previous,
            trend_percent=trend_percent,
            trend_direction=trend_direction,
        )

    @staticmethod
    def _get_feature_label(feature: FeatureName) -> str:
        """Get human-readable label for a feature."""
        labels = {
            FeatureName.GARA_INSCRIPTION: "Iscrizione gara",
            FeatureName.GARA_CREATE: "Creazione gara",
            FeatureName.GARA_VIEW_CLASSIFICATION: "Visualizzazione classifica",
            FeatureName.MATCH_GARA_PLAYED: "Match di gara",
            FeatureName.MATCH_INDIVIDUAL_CREATE: "Proposta match individuale",
            FeatureName.MATCH_INDIVIDUAL_ACCEPT: "Accettazione match individuale",
            FeatureName.MATCH_RESULT_SUBMIT: "Inserimento risultato",
            FeatureName.CHALLENGE_SEND: "Invio sfida",
            FeatureName.CHALLENGE_ACCEPT: "Accettazione sfida",
            FeatureName.AVAILABILITY_SIGNAL: "Segnalazione disponibilità",
            FeatureName.ACHIEVEMENT_VIEW: "Visualizzazione achievement",
            FeatureName.LEADERBOARD_XP_VIEW: "Visualizzazione classifica XP",
            FeatureName.PROFILE_STATS_VIEW: "Visualizzazione statistiche profilo",
            FeatureName.DRILL_COMPLETE: "Completamento drill",
            FeatureName.DRILL_START: "Avvio drill",
        }
        return labels.get(feature, feature.value)
    # ========== BUSINESS & COMMUNITY KPIs ==========

    @staticmethod
    def get_director_performance() -> List[Dict[str, Any]]:
        """
        Get performance metrics for tournament directors.
        Metrics:
        - Volume: Number of Garas managed
        - Saturation: Avg (Inscriptions / Max Participants) * 100
        """
        from ..user.models import User, DirectorAssignment
        from ..competition.models import Gara, Inscription

        # 1. Get all users who are directors (or admins acting as directors)
        # We look for explicit assignments or admins who created garas
        # For simplicity in this iteration, we focus on users with 'director' role
        # or who have entries in DirectorAssignment
        
        # Get active director assignments
        assignments = DirectorAssignment.query.all()
        director_ids = set(a.user_id for a in assignments)
        
        # Also include anyone who is a director_id on a Gara (direct link)
        garas_with_directors = Gara.query.filter(Gara.director_id.isnot(None)).all()
        for g in garas_with_directors:
            if g.director_id:
                director_ids.add(g.director_id)
                
        results = []
        
        for d_id in director_ids:
            director = User.query.get(d_id)
            if not director:
                continue
                
            # Find garas managed by this director
            # 1. Direct assignment
            managed_garas = Gara.query.filter_by(director_id=d_id).all()
            
            # 2. Assignment via Campionato (simplified for now: if assigned to Campionato, manages all its garas)
            camp_assignments = DirectorAssignment.query.filter_by(
                user_id=d_id, entity_type="campionato"
            ).all()
            
            for ca in camp_assignments:
                if ca.campionato:
                    managed_garas.extend(ca.campionato.gare)
                    
            # 3. Assignment via Gara (explicit)
            gara_assignments = DirectorAssignment.query.filter_by(
                user_id=d_id, entity_type="gara"
            ).all()
            
            for ga in gara_assignments:
                if ga.gara and ga.gara not in managed_garas:
                    managed_garas.append(ga.gara)
            
            # De-duplicate
            managed_garas = list(set(managed_garas))
            
            if not managed_garas:
                continue
                
            # Calculate metrics
            total_garas = len(managed_garas)
            completed_garas = sum(1 for g in managed_garas if g.status == "completed")
            
            # Saturation
            saturation_sum = 0.0
            saturation_count = 0
            
            for g in managed_garas:
                if g.max_participants and g.max_participants > 0:
                    insc_count = len(g.inscriptions)
                    saturation = min((insc_count / g.max_participants) * 100, 100.0)
                    saturation_sum += saturation
                    saturation_count += 1
            
            avg_saturation = (
                round(saturation_sum / saturation_count, 1) if saturation_count > 0 else 0.0
            )
            
            results.append({
                "director_id": director.id,
                "director_name": director.username,
                "total_garas": total_garas,
                "completed_garas": completed_garas,
                "avg_saturation": avg_saturation
            })
            
        # Sort by best saturation
        results.sort(key=lambda x: x["avg_saturation"], reverse=True)
        return results

    @staticmethod
    def get_community_health() -> Dict[str, Any]:
        """
        Get community health metrics: Stickiness, Virality, Churn.
        """
        from ..match.models import Match
        
        # 1. Stickiness: DAU / MAU
        dau = KpiService.get_dau()
        mau = KpiService.get_mau()
        stickiness = round((dau / mau * 100), 1) if mau > 0 else 0.0
        
        # 2. Real Churn: Users active last month (30-60d ago) but NOT active this month (0-30d)
        today = datetime.utcnow()
        thirty_days_ago = today - timedelta(days=30)
        sixty_days_ago = today - timedelta(days=60)
        
        # Users active 30-60 days ago
        active_last_month = (
            db.session.query(Match.player1_id)
            .filter(
                Match.updated_at >= sixty_days_ago,
                Match.updated_at < thirty_days_ago,
                Match.status == "completed"
            )
            .union(
                db.session.query(Match.player2_id)
                .filter(
                    Match.updated_at >= sixty_days_ago,
                    Match.updated_at < thirty_days_ago,
                    Match.status == "completed"
                )
            ).distinct().all()
        )
        prev_active_ids = {r[0] for r in active_last_month if r[0]}
        
        # Users active last 30 days
        active_this_month = (
            db.session.query(Match.player1_id)
            .filter(
                Match.updated_at >= thirty_days_ago,
                Match.status == "completed"
            )
            .union(
                db.session.query(Match.player2_id)
                .filter(
                    Match.updated_at >= thirty_days_ago,
                    Match.status == "completed"
                )
            ).distinct().all()
        )
        curr_active_ids = {r[0] for r in active_this_month if r[0]}
        
        # Churned = In PREV but Not in CURR
        churned_count = len(prev_active_ids - curr_active_ids)
        churn_rate = (
            round((churned_count / len(prev_active_ids) * 100), 1)
            if len(prev_active_ids) > 0
            else 0.0
        )
        
        # 3. Virality: % of matches between New (<30d) and Vet (>30d) users
        # Sample last 100 matches for performance
        recent_matches = Match.query.filter_by(status="completed").order_by(Match.updated_at.desc()).limit(100).all()
        
        viral_matches = 0
        total_sample = 0
        
        for m in recent_matches:
            if not m.player1 or not m.player2:
                continue
                
            p1_age = (m.updated_at - m.player1.created_at).days
            p2_age = (m.updated_at - m.player2.created_at).days
            
            is_p1_new = p1_age <= 30
            is_p2_new = p2_age <= 30
            
            # Virality condition: One new, One old
            if (is_p1_new and not is_p2_new) or (not is_p1_new and is_p2_new):
                viral_matches += 1
            
            total_sample += 1
            
        virality_score = (
            round((viral_matches / total_sample * 100), 1)
            if total_sample > 0
            else 0.0
        )
            
        return {
            "stickiness": stickiness,
            "churn_count": churned_count,
            "churn_rate": churn_rate,
            "virality_score": virality_score
        }

    @staticmethod
    def get_power_users(limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top users by activity in the last 30 days.
        """
        from ..user.models import User
        from ..match.models import Match
        
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        # Count matches as P1
        p1_counts = (
            db.session.query(
                Match.player1_id.label("user_id"),
                func.count(Match.id).label("count")
            )
            .filter(
                Match.updated_at >= thirty_days_ago,
                Match.status == "completed"
            )
            .group_by(Match.player1_id)
            .all()
        )
        
        # Count matches as P2
        p2_counts = (
            db.session.query(
                Match.player2_id.label("user_id"),
                func.count(Match.id).label("count")
            )
            .filter(
                Match.updated_at >= thirty_days_ago,
                Match.status == "completed"
            )
            .group_by(Match.player2_id)
            .all()
        )
        
        # Merge counts
        user_counts = {}
        for r in p1_counts:
            if r.user_id:
                user_counts[r.user_id] = user_counts.get(r.user_id, 0) + r.count
                
        for r in p2_counts:
            if r.user_id:
                user_counts[r.user_id] = user_counts.get(r.user_id, 0) + r.count
                
        # Sort and get top N
        sorted_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
        
        results = []
        for uid, count in sorted_users:
            user = User.query.get(uid)
            if user:
                results.append({
                    "user_id": uid,
                    "username": user.username,
                    "match_count": count
                })
                
        return results
