"""
Module: models/classification/services.py
Purpose: Business logic services for classification domain with caching and optimization
Data Structures: ClassificationService, RoundClassificationService,
                PlayerEncounterService
Dependencies: models.classification.models, models.base.db
Enhanced: Phase 3.4 - Performance Optimization
"""

from typing import List, Tuple, Optional, Dict, Any
from sqlalchemy.orm import selectinload, joinedload
from models.base import db
from .models import Classification, RoundClassification, PlayerEncounter
from models.competition.models import Inscription
from models.user.models import User
from ..caching import cached, cache_invalidate, cache_manager
from ..optimization import optimized_query, bulk_load_relationships


class ClassificationService:
    """Service for managing tournament classifications with caching and optimization."""

    @staticmethod
    @cached(ttl_seconds=300, tags=['classification', 'tournament'], key_generator='tournament')
    @optimized_query(cache_ttl=300, cache_tags=['tournament_classification'])
    def update_tournament_classification(tournament_id: int) -> List[Classification]:
        """
        Update overall tournament classification based on all completed provas.
        Results are cached for 5 minutes and invalidated on tournament changes.

        Args:
            tournament_id: ID of the tournament

        Returns:
            List of updated Classification objects
        """
        from models.competition.models import Prova
        from models.match.models import Match

        # Get all provas for this tournament with optimized loading
        provas_query = Prova.query.filter_by(tournament_id=tournament_id)
        provas = bulk_load_relationships(
            provas_query,
            "matches",
            "inscriptions"
        ).all()

        # Aggregate stats across all provas
        player_stats = {}

        for prova in provas:
            # Get completed matches - already loaded via selectinload
            matches = [
                match for match in prova.matches
                if match.status == "completed" and not match.is_bye
            ]

            # Process each match
            for match in matches:
                # Initialize players if not seen
                for player_id in [match.player1_id, match.player2_id]:
                    if player_id not in player_stats:
                        player_stats[player_id] = {
                            "matches_won": 0,
                            "point_difference": 0,
                            "provas_played": set(),
                        }

                # Update winner stats
                if match.player1_score > match.player2_score:
                    player_stats[match.player1_id]["matches_won"] += 1
                    point_diff = match.player1_score - match.player2_score
                    player_stats[match.player1_id]["point_difference"] += point_diff
                    player_stats[match.player2_id]["point_difference"] -= point_diff
                else:
                    player_stats[match.player2_id]["matches_won"] += 1
                    point_diff = match.player2_score - match.player1_score
                    player_stats[match.player2_id]["point_difference"] += point_diff
                    player_stats[match.player1_id]["point_difference"] -= point_diff

                # Track prova participation
                player_stats[match.player1_id]["provas_played"].add(prova.id)
                player_stats[match.player2_id]["provas_played"].add(prova.id)

        # Sort players by classification criteria
        sorted_players = sorted(
            player_stats.items(),
            key=lambda x: (
                -x[1]["matches_won"],
                -x[1]["point_difference"],
                x[0],  # Player ID for stability
            ),
        )

        # Batch load existing classifications to avoid N+1
        existing_classifications = {
            c.user_id: c for c in 
            Classification.query.filter_by(tournament_id=tournament_id).all()
        }

        # Update or create Classification records
        classifications = []
        for position, (player_id, stats) in enumerate(sorted_players, 1):
            classification = existing_classifications.get(player_id)

            if not classification:
                classification = Classification(
                    tournament_id=tournament_id, user_id=player_id
                )

            classification.position = position
            classification.total_matches_won = stats["matches_won"]
            classification.total_point_difference = stats["point_difference"]
            classification.provas_played = len(stats["provas_played"])

            db.session.add(classification)
            classifications.append(classification)

        db.session.commit()
        return classifications

    @staticmethod
    @cached(ttl_seconds=600, tags=['classification', 'tournament'], key_generator='tournament')
    def get_tournament_standings(tournament_id: int) -> List[Classification]:
        """
        Get current tournament standings with caching.
        Cached for 10 minutes as standings don't change frequently.

        Args:
            tournament_id: ID of the tournament

        Returns:
            List of Classification objects ordered by position
        """
        return (
            Classification.query
            .filter_by(tournament_id=tournament_id)
            .options(joinedload(getattr(Classification, 'user')))  # Eager load user data
            .order_by(Classification.position)
            .all()
        )

    @staticmethod
    @cached(ttl_seconds=300, tags=['classification', 'user'])
    def get_player_ranking(
        tournament_id: int, user_id: int
    ) -> Optional[Classification]:
        """
        Get a specific player's ranking in a tournament with caching.

        Args:
            tournament_id: ID of the tournament
            user_id: ID of the player

        Returns:
            Classification object or None if not found
        """
        return (
            Classification.query
            .options(joinedload(getattr(Classification, 'user')))
            .filter_by(tournament_id=tournament_id, user_id=user_id)
            .first()
        )
    
    @staticmethod
    @cache_invalidate(tags=['classification', 'tournament'])
    def invalidate_tournament_cache(tournament_id: int) -> None:
        """Invalidate all classification caches for a tournament."""
        # Additional specific cache invalidation
        cache_manager.invalidate_by_tags([f'tournament:{tournament_id}'])
    
    @staticmethod
    @cached(ttl_seconds=1800, tags=['classification', 'tournament'])
    def get_player_statistics_summary(tournament_id: int) -> Dict[str, Any]:
        """Get comprehensive statistics summary for the tournament."""
        standings = ClassificationService.get_tournament_standings(tournament_id)
        
        if not standings:
            return {"total_players": 0, "completed": False}
        
        total_matches = sum(c.total_matches_won for c in standings)
        avg_matches_per_player = total_matches / len(standings) if standings else 0
        
        return {
            "total_players": len(standings),
            "total_matches_played": total_matches,
            "average_matches_per_player": round(avg_matches_per_player, 1),
            "leader": {
                "user_id": standings[0].user_id,
                "username": standings[0].user.username if standings[0].user else "Unknown",
                "matches_won": standings[0].total_matches_won,
                "point_difference": standings[0].total_point_difference
            } if standings else None,
            "completed": all(c.total_matches_won > 0 for c in standings)
        }


