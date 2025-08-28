from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, Sequence, Tuple, Dict, Any, Optional, List
from datetime import datetime


@dataclass(frozen=True)
class Pairing:
    """Enhanced Value Object for matchmaking output with metadata."""

    players: Tuple[int, ...]
    is_bye: bool = False
    round_number: Optional[int] = None

    # Enhanced metadata
    pairing_quality: float = 1.0  # 0.0 = poor, 1.0 = excellent
    estimated_duration: Optional[int] = None  # minutes
    requires_handicap: bool = False
    notes: Optional[str] = None

    @property
    def player1_id(self) -> Optional[int]:
        """Get first player ID."""
        return self.players[0] if len(self.players) > 0 else None

    @property
    def player2_id(self) -> Optional[int]:
        """Get second player ID."""
        return self.players[1] if len(self.players) > 1 else None

    @property
    def is_valid_pairing(self) -> bool:
        """Check if this is a valid pairing."""
        if self.is_bye:
            return len(self.players) == 1
        return len(self.players) == 2 and self.players[0] != self.players[1]

    def get_opponent_id(self, player_id: int) -> Optional[int]:
        """Get opponent ID for given player."""
        if self.is_bye or player_id not in self.players:
            return None
        return next((pid for pid in self.players if pid != player_id), None)


@dataclass(frozen=True)
class ValidationResult:
    """Enhanced validation result with severity levels."""

    ok: bool
    messages: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    errors: Tuple[str, ...] = ()

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @classmethod
    def success(
        cls, messages: Optional[List[str]] = None, warnings: Optional[List[str]] = None
    ) -> "ValidationResult":
        """Create successful validation result."""
        return cls(
            ok=True, messages=tuple(messages or []), warnings=tuple(warnings or [])
        )

    @classmethod
    def failure(
        cls, errors: List[str], warnings: Optional[List[str]] = None
    ) -> "ValidationResult":
        """Create failed validation result."""
        return cls(
            ok=False,
            errors=tuple(errors),
            warnings=tuple(warnings or []),
            messages=tuple(errors + (warnings or [])),
        )


@dataclass(frozen=True)
class StrategyMetrics:
    """Performance and quality metrics for strategy execution."""

    execution_time_ms: float
    pairings_generated: int
    bye_count: int
    average_pairing_quality: float
    cache_hit: bool = False
    validation_time_ms: float = 0.0

    @property
    def total_time_ms(self) -> float:
        return self.execution_time_ms + self.validation_time_ms


