"""
Module: models/kpi/milestone_service.py
Purpose: Milestone checking and activity alerts
"""

from __future__ import annotations

from typing import List, Tuple

from ..base import utc_now
from ..transaction.manager import transactional
from .models import KpiMilestone
from .enums import (
    MilestoneType,
    AlertType,
    USER_MILESTONES,
    MATCH_MILESTONES,
    GARA_MILESTONES,
)
from .metrics_service import MetricsService


class MilestoneService:
    """Milestone checking and activity alert detection."""

    @staticmethod
    @transactional(domain="kpi")
    def check_and_record_milestones() -> List[Tuple[MilestoneType, int]]:
        """Check for new milestones and record them. Returns newly reached milestones."""
        newly_reached = []

        total_users = MetricsService.get_total_users()
        for threshold in USER_MILESTONES:
            if total_users >= threshold and not KpiMilestone.is_reached(
                MilestoneType.USERS_TOTAL, threshold
            ):
                KpiMilestone.mark_reached(MilestoneType.USERS_TOTAL, threshold)
                newly_reached.append((MilestoneType.USERS_TOTAL, threshold))

        total_matches = MetricsService.get_total_matches()
        for threshold in MATCH_MILESTONES:
            if total_matches >= threshold and not KpiMilestone.is_reached(
                MilestoneType.MATCHES_TOTAL, threshold
            ):
                KpiMilestone.mark_reached(MilestoneType.MATCHES_TOTAL, threshold)
                newly_reached.append((MilestoneType.MATCHES_TOTAL, threshold))

        from ..competition.models import Gara

        completed_gare = Gara.query.filter_by(status="completed").count()
        for threshold in GARA_MILESTONES:
            if completed_gare >= threshold and not KpiMilestone.is_reached(
                MilestoneType.GARE_COMPLETED, threshold
            ):
                KpiMilestone.mark_reached(MilestoneType.GARE_COMPLETED, threshold)
                newly_reached.append((MilestoneType.GARE_COMPLETED, threshold))

        return newly_reached

    @staticmethod
    def check_activity_alerts() -> List[AlertType]:
        """Check for activity drop alerts. Returns triggered alerts."""
        from ..match.models import Match
        from ..user.models import User

        alerts = []

        last_match = (
            Match.query.filter_by(status="completed")
            .order_by(Match.updated_at.desc())
            .first()
        )

        if last_match:
            days_since_match = (utc_now() - last_match.updated_at).days
            if days_since_match >= 7:
                alerts.append(AlertType.NO_MATCH_7_DAYS)
            elif days_since_match >= 3:
                alerts.append(AlertType.NO_MATCH_3_DAYS)

        last_user = (
            User.query.filter(User.deleted_at.is_(None))
            .order_by(User.created_at.desc())
            .first()
        )

        if last_user:
            days_since_registration = (utc_now() - last_user.created_at).days
            if days_since_registration >= 7:
                alerts.append(AlertType.NO_REGISTRATION_7_DAYS)

        return alerts
