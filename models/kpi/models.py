"""
Module: models/kpi/models.py
Purpose: SQLAlchemy models for KPI tracking system
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from ..base import db, BaseModel, TimestampMixin
from .enums import FeatureName, MilestoneType


class KpiFeatureUsage(BaseModel, TimestampMixin):
    """Aggregated feature usage tracking (anonymous/GDPR compliant)."""

    __tablename__ = "kpi_feature_usage"

    id = db.Column(db.Integer, primary_key=True)
    feature_name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    usage_count = db.Column(db.Integer, default=0)
    unique_users = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.UniqueConstraint("feature_name", "date", name="uq_feature_date"),
    )

    @classmethod
    def get_or_create(
        cls, feature_name: FeatureName, for_date: Optional[date] = None
    ) -> "KpiFeatureUsage":
        """Get or create a feature usage record for a date.
        Handles race conditions during concurrent creation.
        """
        if for_date is None:
            for_date = date.today()

        record = cls.query.filter_by(
            feature_name=feature_name.value, date=for_date
        ).first()

        if not record:
            from sqlalchemy.exc import IntegrityError
            # Use a savepoint to protect the outer transaction
            try:
                with db.session.begin_nested():
                    record = cls(
                        feature_name=feature_name.value,
                        date=for_date,
                        usage_count=0,
                        unique_users=0,
                    )
                    db.session.add(record)
            except IntegrityError:
                record = cls.query.filter_by(
                    feature_name=feature_name.value, date=for_date
                ).first()
                if not record:
                    raise

        return record

    @classmethod
    def increment(
        cls,
        feature_name: FeatureName,
        for_date: Optional[date] = None,
        increment_unique: bool = True,
    ) -> "KpiFeatureUsage":
        """Increment usage count for a feature."""
        record = cls.get_or_create(feature_name, for_date)
        record.usage_count += 1
        if increment_unique:
            record.unique_users += 1
        return record


class KpiDailySnapshot(BaseModel, TimestampMixin):
    """Daily snapshot of aggregate platform metrics."""

    __tablename__ = "kpi_daily_snapshot"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)

    # User metrics
    total_users = db.Column(db.Integer, default=0)
    new_users = db.Column(db.Integer, default=0)
    active_users = db.Column(db.Integer, default=0)

    # Match metrics
    total_matches = db.Column(db.Integer, default=0)
    new_matches = db.Column(db.Integer, default=0)

    # Gara metrics
    total_gare = db.Column(db.Integer, default=0)
    active_gare = db.Column(db.Integer, default=0)
    completed_gare = db.Column(db.Integer, default=0)

    # Gamification metrics
    total_xp_awarded = db.Column(db.Integer, default=0)
    avg_user_level = db.Column(db.Float, default=0.0)

    # Retention metrics
    retention_7d = db.Column(db.Float, default=0.0)
    retention_30d = db.Column(db.Float, default=0.0)

    @classmethod
    def get_or_create(cls, for_date: Optional[date] = None) -> "KpiDailySnapshot":
        """Get or create a daily snapshot for a date.
        Handles race conditions during concurrent creation.
        """
        if for_date is None:
            for_date = date.today()

        snapshot = cls.query.filter_by(date=for_date).first()

        if not snapshot:
            from sqlalchemy.exc import IntegrityError
            # Use a savepoint to protect the outer transaction
            try:
                with db.session.begin_nested():
                    snapshot = cls(date=for_date)
                    db.session.add(snapshot)
            except IntegrityError:
                snapshot = cls.query.filter_by(date=for_date).first()
                if not snapshot:
                    raise

        return snapshot


class KpiMilestone(BaseModel):
    """Track reached milestones to avoid duplicate notifications."""

    __tablename__ = "kpi_milestone"

    id = db.Column(db.Integer, primary_key=True)
    milestone_type = db.Column(db.String(50), nullable=False)
    milestone_value = db.Column(db.Integer, nullable=False)
    reached_at = db.Column(db.DateTime, default=datetime.utcnow)
    notification_sent = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint(
            "milestone_type", "milestone_value", name="uq_milestone_type_value"
        ),
    )

    @classmethod
    def is_reached(cls, milestone_type: MilestoneType, value: int) -> bool:
        """Check if a milestone has already been reached."""
        return (
            cls.query.filter_by(
                milestone_type=milestone_type.value, milestone_value=value
            ).first()
            is not None
        )

    @classmethod
    def mark_reached(
        cls, milestone_type: MilestoneType, value: int, send_notification: bool = True
    ) -> "KpiMilestone":
        """Mark a milestone as reached."""
        milestone = cls.query.filter_by(
            milestone_type=milestone_type.value, milestone_value=value
        ).first()

        if not milestone:
            milestone = cls(
                milestone_type=milestone_type.value,
                milestone_value=value,
                reached_at=datetime.utcnow(),
                notification_sent=send_notification,
            )
            db.session.add(milestone)

        return milestone
