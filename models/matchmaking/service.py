from __future__ import annotations
from typing import Sequence, Dict, Any, Optional, List, TYPE_CHECKING
from datetime import datetime, timedelta
from functools import lru_cache
import hashlib
import json

from .registry import EngineRegistry
from .strategies.base import Pairing
from ..base import db
from ..classification.services import ClassificationService
from ..match.services import MatchService
from ..rating.services import RatingService, HandicapService
from ..challenge.services import ChallengeService

# Import the new advanced strategy
from .strategies.advanced_amalfi import AdvancedAmalfiStrategy
from .strategies.amalfi_adapter import AmalfiStrategy

if TYPE_CHECKING:
    from ..competition.models import Prova


class MatchmakingOrchestrator:
    """Advanced orchestrator for cross-domain matchmaking operations."""

    def __init__(self, matchmaking_service: "MatchmakingService"):
        self._matchmaking = matchmaking_service
        self._cache = {}
        self._cache_ttl = timedelta(minutes=5)  # Cache for 5 minutes

    def create_round_with_handicaps(
        self,
        prova_id: int,
        round_number: int,
        strategy_name: str = "amalfi",
        apply_handicaps: bool = True,
        handicap_rule_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create round with automatic handicap calculation."""

        # Get prova and validate
        from ..competition.models import Prova

        prova = db.session.get(Prova, prova_id)
        if prova is None:
            from flask import abort

            abort(404)

        # Generate pairings
        pairings = self._matchmaking.run(
            strategy_name=strategy_name, prova=prova, round_number=round_number
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
                "prova_id": prova_id,
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
        self, prova_id: int, user_id: int, round_number: int
    ) -> List[Dict[str, Any]]:
        """Suggest X replacement strategies (bye alternatives)."""

        strategies = []

        # Strategy 1: Challenge completion
        suitable_challenge = ChallengeService.get_challenge_for_x_replacement(prova_id)
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
            prova_id, user_id, round_number
        )
        if available_players:
            strategies.append(
                {
                    "type": "individual_match",
                    "name": "Individual Match",
                    "description": f"Play individual match with available player",
                    "available_players": available_players[:3],  # Limit to top 3
                    "estimated_duration": "30-45 minutes",
                    "scoring_method": "direct_match_result",
                }
            )

        # Strategy 3: Previous round makeup (if any incomplete)
        incomplete_matches = self._get_user_incomplete_matches(prova_id, user_id)
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
        self, prova_id: int, user_id: int, round_number: int
    ) -> List[Dict[str, Any]]:
        """Get players available for individual match during bye."""

        # Get players in same prova
        from ..competition.models import Inscription
        from ..match.models import Match
        from ..user.models import User

        # Get all players in prova
        inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()
        player_ids = [i.user_id for i in inscriptions if not i.is_withdrawn]

        # Get players who are not currently playing
        playing_matches = Match.query.filter(
            Match.prova_id == prova_id,
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

        # Sort by rating similarity to user
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
        self, prova_id: int, user_id: int
    ) -> List[Dict[str, Any]]:
        """Get user's incomplete matches."""
        from ..match.models import Match

        incomplete_matches = Match.query.filter(
            Match.prova_id == prova_id,
            Match.__table__.c.status.in_(["pending", "playing"]),
            db.or_(Match.player1_id == user_id, Match.player2_id == user_id),
        ).all()

        return [
            {
                "id": match.id,
                "round_number": match.round_number,
                "opponent": match.player2.username
                if match.player1_id == user_id
                else match.player1.username
                if match.player2_id
                else "Bye",
                "status": match.status,
            }
            for match in incomplete_matches
            if match.player1 and match.player2
        ]


class MatchmakingService:
    """Enhanced service for tournament pairing with strategy pattern."""

    def __init__(self, registry: Optional[EngineRegistry] = None):
        self._registry = registry or EngineRegistry()
        self._orchestrator = MatchmakingOrchestrator(self)

        # Register the advanced Amalfi strategy
        self._register_advanced_strategies()

    def _register_advanced_strategies(self):
        """Register advanced pairing strategies."""
        # Register the advanced Amalfi strategy
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
        prova: object,
        round_number: int,
        preview: bool = False,
    ) -> Sequence[Pairing]:
        """Execute pairing strategy with enhanced features."""
        try:
            strategy = self._registry.get(strategy_name)
        except KeyError:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        if preview:
            return strategy.preview(prova, round_number)
        else:
            return strategy.propose(prova, round_number)

    def validate(self, strategy_name: str, prova: object) -> Dict[str, Any]:
        """Validate prova for specific strategy."""
        try:
            strategy = self._registry.get(strategy_name)
        except KeyError:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        result = strategy.validate(prova)
        return {
            "valid": result.ok,
            "messages": result.messages,
            "warnings": result.warnings,
            "errors": result.errors,
        }

    def get_available_strategies(self) -> List[Dict[str, Any]]:
        """Get list of available strategies with metadata."""
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
