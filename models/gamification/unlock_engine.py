"""
Unlock Engine - Gamification Rule Evaluator

This module implements the Attribute-Based Access Control (ABAC) logic.
It evaluates configured rules against the user's current context and metrics.

Architecture:
- FeatureConfig contains a list of RuleSets (OR logic).
- Each RuleSet contains a list of Conditions (AND logic).
- Engine checks if ANY RuleSet passes.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
import logging

from models.base import db
from models.user.models import User
from models.gamification.feature_models import FeatureConfig
from models.kpi.user_metrics import UserMetricService
from models.gamification.models import UserLevel

logger = logging.getLogger(__name__)


class UnlockEngine:
    """
    Evaluates complex rules to determine if a user can access a feature.
    """

    @staticmethod
    def check_eligibility(
        user_id: int,
        feature_code: str,
        context: Optional[Dict[str, Any]] = None,
        cache: Optional[Dict[Any, Any]] = None,
    ) -> bool:
        """
        Check if user meets requirements for a feature.

        Args:
            user_id: User to check
            feature_code: Feature identifier
            context: Optional context (e.g., location_id)
            cache: Optional memoization dict per le metriche, da passare SOLO
                dai path di sola lettura (vedi UserMetricService.get_metric,
                issue #9).

        Returns:
            True if unlocked, False otherwise.
        """
        # 1. Load Feature Configuration
        config = db.session.get(FeatureConfig, feature_code)
        if not config:
            # If no config exists, default to LOCKED (False) or OPEN (True)?
            # Safer to default to True for unspecified features?
            # Or assume everything restricted needs config?
            # Let's assume features are OPEN unless configured restricted,
            # BUT usually in RBAC/ABAC default is DENY.
            # However, for gamification, "base features" are implicit.
            # If code is not found in DB, we should probably check if it's a
            # known restricted feature code.
            # For now, let's say if it's not in DB, it's NOT restricted (Open).
            # But the user specifically defined 0. Base Features.
            return True

        if not config.is_active:
            return False  # Feature disabled globally

        # 2. Parse Rules
        rule_sets = config.get_rules()
        if not rule_sets:
            return True  # No rules = Open to everyone (if active)

        # 3. Evaluate Rule Sets (OR Logic)
        user = db.session.get(User, user_id)
        if not user:
            return False

        for rule_set in rule_sets:
            if UnlockEngine._evaluate_rule_set(user, rule_set, context, cache):
                return True

        return False

    @staticmethod
    def _evaluate_rule_set(
        user: User,
        rule_set: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        cache: Optional[Dict[Any, Any]] = None,
    ) -> bool:
        """
        Evaluate a single Rule Set (AND logic).
        All conditions in the set must be True.
        """
        conditions = rule_set.get("conditions", [])
        if not conditions:
            return True  # Empty set passes

        for condition in conditions:
            if not UnlockEngine._evaluate_condition(user, condition, context, cache):
                return False

        return True

    @staticmethod
    def _evaluate_condition(
        user: User,
        condition: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        cache: Optional[Dict[Any, Any]] = None,
    ) -> bool:
        """
        Evaluate a specific condition.
        Condition types: LEVEL, METRIC, ROLE, ACHIEVEMENT
        """
        c_type = condition.get("type", "").upper()

        if c_type == "LEVEL":
            return UnlockEngine._check_level(user, condition)

        elif c_type == "METRIC":
            return UnlockEngine._check_metric(user, condition, context, cache)

        elif c_type == "ROLE":
            return UnlockEngine._check_role(user, condition)

        elif c_type == "ACHIEVEMENT":
            return UnlockEngine._check_achievement(user, condition)

        logger.warning(f"Unknown condition type: {c_type}")
        return False

    @staticmethod
    def _check_level(user: User, condition: Dict[str, Any]) -> bool:
        """Check user level."""
        required_level = int(condition.get("value", 1))
        operator = condition.get("operator", "gte")

        # Get user level from UserLevel model
        user_level = db.session.get(UserLevel, user.id)
        current_level = user_level.current_level if user_level else 1

        return UnlockEngine._compare(current_level, operator, required_level)

    @staticmethod
    def _check_metric(
        user: User,
        condition: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        cache: Optional[Dict[Any, Any]] = None,
    ) -> bool:
        """Check a specific user metric."""
        metric_name = condition.get("metric")
        target_value = float(condition.get("value", 0))
        operator = condition.get("operator", "gte")

        current_value = UserMetricService.get_metric(
            user.id, metric_name, context, cache=cache
        )
        # Ensure current_value is numeric for comparison if target is numeric
        if isinstance(current_value, (int, float)):
            return UnlockEngine._compare(current_value, operator, target_value)
        return False

    @staticmethod
    def _check_role(user: User, condition: Dict[str, Any]) -> bool:
        """Check if user has a specific role."""
        target_role = condition.get("value", "").upper()

        if target_role == "ADMIN":
            return user.is_admin
        elif target_role == "DIRECTOR":
            return user.is_director or user.is_admin
        elif target_role == "VENUE_MANAGER":
            return user.is_venue_manager or user.is_admin
        elif target_role == "EXAMINER":
            # is_examiner include già il bypass admin (ADR-038)
            return user.is_examiner

        return False

    @staticmethod
    def _check_achievement(user: User, condition: Dict[str, Any]) -> bool:
        """Check if user has an achievement."""
        slug = condition.get("value")
        # Reuse existing User method which calls AchievementService
        return user.has_unlocked_achievement(slug)

    @staticmethod
    def _compare(current: float, operator: str, target: float) -> bool:
        """Helper for comparisons."""
        if operator == "gte":
            return current >= target
        if operator == "gt":
            return current > target
        if operator == "lte":
            return current <= target
        if operator == "lt":
            return current < target
        if operator == "eq":
            return current == target
        return False

    @staticmethod
    def get_locked_reason(user_id: int, feature_code: str) -> str:
        """
        Get a human-readable reason why a feature is locked.
        Useful for notifying the user "You need 5 more matches".
        """
        # MVP: Return generic message or description of first failing condition.
        # This implementation requires re-evaluating and capturing failure.
        return "Requisiti non soddisfatti."
