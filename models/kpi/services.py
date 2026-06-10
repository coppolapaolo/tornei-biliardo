"""
Module: models/kpi/services.py
Purpose: KPI service facade — dataclasses, helpers, and delegation to sub-modules
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


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
            return (
                f"{self.start.strftime('%d/%m/%Y')} - {self.end.strftime('%d/%m/%Y')}"
            )


def _build_date_filters(date_column: Any, date_range: Optional[DateRange]) -> List[Any]:
    """Build SQLAlchemy filter conditions for date range."""
    filters = []
    if date_range:
        if date_range.start is not None:
            filters.append(date_column >= date_range.start)
        if date_range.end is not None:
            filters.append(date_column <= date_range.end)
    return filters


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


# Import sub-modules after defining shared symbols to avoid circular imports
from .metrics_service import MetricsService  # noqa: E402
from .community_service import CommunityService  # noqa: E402
from .milestone_service import MilestoneService  # noqa: E402


class KpiService:
    """Facade: delegates to MetricsService, CommunityService, MilestoneService."""

    # --- Acquisition ---
    get_total_users = MetricsService.get_total_users
    get_new_users = MetricsService.get_new_users
    get_new_users_trend = MetricsService.get_new_users_trend
    get_daily_registrations = MetricsService.get_daily_registrations

    # --- Activation ---
    get_activation_rate = MetricsService.get_activation_rate
    get_dormant_users_count = MetricsService.get_dormant_users_count

    # --- Retention ---
    get_active_users_count = MetricsService.get_active_users_count
    get_dau = MetricsService.get_dau
    get_wau = MetricsService.get_wau
    get_mau = MetricsService.get_mau
    get_retention_rate = MetricsService.get_retention_rate

    # --- Engagement ---
    get_total_matches = MetricsService.get_total_matches
    get_matches_in_period = MetricsService.get_matches_in_period
    get_matches_trend = MetricsService.get_matches_trend
    get_daily_matches = MetricsService.get_daily_matches
    get_active_gare_count = MetricsService.get_active_gare_count
    get_completed_gare_count = MetricsService.get_completed_gare_count
    get_avg_user_level = MetricsService.get_avg_user_level
    get_total_xp_in_period = MetricsService.get_total_xp_in_period
    get_matches_per_active_user = MetricsService.get_matches_per_active_user

    # --- Feature Adoption ---
    get_feature_usage = MetricsService.get_feature_usage

    # --- Community & Business ---
    get_director_performance = CommunityService.get_director_performance
    get_community_health = CommunityService.get_community_health
    get_power_users = CommunityService.get_power_users

    # --- Milestones & Alerts ---
    check_and_record_milestones = MilestoneService.check_and_record_milestones
    check_activity_alerts = MilestoneService.check_activity_alerts

    # --- Overview (stays here as orchestrator) ---
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

    _calculate_trend = staticmethod(_calculate_trend)
