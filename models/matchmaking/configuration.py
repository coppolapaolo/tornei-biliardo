"""
Matchmaking Strategy Configuration System

Provides comprehensive configuration management for tournament pairing strategies,
enabling tournament directors to customize algorithm behavior based on tournament
format, player preferences, and organizational requirements.

Features:
- Strategy-specific constraint validation
- Policy compatibility checking
- Configuration serialization for database storage
- Tournament format optimization recommendations

Business Context:
    American Pool tournaments require different approaches based on format:
    - Casual events: Random pairing with anti-rematch
    - Competitive tournaments: Amalfi algorithm with classification
    - League play: Round-robin for complete standings
    - Championships: Elimination brackets for clear winners
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple


class MatchmakingStrategy(str, Enum):
    AMALFI = "amalfi"
    ROUND_ROBIN = "round_robin"
    DIRECT_ELIMINATION = "direct_elimination"
    DOUBLE_KNOCKOUT = "double_knockout"
    RANDOM = "random"


class FirstRoundPolicy(str, Enum):
    RANDOM = "random"
    RATING = "rating"
    CLASSIFICATION = "classification"


class OddNumberPolicy(str, Enum):
    BYE = "bye"
    BYE_WITH_CHALLENGE = "bye_with_challenge"
    TRIO = "trio"


# =============================================================================
# Strategy Behavior Configuration
# =============================================================================
# These enums and config define behavioral differences between strategies


class ClassificationType(str, Enum):
    """How classification is structured."""

    PER_ROUND = "per_round"  # Separate classification per round (Amalfi)
    OVERALL = "overall"  # Single cumulative classification (Random)


class ClassificationCriteria(str, Enum):
    """What determines ranking in classification."""

    MATCH_WINS = "match_wins"  # Primary: wins, secondary: rack difference (Amalfi)
    RACKS_WON = "racks_won"  # Only total racks won count (Random)


class ClassificationUpdateTiming(str, Enum):
    """When classification is recalculated."""

    ON_ROUND_COMPLETE = "round_complete"  # After all round matches finish (Amalfi)
    ON_MATCH_COMPLETE = "match_complete"  # After each individual match (Random)


@dataclass(frozen=True)
class StrategyBehaviorConfig:
    """Defines behavioral differences between matchmaking strategies.

    This configuration captures how different strategies behave regarding:
    - Round locking (can previous rounds be modified?)
    - Classification (structure, criteria, update timing)
    - Bye/odd number handling defaults
    - Match reset permissions

    Design: Frozen dataclass for immutability. Use STRATEGY_BEHAVIORS registry
    to access configuration for each strategy.
    """

    # Round locking
    supports_round_locking: bool

    # Classification behavior
    classification_type: ClassificationType
    classification_criteria: ClassificationCriteria
    classification_update: ClassificationUpdateTiming

    # Bye/odd number handling - function that takes distance and returns default policy
    default_odd_policy_fn: Callable[[int], OddNumberPolicy]

    # Trio constraint
    trio_max_distance: int = 7

    def get_default_odd_policy(self, distance: int) -> OddNumberPolicy:
        """Get the default odd number policy based on distance."""
        return self.default_odd_policy_fn(distance)

    def can_use_trio(self, distance: int) -> bool:
        """Check if trio matches are allowed for this distance."""
        return distance <= self.trio_max_distance


def _amalfi_odd_policy(distance: int) -> OddNumberPolicy:
    """Amalfi default: always BYE (X)."""
    return OddNumberPolicy.BYE


def _random_odd_policy(distance: int) -> OddNumberPolicy:
    """Random default: TRIO if distance <= 7, else BYE_WITH_CHALLENGE."""
    if distance <= 7:
        return OddNumberPolicy.TRIO
    return OddNumberPolicy.BYE_WITH_CHALLENGE


STRATEGY_BEHAVIORS: Dict[MatchmakingStrategy, StrategyBehaviorConfig] = {
    MatchmakingStrategy.AMALFI: StrategyBehaviorConfig(
        supports_round_locking=True,
        classification_type=ClassificationType.PER_ROUND,
        classification_criteria=ClassificationCriteria.MATCH_WINS,
        classification_update=ClassificationUpdateTiming.ON_ROUND_COMPLETE,
        default_odd_policy_fn=_amalfi_odd_policy,
    ),
    MatchmakingStrategy.RANDOM: StrategyBehaviorConfig(
        supports_round_locking=False,
        classification_type=ClassificationType.OVERALL,
        classification_criteria=ClassificationCriteria.RACKS_WON,
        classification_update=ClassificationUpdateTiming.ON_MATCH_COMPLETE,
        default_odd_policy_fn=_random_odd_policy,
    ),
    MatchmakingStrategy.ROUND_ROBIN: StrategyBehaviorConfig(
        supports_round_locking=True,
        classification_type=ClassificationType.PER_ROUND,
        classification_criteria=ClassificationCriteria.MATCH_WINS,
        classification_update=ClassificationUpdateTiming.ON_ROUND_COMPLETE,
        default_odd_policy_fn=_amalfi_odd_policy,
    ),
    MatchmakingStrategy.DIRECT_ELIMINATION: StrategyBehaviorConfig(
        supports_round_locking=True,
        classification_type=ClassificationType.PER_ROUND,
        classification_criteria=ClassificationCriteria.MATCH_WINS,
        classification_update=ClassificationUpdateTiming.ON_ROUND_COMPLETE,
        default_odd_policy_fn=_amalfi_odd_policy,
    ),
    MatchmakingStrategy.DOUBLE_KNOCKOUT: StrategyBehaviorConfig(
        supports_round_locking=True,
        classification_type=ClassificationType.PER_ROUND,
        classification_criteria=ClassificationCriteria.MATCH_WINS,
        classification_update=ClassificationUpdateTiming.ON_ROUND_COMPLETE,
        default_odd_policy_fn=_amalfi_odd_policy,
    ),
}


def get_strategy_behavior(strategy: MatchmakingStrategy) -> StrategyBehaviorConfig:
    """Get behavior configuration for a strategy.

    Args:
        strategy: The matchmaking strategy

    Returns:
        StrategyBehaviorConfig for the strategy

    Raises:
        KeyError: If strategy not found in registry
    """
    return STRATEGY_BEHAVIORS[strategy]


@dataclass
class StrategyConfiguration:
    """Comprehensive configuration for tournament matchmaking strategies.

    Encapsulates all settings that control how pairing algorithms behave,
    including first-round seeding, odd-number handling, and anti-rematch policies.
    Provides validation to ensure configuration compatibility with chosen strategy.

    Design Pattern: Value Object with validation capabilities
    """

    strategy: MatchmakingStrategy
    first_round_policy: FirstRoundPolicy
    odd_number_policy: OddNumberPolicy
    anti_rematch_enabled: bool
    rounds_count: Optional[int] = None

    def validate(
        self,
        num_players: Optional[int] = None,
        distance: Optional[int] = None,
        is_race_to: Optional[bool] = None,
    ) -> List[str]:
        """Validate config consistency against strategy constraints.

        Full title: Validate configuration consistency against strategy
        constraints and tournament parameters.

        Comprehensive validation ensuring the configuration will produce successful
        tournament execution without runtime failures or suboptimal player experience.

        Validation Categories:
        1. Strategy-specific policy compatibility
        2. Player count vs. strategy requirements
        3. Trio match feasibility (distance-dependent)
        4. Required vs. optional feature alignment
        5. Round count optimization for fixed-round strategies

        Args:
            num_players: Expected tournament player count for optimization
            distance: Tournament format distance (affects trio match complexity)
            is_race_to: Whether match uses race-to or exact scoring
                (trio requires race-to)

        Returns:
            List of validation error messages (empty if configuration is valid)

        Business Value:
            Prevents tournament setup errors that could disrupt player experience
            and provides clear guidance for configuration improvements.
        """
        errors = []

        # Retrieve strategy-specific requirements and limitations
        constraints = STRATEGY_CONSTRAINTS.get(self.strategy)
        if not constraints:
            errors.append(f"Strategia {self.strategy} non supportata")
            return errors

        # Ensure first-round seeding policy is supported by chosen strategy
        if (
            self.first_round_policy.value
            not in constraints["first_round_policies"]
        ):
            errors.append(
                f"{self.strategy} non supporta la policy di "
                f"primo turno {self.first_round_policy}"
            )

        # Verify odd-player handling method is compatible with strategy
        if self.odd_number_policy.value not in constraints["odd_policies"]:
            errors.append(
                f"{self.strategy} non supporta la policy per "
                f"numero dispari {self.odd_number_policy}"
            )

        # Check trio match feasibility against tournament format complexity
        if self.odd_number_policy == OddNumberPolicy.TRIO:
            if distance and distance > 7:
                errors.append("Match a tre supportati solo fino a distanza 7")
            if is_race_to is False:
                errors.append(
                    "Match a tre richiedono modalità 'al N' (is_race_to=True)"
                )

        # Ensure anti-rematch requirements are met for strategy integrity
        if not self.anti_rematch_enabled and constraints.get(
            "anti_rematch_required"
        ):
            errors.append(
                f"{self.strategy} richiede anti-rematch abilitato"
            )

        # Verify round count matches strategy requirements for optimal
        # tournament flow
        if constraints["fixed_rounds"] and num_players:
            required_rounds = calculate_rounds_for_strategy(
                self.strategy, num_players
            )
            if self.rounds_count and self.rounds_count != required_rounds:
                errors.append(
                    f"{self.strategy} con {num_players} giocatori "
                    f"richiede esattamente {required_rounds} turni"
                )

        return errors

    def to_dict(self) -> Dict:
        """Serialize configuration to dictionary format for database persistence.

        Returns:
            Dictionary with all configuration values in database-compatible format
        """
        return {
            "matchmaking_strategy": self.strategy.value,
            "first_round_policy": self.first_round_policy.value,
            "odd_number_policy": self.odd_number_policy.value,
            "anti_rematch_enabled": self.anti_rematch_enabled,
            "rounds_count": self.rounds_count,
        }

    @classmethod
    def from_gara(cls, gara) -> "StrategyConfiguration":
        """Reconstruct configuration from tournament (Gara) database model.

        Factory method for creating configuration objects from persisted tournament
        settings, enabling consistent strategy behavior across tournament sessions.

        Args:
            gara: Tournament model with stored configuration attributes

        Returns:
            StrategyConfiguration object ready for validation and execution
        """
        return cls(
            strategy=MatchmakingStrategy(
                gara.matchmaking_strategy or MatchmakingStrategy.AMALFI.value
            ),
            first_round_policy=FirstRoundPolicy(
                gara.first_round_policy or FirstRoundPolicy.RANDOM.value
            ),
            odd_number_policy=OddNumberPolicy(
                gara.odd_number_policy or OddNumberPolicy.BYE.value
            ),
            anti_rematch_enabled=(
                gara.anti_rematch_enabled
                if gara.anti_rematch_enabled is not None
                else True
            ),
            rounds_count=gara.rounds_count,
        )


# Strategy constraints definition
STRATEGY_CONSTRAINTS = {
    MatchmakingStrategy.ROUND_ROBIN: {
        "first_round_policies": ["random"],
        "odd_policies": ["bye", "bye_with_challenge"],
        "fixed_rounds": True,
        "anti_rematch": False,
        "anti_rematch_required": False,
        "description": "Girone all'italiana: tutti contro tutti",
    },
    MatchmakingStrategy.DIRECT_ELIMINATION: {
        "first_round_policies": ["random", "rating", "classification"],
        "odd_policies": ["bye", "bye_with_challenge"],
        "fixed_rounds": True,
        "anti_rematch": False,
        "anti_rematch_required": False,
        "description": "Eliminazione diretta: chi perde è eliminato",
    },
    MatchmakingStrategy.DOUBLE_KNOCKOUT: {
        "first_round_policies": ["random", "rating", "classification"],
        "odd_policies": ["bye", "bye_with_challenge"],
        "fixed_rounds": True,
        "anti_rematch": False,
        "anti_rematch_required": False,
        "description": "Doppia eliminazione: due sconfitte per essere eliminati",
    },
    MatchmakingStrategy.AMALFI: {
        "first_round_policies": ["random", "rating", "classification"],
        "odd_policies": ["bye", "bye_with_challenge", "trio"],
        "fixed_rounds": False,
        "anti_rematch": True,
        "anti_rematch_required": True,
        "description": "Sistema Amalfi: abbinamenti dinamici con anti-reincontro",
    },
    MatchmakingStrategy.RANDOM: {
        "first_round_policies": ["random"],
        "odd_policies": ["bye", "bye_with_challenge", "trio"],
        "fixed_rounds": False,
        "anti_rematch": True,
        "anti_rematch_required": False,
        "description": "Abbinamenti casuali con anti-reincontro",
    },
}


def calculate_rounds_for_strategy(
    strategy: MatchmakingStrategy, num_players: int
) -> int:
    """Calculate optimal round count for tournament strategy and player count.

    Different strategies require specific round counts for proper tournament flow:
    - Round-Robin: n-1 rounds (everyone plays everyone)
    - Direct Elimination: log2(n) rounds (binary elimination tree)
    - Double Knockout: 2*log2(n) rounds (winners + losers brackets)
    - Flexible strategies: Sensible defaults based on tournament size

    Args:
        strategy: Tournament pairing algorithm
        num_players: Total confirmed player count

    Returns:
        Recommended number of rounds for optimal tournament progression

    Business Logic:
        Proper round calculation ensures tournaments conclude naturally
        with clear winners and appropriate time investment for participants.
    """
    import math

    if strategy == MatchmakingStrategy.ROUND_ROBIN:
        return num_players - 1 if num_players > 1 else 1
    elif strategy == MatchmakingStrategy.DIRECT_ELIMINATION:
        return math.ceil(math.log2(num_players)) if num_players > 1 else 1
    elif strategy == MatchmakingStrategy.DOUBLE_KNOCKOUT:
        # Double elimination needs approximately 2 * log2(n) rounds
        return 2 * math.ceil(math.log2(num_players)) if num_players > 1 else 1
    else:
        # For flexible strategies, return a sensible default
        return min(num_players - 1, 5)


def get_trio_configuration(distance: int) -> Optional[Dict]:
    """Get trio match format configuration based on tournament distance.

    Trio matches (three-player format) are used when odd player counts occur
    in tournaments. The format complexity scales with tournament distance to
    maintain appropriate match duration and competitive balance.

    Configuration Elements:
    - mini_rounds: Number of rotation phases within the trio match
    - racks_per_player: Individual rack allocation for fair competition
    - total_racks: Overall match length
    - scoring: Point calculation method for tournament standings

    Args:
        distance: Tournament format distance (3-7 supported)

    Returns:
        Dict with trio configuration parameters, or None if distance unsupported

    Business Context:
        Pool trio matches require careful balancing of game time, fairness,
        and integration with overall tournament scoring systems.
    """
    trio_configs = {
        3: {
            "mini_rounds": 1,
            "racks_per_player": 2,
            "total_racks": 3,
            "scoring": "1 + racks_won",
        },
        4: {
            "mini_rounds": 2,
            "racks_per_player": 4,
            "total_racks": 6,
            "scoring": "racks_won",
        },
        5: {
            "mini_rounds": 2,
            "racks_per_player": 4,
            "total_racks": 6,
            "scoring": "1 + racks_won",
        },
        6: {
            "mini_rounds": 3,
            "racks_per_player": 6,
            "total_racks": 9,
            "scoring": "racks_won",
        },
        7: {
            "mini_rounds": 3,
            "racks_per_player": 6,
            "total_racks": 9,
            "scoring": "1 + racks_won",
        },
    }
    return trio_configs.get(distance)


def validate_strategy_change(
    old_strategy: MatchmakingStrategy,
    new_strategy: MatchmakingStrategy,
    gara_status: str,
) -> Tuple[bool, Optional[str]]:
    """Validate tournament strategy change based on competition status.

    Full title: Validate tournament strategy change based on current
    competition status and compatibility.

    Strategy changes are restricted to prevent tournament disruption and maintain
    competitive integrity. Only compatible strategies can be swapped, and only
    during appropriate tournament phases.

    Validation Rules:
    1. Strategy changes only allowed during SETUP phase (before player registration)
    2. Format compatibility required (can't mix elimination with round-robin)
    3. Player commitment considerations (elimination vs. guaranteed games)

    Args:
        old_strategy: Current tournament strategy
        new_strategy: Desired new strategy
        gara_status: Current tournament phase status

    Returns:
        Tuple of (change_allowed, reason_if_blocked)

    Business Impact:
        Prevents tournament disruption while allowing reasonable configuration
        adjustments during setup phases.
    """
    from models.status_enum import GaraStatus

    # Strategy changes restricted to setup phase to prevent player disruption
    if gara_status != GaraStatus.SETUP.value:
        return False, "La strategia può essere modificata solo in fase di setup"

    # Ensure new strategy is compatible with tournament format expectations
    if old_strategy in [
        MatchmakingStrategy.DIRECT_ELIMINATION,
        MatchmakingStrategy.DOUBLE_KNOCKOUT,
    ]:
        if new_strategy not in [
            MatchmakingStrategy.DIRECT_ELIMINATION,
            MatchmakingStrategy.DOUBLE_KNOCKOUT,
        ]:
            return False, "Non è possibile passare da eliminazione a girone"

    return True, None
