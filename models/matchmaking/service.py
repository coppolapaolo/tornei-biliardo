from __future__ import annotations
from typing import Sequence, Dict, Any, Optional, List
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


class MatchmakingOrchestrator:
    """Advanced orchestrator for cross-domain matchmaking operations."""
    
    def __init__(self, matchmaking_service: 'MatchmakingService'):
        self._matchmaking = matchmaking_service
        self._cache = {}
        self._cache_ttl = timedelta(minutes=5)  # Cache for 5 minutes
    
    def create_round_with_handicaps(
        self,
        prova_id: int,
        round_number: int,
        strategy_name: str = "amalfi",
        apply_handicaps: bool = True,
        handicap_rule_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create round with automatic handicap calculation."""
        
        # Get prova and validate
        from ..competition.models import Prova
        prova = Prova.query.get_or_404(prova_id)
        
        # Generate pairings
        pairings = self._matchmaking.run(
            strategy_name=strategy_name,
            prova=prova,
            round_number=round_number
        )
        
        # Apply handicaps if requested
        enhanced_pairings = []
        for pairing in pairings:
            enhanced_pairing = {
                "pairing": pairing,
                "handicap": None,
                "suggested_format": self._suggest_match_format(pairing)
            }
            
            if apply_handicaps and not pairing.is_bye:
                handicap = HandicapService.calculate_handicap(
                    player1_id=pairing.player1_id,
                    player2_id=pairing.player2_id,
                    rule_id=handicap_rule_id
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
                "suggested_format": enhanced["suggested_format"]
            }
            
            match = MatchService.create_match(**match_data)
            matches.append(match)
        
        return {
            "round_number": round_number,
            "total_matches": len(matches),
            "matches_with_handicap": len([m for m in enhanced_pairings if m["handicap"]]),
            "bye_matches": len([m for m in matches if m.is_bye]),
            "matches": matches
        }
    
    def suggest_x_replacement_strategies(
        self,
        prova_id: int,
        user_id: int,
        round_number: int
    ) -> List[Dict[str, Any]]:
        """Suggest X replacement strategies (bye alternatives)."""
        
        strategies = []
        
        # Strategy 1: Challenge completion
        suitable_challenge = ChallengeService.get_challenge_for_x_replacement(prova_id)
        if suitable_challenge:
            strategies.append({
                "type": "challenge",
                "name": "Individual Challenge",
                "description": f"Complete '{suitable_challenge.name}' challenge",
                "challenge_id": suitable_challenge.id,
                "estimated_duration": "15-30 minutes",
                "scoring_method": "challenge_score_to_rack_difference"
            })
        
        # Strategy 2: Individual match proposal
        available_players = self._get_available_players_for_individual_match(
            prova_id, user_id, round_number
        )
        if available_players:
            strategies.append({
                "type": "individual_match",
                "name": "Individual Match",
                "description": f"Play individual match with available player",
                "available_players": available_players[:3],  # Limit to top 3
                "estimated_duration": "30-45 minutes",
                "scoring_method": "direct_match_result"
            })
        
        # Strategy 3: Previous round makeup (if any incomplete)
        incomplete_matches = self._get_user_incomplete_matches(prova_id, user_id)
        if incomplete_matches:
            strategies.append({
                "type": "makeup_match",
                "name": "Makeup Match",
                "description": "Complete previously incomplete match",
                "incomplete_matches": incomplete_matches,
                "estimated_duration": "Variable",
                "scoring_method": "complete_existing_match"
            })
        
        return strategies
    
    def _suggest_match_format(self, pairing: Pairing) -> Dict[str, Any]:
        """Suggest optimal match format based on player categories/ratings."""
        
        if pairing.is_bye:
            return {"format": "bye", "reason": "No opponent"}
        
        # Get player categories
        cat1 = RatingService.get_player_effective_category(pairing.player1_id)
        cat2 = RatingService.get_player_effective_category(pairing.player2_id)
        
        # Default format
        suggested_format = {
            "race_to": 5,
            "discipline": "palla_8",
            "break_rule": "alternate",
            "format_name": "Standard"
        }
        
        # Adjust based on categories
        if cat1 and cat2:
            from ..rating.models import CategoryLevel
            
            # Beginner matches - shorter format
            if cat1 in [CategoryLevel.C, CategoryLevel.D] and cat2 in [CategoryLevel.C, CategoryLevel.D]:
                suggested_format.update({
                    "race_to": 3,
                    "format_name": "Beginner Friendly",
                    "reason": "Shorter format for developing players"
                })
            
            # Expert matches - longer format
            elif cat1 == CategoryLevel.A and cat2 == CategoryLevel.A:
                suggested_format.update({
                    "race_to": 7,
                    "format_name": "Expert Level",
                    "reason": "Extended format for advanced players"
                })
        
        return suggested_format
    
    def _get_available_players_for_individual_match(
        self,
        prova_id: int,
        user_id: int,
        round_number: int
    ) -> List[Dict[str, Any]]:
        """Get players available for individual match during bye."""
        
        # Get players in same prova who also have bye or finished early
        from ..competition.models import Inscription
        from ..match.models import Match
        from ..user.models import User
        
        # Get all players in prova
        prova_players = (db.session.query(User)
                        .join(Inscription, User.id == Inscription.user_id)
                        .filter(Inscription.prova_id == prova_id)
                        .filter(User.id != user_id)
                        .all())
        
        available_players = []
        
        for player in prova_players:
            # Check if player has bye or finished match early
            player_match = Match.query.filter_by(
                prova_id=prova_id,
                round_number=round_number
            ).filter(
                db.or_(
                    Match.player1_id == player.id,
                    Match.player2_id == player.id
                )
            ).first()
            
            if player_match:
                # Check if bye or completed quickly
                if (player_match.is_bye or 
                    (player_match.status == "completed" and 
                     player_match.completed_at and 
                     (datetime.utcnow() - player_match.completed_at).total_seconds() < 1800)):  # 30 min
                    
                    # Get player rating/category for matchmaking
                    category = RatingService.get_player_effective_category(player.id)
                    
                    available_players.append({
                        "user_id": player.id,
                        "username": player.username,
                        "category": category.value if category else "Unrated",
                        "match_status": "bye" if player_match.is_bye else "completed_early",
                        "estimated_availability": "immediate" if player_match.is_bye else "5-10 minutes"
                    })
        
        return available_players
    
    def _get_user_incomplete_matches(self, prova_id: int, user_id: int) -> List[Dict[str, Any]]:
        """Get user's incomplete matches in the prova."""
        from ..match.models import Match
        
        incomplete = Match.query.filter(
            Match.prova_id == prova_id,
            db.or_(
                Match.player1_id == user_id,
                Match.player2_id == user_id
            ),
            Match.status.in_(["created", "in_progress"])
        ).all()
        
        return [{
            "match_id": match.id,
            "round_number": match.round_number,
            "opponent_id": match.player2_id if match.player1_id == user_id else match.player1_id,
            "status": match.status,
            "created_at": match.created_at
        } for match in incomplete]


class MatchmakingService:
    """Enhanced orchestrator with caching and cross-domain integration.
    Sprint 3: Advanced patterns with handicaps and X-replacement strategies.
    """

    def __init__(self, registry: EngineRegistry) -> None:
        self._registry = registry
        self._orchestrator = MatchmakingOrchestrator(self)
        self._preview_cache = {}
        self._cache_hits = 0
        self._cache_misses = 0
    
    @property
    def orchestrator(self) -> MatchmakingOrchestrator:
        """Access to advanced orchestration features."""
        return self._orchestrator
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get caching performance statistics."""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
        
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_percent": round(hit_rate, 1),
            "cached_previews": len(self._preview_cache)
        }
    
    def clear_cache(self) -> None:
        """Clear preview cache."""
        self._preview_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def preview(
        self, *, strategy_name: str, prova: object, round_number: int, use_cache: bool = True
    ) -> Sequence[Pairing]:
        """Calcola la preview degli abbinamenti con caching opzionale."""
        
        # Generate cache key
        cache_key = None
        if use_cache:
            cache_data = {
                "strategy": strategy_name,
                "prova_id": prova.id,
                "round_number": round_number,
                "inscriptions_hash": self._get_inscriptions_hash(prova)
            }
            cache_key = hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()
            
            # Check cache
            if cache_key in self._preview_cache:
                cache_entry = self._preview_cache[cache_key]
                if datetime.utcnow() - cache_entry["timestamp"] < timedelta(minutes=5):
                    self._cache_hits += 1
                    return cache_entry["result"]
        
        self._cache_misses += 1
        
        # Execute strategy
        strategy = self._registry.get(strategy_name)
        validation = strategy.validate(prova)
        if not validation.ok:
            msgs = "; ".join(validation.messages) or "Validazione pairing fallita"
            raise ValueError(msgs)
        
        result = strategy.preview(prova, round_number)
        
        # Cache result
        if use_cache and cache_key:
            self._preview_cache[cache_key] = {
                "result": result,
                "timestamp": datetime.utcnow()
            }
            
            # Limit cache size
            if len(self._preview_cache) > 100:
                # Remove oldest entries
                sorted_cache = sorted(
                    self._preview_cache.items(),
                    key=lambda x: x[1]["timestamp"]
                )
                for old_key, _ in sorted_cache[:20]:  # Remove 20 oldest
                    del self._preview_cache[old_key]
        
        return result

    def run(
        self, *, strategy_name: str, prova: object, round_number: int
    ) -> Sequence[Pairing]:
        """Esegue il pairing *effettivo* con invalidazione cache."""
        
        # Clear relevant cache entries
        keys_to_remove = []
        for key, entry in self._preview_cache.items():
            if f'"prova_id": {prova.id}' in key:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._preview_cache[key]
        
        # Execute strategy
        strategy = self._registry.get(strategy_name)
        validation = strategy.validate(prova)
        if not validation.ok:
            msgs = "; ".join(validation.messages) or "Validazione pairing fallita"
            raise ValueError(msgs)
        
        return strategy.propose(prova, round_number)
    
    def get_available_strategies(self) -> List[Dict[str, Any]]:
        """Get list of available strategies with metadata."""
        strategies = []
        
        for name in self._registry.available():
            strategy = self._registry.get(name)
            
            # Get strategy metadata
            metadata = {
                "name": name,
                "display_name": getattr(strategy, 'display_name', name.title()),
                "description": getattr(strategy, 'description', f"{name} pairing strategy"),
                "supports_preview": hasattr(strategy, 'preview'),
                "requires_classification": getattr(strategy, 'requires_classification', True),
                "min_players": getattr(strategy, 'min_players', 2),
                "max_players": getattr(strategy, 'max_players', None),
                "supports_byes": getattr(strategy, 'supports_byes', True)
            }
            
            strategies.append(metadata)
        
        return strategies
    
    def _get_inscriptions_hash(self, prova) -> str:
        """Generate hash of current inscriptions for cache invalidation."""
        from ..competition.models import Inscription
        
        inscriptions = (Inscription.query
                       .filter_by(prova_id=prova.id)
                       .order_by(Inscription.user_id)
                       .all())
        
        inscription_data = [(i.user_id, i.status) for i in inscriptions]
        return hashlib.md5(str(inscription_data).encode()).hexdigest()
