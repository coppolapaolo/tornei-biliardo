"""
Rating Calculation Service

Handles the mathematical logic for updating Elo ratings based on match results.
Supports both standard 1v1 matches and Trio matches (treated as multi-way comparison).
"""
import math
from typing import Tuple, List, Dict, Optional
from models.rating.models import RatingSystem, PlayerRating
from models.match.models import Match, TrioMatch
from models.base import db
import logging

logger = logging.getLogger(__name__)

ELO_K_FACTOR = 32

class RatingCalculationService:
    """Service for calculating rating updates."""

    @staticmethod
    def calculate_expected_score(user_rating: int, opponent_rating: int) -> float:
        """
        Calculate expected score based on Elo formula.
        E = 1 / (1 + 10 ^ ((R_opp - R_user) / 400))
        """
        return 1.0 / (1.0 + math.pow(10, (opponent_rating - user_rating) / 400.0))

    @staticmethod
    def calculate_new_rating(current_rating: int, expected_score: float, actual_score: float, k_factor: int = ELO_K_FACTOR) -> int:
        """
        Calculate new rating based on standard Elo formula.
        R_new = R_old + K * (S - E)
        """
        delta = k_factor * (actual_score - expected_score)
        return int(round(current_rating + delta))

    @staticmethod
    def process_match_result(match: Match) -> None:
        """
        Process the result of a completed match and update ratings.
        """
        if match.is_trio and match.trio_match:
            RatingCalculationService._process_trio_match(match.trio_match)
        else:
            RatingCalculationService._process_standard_match(match)

    @staticmethod
    def _process_standard_match(match: Match) -> None:
        """Handle standard 1v1 match."""
        if not match.player1_id or not match.player2_id:
            logger.warning(f"Standard match {match.id} missing players, skipping rating update.")
            return

        # Get current ratings (default to 1200 if not set)
        p1_rating_obj = PlayerRating.get_user_rating(match.player1_id, RatingSystem.ELO)
        p2_rating_obj = PlayerRating.get_user_rating(match.player2_id, RatingSystem.ELO)

        r1 = p1_rating_obj.rating_value if p1_rating_obj else 1200
        r2 = p2_rating_obj.rating_value if p2_rating_obj else 1200

        # Determine actual scores
        # 1 = Win, 0 = Loss, 0.5 = Draw (if winner_id is None)
        if match.winner_id == match.player1_id:
            s1 = 1.0
            s2 = 0.0
        elif match.winner_id == match.player2_id:
            s1 = 0.0
            s2 = 1.0
        else:
            s1 = 0.5
            s2 = 0.5
        
        # Calculate Expected Scores
        e1 = RatingCalculationService.calculate_expected_score(r1, r2)
        e2 = RatingCalculationService.calculate_expected_score(r2, r1)

        # Calculate new ratings
        new_r1 = RatingCalculationService.calculate_new_rating(r1, e1, s1)
        new_r2 = RatingCalculationService.calculate_new_rating(r2, e2, s2)

        # Update Database
        RatingCalculationService._update_player_rating_db(match.player1_id, new_r1, p1_rating_obj)
        RatingCalculationService._update_player_rating_db(match.player2_id, new_r2, p2_rating_obj)
        
        logger.info(f"Updated ratings for Match {match.id}: P1 {r1}->{new_r1}, P2 {r2}->{new_r2}")

    @staticmethod
    def _process_trio_match(trio: TrioMatch) -> None:
        """
        Handle Trio match.
        Logic:
        - S=1 if strictly greater than both opponents
        - S=0.5 if tied for best score
        - S=0 otherwise
        - E calculated against average of opponents
        """
        scores = {
            trio.player1_id: trio.player1_racks,
            trio.player2_id: trio.player2_racks,
            trio.player3_id: trio.player3_racks
        }
        
        player_ids = [trio.player1_id, trio.player2_id, trio.player3_id]
        
        # Load ratings
        ratings = {}
        rating_objs = {}
        for pid in player_ids:
            obj = PlayerRating.get_user_rating(pid, RatingSystem.ELO)
            rating_objs[pid] = obj
            ratings[pid] = obj.rating_value if obj else 1200

        # Calculate Delta for each player independently
        updates = {}
        for pid in player_ids:
            my_score = scores[pid]
            others = [p for p in player_ids if p != pid]
            other_scores = [scores[o] for o in others]
            other_ratings = [ratings[o] for o in others]
            
            # Determine Actual Score S
            # Win (1.0): Strictly greater than ALL others
            if all(my_score > os for os in other_scores):
                actual_s = 1.0
            # Draw (0.5): Greater than or equal to ALL, but EQUAL to at least one (tied for first)
            elif all(my_score >= os for os in other_scores) and any(my_score == os for os in other_scores):
                actual_s = 0.5
            # Loss (0.0): Less than someone
            else:
                actual_s = 0.0
            
            # Determine Expected Score E
            # Vs Average rating of opponents
            avg_opp_rating = sum(other_ratings) / len(other_ratings)
            expected_e = RatingCalculationService.calculate_expected_score(ratings[pid], avg_opp_rating)
            
            # Calculate New Rating
            new_rating = RatingCalculationService.calculate_new_rating(ratings[pid], expected_e, actual_s)
            updates[pid] = new_rating
            
            logger.info(f"Trio {trio.id} Player {pid}: Score={my_score} vs {other_scores}, S={actual_s}, E={expected_e:.3f}, R={ratings[pid]}->{new_rating}")

        # Apply updates
        for pid, new_r in updates.items():
            RatingCalculationService._update_player_rating_db(pid, new_r, rating_objs.get(pid))

    @staticmethod
    def _update_player_rating_db(user_id: int, new_val: int, exist_obj: Optional[PlayerRating]) -> None:
        """Helper to save rating to DB and sync with User model."""
        # Update/Create PlayerRating
        if exist_obj:
            exist_obj.update_rating(new_val)
        else:
            new_rating = PlayerRating(
                user_id=user_id,
                rating_system=RatingSystem.ELO,
                rating_value=new_val,
                games_played=1
            )
            db.session.add(new_rating)
            
        # Sync to User model for easier access
        from models.user.models import User
        user = db.session.get(User, user_id)
        if user:
            user.elo_rating = new_val
            db.session.add(user)
