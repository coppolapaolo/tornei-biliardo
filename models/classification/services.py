"""
Module: models/classification/services.py
Purpose: Business logic services for classification domain with caching and optimization
Data Structures: ClassificationService, RoundClassificationService,
                PlayerEncounterService
Dependencies: models.classification.models, models.base.db
Enhanced: Phase 3.4 - Performance Optimization
"""

from typing import List, Tuple, Optional, Dict, Any
from sqlalchemy.orm import joinedload
from models.base import db
from .models import Classification, RoundClassification, PlayerEncounter
from models.competition.models import Inscription
from models.user.models import User
from ..caching import cached, cache_invalidate, cache_manager
from ..optimization import optimized_query, bulk_load_relationships
from ..scoring.policies import ScoringPolicy
from ..scoring.strategies import (
    ClassicScoringPolicy,
    FargoRatingScoringPolicy,
    EloRatingScoringPolicy,
)


class ClassificationService:
    """Service for managing campionato classifications with caching and optimization."""

    @staticmethod
    def _get_scoring_policy(campionato) -> ScoringPolicy:
        """Get the appropriate scoring policy for a campionato."""
        policy_map = {
            "classic": ClassicScoringPolicy(),
            "fargo": FargoRatingScoringPolicy(),
            "elo": EloRatingScoringPolicy(),
        }
        return policy_map.get(campionato.scoring_policy, ClassicScoringPolicy())

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

        Args:
            campionato_id: ID of the campionato

        Returns:
            List of updated Classification objects
        """
        from models.competition.models import Gara
        from models.campionato.models import Campionato

        # Get campionato to determine scoring policy
        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise ValueError(f"Campionato {campionato_id} not found")

        # Get scoring policy based on campionato configuration
        scoring_policy = ClassificationService._get_scoring_policy(campionato)

        # Get all provas for this campionato with optimized loading
        gare_query = db.session.query(Gara).filter_by(campionato_id=campionato_id)
        gare = bulk_load_relationships(
            gare_query, Gara.matches, Gara.inscriptions
        ).all()

        # Get all players in the campionato
        player_ids = set()
        match_results = []

        for gara in gare:
            # Get completed matches - already loaded via selectinload
            matches = [
                match
                for match in gara.matches
                if match.status == "completed" and not match.is_bye
            ]

            # Collect player IDs and match results
            for match in matches:
                player_ids.add(match.player1_id)
                player_ids.add(match.player2_id)
                match_results.append(
                    {
                        "player1_id": match.player1_id,
                        "player2_id": match.player2_id,
                        "player1_score": match.player1_score,
                        "player2_score": match.player2_score,
                    }
                )

        # Get player objects
        players = db.session.query(User).filter(User.id.in_(player_ids)).all()

        # Calculate standings using scoring policy
        standings = scoring_policy.calculate_standings(players, match_results)

        # Batch load existing classifications to avoid N+1
        existing_classifications = {
            c.user_id: c
            for c in db.session.query(Classification)
            .filter_by(campionato_id=campionato_id)
            .all()
        }

        # Update or create Classification records
        classifications = []
        for position, (player, score_data) in enumerate(standings, 1):
            player_id = player.id
            classification = existing_classifications.get(player_id)

            if not classification:
                classification = Classification(
                    campionato_id=campionato_id, user_id=player_id
                )

            classification.position = position
            # Extract stats from score_data based on the scoring policy used
            if isinstance(score_data, dict) and "matches_won" in score_data:
                # Classic scoring policy
                classification.total_matches_won = score_data["matches_won"]
                classification.total_point_difference = score_data["rack_diff"]
                classification.gare_played = len(score_data.get("gare_played", []))
            else:
                # For other policies, use default values
                classification.total_matches_won = getattr(score_data, "wins", 0) or 0
                classification.total_point_difference = (
                    getattr(score_data, "rack_diff", 0) or 0
                )
                classification.gare_played = 0

            db.session.add(classification)
            classifications.append(classification)

        db.session.commit()
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


__all__ = [
    "ClassificationService",
    "RoundClassificationService",
    "PlayerEncounterService",
]
