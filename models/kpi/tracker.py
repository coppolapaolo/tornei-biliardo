"""
Module: models/kpi/tracker.py
Purpose: Feature usage tracking system (anonymous/GDPR compliant)
"""

from __future__ import annotations

from functools import wraps
from typing import Callable, Optional, Any
from datetime import date
import logging

from flask import g, has_request_context

from ..base import db
from .models import KpiFeatureUsage
from .enums import FeatureName

logger = logging.getLogger(__name__)


class FeatureTracker:
    """
    Tracks feature usage in an anonymous, GDPR-compliant way.

    Usage:
        # Direct tracking
        FeatureTracker.track(FeatureName.GARA_INSCRIPTION)

        # As decorator
        @track_feature(FeatureName.GARA_INSCRIPTION)
        def create_inscription():
            ...
    """

    # Session-level tracking to count unique users per day
    _session_tracked: set[str] = set()

    @classmethod
    def track(
        cls,
        feature: FeatureName,
        for_date: Optional[date] = None,
    ) -> None:
        """
        Track a feature usage event.

        Args:
            feature: The feature being used
            for_date: Optional date override (defaults to today)
        """
        try:
            if for_date is None:
                for_date = date.today()

            # Check if this is a unique usage for this session
            session_key = cls._get_session_key(feature, for_date)
            is_unique = session_key not in cls._session_tracked

            # Get or create the record
            record = KpiFeatureUsage.get_or_create(feature, for_date)
            record.usage_count += 1

            if is_unique:
                record.unique_users += 1
                cls._session_tracked.add(session_key)

            db.session.commit()

        except Exception as e:
            logger.warning(f"Failed to track feature {feature.value}: {e}")
            db.session.rollback()

    @classmethod
    def track_batch(cls, features: list[FeatureName]) -> None:
        """Track multiple features at once."""
        for feature in features:
            cls.track(feature)

    @classmethod
    def _get_session_key(cls, feature: FeatureName, for_date: date) -> str:
        """Generate a session-unique key for tracking unique users."""
        # Use request-level tracking if available
        if has_request_context():
            # Get a pseudo-anonymous session identifier
            session_id = getattr(g, "_kpi_session_id", None)
            if session_id is None:
                # Generate a new session ID for this request
                import uuid

                session_id = str(uuid.uuid4())[:8]
                g._kpi_session_id = session_id
            return f"{feature.value}:{for_date}:{session_id}"

        # Fallback for non-request context
        return f"{feature.value}:{for_date}:default"

    @classmethod
    def reset_session(cls) -> None:
        """Reset session tracking (call at end of request if needed)."""
        cls._session_tracked.clear()


def track_feature(feature: FeatureName) -> Callable:
    """
    Decorator to track feature usage on a route or function.

    Usage:
        @app.route('/gare/<int:gara_id>/inscription', methods=['POST'])
        @track_feature(FeatureName.GARA_INSCRIPTION)
        def create_inscription(gara_id):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Track before executing
            FeatureTracker.track(feature)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def track_feature_on_success(feature: FeatureName) -> Callable:
    """
    Decorator that only tracks if the function doesn't raise an exception.

    Usage:
        @track_feature_on_success(FeatureName.MATCH_RESULT_SUBMIT)
        def submit_result():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            # Track only after successful execution
            FeatureTracker.track(feature)
            return result

        return wrapper

    return decorator


# Convenience functions for common tracking scenarios
def track_gara_inscription() -> None:
    """Track gara inscription."""
    FeatureTracker.track(FeatureName.GARA_INSCRIPTION)


def track_gara_create() -> None:
    """Track gara creation."""
    FeatureTracker.track(FeatureName.GARA_CREATE)


def track_classification_view() -> None:
    """Track classification view."""
    FeatureTracker.track(FeatureName.GARA_VIEW_CLASSIFICATION)


def track_match_played() -> None:
    """Track gara match played."""
    FeatureTracker.track(FeatureName.MATCH_GARA_PLAYED)


def track_individual_match_create() -> None:
    """Track individual match proposal."""
    FeatureTracker.track(FeatureName.MATCH_INDIVIDUAL_CREATE)


def track_individual_match_accept() -> None:
    """Track individual match acceptance."""
    FeatureTracker.track(FeatureName.MATCH_INDIVIDUAL_ACCEPT)


def track_result_submit() -> None:
    """Track match result submission."""
    FeatureTracker.track(FeatureName.MATCH_RESULT_SUBMIT)


def track_challenge_send() -> None:
    """Track challenge sent."""
    FeatureTracker.track(FeatureName.CHALLENGE_SEND)


def track_challenge_accept() -> None:
    """Track challenge accepted."""
    FeatureTracker.track(FeatureName.CHALLENGE_ACCEPT)


def track_availability_signal() -> None:
    """Track availability signaled."""
    FeatureTracker.track(FeatureName.AVAILABILITY_SIGNAL)


def track_achievement_view() -> None:
    """Track achievement view."""
    FeatureTracker.track(FeatureName.ACHIEVEMENT_VIEW)


def track_leaderboard_view() -> None:
    """Track leaderboard XP view."""
    FeatureTracker.track(FeatureName.LEADERBOARD_XP_VIEW)


def track_profile_stats_view() -> None:
    """Track profile stats view."""
    FeatureTracker.track(FeatureName.PROFILE_STATS_VIEW)


def track_drill_start() -> None:
    """Track drill start."""
    FeatureTracker.track(FeatureName.DRILL_START)


def track_drill_complete() -> None:
    """Track drill completion."""
    FeatureTracker.track(FeatureName.DRILL_COMPLETE)
