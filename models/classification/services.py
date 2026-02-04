"""
Module: models/classification/services.py
Purpose: Business logic services for classification domain with caching and optimization
Data Structures: ClassificationService, RoundClassificationService,
                GaraClassificationService, StrategyBasedClassificationService,
                PlayerEncounterService
Dependencies: models.classification.models, models.base.db
Enhanced: Phase 3.4 - Performance Optimization, Phase 5 - Strategy Pattern Refactor
"""

from typing import List, Tuple, Optional, Dict, Any
from sqlalchemy.orm import joinedload
from models.base import db
from .models import Classification, RoundClassification, GaraClassification, PlayerEncounter
from models.competition.models import Inscription
from models.user.models import User
from ..caching import cached, cache_invalidate, cache_manager
from ..optimization import optimized_query
from ..transaction import transactional

# Strategy pattern imports
from .strategies.base import ClassificationResult, ClassificationScope, PlayerScore
from .registry import get_classification_registry
from .score_aggregator import ScoreAggregator
from .tiebreaker_resolver import TiebreakerResolver


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

        gare = db.session.query(Gara).filter_by(campionato_id=campionato_id).all()
        player_gare: Dict[int, set] = {}

        for gara in gare:
            # Include both 'completed' and 'validated' as finished matches
            completed_matches = [
                m for m in gara.matches
                if m.status in ["completed", "validated"] and not m.is_bye
            ]
            for match in completed_matches:
                if match.player1_id:
                    player_gare.setdefault(match.player1_id, set()).add(gara.id)
                if match.player2_id:
                    player_gare.setdefault(match.player2_id, set()).add(gara.id)

        return {pid: len(gare_ids) for pid, gare_ids in player_gare.items()}

    @staticmethod
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

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise

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


class RoundClassificationService:
    """Service for managing round-by-round classifications with caching."""

    @staticmethod
    @cached(ttl_seconds=900, tags=["classification", "gara"], key_generator="gara")
    def get_round_standings(
        gara_id: int, round_number: int
    ) -> List[RoundClassification]:
        """
        Get standings after a specific round with caching.
        Cached for 15 minutes as round standings are stable.

        Args:
            gara_id: ID of the gara
            round_number: Round number

        Returns:
            List of RoundClassification objects ordered by position
        """
        return (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=round_number)
            .options(joinedload(getattr(RoundClassification, "user")))
            .order_by(RoundClassification.position)
            .all()
        )

    @staticmethod
    @cached(ttl_seconds=600, tags=["classification", "user", "gara"])
    def get_player_progression(gara_id: int, user_id: int) -> List[RoundClassification]:
        """
        Get a player's position progression across all rounds with caching.

        Args:
            gara_id: ID of the gara
            user_id: ID of the player

        Returns:
            List of RoundClassification objects ordered by round
        """
        return (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, user_id=user_id)
            .order_by(RoundClassification.round_number)
            .all()
        )

    @staticmethod
    @cache_invalidate(tags=["classification", "gara"])
    def calculate_and_save_round_classification(
        gara_id: int, round_number: int
    ) -> List[RoundClassification]:
        """
        Calculate and save classification after a round.

        Wrapper around the model's static method that returns
        the created/updated RoundClassification objects.

        Args:
            gara_id: ID of the gara
            round_number: Round number to calculate

        Returns:
            List of RoundClassification objects
        """
        # Use the model's calculation method
        RoundClassification.calculate_classification_after_round(gara_id, round_number)

        # Return the created classifications
        return RoundClassificationService.get_round_standings(gara_id, round_number)


