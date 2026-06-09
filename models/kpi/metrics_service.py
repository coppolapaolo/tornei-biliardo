"""
Module: models/kpi/metrics_service.py
Purpose: Acquisition, Activation, Retention, Engagement, and Feature Adoption metrics
"""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, List, Any, Optional

from sqlalchemy import func, and_, or_

from ..base import db, utc_now
from ..status_enum import GaraStatus, MatchStatus
from .models import KpiFeatureUsage
from .enums import FeatureName
from .services import MetricWithTrend, DateRange, _build_date_filters, _calculate_trend


class MetricsService:
    """Acquisition, Activation, Retention, Engagement, and Feature Adoption metrics."""

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
        current = MetricsService.get_new_users(date_range)
        if date_range and date_range.is_bounded:
            prev_range = DateRange.previous_period(date_range)
            previous = MetricsService.get_new_users(prev_range)
        else:
            previous = 0
        return _calculate_trend(current, previous)

    @staticmethod
    def get_daily_registrations(
        date_range: Optional[DateRange],
    ) -> List[Dict[str, Any]]:
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

        # Giocatori distinti via UNION delle due posizioni: un utente che gioca
        # sia come player1 sia come player2 NON va contato due volte (la vecchia
        # somma dei due distinct() gonfiava il numeratore).
        p1 = db.session.query(Match.player1_id).filter(
            Match.status == MatchStatus.COMPLETED.value,
            Match.player1_id.isnot(None),
        )
        p2 = db.session.query(Match.player2_id).filter(
            Match.status == MatchStatus.COMPLETED.value,
            Match.player2_id.isnot(None),
        )
        unique_players = min(p1.union(p2).count(), total_users)
        return round((unique_players / total_users) * 100, 1)

    @staticmethod
    def get_dormant_users_count() -> int:
        """Get count of users registered but never played a match."""
        from ..user.models import User
        from ..match.models import Match

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
        """Get count of DISTINCT users active in last N days (match activity).

        Conta gli utenti distinti sull'UNIONE di player1/player2: un utente che
        nel periodo compare sia come player1 sia come player2 va contato una
        sola volta. (Prima si sommavano due COUNT(DISTINCT) per-colonna →
        doppio conteggio, con DAU/WAU/MAU gonfiati e stickiness dau/mau
        potenzialmente > 100%.)
        """
        from ..match.models import Match

        cutoff = utc_now() - timedelta(days=days)

        active_ids = set()
        for (pid,) in (
            db.session.query(Match.player1_id)
            .filter(
                Match.updated_at >= cutoff,
                Match.status == MatchStatus.COMPLETED.value,
                Match.player1_id.isnot(None),
            )
            .distinct()
            .all()
        ):
            active_ids.add(pid)
        for (pid,) in (
            db.session.query(Match.player2_id)
            .filter(
                Match.updated_at >= cutoff,
                Match.status == MatchStatus.COMPLETED.value,
                Match.player2_id.isnot(None),
            )
            .distinct()
            .all()
        ):
            active_ids.add(pid)

        return len(active_ids)

    @staticmethod
    def get_dau() -> int:
        """Get Daily Active Users."""
        return MetricsService.get_active_users_count(1)

    @staticmethod
    def get_wau() -> int:
        """Get Weekly Active Users."""
        return MetricsService.get_active_users_count(7)

    @staticmethod
    def get_mau() -> int:
        """Get Monthly Active Users."""
        return MetricsService.get_active_users_count(30)

    @staticmethod
    def get_retention_rate(days: int) -> float:
        """Get retention rate: % of users who returned after N days from
        registration."""
        from ..user.models import User
        from ..match.models import Match

        cutoff_registration = utc_now() - timedelta(days=days * 2)

        eligible_users = User.query.filter(
            and_(
                User.deleted_at.is_(None),
                User.created_at <= cutoff_registration,
            )
        ).all()

        if not eligible_users:
            return 0.0

        eligible_ids = [u.id for u in eligible_users]

        retained_count = 0
        for user in eligible_users:
            activity_after = user.created_at + timedelta(days=days)
            has_activity = Match.query.filter(
                and_(
                    or_(Match.player1_id == user.id, Match.player2_id == user.id),
                    Match.updated_at >= activity_after,
                    Match.status == MatchStatus.COMPLETED.value,
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

        return Match.query.filter_by(status=MatchStatus.COMPLETED.value).count()

    @staticmethod
    def get_matches_in_period(date_range: Optional[DateRange]) -> int:
        """Get matches completed in date range."""
        from ..match.models import Match

        filters = [Match.status == MatchStatus.COMPLETED.value]
        filters.extend(_build_date_filters(func.date(Match.updated_at), date_range))
        return Match.query.filter(and_(*filters)).count()

    @staticmethod
    def get_matches_trend(date_range: Optional[DateRange]) -> MetricWithTrend:
        """Get matches with trend comparison."""
        current = MetricsService.get_matches_in_period(date_range)
        if date_range and date_range.is_bounded:
            prev_range = DateRange.previous_period(date_range)
            previous = MetricsService.get_matches_in_period(prev_range)
        else:
            previous = 0
        return _calculate_trend(current, previous)

    @staticmethod
    def get_daily_matches(date_range: Optional[DateRange]) -> List[Dict[str, Any]]:
        """Get daily match counts for charting."""
        from ..match.models import Match

        filters = [Match.status == MatchStatus.COMPLETED.value]
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

        return Gara.query.filter_by(status=GaraStatus.PLAYING.value).count()

    @staticmethod
    def get_completed_gare_count(date_range: Optional[DateRange] = None) -> int:
        """Get count of completed gare."""
        from ..competition.models import Gara

        filters = [Gara.status == GaraStatus.COMPLETED.value]
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
        matches = MetricsService.get_matches_in_period(date_range)
        if date_range and date_range.is_bounded:
            days = (date_range.end - date_range.start).days + 1  # type: ignore
        else:
            days = 30
        active_users = MetricsService.get_active_users_count(days)
        if active_users == 0:
            return 0.0
        return round(matches / active_users, 1)

    # ========== FEATURE ADOPTION ==========

    @staticmethod
    def get_feature_usage(date_range: Optional[DateRange]) -> List[Dict[str, Any]]:
        """Get feature usage stats for all features."""
        results = []

        filters = _build_date_filters(KpiFeatureUsage.date, date_range)
        query = db.session.query(
            KpiFeatureUsage.feature_name,
            func.sum(KpiFeatureUsage.usage_count).label("usage"),
            func.sum(KpiFeatureUsage.unique_users).label("unique"),
        )
        if filters:
            query = query.filter(and_(*filters))
        current_usage = query.group_by(KpiFeatureUsage.feature_name).all()

        usage_map = {
            r.feature_name: (r.usage or 0, r.unique or 0) for r in current_usage
        }

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

        total_usage = sum(u for u, _ in usage_map.values())

        for feature in FeatureName:
            current, unique = usage_map.get(feature.value, (0, 0))
            previous = prev_map.get(feature.value, 0)
            trend = _calculate_trend(current, previous)

            results.append(
                {
                    "feature_name": feature.value,
                    "feature_label": _get_feature_label(feature),
                    "usage_count": current,
                    "unique_users": unique,
                    "trend_percent": trend.trend_percent,
                    "trend_direction": trend.trend_direction,
                    "percentage": (
                        round((current / total_usage * 100), 1)
                        if total_usage > 0
                        else 0
                    ),
                }
            )

        results.sort(key=lambda x: x["usage_count"], reverse=True)
        return results


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
