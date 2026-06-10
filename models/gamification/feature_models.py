"""
Gamification Feature Models - ABAC Configuration and Usage Tracking

This module defines the models for the Attribute-Based Access Control (ABAC) system.
- FeatureConfig: Stores the JSON rules for unlocking features.
- UserFeatureUsage: Tracks when a user utilizes a specific feature (for Nudge logic).
"""

from __future__ import annotations
from typing import Dict, Any, List
import json

from ..base import db, BaseModel, TimestampMixin


class FeatureConfig(BaseModel):
    """
    Configuration for a system feature that requires unlocking.

    Stores the "Gatekeeper" rules in a JSON format to allow flexible AND/OR logic
    without requiring schema migrations for every new condition type.
    """

    __tablename__ = "feature_config"

    code = db.Column(db.String(50), primary_key=True)  # e.g., "create_match_direct"
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # The Rules Engine Configuration
    # List of RuleSets (OR logic). Each RuleSet is a list of Conditions (AND logic).
    # [
    #   {
    #     "description": "Level 5 requirement",
    #     "conditions": [{"type": "LEVEL", "operator": "gte", "value": 5}]
    #   },
    #   { "description": "Admin Override", ... }
    # ]
    rules = db.Column(db.Text, nullable=False, default="[]")

    is_active = db.Column(db.Boolean, default=True)

    # UI Metadata
    badge_slug = db.Column(
        db.String(100), nullable=True
    )  # Associated badge to show in UI

    def get_rules(self) -> List[Dict[str, Any]]:
        """Return parsed JSON rules."""
        if not self.rules:
            return []
        try:
            return json.loads(self.rules)
        except json.JSONDecodeError:
            return []

    def set_rules(self, rules_list: List[Dict[str, Any]]) -> None:
        """Serialize rules to JSON."""
        self.rules = json.dumps(rules_list)

    def __repr__(self) -> str:
        return f"<FeatureConfig code={self.code}>"


class UserFeatureUsage(db.Model, TimestampMixin):
    """
    Tracks accurate usage of features by users.

    Used primarily for the "Nudge" system: if a user has unlocked a feature
    but hasn't used it yet, we nudge them.
    """

    __tablename__ = "user_feature_usage"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    feature_code = db.Column(
        db.String(50),
        db.ForeignKey("feature_config.code", ondelete="CASCADE"),
        nullable=False,
    )

    usage_count = db.Column(db.Integer, default=0)
    last_used_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id], backref="feature_usages")
    feature = db.relationship("FeatureConfig", foreign_keys=[feature_code])

    __table_args__ = (
        db.UniqueConstraint("user_id", "feature_code", name="uq_user_feature_usage"),
        db.Index("idx_feature_usage_user", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<UserFeatureUsage user={self.user_id} feature={self.feature_code} count={self.usage_count}>"
