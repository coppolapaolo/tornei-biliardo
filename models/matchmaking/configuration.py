"""
Module: models/matchmaking/configuration.py
Purpose: Strategy configuration and validation
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


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


class RatingType(str, Enum):
    FARGO = "fargo"
    ELO = "elo"


@dataclass
class StrategyConfiguration:
    """Configuration for a matchmaking strategy."""

    strategy: MatchmakingStrategy
    first_round_policy: FirstRoundPolicy
    odd_number_policy: OddNumberPolicy
    anti_rematch_enabled: bool
    rounds_count: Optional[int] = None
    rating_type: Optional[RatingType] = None

    def validate(
        self, num_players: Optional[int] = None, distance: Optional[int] = None
    ) -> List[str]:
        """Validate the configuration for consistency."""
        errors = []

        # Get strategy constraints
        constraints = STRATEGY_CONSTRAINTS.get(self.strategy)
        if not constraints:
            errors.append(f"Strategia {self.strategy} non supportata")
            return errors

        # Validate first round policy
        if self.first_round_policy.value not in constraints["first_round_policies"]:
            errors.append(
                f"{self.strategy} non supporta la policy di primo turno {self.first_round_policy}"
            )

        # Validate odd number policy
        if self.odd_number_policy.value not in constraints["odd_policies"]:
            errors.append(
                f"{self.strategy} non supporta la policy per numero dispari {self.odd_number_policy}"
            )

        # Validate trio with distance
        if self.odd_number_policy == OddNumberPolicy.TRIO:
            if distance and distance > 7:
                errors.append("Match a tre supportati solo fino a distanza 7")

        # Validate anti-rematch
        if not self.anti_rematch_enabled and constraints.get("anti_rematch_required"):
            errors.append(f"{self.strategy} richiede anti-rematch abilitato")

        # Validate rounds count for fixed-rounds strategies
        if constraints["fixed_rounds"] and num_players:
            required_rounds = calculate_rounds_for_strategy(self.strategy, num_players)
            if self.rounds_count and self.rounds_count != required_rounds:
                errors.append(
                    f"{self.strategy} con {num_players} giocatori richiede esattamente {required_rounds} turni"
                )

        return errors

    def to_dict(self) -> Dict:
        """Convert to dictionary for database storage."""
        return {
            "matchmaking_strategy": self.strategy.value,
            "first_round_policy": self.first_round_policy.value,
            "odd_number_policy": self.odd_number_policy.value,
            "anti_rematch_enabled": self.anti_rematch_enabled,
            "rounds_count": self.rounds_count,
            "rating_type": self.rating_type.value if self.rating_type else None,
        }

    @classmethod
    def from_gara(cls, gara) -> "StrategyConfiguration":
        """Create configuration from Gara model."""
        return cls(
            strategy=MatchmakingStrategy(gara.matchmaking_strategy),
            first_round_policy=FirstRoundPolicy(gara.first_round_policy),
            odd_number_policy=OddNumberPolicy(gara.odd_number_policy),
            anti_rematch_enabled=gara.anti_rematch_enabled,
            rounds_count=gara.rounds_count,
            rating_type=(
                RatingType(gara.rating_type)
                if hasattr(gara, "rating_type") and gara.rating_type
                else None
            ),
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
    """Calculate the optimal number of rounds for a strategy."""
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
    """Get trio match configuration for a given distance."""
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
    """Validate if a strategy can be changed based on competition status."""
    from models.status_enum import GaraStatus

    # Can only change strategy in SETUP status
    if gara_status != GaraStatus.SETUP.value:
        return False, "La strategia può essere modificata solo in fase di setup"

    # Check if strategies are compatible for migration
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
