"""
Module: models/kpi/__init__.py
Purpose: KPI tracking and metrics system for admin dashboard
"""

from .enums import FeatureName, MilestoneType, AlertType
from .models import KpiFeatureUsage, KpiDailySnapshot, KpiMilestone
from .services import KpiService, DateRange, MetricWithTrend
from .tracker import (
    FeatureTracker,
    track_feature,
    track_feature_on_success,
    # Convenience functions
    track_gara_inscription,
    track_gara_create,
    track_classification_view,
    track_match_played,
    track_individual_match_create,
    track_individual_match_accept,
    track_result_submit,
    track_challenge_send,
    track_challenge_accept,
    track_availability_signal,
    track_achievement_view,
    track_leaderboard_view,
    track_profile_stats_view,
    track_drill_start,
    track_drill_complete,
)
from .notifications import KpiNotificationService

__all__ = [
    # Enums
    "FeatureName",
    "MilestoneType",
    "AlertType",
    # Models
    "KpiFeatureUsage",
    "KpiDailySnapshot",
    "KpiMilestone",
    # Services
    "KpiService",
    "DateRange",
    "MetricWithTrend",
    # Tracker
    "FeatureTracker",
    "track_feature",
    "track_feature_on_success",
    # Convenience functions
    "track_gara_inscription",
    "track_gara_create",
    "track_classification_view",
    "track_match_played",
    "track_individual_match_create",
    "track_individual_match_accept",
    "track_result_submit",
    "track_challenge_send",
    "track_challenge_accept",
    "track_availability_signal",
    "track_achievement_view",
    "track_leaderboard_view",
    "track_profile_stats_view",
    "track_drill_start",
    "track_drill_complete",
    # Notifications
    "KpiNotificationService",
]
