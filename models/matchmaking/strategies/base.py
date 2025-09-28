from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence, Tuple, Dict, Any, Optional, List


@dataclass(frozen=True)
class Pairing:
    """Immutable Value Object representing a tournament match pairing with
    quality metrics.

    Central data structure for all matchmaking algorithms. Encapsulates player
    assignments, match type classification (regular, bye, trio), and quality
    assessment for tournament optimization. Supports both traditional 1v1 matches
    and trio matches for odd player counts.

    Design Pattern: Value Object (immutable, equality-based)
    Business Context: American Pool tournament pairing with flexible match formats
    """

    players: Tuple[int, ...]
    is_bye: bool = False
    round_number: Optional[int] = None

    # Operational metadata
    estimated_duration: Optional[int] = None  # Expected match duration in minutes
    requires_handicap: bool = False  # Whether skill balancing is recommended
    notes: Optional[str] = None  # Strategy-specific annotations and context

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
        """Validate pairing structure according to pool tournament rules.

        Business Rules:
        - Bye matches: exactly 1 player (opponent sits out)
        - Regular matches: exactly 2 different players
        - Trio matches: exactly 3 different players (for odd numbers)

        Returns:
            True if pairing follows tournament format rules
        """
        if self.is_bye:
            return len(self.players) == 1
        elif len(self.players) == 2:
            return self.players[0] != self.players[1]  # Regular 2-player match
        elif len(self.players) == 3:
            # Trio match - all players must be different
            return len(set(self.players)) == 3
        return False  # Invalid number of players

    @property
    def is_trio(self) -> bool:
        """Check if this is a trio pairing."""
        return len(self.players) == 3 and len(set(self.players)) == 3


@dataclass(frozen=True)
class ValidationResult:
    """Immutable validation result with hierarchical feedback levels.

    Distinguishes between blocking errors (prevent execution) and warnings
    (suboptimal but acceptable). Enables graceful degradation and informed
    decision-making during tournament setup and execution.

    Design Pattern: Value Object with Factory Methods
    """

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


class PairingStrategy(ABC):
    """Abstract base interface for tournament pairing algorithms.

    Defines the contract for all matchmaking strategies used in pool tournaments.
    Each strategy implements specific pairing logic while adhering to common
    validation and execution patterns.

    Supported Tournament Formats:
    - Amalfi: Adaptive pairing with anti-rematch intelligence
    - Round-Robin: Complete all-play-all format
    - Elimination: Single/double knockout brackets
    - Random: Casual pairing with rematch prevention

    Design Pattern: Strategy + Template Method
    Business Context: Flexible tournament organization for American Pool communities
    """

    # Strategy metadata (with default values)
    name: str = "base_strategy"
    display_name: str = "Base Strategy"
    description: str = "Base strategy implementation"
    min_players: int = 2
    max_players: Optional[int] = None
    supports_byes: bool = True
    requires_classification: bool = False

    @abstractmethod
    def validate(self, gara: object) -> ValidationResult:
        """Validate tournament configuration against strategy-specific requirements.

        Each strategy has different constraints (player counts, round limits, etc.).
        This method enables early detection of configuration issues before
        tournament execution, preventing runtime failures and player frustration.

        Args:
            gara: Tournament/competition object to validate

        Returns:
            ValidationResult indicating compatibility and any configuration issues
        """
        ...

    def create_round(self, gara: object, round_number: int) -> Sequence[Pairing]:
        """Generate tournament round pairings with persistent side effects.

        Primary execution method that generates player pairings and applies
        necessary side effects (creating Match objects, updating classifications,
        recording encounters). Distinct from preview methods that don't modify state.

        Args:
            gara: Tournament object with player inscriptions and history
            round_number: Sequential round number (affects some algorithms)

        Returns:
            Sequence of Pairing objects representing this round's matches

        Side Effects:
            - May create Match objects in database
            - May update player classifications and encounter history
            - May trigger notifications and other cross-domain operations
        """
        # Default implementation for compatibility: call propose if it exists
        if hasattr(self, 'propose'):
            return self.propose(gara, round_number)  # type: ignore
        else:
            raise NotImplementedError("Subclasses must implement create_round")



