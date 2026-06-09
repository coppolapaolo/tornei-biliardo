"""
Module: models/classification/gara_classification.py
Purpose: Gara-level classification services (round, final, strategy-based)
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import joinedload
from models.base import db
from models.competition.models import Inscription
from models.user.models import User
from .models import RoundClassification, GaraClassification
from ..caching import cached, cache_invalidate
from ..transaction import transactional

# Strategy pattern imports
from .strategies.base import ClassificationResult, ClassificationScope, PlayerScore
from .registry import get_classification_registry
from .score_aggregator import ScoreAggregator
from .tiebreaker_resolver import TiebreakerResolver


class RoundClassificationService:
    """Service for managing round-by-round classifications with caching."""

    @staticmethod
    @cached(
        ttl_seconds=900,
        tags=["classification", "gara"],
        key_generator="gara_round",
    )
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
        """Get appropriate round strategy based on gara.classification_system.

        Args:
            gara: Gara model instance

        Returns:
            ClassificationStrategy for this gara type
        """
        cs = (getattr(gara, "classification_system", None) or "WINS").upper()
        # round_robin matchmaking conserva la sua strategia round dedicata
        # (semantica già allineata a WINS, ma serve l'ordine stabile per pairing)
        if gara.matchmaking_strategy == "round_robin":
            return self._registry.get("round_robin_round")
        strategy_map = {
            "WINS": "amalfi_round",
            "POSITION": "amalfi_round",
            "RACK": "random_round",
        }
        return self._registry.get(strategy_map.get(cs, "amalfi_round"))

    def get_gara_final_strategy(self, gara) -> Any:
        """Get strategy for final gara classification.

        Args:
            gara: Gara model instance

        Returns:
            ClassificationStrategy for gara final ranking
        """
        cs = (getattr(gara, "classification_system", None) or "WINS").upper()
        strategy_map = {
            "WINS": "amalfi_gara",
            "POSITION": "amalfi_gara",
            "RACK": "random_gara",
        }
        return self._registry.get(strategy_map.get(cs, "amalfi_gara"))

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