class PlayerEncounterService:
    """Service for managing player encounter tracking with optimization."""

    @staticmethod
    @cached(ttl_seconds=300, tags=["encounter", "gara"])
    def get_player_encounters(gara_id: int, player_id: int) -> List[PlayerEncounter]:
        """
        Get all encounters for a player in a gara with caching.

        Args:
            gara_id: ID of the gara
            player_id: ID of the player

        Returns:
            List of PlayerEncounter objects
        """
        return (
            db.session.query(PlayerEncounter)
            .filter(
                PlayerEncounter.gara_id == gara_id,
                db.or_(
                    PlayerEncounter.player1_id == player_id,
                    PlayerEncounter.player2_id == player_id,
                ),
            )
            .all()
        )

    @staticmethod
    def get_available_opponents(
        gara_id: int, player_id: int, candidate_ids: List[int]
    ) -> List[int]:
        """
        Get available opponents from a list of candidates with optimized lookup.

        Args:
            gara_id: ID of the gara
            player_id: ID of the player
            candidate_ids: List of potential opponent IDs

        Returns:
            List of player IDs who haven't played against the given player
        """
        # Use cached encounter matrix for efficiency
        encounter_matrix = PlayerEncounterService.get_encounter_matrix(gara_id)

        # Return candidates who haven't been played
        return [
            cid
            for cid in candidate_ids
            if not encounter_matrix.get((player_id, cid), False)
        ]

    @staticmethod
    @cache_invalidate(tags=["encounter", "gara"])
    def record_match_encounters(match) -> None:
        """
        Record player encounters from a match with cache invalidation.

        Args:
            match: Match object to record encounters from
        """
        if match.is_bye or not match.player2_id:
            return

        PlayerEncounter.record_encounter(
            gara_id=match.gara_id,
            player1_id=match.player1_id,
            player2_id=match.player2_id,
            round_number=match.round_number,
        )

    @staticmethod
    @cached(ttl_seconds=600, tags=["encounter", "gara"], key_generator="gara")
    def get_encounter_matrix(gara_id: int) -> Dict[Tuple[int, int], bool]:
        """
        Get encounter matrix for all players in a gara with caching.
        Cached for 10 minutes as encounter data is relatively stable.

        Returns a dictionary where keys are (player1_id, player2_id) tuples
        and values are True if they have played.

        Args:
            gara_id: ID of the gara

        Returns:
            Dictionary mapping player pairs to encounter status
        """
        encounters = db.session.query(PlayerEncounter).filter_by(gara_id=gara_id).all()

        matrix = {}
        for encounter in encounters:
            matrix[(encounter.player1_id, encounter.player2_id)] = True
            matrix[(encounter.player2_id, encounter.player1_id)] = True

        return matrix

    @staticmethod
    @cached(ttl_seconds=1200, tags=["encounter", "gara"])
    def get_encounter_statistics(gara_id: int) -> Dict[str, Any]:
        """Get comprehensive encounter statistics for the gara."""
        encounters = db.session.query(PlayerEncounter).filter_by(gara_id=gara_id).all()

        if not encounters:
            return {"total_encounters": 0, "unique_players": 0}

        unique_players = set()
        for encounter in encounters:
            unique_players.add(encounter.player1_id)
            unique_players.add(encounter.player2_id)

        total_possible = len(unique_players) * (len(unique_players) - 1) // 2
        completion_rate = (
            (len(encounters) / total_possible * 100) if total_possible > 0 else 0
        )

        return {
            "total_encounters": len(encounters),
            "unique_players": len(unique_players),
            "total_possible_encounters": total_possible,
            "completion_rate_percent": round(completion_rate, 1),
        }


def visible_user_ids_for_gara(gara_id: int) -> set[int]:
    # iscritti non ritirati
    active = {
        ins.user_id
        for ins in db.session.query(Inscription).filter_by(gara_id=gara_id).all()
    }
    # utenti soft-deleted
    deleted = {
        u.id for u in db.session.query(User).filter(User.deleted_at.isnot(None)).all()
    }
    return active - deleted


