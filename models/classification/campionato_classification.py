"""
Module: models/classification/campionato_classification.py
Purpose: Campionato-level classification services with caching and optimization
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import joinedload, selectinload
from models.base import db
from .models import Classification
from ..status_enum import MatchStatus
from ..caching import cached, cache_invalidate, cache_manager
from ..optimization import optimized_query
from ..transaction import transactional

from .registry import get_classification_registry
from .score_aggregator import ScoreAggregator


class ClassificationService:
    """Service for managing campionato classifications with caching and optimization."""

    @staticmethod
    def _get_campionato_strategy(campionato_type: str):
        """Get the appropriate classification strategy for a campionato type."""
        strategy_map = {
            "amalfi": "amalfi_campionato",
            "random": "random_campionato",
        }
        strategy_name = strategy_map.get(campionato_type, "amalfi_campionato")
        registry = get_classification_registry()
        return registry.get(strategy_name)

    @staticmethod
    def _count_gare_played(campionato_id: int) -> Dict[int, int]:
        """Count how many gare each player participated in.

        Returns:
            Dict mapping player_id -> number of gare played
        """
        from models.competition.models import Gara

        # selectinload avoids N+1: one IN-query loads all matches for all gare,
        # instead of one lazy-load per gara when accessing `gara.matches` below.
        gare = (
            db.session.query(Gara)
            .filter_by(campionato_id=campionato_id)
            .options(selectinload(Gara.matches))
            .all()
        )
        player_gare: Dict[int, set] = {}

        for gara in gare:
            # Include both 'completed' and 'validated' as finished matches
            completed_matches = [
                m for m in gara.matches
                if MatchStatus.is_finished(m.status) and not m.is_bye
            ]
            for match in completed_matches:
                if match.player1_id:
                    player_gare.setdefault(match.player1_id, set()).add(gara.id)
                if match.player2_id:
                    player_gare.setdefault(match.player2_id, set()).add(gara.id)

        return {pid: len(gare_ids) for pid, gare_ids in player_gare.items()}

    @staticmethod
    @transactional(domain="classification")
    @cached(
        ttl_seconds=300,
        tags=["classification", "campionato"],
        key_generator="campionato",
    )
    @optimized_query(cache_ttl=300, cache_tags=["campionato_classification"])
    def update_campionato_classification(campionato_id: int) -> List[Classification]:
        """
        Update overall campionato classification based on all completed provas.
        Results are cached for 5 minutes and invalidated on campionato changes.

        Uses ScoreAggregator for data collection and classification strategies
        for ranking, ensuring consistent use of PlayerScore value objects.

        Args:
            campionato_id: ID of the campionato

        Returns:
            List of updated Classification objects
        """
        from models.campionato.models import Campionato

        # Get campionato to determine strategy
        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise ValueError(f"Campionato {campionato_id} not found")

        # Use ScoreAggregator to collect PlayerScore objects
        aggregator = ScoreAggregator()
        scores = aggregator.aggregate_campionato_scores(campionato_id)

        if not scores:
            return []

        # Get classification strategy based on campionato type
        strategy = ClassificationService._get_campionato_strategy(
            campionato.campionato_type
        )

        # Calculate classification using strategy
        result = strategy.calculate(
            scores,
            context={"campionato_id": campionato_id},
        )

        # Count gare played per player
        gare_played_map = ClassificationService._count_gare_played(campionato_id)

        # Batch load existing classifications to avoid N+1
        existing_classifications = {
            c.user_id: c
            for c in db.session.query(Classification)
            .filter_by(campionato_id=campionato_id)
            .all()
        }

        # Update or create Classification records from strategy result
        classifications = []
        for entry in result.entries:
            player_id = entry.player_id
            classification = existing_classifications.get(player_id)

            if not classification:
                classification = Classification(
                    campionato_id=campionato_id, user_id=player_id
                )

            classification.position = entry.position
            classification.total_matches_won = entry.score.matches_won
            classification.total_racks_won = entry.score.racks_won
            classification.total_point_difference = entry.score.rack_difference
            classification.gare_played = gare_played_map.get(player_id, 0)

            db.session.add(classification)
            classifications.append(classification)

        # Transaction managed by @transactional decorator
        return classifications

    @staticmethod
    @cached(
        ttl_seconds=600,
        tags=["classification", "campionato"],
        key_generator="campionato",
    )
    def get_campionato_standings(campionato_id: int) -> List[Classification]:
        """
        Get current campionato standings with caching.
        Cached for 10 minutes as standings don't change frequently.

        Args:
            campionato_id: ID of the campionato

        Returns:
            List of Classification objects ordered by position
        """
        return (
            db.session.query(Classification)
            .filter_by(campionato_id=campionato_id)
            .options(
                joinedload(getattr(Classification, "user"))
            )  # Eager load user data
            .order_by(Classification.position)
            .all()
        )

    @staticmethod
    @cached(ttl_seconds=300, tags=["classification", "user"])
    def get_player_ranking(
        campionato_id: int, user_id: int
    ) -> Optional[Classification]:
        """
        Get a specific player's ranking in a campionato with caching.

        Args:
            campionato_id: ID of the campionato
            user_id: ID of the player

        Returns:
            Classification object or None if not found
        """
        return (
            db.session.query(Classification)
            .options(joinedload(getattr(Classification, "user")))
            .filter_by(campionato_id=campionato_id, user_id=user_id)
            .first()
        )

    @staticmethod
    @cache_invalidate(tags=["classification", "campionato"])
    def invalidate_campionato_cache(campionato_id: int) -> None:
        """Invalidate all classification caches for a campionato."""
        # Additional specific cache invalidation
        cache_manager.invalidate_by_tags([f"campionato:{campionato_id}"])

    @staticmethod
    @cached(ttl_seconds=1800, tags=["classification", "campionato"])
    def get_player_statistics_summary(campionato_id: int) -> Dict[str, Any]:
        """Get comprehensive statistics summary for the campionato."""
        standings = ClassificationService.get_campionato_standings(campionato_id)

        if not standings:
            return {"total_players": 0, "completed": False}

        total_matches = sum(c.total_matches_won for c in standings)
        avg_matches_per_player = total_matches / len(standings) if standings else 0

        return {
            "total_players": len(standings),
            "total_matches_played": total_matches,
            "average_matches_per_player": round(avg_matches_per_player, 1),
            "leader": (
                {
                    "user_id": standings[0].user_id,
                    "username": (
                        standings[0].user.username if standings[0].user else "Unknown"
                    ),
                    "matches_won": standings[0].total_matches_won,
                    "point_difference": standings[0].total_point_difference,
                }
                if standings
                else None
            ),
            "completed": all(c.total_matches_won > 0 for c in standings),
        }

    @staticmethod
    @cache_invalidate(tags=["classification", "gara"])
    def recalculate_classification_after_match_edit(
        match_id: int, modified_by_id: int
    ) -> None:
        """
        Recalculate classification after a match has been edited by an admin.

        Args:
            match_id: ID of the modified match
            modified_by_id: ID of the admin who made the modification
        """
        from models.match.models import Match
        from .gara_classification import RoundClassificationService

        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        gara_id = match.gara_id
        round_number = match.round_number

        # Recalculate classification for the round containing the modified match
        RoundClassificationService.calculate_and_save_round_classification(
            gara_id, round_number
        )

        # If this is part of a campionato, update campionato classification too
        if match.gara.campionato_id:
            ClassificationService.update_campionato_classification(
                match.gara.campionato_id
            )

        # Invalidate related caches
        ClassificationService.invalidate_campionato_cache(match.gara.campionato_id or 0)
        cache_manager.invalidate_by_tags([f"gara:{gara_id}"])
