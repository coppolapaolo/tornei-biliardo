"""
Module: models/orchestration/service.py
Purpose: Cross-domain service orchestration for complex business operations
Requirements: Coordinate operations across User, Campionato, Competition, Match, Rating, and Challenge domains
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import logging

from ..user.services import UserService
from ..campionato.services import TournamentService
from ..competition.services import GaraService
from ..matchmaking.service import MatchmakingService
from ..rating.services import CategoryService
from models.base import utc_now

# Setup logging
logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Types of orchestrated operations."""

    TOURNAMENT_SETUP = "campionato_setup"
    COMPETITION_LIFECYCLE = "competition_lifecycle"
    ROUND_GENERATION = "round_generation"
    RESULT_PROCESSING = "result_processing"
    USER_ONBOARDING = "user_onboarding"
    RATING_UPDATE = "rating_update"
    TOURNAMENT_RESET = "tournament_reset"
    TOURNAMENT_CANCELLATION = "tournament_cancellation"


@dataclass
class OperationResult:
    """Result of an orchestrated operation."""

    success: bool
    operation_type: OperationType
    data: Dict[str, Any]
    errors: List[str]
    warnings: List[str]
    execution_time_ms: float
    affected_domains: List[str]

    @classmethod
    def success_result(
        cls,
        operation_type: OperationType,
        data: Dict[str, Any],
        execution_time_ms: float,
        affected_domains: List[str],
        warnings: Optional[List[str]] = None,
    ) -> "OperationResult":
        return cls(
            success=True,
            operation_type=operation_type,
            data=data,
            errors=[],
            warnings=warnings or [],
            execution_time_ms=execution_time_ms,
            affected_domains=affected_domains,
        )

    @classmethod
    def failure_result(
        cls,
        operation_type: OperationType,
        errors: List[str],
        execution_time_ms: float,
        affected_domains: List[str],
        warnings: Optional[List[str]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> "OperationResult":
        return cls(
            success=False,
            operation_type=operation_type,
            data=data or {},
            errors=errors,
            warnings=warnings or [],
            execution_time_ms=execution_time_ms,
            affected_domains=affected_domains,
        )


class DomainOrchestrator:
    """Cross-domain service orchestrator for complex business operations."""

    def __init__(self, matchmaking_service: MatchmakingService):
        self.matchmaking = matchmaking_service
        self._operation_history: List[OperationResult] = []

    def setup_complete_campionato(
        self,
        campionato_data: Dict[str, Any],
        competition_configs: List[Dict[str, Any]],
        auto_assign_categories: bool = True,
        setup_handicap_rules: bool = True,
    ) -> OperationResult:
        """Orchestrate complete campionato setup across multiple domains."""

        start_time = utc_now()
        affected_domains = ["campionato", "competition", "user", "rating"]

        try:
            # Phase 1: Create campionato
            campionato = TournamentService.create_campionato(
                name=campionato_data["name"],
                description=campionato_data.get("description"),
                start_date=campionato_data["start_date"],
                end_date=campionato_data.get("end_date"),
                creator_id=campionato_data["creator_id"],
                max_participants=campionato_data.get("max_participants"),
            )

            # Phase 2: Create competitions
            competitions = []
            for comp_config in competition_configs:
                comp_config["campionato_id"] = campionato.id
                competition = GaraService.create_gara(**comp_config)
                competitions.append(competition)

            # Phase 3: Auto-assign categories if requested
            category_assignments = []
            if auto_assign_categories:
                category_assignments = self._auto_assign_player_categories(
                    campionato.id
                )
                affected_domains.append("rating")

            # Phase 4: Setup handicap rules if requested
            handicap_rules = []
            if setup_handicap_rules:
                handicap_rules = self._setup_campionato_handicap_rules(campionato.id)

            # Phase 5: Initialize matchmaking for each competition
            matchmaking_configs = []
            for competition in competitions:
                config = self._initialize_competition_matchmaking(competition.id)
                matchmaking_configs.append(config)
                affected_domains.append("matchmaking")

            execution_time = (utc_now() - start_time).total_seconds() * 1000

            result_data = {
                "campionato": {
                    "id": campionato.id,
                    "name": campionato.name,
                    "competitions_count": len(competitions),
                },
                "competitions": [{"id": c.id, "name": c.name} for c in competitions],
                "category_assignments": len(category_assignments),
                "handicap_rules": len(handicap_rules),
                "matchmaking_configs": matchmaking_configs,
            }

            result = OperationResult.success_result(
                operation_type=OperationType.TOURNAMENT_SETUP,
                data=result_data,
                execution_time_ms=execution_time,
                affected_domains=affected_domains,
            )

            self._operation_history.append(result)
            logger.info(
                f"Campionato setup completed: {campionato.name} ({campionato.id})"
            )

            return result

        except Exception as e:
            execution_time = (utc_now() - start_time).total_seconds() * 1000

            result = OperationResult.failure_result(
                operation_type=OperationType.TOURNAMENT_SETUP,
                errors=[f"Campionato setup failed: {str(e)}"],
                execution_time_ms=execution_time,
                affected_domains=affected_domains,
            )

            self._operation_history.append(result)
            logger.error(f"Campionato setup failed: {str(e)}")

            return result

    def orchestrate_user_onboarding(
        self,
        user_data: Dict[str, Any],
        auto_category_assignment: bool = True,
        setup_preferences: bool = True,
    ) -> OperationResult:
        """Orchestrate complete user onboarding across domains."""

        start_time = utc_now()
        affected_domains = ["user"]

        try:
            # Phase 1: Create user
            user = UserService.create_user(
                username=user_data["username"],
                email=user_data["email"],
                password=user_data["password"],
                role=user_data.get("role", "player"),
                phone=user_data.get("phone"),
            )

            onboarding_steps = ["user_created"]

            # Phase 2: Auto-assign category if requested
            category_assignment = None
            if auto_category_assignment and user.is_player:
                # Use default category for new players
                from ..rating.models import CategoryLevel

                category_assignment = CategoryService.assign_category(
                    user_id=user.id,
                    category=CategoryLevel.D,  # Start with beginner
                    assigned_by_id=user.id,  # Self-assignment for new player
                    reason="Automatic assignment for new player",
                )
                onboarding_steps.append("category_assigned")
                affected_domains.append("rating")

            # Phase 3: Setup user preferences if requested
            preferences = None
            if setup_preferences:
                preferences = self._setup_user_preferences(user.id)
                onboarding_steps.append("preferences_configured")
                affected_domains.append("notification")

            # Phase 4: Create welcome challenges if applicable
            welcome_challenges = []
            if user.is_player:
                welcome_challenges = self._create_welcome_challenges(user.id)
                if welcome_challenges:
                    onboarding_steps.append(
                        f"created_{len(welcome_challenges)}_welcome_challenges"
                    )
                    affected_domains.append("challenge")

            execution_time = (utc_now() - start_time).total_seconds() * 1000

            result_data = {
                "user": {"id": user.id, "username": user.username, "role": user.role},
                "onboarding_steps": onboarding_steps,
                "category_assignment": (
                    category_assignment.id if category_assignment else None
                ),
                "preferences_configured": preferences is not None,
                "welcome_challenges": len(welcome_challenges),
            }

            result = OperationResult.success_result(
                operation_type=OperationType.USER_ONBOARDING,
                data=result_data,
                execution_time_ms=execution_time,
                affected_domains=affected_domains,
            )

            self._operation_history.append(result)
            logger.info(f"User onboarding completed: {user.username} ({user.id})")

            return result

        except Exception as e:
            execution_time = (utc_now() - start_time).total_seconds() * 1000

            result = OperationResult.failure_result(
                operation_type=OperationType.USER_ONBOARDING,
                errors=[f"User onboarding failed: {str(e)}"],
                execution_time_ms=execution_time,
                affected_domains=affected_domains,
            )

            self._operation_history.append(result)
            logger.error(f"User onboarding failed: {str(e)}")

            return result

    def get_operation_history(
        self, operation_type: Optional[OperationType] = None, limit: int = 50
    ) -> List[OperationResult]:
        """Get history of orchestrated operations."""

        history = self._operation_history

        if operation_type:
            history = [op for op in history if op.operation_type == operation_type]

        return history[-limit:]

    def get_orchestration_metrics(self) -> Dict[str, Any]:
        """Get metrics about orchestration performance."""

        if not self._operation_history:
            return {"total_operations": 0}

        total_ops = len(self._operation_history)
        successful_ops = len([op for op in self._operation_history if op.success])

        avg_execution_time = (
            sum(op.execution_time_ms for op in self._operation_history) / total_ops
        )

        # Count by operation type
        type_counts = {}
        for op_type in OperationType:
            count = len(
                [op for op in self._operation_history if op.operation_type == op_type]
            )
            type_counts[op_type.value] = count

        # Count by affected domains
        domain_involvement = {}
        for op in self._operation_history:
            for domain in op.affected_domains:
                domain_involvement[domain] = domain_involvement.get(domain, 0) + 1

        return {
            "total_operations": total_ops,
            "successful_operations": successful_ops,
            "success_rate_percent": round(successful_ops / total_ops * 100, 1),
            "average_execution_time_ms": round(avg_execution_time, 2),
            "operations_by_type": type_counts,
            "domain_involvement": domain_involvement,
        }

    # Private helper methods

    def _auto_assign_player_categories(
        self, campionato_id: int
    ) -> List[Dict[str, Any]]:
        """Auto-assign categories to campionato participants."""
        # Implementation would analyze player history and assign appropriate categories
        # For now, return empty list
        return []

    def _setup_campionato_handicap_rules(
        self, campionato_id: int
    ) -> List[Dict[str, Any]]:
        """Setup handicap rules for campionato."""
        # Implementation would create campionato-specific handicap rules
        return []

    def _initialize_competition_matchmaking(self, gara_id: int) -> Dict[str, Any]:
        """Initialize matchmaking configuration for competition."""
        return {
            "gara_id": gara_id,
            "strategy": "amalfi",
            "supports_handicaps": True,
            "supports_x_replacement": True,
        }

    def _setup_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """Setup default user preferences."""
        # Implementation would create notification preferences, etc.
        return {"notifications_enabled": True}

    def _create_welcome_challenges(self, user_id: int) -> List[Dict[str, Any]]:
        """Create welcome challenges for new player."""
        # Implementation would create beginner-friendly challenges
        return []
