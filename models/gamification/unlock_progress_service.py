"""
UnlockProgressService - Calculate user progress toward feature unlocks.

This service provides detailed progress information for features that are
still locked for a user, including:
- Which conditions are met/unmet
- Current vs required values
- Actionable hints for what to do next

Used for the user-facing "progression visible" dashboard.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional

from models.base import db
from models.gamification.feature_models import FeatureConfig
from models.gamification.models import UserLevel
from models.kpi.user_metrics import UserMetricService
from models.user.models import User


class UnlockProgressService:
    """Service to calculate user progress toward feature unlocks."""

    @staticmethod
    def get_feature_progress(user_id: int, feature_code: str) -> Dict[str, Any]:
        """
        Get user's progress toward unlocking a feature.

        Args:
            user_id: User ID to check progress for
            feature_code: Feature code to check

        Returns:
            Dictionary with progress information:
            {
                "feature_code": "create_match_direct",
                "feature_name": "Match Individuali",
                "description": "...",
                "is_unlocked": False,
                "rule_sets": [
                    {
                        "is_met": False,
                        "conditions": [
                            {
                                "type": "METRIC",
                                "description": "5+ gare giocate",
                                "is_met": True,
                                "current_value": 7,
                                "required_value": 5
                            }
                        ]
                    }
                ],
                "next_action": "Gioca altre 2 gare per sbloccare"
            }
        """
        feature = db.session.get(FeatureConfig, feature_code)
        if not feature:
            return {"error": "Feature not found", "feature_code": feature_code}

        user = db.session.get(User, user_id)
        if not user:
            return {"error": "User not found", "feature_code": feature_code}

        is_unlocked = user.can_access(feature_code)

        # Analyze each rule set
        rules = feature.get_rules()
        rule_sets_progress = []

        for rule_set in rules:
            conditions_progress = []
            all_conditions_met = True

            for cond in rule_set.get("conditions", []):
                condition_progress = UnlockProgressService._evaluate_condition(
                    user_id, cond
                )
                conditions_progress.append(condition_progress)
                if not condition_progress["is_met"]:
                    all_conditions_met = False

            rule_sets_progress.append({
                "is_met": all_conditions_met,
                "conditions": conditions_progress
            })

        # Determine next action from first unmet condition
        next_action = None
        if not is_unlocked:
            for rule_set in rule_sets_progress:
                if not rule_set["is_met"]:
                    for cond in rule_set["conditions"]:
                        if not cond["is_met"]:
                            next_action = UnlockProgressService._get_action_hint(cond)
                            break
                    if next_action:
                        break

        return {
            "feature_code": feature_code,
            "feature_name": feature.name,
            "description": feature.description or "",
            "is_unlocked": is_unlocked,
            "is_active": feature.is_active,
            "rule_sets": rule_sets_progress,
            "next_action": next_action
        }

    @staticmethod
    def _evaluate_condition(user_id: int, condition: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a single condition and return progress details."""
        cond_type = condition.get("type", "").upper()

        if cond_type == "LEVEL":
            user_level = db.session.get(UserLevel, user_id)
            current = user_level.current_level if user_level else 1
            required = int(condition.get("value", 1))
            operator = condition.get("operator", "gte")
            is_met = UnlockProgressService._compare(current, operator, required)

            return {
                "type": "LEVEL",
                "description": f"Livello {required}+",
                "is_met": is_met,
                "current_value": current,
                "required_value": required,
                "operator": operator
            }

        elif cond_type == "METRIC":
            metric_name = condition.get("metric", "")
            required = int(condition.get("value", 0))
            operator = condition.get("operator", "gte")
            current = UserMetricService.get_metric(user_id, metric_name)
            is_met = UnlockProgressService._compare(current, operator, required)

            # Human-readable metric names
            metric_labels = {
                "total_matches": "match giocati",
                "scores_inserted": "punteggi inseriti",
                "tournaments_played": "gare giocate",
                "tournaments_organized": "gare organizzate",
                "distinct_opponents": "avversari diversi",
                "matches_in_location": "match in sala",
                "challenges_completed": "drill completati",
                "gare_with_drill_played": "gare con drill",
                "tournament_drills_completed": "drill in gara",
            }
            metric_label = metric_labels.get(metric_name, metric_name.replace("_", " "))

            return {
                "type": "METRIC",
                "metric": metric_name,
                "description": f"{required}+ {metric_label}",
                "is_met": is_met,
                "current_value": current,
                "required_value": required,
                "operator": operator
            }

        elif cond_type == "ROLE":
            target_role = condition.get("value", "").upper()
            user = db.session.get(User, user_id)

            is_met = False
            if user:
                if target_role == "ADMIN":
                    is_met = user.is_admin
                elif target_role == "DIRECTOR":
                    is_met = user.is_director or user.is_admin
                elif target_role == "VENUE_MANAGER":
                    is_met = user.is_venue_manager or user.is_admin

            role_labels = {
                "ADMIN": "Admin",
                "DIRECTOR": "Director",
                "VENUE_MANAGER": "Gestore Sala"
            }

            return {
                "type": "ROLE",
                "description": f"Ruolo: {role_labels.get(target_role, target_role)}",
                "is_met": is_met,
                "required_value": target_role
            }

        elif cond_type == "ACHIEVEMENT":
            slug = condition.get("value", "")
            user = db.session.get(User, user_id)
            is_met = user.has_unlocked_achievement(slug) if user else False

            return {
                "type": "ACHIEVEMENT",
                "description": f"Achievement: {slug}",
                "is_met": is_met,
                "required_value": slug
            }

        return {
            "type": cond_type,
            "description": f"Condizione sconosciuta: {cond_type}",
            "is_met": False
        }

    @staticmethod
    def _compare(current: float, operator: str, target: float) -> bool:
        """Compare values based on operator."""
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
    def _get_action_hint(condition: Dict[str, Any]) -> str:
        """Generate a user-friendly hint for what to do next."""
        cond_type = condition.get("type", "")

        if cond_type == "LEVEL":
            required = condition.get("required_value", 1)
            return f"Guadagna XP per raggiungere il livello {required}"

        elif cond_type == "METRIC":
            current = condition.get("current_value", 0)
            required = condition.get("required_value", 0)
            remaining = max(0, required - current)
            metric = condition.get("metric", "")

            # Specific hints based on metric type
            hints = {
                "total_matches": f"Gioca altri {remaining} match",
                "scores_inserted": f"Inserisci punteggi in altri {remaining} match",
                "tournaments_played": f"Partecipa ad altre {remaining} gare",
                "tournaments_organized": f"Organizza altre {remaining} gare",
                "distinct_opponents": f"Gioca contro altri {remaining} avversari",
                "challenges_completed": f"Completa altri {remaining} drill",
                "gare_with_drill_played": f"Partecipa a {remaining} gare con drill",
                "tournament_drills_completed": f"Completa {remaining} drill in gara",
            }
            return hints.get(metric, f"Ti mancano {remaining} per completare")

        elif cond_type == "ROLE":
            role = condition.get("required_value", "")
            if role == "DIRECTOR":
                return "Diventa Director per sbloccare"
            elif role == "VENUE_MANAGER":
                return "Diventa Gestore Sala per sbloccare"
            return f"Richiede ruolo {role}"

        elif cond_type == "ACHIEVEMENT":
            slug = condition.get("required_value", "")
            return f"Sblocca l'achievement '{slug}'"

        return "Continua a usare la piattaforma"

    @staticmethod
    def get_all_features_progress(
        user_id: int,
        include_unlocked: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get progress for all gated features.

        Args:
            user_id: User ID to check
            include_unlocked: Whether to include already unlocked features

        Returns:
            List of feature progress dictionaries
        """
        features = FeatureConfig.query.filter_by(is_active=True).all()
        result = []

        for feature in features:
            progress = UnlockProgressService.get_feature_progress(
                user_id, feature.code
            )
            if include_unlocked or not progress.get("is_unlocked", False):
                result.append(progress)

        return result

    @staticmethod
    def get_locked_features_progress(user_id: int) -> List[Dict[str, Any]]:
        """
        Get progress for features that are still locked for the user.

        Useful for showing "what's next" on user dashboard.

        Args:
            user_id: User ID to check

        Returns:
            List of locked feature progress dictionaries
        """
        return UnlockProgressService.get_all_features_progress(
            user_id, include_unlocked=False
        )