class StrategyBasedClassificationService:
    """Unified classification service using strategy pattern.

    This is the new recommended service for classification calculations.
    Uses pluggable strategies for different ranking criteria.
    """

    def __init__(self) -> None:
        self._registry = get_classification_registry()
        self._aggregator = ScoreAggregator()
        self._tiebreaker = TiebreakerResolver()

    def get_strategy_for_gara(self, gara) -> Any:
        """Get appropriate round strategy based on gara's matchmaking strategy.

        Args:
            gara: Gara model instance

        Returns:
            ClassificationStrategy for this gara type
        """
        strategy_map = {
            "amalfi": "amalfi_round",
            "random": "random_round",
            "round_robin": "round_robin_round",
        }
        strategy_name = strategy_map.get(gara.matchmaking_strategy, "amalfi_round")
        return self._registry.get(strategy_name)

    def get_gara_final_strategy(self, gara) -> Any:
        """Get strategy for final gara classification.

        Args:
            gara: Gara model instance

        Returns:
            ClassificationStrategy for gara final ranking
        """
        strategy_map = {
            "amalfi": "amalfi_gara",
            "random": "random_gara",
        }
        strategy_name = strategy_map.get(gara.matchmaking_strategy, "amalfi_gara")
        return self._registry.get(strategy_name)

    @transactional(domain="classification")
    def calculate_round_classification(
        self,
        gara_id: int,
        round_number: int,
    ) -> ClassificationResult:
        """Calculate classification after a round using strategy pattern.

        Args:
            gara_id: ID of the gara
            round_number: Round number to calculate

        Returns:
            ClassificationResult with ordered entries
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        # Get appropriate strategy
        strategy = self.get_strategy_for_gara(gara)

        # Aggregate scores from matches
        scores = self._aggregator.aggregate_round_scores(gara_id, round_number)

        # Get previous classification if exists
        previous = None
        if round_number > 1:
            previous = self._load_previous_classification(gara_id, round_number - 1)

        # Calculate using strategy
        result = strategy.calculate(
            scores=scores,
            previous_classification=previous,
            context={"gara_id": gara_id, "round_number": round_number},
        )

        # Persist result to database
        self._save_round_classification(gara_id, round_number, result)

        return result

    @transactional(domain="classification")
    def calculate_gara_classification(
        self,
        gara_id: int,
        spot_shot_results: Optional[Dict[int, int]] = None,
    ) -> ClassificationResult:
        """Calculate final gara classification with tiebreaker resolution.

        Args:
            gara_id: ID of the gara
            spot_shot_results: Optional spot shot rally results for tiebreaking

        Returns:
            ClassificationResult with resolved positions
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        # Get final round classification
        final_round = gara.current_round or 1
        previous = self._load_previous_classification(gara_id, final_round)

        if previous is None:
            # Calculate final round first
            previous = self.calculate_round_classification(gara_id, final_round)

        # Get gara-level strategy
        strategy = self.get_gara_final_strategy(gara)

        # Calculate final classification
        result = strategy.calculate(
            scores=[],  # Gara strategy uses previous classification
            previous_classification=previous,
            context={
                "gara_id": gara_id,
                "spot_shot_results": spot_shot_results,
            },
        )

        # Persist final gara classification
        self._save_gara_classification(gara_id, result)

        return result

    def _load_previous_classification(
        self,
        gara_id: int,
        round_number: int,
    ) -> Optional[ClassificationResult]:
        """Load previous round classification from database.

        Args:
            gara_id: ID of the gara
            round_number: Round number to load

        Returns:
            ClassificationResult or None if not found
        """
        from .strategies.base import ClassificationEntry

        round_classifications = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=round_number)
            .order_by(RoundClassification.position)
            .all()
        )

        if not round_classifications:
            return None

        entries = []
        for rc in round_classifications:
            score = PlayerScore(
                player_id=rc.user_id,
                matches_won=rc.matches_won,
                rack_difference=rc.rack_difference,
                previous_position=rc.previous_position,
            )
            entries.append(
                ClassificationEntry(
                    player_id=rc.user_id,
                    position=rc.position,
                    score=score,
                    tied_with=(),
                    tiebreaker_resolved=True,
                )
            )

        return ClassificationResult(
            entries=tuple(entries),
            scope=ClassificationScope.ROUND,
            has_ties=False,
            metadata={"round_number": round_number, "gara_id": gara_id},
        )

    def _save_round_classification(
        self,
        gara_id: int,
        round_number: int,
        result: ClassificationResult,
    ) -> None:
        """Save round classification to database.

        Args:
            gara_id: ID of the gara
            round_number: Round number
            result: ClassificationResult to save
        """
        # Delete existing classifications for this round
        db.session.query(RoundClassification).filter_by(
            gara_id=gara_id, round_number=round_number
        ).delete()

        # Create new classifications
        for entry in result.entries:
            classification = RoundClassification(
                gara_id=gara_id,
                round_number=round_number,
                user_id=entry.player_id,
                position=entry.position,
                matches_won=entry.score.matches_won,
                rack_difference=entry.score.rack_difference,
                previous_position=entry.score.previous_position,
            )
            db.session.add(classification)

    def _save_gara_classification(
        self,
        gara_id: int,
        result: ClassificationResult,
    ) -> None:
        """Save final gara classification to database.

        Args:
            gara_id: ID of the gara
            result: ClassificationResult to save
        """
        # Delete existing classifications for this gara
        db.session.query(GaraClassification).filter_by(gara_id=gara_id).delete()

        # Create new classifications
        for entry in result.entries:
            classification = GaraClassification(
                gara_id=gara_id,
                user_id=entry.player_id,
                position=entry.position,
                matches_won=entry.score.matches_won,
                matches_lost=entry.score.matches_lost,
                racks_won=entry.score.racks_won,
                racks_lost=entry.score.racks_lost,
                rack_difference=entry.score.rack_difference,
                spot_shot_wins=entry.score.spot_shot_wins,
                tied_with_player_ids=list(entry.tied_with) if entry.tied_with else None,
                tiebreaker_resolved=entry.tiebreaker_resolved,
            )
            db.session.add(classification)