class PairingStrategy(ABC):
    """Enhanced abstract base class for pairing strategies."""

    # Strategy metadata (with default values)
    name: str = "base_strategy"
    display_name: str = "Base Strategy"
    description: str = "Base strategy implementation"
    min_players: int = 2
    max_players: Optional[int] = None
    supports_byes: bool = True
    requires_classification: bool = False

    @abstractmethod
    def validate(self, prova: object) -> ValidationResult:
        """Validate prova state for this strategy."""
        ...

    @abstractmethod
    def preview(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Generate preview without side effects."""
        ...

    @abstractmethod
    def propose(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Generate actual pairings with side effects."""
        ...

    @abstractmethod
    def get_metrics(self) -> Optional[StrategyMetrics]:
        """Get performance metrics from last execution."""
        ...


class BaseStrategy(PairingStrategy):
    """Abstract base class implementing template method pattern for strategies."""

    # Strategy metadata (to be overridden)
    name: str = "base"
    display_name: str = "Base Strategy"
    description: str = "Abstract base strategy"
    min_players: int = 2
    max_players: Optional[int] = None
    supports_byes: bool = True
    requires_classification: bool = False

    def __init__(self):
        self._last_metrics: Optional[StrategyMetrics] = None
        self._execution_start: Optional[datetime] = None

    def validate(self, prova: object) -> ValidationResult:
        """Template method for validation with common checks."""
        validation_start = datetime.utcnow()

        errors = []
        warnings = []

        # Common validations
        if not hasattr(prova, "inscriptions"):
            errors.append("Prova must have inscriptions attribute")
        else:
            active_inscriptions = self._get_active_inscriptions(prova)
            player_count = len(active_inscriptions)

            if player_count < self.min_players:
                errors.append(
                    f"Insufficient players: {player_count} < {self.min_players}"
                )

            if self.max_players and player_count > self.max_players:
                errors.append(f"Too many players: {player_count} > {self.max_players}")

            if player_count % 2 != 0 and not self.supports_byes:
                errors.append(
                    f"Strategy does not support odd number of players: {player_count}"
                )

        # Strategy-specific validation
        strategy_validation = self._validate_strategy_specific(prova)
        errors.extend(strategy_validation.get("errors", []))
        warnings.extend(strategy_validation.get("warnings", []))

        validation_time = (datetime.utcnow() - validation_start).total_seconds() * 1000

        if errors:
            return ValidationResult.failure(errors, warnings)
        else:
            return ValidationResult.success(warnings=warnings)

    def preview(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Template method for preview generation."""
        self._execution_start = datetime.utcnow()

        # Validate first
        validation = self.validate(prova)
        if not validation.ok:
            raise ValueError(f"Validation failed: {'; '.join(validation.errors)}")

        # Get active players
        active_inscriptions = self._get_active_inscriptions(prova)

        # Pre-processing hook
        processed_data = self._preprocess_data(prova, active_inscriptions, round_number)

        # Generate pairings (strategy-specific)
        pairings = self._generate_pairings(
            processed_data, round_number, preview_mode=True
        )

        # Post-processing hook
        enhanced_pairings = self._postprocess_pairings(pairings, prova, round_number)

        # Record metrics
        self._record_metrics(enhanced_pairings, validation_time_ms=0.0)

        return enhanced_pairings

    def propose(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Template method for actual pairing generation with side effects."""
        self._execution_start = datetime.utcnow()

        # Validate first
        validation = self.validate(prova)
        if not validation.ok:
            raise ValueError(f"Validation failed: {'; '.join(validation.errors)}")

        # Get active players
        active_inscriptions = self._get_active_inscriptions(prova)

        # Pre-processing hook
        processed_data = self._preprocess_data(prova, active_inscriptions, round_number)

        # Generate pairings (strategy-specific)
        pairings = self._generate_pairings(
            processed_data, round_number, preview_mode=False
        )

        # Post-processing hook
        enhanced_pairings = self._postprocess_pairings(pairings, prova, round_number)

        # Apply side effects
        self._apply_side_effects(enhanced_pairings, prova, round_number)

        # Record metrics
        self._record_metrics(enhanced_pairings, validation_time_ms=0.0)

        return enhanced_pairings

    def get_metrics(self) -> Optional[StrategyMetrics]:
        """Get metrics from last execution."""
        return self._last_metrics

    # Template method hooks (to be implemented by subclasses)

    @abstractmethod
    def _generate_pairings(
        self,
        processed_data: Dict[str, Any],
        round_number: int,
        preview_mode: bool = True,
    ) -> Sequence[Pairing]:
        """Generate the actual pairings (strategy-specific logic)."""
        pass

    def _validate_strategy_specific(self, prova: object) -> Dict[str, List[str]]:
        """Override for strategy-specific validation."""
        return {"errors": [], "warnings": []}

    def _preprocess_data(
        self, prova: object, active_inscriptions: List[Any], round_number: int
    ) -> Dict[str, Any]:
        """Override for strategy-specific preprocessing."""
        return {
            "prova": prova,
            "players": [i.user_id for i in active_inscriptions],
            "round_number": round_number,
        }

    def _postprocess_pairings(
        self, pairings: Sequence[Pairing], prova: object, round_number: int
    ) -> Sequence[Pairing]:
        """Override for strategy-specific postprocessing."""
        return pairings

    def _apply_side_effects(
        self, pairings: Sequence[Pairing], prova: object, round_number: int
    ) -> None:
        """Override for strategy-specific side effects (e.g., updating classification)."""
        pass

    # Helper methods

    def _get_active_inscriptions(self, prova: object) -> List[Any]:
        """Get active inscriptions for the prova."""
        inscriptions = getattr(prova, "inscriptions", [])
        return [
            i for i in inscriptions if hasattr(i, "status") and i.status == "confirmed"
        ]

    def _calculate_pairing_quality(
        self, player1_id: int, player2_id: int, prova: object
    ) -> float:
        """Calculate quality score for a pairing (0.0 = poor, 1.0 = excellent)."""
        # Base implementation: random quality
        # Override in subclasses for sophisticated quality calculation
        return 0.8  # Default to good quality

    def _record_metrics(
        self, pairings: Sequence[Pairing], validation_time_ms: float = 0.0
    ) -> None:
        """Record execution metrics."""
        if self._execution_start:
            execution_time = (
                datetime.utcnow() - self._execution_start
            ).total_seconds() * 1000

            bye_count = sum(1 for p in pairings if p.is_bye)
            avg_quality = (
                sum(p.pairing_quality for p in pairings) / len(pairings)
                if pairings
                else 0.0
            )

            self._last_metrics = StrategyMetrics(
                execution_time_ms=execution_time,
                pairings_generated=len(pairings),
                bye_count=bye_count,
                average_pairing_quality=avg_quality,
                validation_time_ms=validation_time_ms,
            )