class RoundClassificationService:
    """Service for managing round-by-round classifications with caching."""

    @staticmethod
    @cached(ttl_seconds=900, tags=['classification', 'prova'], key_generator='prova')
    def get_round_standings(
        prova_id: int, round_number: int
    ) -> List[RoundClassification]:
        """
        Get standings after a specific round with caching.
        Cached for 15 minutes as round standings are stable.

        Args:
            prova_id: ID of the prova
            round_number: Round number

        Returns:
            List of RoundClassification objects ordered by position
        """
        return (
            RoundClassification.query
            .filter_by(prova_id=prova_id, round_number=round_number)
            .options(joinedload(getattr(RoundClassification, 'user')))
            .order_by(RoundClassification.position)
            .all()
        )

    @staticmethod
    @cached(ttl_seconds=600, tags=['classification', 'user', 'prova'])
    def get_player_progression(
        prova_id: int, user_id: int
    ) -> List[RoundClassification]:
        """
        Get a player's position progression across all rounds with caching.

        Args:
            prova_id: ID of the prova
            user_id: ID of the player

        Returns:
            List of RoundClassification objects ordered by round
        """
        return (
            RoundClassification.query
            .filter_by(prova_id=prova_id, user_id=user_id)
            .order_by(RoundClassification.round_number)
            .all()
        )

    @staticmethod
    @cache_invalidate(tags=['classification', 'prova'])
    def calculate_and_save_round_classification(
        prova_id: int, round_number: int
    ) -> List[RoundClassification]:
        """
        Calculate and save classification after a round.

        Wrapper around the model's static method that returns
        the created/updated RoundClassification objects.

        Args:
            prova_id: ID of the prova
            round_number: Round number to calculate

        Returns:
            List of RoundClassification objects
        """
        # Use the model's calculation method
        RoundClassification.calculate_classification_after_round(prova_id, round_number)

        # Return the created classifications
        return RoundClassificationService.get_round_standings(prova_id, round_number)


