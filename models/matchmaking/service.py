from __future__ import annotations
from typing import Sequence, Dict, Any, Optional, List, TYPE_CHECKING
from datetime import timedelta

from .registry import EngineRegistry, PairingContext
from .strategies.base import Pairing
from ..base import db
from ..match.services import MatchService
from ..rating.services import RatingService, HandicapService
from ..challenge.services import ChallengeService

# Import strategies
from .strategies.advanced_amalfi import AdvancedAmalfiStrategy
from .strategies.amalfi_adapter import AmalfiStrategy
from .strategies.amalfi_unified_adapter import AmalfiUnifiedAdapter

if TYPE_CHECKING:
    pass


class MatchmakingOrchestrator:
    """Advanced orchestrator for cross-domain matchmaking operations.

    Coordinates complex tournament operations that span multiple business domains,
    including handicap calculations, X-replacement strategies (bye alternatives),
    and match format suggestions based on player categories. This orchestrator
    implements the Facade pattern to simplify interactions between the matchmaking
    system and other domain services (rating, handicap, challenges).

    Design Pattern: Facade + Strategy + Template Method
    Business Context: Pool tournament management with community features
    """

    def __init__(self, matchmaking_service: "MatchmakingService"):
        self._matchmaking = matchmaking_service
        self._cache = {}
        self._cache_ttl = timedelta(minutes=5)  # Cache for 5 minutes

    def create_round_with_handicaps(
        self,
        gara_id: int,
        round_number: int,
        strategy_name: str = "amalfi",
        apply_handicaps: bool = True,
        handicap_rule_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create tournament round with automatic handicap calculation and enhanced match data.

        This method combines matchmaking strategy execution with handicap system integration
        to create fair matches between players of different skill levels. It's designed
        for competitive pool tournaments where skill balancing is crucial for game quality.

        Args:
            gara_id: Tournament/competition identifier
            round_number: Sequential round number (1-based)
            strategy_name: Pairing algorithm to use ("amalfi", "round_robin", etc.)
            apply_handicaps: Whether to calculate skill-based handicaps
            handicap_rule_id: Specific handicap calculation rule to use

        Returns:
            Dict containing round statistics, match count breakdowns, and created Match objects
            with embedded handicap data for fair play enforcement

        Business Logic:
            - Pool tournaments often require handicaps to balance skill differences
            - Different disciplines (8-ball, 9-ball, etc.) may need different handicap rules
            - Match format suggestions help tournament directors optimize game duration
        """

        # Get gara and validate
        from ..competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if gara is None:
            from flask import abort

            abort(404)

        # Generate pairings
        pairings = self._matchmaking.run(
            strategy_name=strategy_name, gara=gara, round_number=round_number
        )

        # Apply handicaps if requested
        enhanced_pairings = []
        for pairing in pairings:
            enhanced_pairing = {
                "pairing": pairing,
                "handicap": None,
                "suggested_format": self._suggest_match_format(pairing),
            }

            if (
                apply_handicaps
                and not pairing.is_bye
                and pairing.player1_id is not None
                and pairing.player2_id is not None
            ):
                handicap = HandicapService.calculate_handicap(
                    player1_id=pairing.player1_id,
                    player2_id=pairing.player2_id,
                    rule_id=handicap_rule_id,
                )
                enhanced_pairing["handicap"] = handicap

            enhanced_pairings.append(enhanced_pairing)

        # Create matches with enhanced data
        matches = []
        for enhanced in enhanced_pairings:
            match_data = {
                "gara_id": gara_id,
                "round_number": round_number,
                "player1_id": enhanced["pairing"].player1_id,
                "player2_id": enhanced["pairing"].player2_id,
                "is_bye": enhanced["pairing"].is_bye,
                "handicap_data": enhanced["handicap"],
                "suggested_format": enhanced["suggested_format"],
            }

            match = MatchService.create_match(**match_data)
            matches.append(match)

        return {
            "round_number": round_number,
            "total_matches": len(matches),
            "matches_with_handicap": len(
                [m for m in enhanced_pairings if m["handicap"]]
            ),
            "bye_matches": len([m for m in matches if m.is_bye]),
            "matches": matches,
        }

    def suggest_x_replacement_strategies(
        self, gara_id: int, user_id: int, round_number: int
    ) -> List[Dict[str, Any]]:
        """Suggest alternative activities for players who received a bye (X replacement).

        In pool tournaments, when there's an odd number of players, one player gets a "bye"
        (sits out the round). This method suggests meaningful alternatives like completing
        skill challenges or playing individual matches to keep all players engaged.

        Args:
            gara_id: Tournament identifier
            user_id: Player who received the bye
            round_number: Current round number

        Returns:
            List of strategy dictionaries, each containing:
            - type: 'challenge', 'individual_match', or 'makeup_match'
            - name: Human-readable strategy name
            - description: What the player would do instead of sitting out
            - specific data: challenge_id, available_players, etc.
            - estimated_duration: Time commitment in minutes
            - scoring_method: How results integrate with tournament scoring

        Business Context:
            Pool tournaments value player engagement. Rather than sitting idle during
            a bye round, players can practice skills, play casual games, or complete
            unfinished matches, maintaining tournament momentum and community interaction.
        """

        strategies = []

        # Strategy 1: Challenge completion
        suitable_challenge = ChallengeService.get_challenge_for_x_replacement(gara_id)
        if suitable_challenge:
            strategies.append(
                {
                    "type": "challenge",
                    "name": "Individual Challenge",
                    "description": f"Complete '{suitable_challenge.name}' challenge",
                    "challenge_id": suitable_challenge.id,
                    "estimated_duration": "15-30 minutes",
                    "scoring_method": "challenge_score_to_rack_difference",
                }
            )

        # Strategy 2: Individual match proposal
        available_players = self._get_available_players_for_individual_match(
            gara_id, user_id, round_number
        )
        if available_players:
            strategies.append(
                {
                    "type": "individual_match",
                    "name": "Individual Match",
                    "description": "Play individual match with available player",
                    "available_players": available_players[:3],  # Limit to top 3
                    "estimated_duration": "30-45 minutes",
                    "scoring_method": "direct_match_result",
                }
            )

        # Strategy 3: Previous round makeup (if any incomplete)
        incomplete_matches = self._get_user_incomplete_matches(gara_id, user_id)
        if incomplete_matches:
            strategies.append(
                {
                    "type": "makeup_match",
                    "name": "Makeup Match",
                    "description": "Complete previously incomplete match",
                    "incomplete_matches": incomplete_matches,
                    "estimated_duration": "Variable",
                    "scoring_method": "complete_existing_match",
                }
            )

        return strategies

    def _suggest_match_format(self, pairing: Pairing) -> Dict[str, Any]:
        """Suggest optimal match format based on player categories/ratings."""

        if pairing.is_bye:
            return {"format": "bye", "reason": "No opponent"}

        # Get player categories
        cat1 = None
        cat2 = None

        if pairing.player1_id is not None:
            cat1 = RatingService.get_player_effective_category(pairing.player1_id)
        if pairing.player2_id is not None:
            cat2 = RatingService.get_player_effective_category(pairing.player2_id)

        # Default format
        suggested_format = {
            "race_to": 5,
            "discipline": "palla_8",
            "break_rule": "alternate",
            "format_name": "Standard",
        }

        # Adjust based on categories
        if cat1 and cat2:
            from ..rating.models import CategoryLevel

            # Beginner matches - shorter format
            if cat1 in [CategoryLevel.C, CategoryLevel.D] and cat2 in [
                CategoryLevel.C,
                CategoryLevel.D,
            ]:
                suggested_format.update(
                    {
                        "race_to": 3,
                        "format_name": "Beginner Friendly",
                        "reason": "Shorter format for developing players",
                    }
                )

            # Expert matches - longer format
            elif cat1 == CategoryLevel.A and cat2 == CategoryLevel.A:
                suggested_format.update(
                    {
                        "race_to": 7,
                        "format_name": "Expert Level",
                        "reason": "Extended format for advanced players",
                    }
                )

        return suggested_format

    def _get_available_players_for_individual_match(
        self, gara_id: int, user_id: int, round_number: int
    ) -> List[Dict[str, Any]]:
        """Get players available for individual match during bye."""

        # Get all registered players in the same tournament
        from ..competition.models import Inscription
        from ..match.models import Match
        from ..user.models import User

        # Get all players in gara
        inscriptions = Inscription.query.filter_by(gara_id=gara_id).all()
        player_ids = [i.user_id for i in inscriptions if not i.is_withdrawn]

        # Identify players currently available (not in active matches)
        playing_matches = Match.query.filter(
            Match.gara_id == gara_id,
            Match.__table__.c.status.in_(["pending", "playing"]),
        ).all()

        playing_player_ids = set()
        for match in playing_matches:
            if match.player1_id:
                playing_player_ids.add(match.player1_id)
            if match.player2_id:
                playing_player_ids.add(match.player2_id)

        available_player_ids = [
            pid
            for pid in player_ids
            if pid not in playing_player_ids and pid != user_id
        ]

        # Get player details
        available_players = []
        for pid in available_player_ids[:5]:  # Limit to 5 for performance
            user = db.session.get(User, pid)
            if user:
                available_players.append(
                    {
                        "id": user.id,
                        "username": user.username,
                        "rating": getattr(user, "fargo_rating", 0)
                        or getattr(user, "elo_rating", 0)
                        or 0,
                    }
                )

        # Prioritize opponents with similar skill levels for competitive balance
        user_obj = db.session.get(User, user_id)
        if user_obj:
            user_rating = (
                getattr(user_obj, "fargo_rating", 0)
                or getattr(user_obj, "elo_rating", 0)
                or 0
            )
            available_players.sort(key=lambda p: abs(p["rating"] - user_rating))

        return available_players

    def _get_user_incomplete_matches(
        self, gara_id: int, user_id: int
    ) -> List[Dict[str, Any]]:
        """Get user's incomplete matches."""
        from ..match.models import Match

        incomplete_matches = Match.query.filter(
            Match.gara_id == gara_id,
            Match.__table__.c.status.in_(["pending", "playing"]),
            db.or_(Match.player1_id == user_id, Match.player2_id == user_id),
        ).all()

        return [
            {
                "id": match.id,
                "round_number": match.round_number,
                "opponent": (
                    match.player2.username
                    if match.player1_id == user_id
                    else match.player1.username if match.player2_id else "Bye"
                ),
                "status": match.status,
            }
            for match in incomplete_matches
            if match.player1 and match.player2
        ]


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
    - Orchestrator Integration: Cross-domain operations (handicaps, challenges)
    - Context Injection: Deterministic behavior for testing and repeatability

    Business Domain: American Pool tournament management with community features
    """

    def __init__(self, registry: Optional[EngineRegistry] = None):
        self._registry = registry or EngineRegistry()
        self._orchestrator = MatchmakingOrchestrator(self)

        # Register the advanced Amalfi strategy
        self._register_advanced_strategies()

    def _register_advanced_strategies(self):
        """Register advanced pairing strategies with conflict resolution.

        Handles the registration of enhanced strategies while avoiding naming conflicts.
        The unified Amalfi strategy takes precedence over the legacy adapter, and the
        advanced Amalfi requires a base strategy to compose functionality.

        Strategy Resolution Logic:
        - Only register if not already present (prevents duplicates)
        - Advanced strategies compose over base strategies (Decorator pattern)
        - Failed registrations are silently ignored to maintain system stability
        """
        # Register the unified Amalfi strategy only if not already present
        try:
            self._registry.get("amalfi_unified")
        except KeyError:
            unified_amalfi = AmalfiUnifiedAdapter()
            self._registry.register(unified_amalfi)

        # Register the advanced Amalfi strategy
        try:
            self._registry.get("amalfi_advanced")
        except KeyError:
            try:
                base_amalfi = self._registry.get("amalfi")
                if base_amalfi and isinstance(base_amalfi, AmalfiStrategy):
                    advanced_amalfi = AdvancedAmalfiStrategy(base_amalfi)
                    self._registry.register(advanced_amalfi)
            except KeyError:
                # If base amalfi strategy is not available, we can't register advanced one
                pass

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
        """Get comprehensive list of available pairing strategies with configuration details.

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

    @property
    def orchestrator(self) -> MatchmakingOrchestrator:
        """Get the matchmaking orchestrator."""
        return self._orchestrator


# Global instance
matchmaking_service = MatchmakingService()