class BaseStrategy(PairingStrategy):
    """Abstract base implementation providing common strategy infrastructure.

    Implements the Template Method pattern to standardize strategy execution flow:
    validation → preprocessing → pairing generation → postprocessing → side effects.
    Concrete strategies override specific steps while benefiting from common
    infrastructure like error handling.

    Features:
    - Standardized validation with common checks
    - Template method execution flow
    - Extensible hook points for customization

    Design Rationale:
        All pool tournament strategies share common concerns (validation,
        error handling) while differing in core pairing logic. This base class
        eliminates duplication while maintaining algorithm flexibility.
    """

    # Strategy metadata (to be overridden)
    name: str = "base"
    display_name: str = "Base Strategy"
    description: str = "Abstract base strategy"
    min_players: int = 2
    max_players: Optional[int] = None
    supports_byes: bool = True
    requires_classification: bool = False

    # Algorithm constants
    BYE_PLAYER_ID: int = -1  # Special player ID for bye handling in algorithms

    def __init__(self):
        pass

    def validate(self, gara: object) -> ValidationResult:
        """Template method providing standardized validation with common
        tournament rules.

        Performs universal validation (inscription requirements, player counts, etc.)
        before delegating to strategy-specific validation logic. This ensures all
        strategies enforce basic tournament integrity rules consistently.

        Validation Hierarchy:
        1. Universal checks (inscriptions, player counts)
        2. Strategy-specific requirements (via _validate_strategy_specific)
        3. Result aggregation with proper severity levels
        """
        errors = []
        warnings = []

        # Common validations
        if not hasattr(gara, "inscriptions"):
            errors.append("Gara must have inscriptions attribute")
        else:
            active_inscriptions = self._get_active_inscriptions(gara)
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
        strategy_validation = self._validate_strategy_specific(gara)
        errors.extend(strategy_validation.get("errors", []))
        warnings.extend(strategy_validation.get("warnings", []))

        if errors:
            return ValidationResult.failure(errors, warnings)
        else:
            return ValidationResult.success(warnings=warnings)

    def create_round(self, gara: object, round_number: int) -> Sequence[Pairing]:
        """Template method orchestrating complete round creation with side effects.

        Standardized execution flow ensuring all strategies follow consistent patterns:
        1. Pre-execution validation
        2. Data preprocessing and player list preparation
        3. Core pairing generation (strategy-specific)
        4. Pairing enhancement and quality calculation
        5. Side effect application (Match creation, classification updates)

        This pattern ensures reliability, consistent behavior, and comprehensive
        instrumentation across all tournament formats.
        """

        # Validate first
        validation = self.validate(gara)
        if not validation.ok:
            raise ValueError(f"Validation failed: {'; '.join(validation.errors)}")

        # Get active players
        active_inscriptions = self._get_active_inscriptions(gara)

        # Pre-processing hook
        processed_data = self._preprocess_data(gara, active_inscriptions, round_number)

        # Generate pairings (strategy-specific)
        pairings = self._generate_pairings(processed_data, round_number)

        # Post-processing hook
        enhanced_pairings = self._postprocess_pairings(pairings, gara, round_number)

        # Apply side effects
        self._apply_side_effects(enhanced_pairings, gara, round_number)


        return enhanced_pairings


    # Template method hooks for strategy customization

    @abstractmethod
    def _generate_pairings(
        self,
        processed_data: Dict[str, Any],
        round_number: int,
    ) -> Sequence[Pairing]:
        """Generate tournament pairings using strategy-specific algorithm.

        Core method where each strategy implements its unique pairing logic.
        Called within the template method flow after validation and preprocessing.

        Args:
            processed_data: Standardized data structure with players, gara, context
            round_number: Sequential round number for round-dependent algorithms

        Returns:
            Sequence of Pairing objects representing the strategy's match assignments

        Strategy Examples:
        - Amalfi: Use classification and encounter history for intelligent pairing
        - Round-Robin: Follow systematic rotation pattern
        - Elimination: Pair winners from previous round
        - Random: Generate random assignments with anti-rematch filtering
        """

    def _validate_strategy_specific(self, gara: object) -> Dict[str, List[str]]:
        """Override for strategy-specific validation."""
        return {"errors": [], "warnings": []}

    def _preprocess_data(
        self, gara: object, active_inscriptions: List[Any], round_number: int
    ) -> Dict[str, Any]:
        """Override for strategy-specific preprocessing."""
        return {
            "gara": gara,
            "players": [i.user_id for i in active_inscriptions],
            "round_number": round_number,
        }

    def _postprocess_pairings(
        self, pairings: Sequence[Pairing], gara: object, round_number: int
    ) -> Sequence[Pairing]:
        """Override for strategy-specific postprocessing."""
        return pairings

    def _apply_side_effects(
        self, pairings: Sequence[Pairing], gara: object, round_number: int
    ) -> None:
        """Override for strategy-specific side effects
        (e.g., updating classification)."""

    # Helper methods

    def _get_active_inscriptions(self, gara: object) -> List[Any]:
        """Get active inscriptions for the gara."""
        inscriptions = getattr(gara, "inscriptions", [])
        return [
            i for i in inscriptions if hasattr(i, "status") and i.status == "confirmed"
        ]