class GaraClassificationService:
    """Service for managing final gara classifications."""

    @staticmethod
    @cached(ttl_seconds=900, tags=["classification", "gara"], key_generator="gara")
    def get_gara_standings(gara_id: int) -> List[GaraClassification]:
        """Get final gara standings with caching.

        Args:
            gara_id: ID of the gara

        Returns:
            List of GaraClassification objects ordered by position
        """
        return (
            db.session.query(GaraClassification)
            .filter_by(gara_id=gara_id)
            .options(joinedload(getattr(GaraClassification, "user")))
            .order_by(GaraClassification.position)
            .all()
        )

    @staticmethod
    @cached(ttl_seconds=600, tags=["classification", "user", "gara"])
    def get_player_gara_result(
        gara_id: int, user_id: int
    ) -> Optional[GaraClassification]:
        """Get a specific player's final result in a gara.

        Args:
            gara_id: ID of the gara
            user_id: ID of the player

        Returns:
            GaraClassification or None if not found
        """
        return (
            db.session.query(GaraClassification)
            .filter_by(gara_id=gara_id, user_id=user_id)
            .first()
        )

    @staticmethod
    def get_podium(gara_id: int) -> List[GaraClassification]:
        """Get top 3 finishers for a gara.

        Args:
            gara_id: ID of the gara

        Returns:
            List of top 3 GaraClassification objects
        """
        return (
            db.session.query(GaraClassification)
            .filter_by(gara_id=gara_id)
            .filter(GaraClassification.position <= 3)
            .options(joinedload(getattr(GaraClassification, "user")))
            .order_by(GaraClassification.position)
            .all()
        )


__all__ = [
    "ClassificationService",
    "RoundClassificationService",
    "GaraClassificationService",
    "StrategyBasedClassificationService",
    "PlayerEncounterService",
]
