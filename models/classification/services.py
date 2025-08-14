"""
Module: models/classification/services.py
Purpose: Business logic services for classification domain
Data Structures: ClassificationService, RoundClassificationService,
                PlayerEncounterService
Dependencies: models.classification.models, models.base.db
ADR Reference: docs/ADR/ADR-0010-domain-separation-phase2.md
"""

from typing import List, Tuple, Optional, Dict
from models.base import db
from .models import Classification, RoundClassification, PlayerEncounter
from models.competition.models import Inscription
from models.user.models import User


class ClassificationService:
    """Service for managing tournament classifications."""

    @staticmethod
    def update_tournament_classification(tournament_id: int) -> List[Classification]:
        """
        Update overall tournament classification based on all completed provas.

        Args:
            tournament_id: ID of the tournament

        Returns:
            List of updated Classification objects
        """
        from models.competition.models import Prova
        from models.match.models import Match

        # Get all provas for this tournament
        provas = Prova.query.filter_by(tournament_id=tournament_id).all()

        # Aggregate stats across all provas
        player_stats = {}

        for prova in provas:
            # Get completed matches for this prova
            matches = Match.query.filter(
                Match.prova_id == prova.id,
                Match.status == "completed",
                Match.is_bye.is_(False),
            ).all()

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

        # Update or create Classification records
        classifications = []
        for position, (player_id, stats) in enumerate(sorted_players, 1):
            classification = Classification.query.filter_by(
                tournament_id=tournament_id, user_id=player_id
            ).first()

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
    def get_tournament_standings(tournament_id: int) -> List[Classification]:
        """
        Get current tournament standings.

        Args:
            tournament_id: ID of the tournament

        Returns:
            List of Classification objects ordered by position
        """
        return (
            Classification.query.filter_by(tournament_id=tournament_id)
            .order_by(Classification.position)
            .all()
        )

    @staticmethod
    def get_player_ranking(
        tournament_id: int, user_id: int
    ) -> Optional[Classification]:
        """
        Get a specific player's ranking in a tournament.

        Args:
            tournament_id: ID of the tournament
            user_id: ID of the player

        Returns:
            Classification object or None if not found
        """
        return Classification.query.filter_by(
            tournament_id=tournament_id, user_id=user_id
        ).first()


class RoundClassificationService:
    """Service for managing round-by-round classifications."""

    @staticmethod
    def get_round_standings(
        prova_id: int, round_number: int
    ) -> List[RoundClassification]:
        """
        Get standings after a specific round.

        Args:
            prova_id: ID of the prova
            round_number: Round number

        Returns:
            List of RoundClassification objects ordered by position
        """
        return (
            RoundClassification.query.filter_by(
                prova_id=prova_id, round_number=round_number
            )
            .order_by(RoundClassification.position)
            .all()
        )

    @staticmethod
    def get_player_progression(
        prova_id: int, user_id: int
    ) -> List[RoundClassification]:
        """
        Get a player's position progression across all rounds.

        Args:
            prova_id: ID of the prova
            user_id: ID of the player

        Returns:
            List of RoundClassification objects ordered by round
        """
        return (
            RoundClassification.query.filter_by(prova_id=prova_id, user_id=user_id)
            .order_by(RoundClassification.round_number)
            .all()
        )

    @staticmethod
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
    """Service for managing player encounter tracking."""

    @staticmethod
    def get_player_encounters(prova_id: int, player_id: int) -> List[PlayerEncounter]:
        """
        Get all encounters for a player in a prova.

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
        Get available opponents from a list of candidates.

        Args:
            prova_id: ID of the prova
            player_id: ID of the player
            candidate_ids: List of potential opponent IDs

        Returns:
            List of player IDs who haven't played against the given player
        """
        # Get all past encounters
        past_opponents = set()
        encounters = PlayerEncounterService.get_player_encounters(prova_id, player_id)

        for encounter in encounters:
            if encounter.player1_id == player_id:
                past_opponents.add(encounter.player2_id)
            else:
                past_opponents.add(encounter.player1_id)

        # Return candidates who haven't been played
        return [cid for cid in candidate_ids if cid not in past_opponents]

    @staticmethod
    def record_match_encounters(match) -> None:
        """
        Record player encounters from a match.

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
    def get_encounter_matrix(prova_id: int) -> Dict[Tuple[int, int], bool]:
        """
        Get encounter matrix for all players in a prova.

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