class PlayerEncounterService:
    """Service for managing player encounter tracking with optimization."""

    @staticmethod
    @cached(ttl_seconds=300, tags=['encounter', 'prova'])
    def get_player_encounters(prova_id: int, player_id: int) -> List[PlayerEncounter]:
        """
        Get all encounters for a player in a prova with caching.

        Args:
            prova_id: ID of the prova
            player_id: ID of the player

        Returns:
            List of PlayerEncounter objects
        """
        return PlayerEncounter.query.filter(
            PlayerEncounter.prova_id == prova_id,
            db.or_(
                PlayerEncounter.player1_id == player_id,
                PlayerEncounter.player2_id == player_id,
            ),
        ).all()

    @staticmethod
    def get_available_opponents(
        prova_id: int, player_id: int, candidate_ids: List[int]
    ) -> List[int]:
        """
        Get available opponents from a list of candidates with optimized lookup.

        Args:
            prova_id: ID of the prova
            player_id: ID of the player
            candidate_ids: List of potential opponent IDs

        Returns:
            List of player IDs who haven't played against the given player
        """
        # Use cached encounter matrix for efficiency
        encounter_matrix = PlayerEncounterService.get_encounter_matrix(prova_id)
        
        # Return candidates who haven't been played
        return [
            cid for cid in candidate_ids 
            if not encounter_matrix.get((player_id, cid), False)
        ]

    @staticmethod
    @cache_invalidate(tags=['encounter', 'prova'])
    def record_match_encounters(match) -> None:
        """
        Record player encounters from a match with cache invalidation.

        Args:
            match: Match object to record encounters from
        """
        if match.is_bye or not match.player2_id:
            return

        PlayerEncounter.record_encounter(
            prova_id=match.prova_id,
            player1_id=match.player1_id,
            player2_id=match.player2_id,
            round_number=match.round_number,
        )

    @staticmethod
    @cached(ttl_seconds=600, tags=['encounter', 'prova'], key_generator='prova')
    def get_encounter_matrix(prova_id: int) -> Dict[Tuple[int, int], bool]:
        """
        Get encounter matrix for all players in a prova with caching.
        Cached for 10 minutes as encounter data is relatively stable.

        Returns a dictionary where keys are (player1_id, player2_id) tuples
        and values are True if they have played.

        Args:
            prova_id: ID of the prova

        Returns:
            Dictionary mapping player pairs to encounter status
        """
        encounters = PlayerEncounter.query.filter_by(prova_id=prova_id).all()

        matrix = {}
        for encounter in encounters:
            matrix[(encounter.player1_id, encounter.player2_id)] = True
            matrix[(encounter.player2_id, encounter.player1_id)] = True

        return matrix
    
    @staticmethod
    @cached(ttl_seconds=1200, tags=['encounter', 'prova'])
    def get_encounter_statistics(prova_id: int) -> Dict[str, Any]:
        """Get comprehensive encounter statistics for the prova."""
        encounters = PlayerEncounter.query.filter_by(prova_id=prova_id).all()
        
        if not encounters:
            return {"total_encounters": 0, "unique_players": 0}
        
        unique_players = set()
        for encounter in encounters:
            unique_players.add(encounter.player1_id)
            unique_players.add(encounter.player2_id)
        
        total_possible = len(unique_players) * (len(unique_players) - 1) // 2
        completion_rate = (len(encounters) / total_possible * 100) if total_possible > 0 else 0
        
        return {
            "total_encounters": len(encounters),
            "unique_players": len(unique_players),
            "total_possible_encounters": total_possible,
            "completion_rate_percent": round(completion_rate, 1)
        }


def visible_user_ids_for_prova(prova_id: int) -> set[int]:
    # iscritti non ritirati
    active = {
        ins.user_id
        for ins in Inscription.query.filter_by(
            prova_id=prova_id, is_withdrawn=False
        ).all()
    }
    # utenti soft-deleted
    deleted = {u.id for u in User.query.filter(User.deleted_at.isnot(None)).all()}
    return active - deleted


__all__ = [
    "ClassificationService",
    "RoundClassificationService",
    "PlayerEncounterService",
]
