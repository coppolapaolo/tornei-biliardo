from __future__ import annotations
from typing import Sequence, Dict, Any, Optional, List

from .registry import EngineRegistry
from .strategies.base import Pairing


class MatchmakingService:
    """Central service for tournament matchmaking using configurable pairing strategies.

    Implements the Strategy Pattern to support multiple tournament formats commonly used
    in American Pool competitions: Amalfi (adaptive), Round-Robin (all-play-all),
    Direct Elimination (knockout), and Random with anti-rematch protection.

    This service acts as the primary interface for tournament directors to generate
    player pairings while enforcing business rules like anti-rematch logic,
    bye handling, and trio match support for odd player counts.

    Architecture:
    - Strategy Registry: Dynamic strategy selection and configuration
    - Context Injection: Deterministic behavior for testing and repeatability

    Business Domain: American Pool tournament management with community features
    """

    def __init__(self, registry: Optional[EngineRegistry] = None):
        self._registry = registry or EngineRegistry()

    def run(
        self,
        strategy_name: str,
        gara: object,
        round_number: int,
        seed: Optional[int] = None,
    ) -> Sequence[Pairing]:
        """Execute pairing strategy with enhanced features and deterministic behavior.

        This is the primary entry point for generating tournament pairings. It supports
        deterministic seeding for testing and replay functionality, which is crucial
        for tournament integrity and debugging pairing issues.

        Args:
            strategy_name: Algorithm to use ("amalfi", "round_robin", etc.)
            gara: Tournament/competition object with player inscriptions
            round_number: Sequential round number (affects some algorithms)
            seed: Optional deterministic seed for reproducible results

        Returns:
            Sequence of Pairing objects representing player matchups for this round

        Raises:
            ValueError: If strategy is unknown or validation fails

        Business Context:
            Tournament directors need consistent, fair pairings. Deterministic seeding
            allows replaying controversial rounds or testing algorithm changes safely.
        """
        try:
            if seed is not None:
                # Use factory to create strategy with deterministic context
                strategy = self._registry.create_strategy(strategy_name, seed)
            else:
                strategy = self._registry.get(strategy_name)
        except KeyError:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        return strategy.create_round(gara, round_number)

    def validate(self, strategy_name: str, gara: object) -> Dict[str, Any]:
        """Validate tournament configuration against strategy requirements.

        Different pairing strategies have specific requirements (minimum players,
        round counts, etc.). This validation prevents runtime failures and provides
        clear feedback to tournament directors during setup.

        Args:
            strategy_name: Algorithm to validate against
            gara: Tournament object to validate

        Returns:
            Dict with validation results:
            - valid: Boolean indicating if configuration is acceptable
            - messages: All validation feedback (errors + warnings)
            - warnings: Non-blocking issues that should be reviewed
            - errors: Blocking issues that prevent strategy execution

        Business Value:
            Early validation prevents tournament disruption and provides clear
            guidance for fixing configuration issues before player registration.
        """
        try:
            strategy = self._registry.get(strategy_name)
        except KeyError:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        result = strategy.validate(gara)
        return {
            "valid": result.ok,
            "messages": result.messages,
            "warnings": result.warnings,
            "errors": result.errors,
        }

    def get_available_strategies(self) -> List[Dict[str, Any]]:
        """Get comprehensive list of available pairing strategies with
        configuration details.

        Provides tournament directors with strategy selection information including
        constraints and capabilities. This supports informed decision-making during
        tournament setup based on player count, desired format, and competition goals.

        Returns:
            List of strategy dictionaries containing:
            - name: Internal strategy identifier
            - display_name: Human-readable name for UI
            - description: Strategy explanation for tournament directors
            - min_players, max_players: Player count constraints
            - supports_byes: Whether odd player counts are handled
            - requires_classification: Whether player rankings are needed

        Business Context:
            Different pool tournament formats suit different scenarios:
            - Round-Robin: Small groups, everyone plays everyone
            - Elimination: Large tournaments, single/double knockout
            - Amalfi: Flexible rounds with intelligent pairing
            - Random: Casual events with anti-rematch protection
        """
        strategies = []
        for name, strategy in self._registry.list().items():
            strategies.append(
                {
                    "name": name,
                    "display_name": getattr(strategy, "display_name", name),
                    "description": getattr(strategy, "description", ""),
                    "min_players": getattr(strategy, "min_players", 2),
                    "max_players": getattr(strategy, "max_players", None),
                    "supports_byes": getattr(strategy, "supports_byes", True),
                    "requires_classification": getattr(
                        strategy, "requires_classification", False
                    ),
                }
            )
        return strategies


# Global instance
matchmaking_service = MatchmakingService()
