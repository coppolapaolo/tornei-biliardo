"""Generic result type for multi-step service operations.

Originally defined in ``models/orchestration/service.py`` alongside the
``DomainOrchestrator`` (removed as dead code). The ``OperationResult`` /
``OperationType`` value objects are still used by live services
(``competition/services.py`` reset/cancel campionato, ``match/match_service.py``
result processing & batch corrections) to return a structured success/failure
payload, so they live here in the shared layer, decoupled from any orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class OperationType(Enum):
    """Types of multi-step service operations."""

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
    """Result of a multi-step service operation."""

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
