"""
Rating Calculation Service

Handles the mathematical logic for updating Elo ratings based on match results.
Supports both standard 1v1 matches and Trio matches (treated as multi-way comparison).
"""

import math
from typing import Optional
from models.rating.models import RatingSystem, PlayerRating, MatchRatingHistory
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
    def calculate_new_rating(
        current_rating: int,
        expected_score: float,
        actual_score: float,
        k_factor: int = ELO_K_FACTOR,
    ) -> int:
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

        Idempotente: se esiste già history per questo match (sistema ELO) il
        calcolo è un no-op. Protegge da MatchCompletedEvent ri-emessi
        (reset→ricompletamento) e da recalc_elo su match già processati.

        NB: il caller (RatingEventHandlers / recalc) è responsabile di NON
        chiamare questo metodo per i match con handicap (effective_has_handicap)
        e per i walkover — qui non rileggiamo quei flag per non duplicare la
        policy, ma l'idempotenza resta una rete di sicurezza.
        """
        if MatchRatingHistory.exists_for_match(match.id, RatingSystem.ELO):
            logger.info(
                f"Match {match.id} già processato per il rating ELO, skip "
                f"(idempotenza)."
            )
            return

        if match.is_trio and match.trio_match:
            RatingCalculationService._process_trio_match(match.trio_match, match.id)
        else:
            RatingCalculationService._process_standard_match(match)

    @staticmethod
    def revert_match_result(match: Match) -> None:
        """Annulla i delta di rating applicati per questo match.

        Per ogni record di history: sottrae il delta dal rating corrente e
        decrementa games_played, poi elimina il record. Usato quando un match
        completato viene riaperto/resettato o prima di eliminarlo.

        Path-dependency: sottrarre il delta (anziché ripristinare il valore
        assoluto) è esatto se il match è l'ultimo processato per quei giocatori
        — il caso tipico di un reset. Per un match "in mezzo" i rating restano
        approssimati finché non si rilancia recalc_elo.
        """
        from models.user.models import User

        records = MatchRatingHistory.query.filter_by(match_id=match.id).all()
        if not records:
            return

        for rec in records:
            rating_obj = PlayerRating.get_user_rating(rec.user_id, rec.rating_system)
            if rating_obj:
                rating_obj.rating_value = rating_obj.rating_value - rec.delta
                rating_obj.games_played = max(
                    0, rating_obj.games_played - rec.games_increment
                )
                db.session.add(rating_obj)
                if rec.rating_system == RatingSystem.ELO:
                    user = db.session.get(User, rec.user_id)
                    if user:
                        user.elo_rating = rating_obj.rating_value
                        db.session.add(user)
            db.session.delete(rec)

        logger.info(
            f"Revert rating per match {match.id}: annullati {len(records)} delta."
        )

    @staticmethod
    def _process_standard_match(match: Match) -> None:
        """Handle standard 1v1 match."""
        if not match.player1_id or not match.player2_id:
            logger.warning(
                f"Standard match {match.id} missing players, skipping rating update."
            )
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

        # Update Database (+ history per idempotenza/revert)
        RatingCalculationService._update_player_rating_db(
            match.player1_id, r1, new_r1, p1_rating_obj, match.id
        )
        RatingCalculationService._update_player_rating_db(
            match.player2_id, r2, new_r2, p2_rating_obj, match.id
        )

        logger.info(
            f"Updated ratings for Match {match.id}: "
            f"P1 {r1}->{new_r1}, P2 {r2}->{new_r2}"
        )

    @staticmethod
    def _process_trio_match(trio: TrioMatch, match_id: int) -> None:
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
            trio.player3_id: trio.player3_racks,
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
            # Draw (0.5): >= ALL others, but EQUAL to at least one (tied 1st)
            elif all(my_score >= os for os in other_scores) and any(
                my_score == os for os in other_scores
            ):
                actual_s = 0.5
            # Loss (0.0): Less than someone
            else:
                actual_s = 0.0

            # Determine Expected Score E
            # Vs Average rating of opponents
            avg_opp_rating = sum(other_ratings) / len(other_ratings)
            expected_e = RatingCalculationService.calculate_expected_score(
                ratings[pid], avg_opp_rating
            )

            # Calculate New Rating
            new_rating = RatingCalculationService.calculate_new_rating(
                ratings[pid], expected_e, actual_s
            )
            updates[pid] = new_rating

            logger.info(
                f"Trio {trio.id} Player {pid}: Score={my_score} vs "
                f"{other_scores}, S={actual_s}, E={expected_e:.3f}, "
                f"R={ratings[pid]}->{new_rating}"
            )

        # Apply updates (+ history per idempotenza/revert)
        for pid, new_r in updates.items():
            RatingCalculationService._update_player_rating_db(
                pid, ratings[pid], new_r, rating_objs.get(pid), match_id
            )

    @staticmethod
    def _update_player_rating_db(
        user_id: int,
        old_val: int,
        new_val: int,
        exist_obj: Optional[PlayerRating],
        match_id: int,
    ) -> None:
        """Helper to save rating to DB, sync User, and record history."""
        # Update/Create PlayerRating
        if exist_obj:
            exist_obj.update_rating(new_val)
        else:
            new_rating = PlayerRating(
                user_id=user_id,
                rating_system=RatingSystem.ELO,
                rating_value=new_val,
                games_played=1,
            )
            db.session.add(new_rating)

        # Record history per idempotenza + revert
        db.session.add(
            MatchRatingHistory(
                match_id=match_id,
                user_id=user_id,
                rating_system=RatingSystem.ELO,
                old_rating=old_val,
                new_rating=new_val,
                delta=new_val - old_val,
                games_increment=1,
            )
        )

        # Sync to User model for easier access
        from models.user.models import User

        user = db.session.get(User, user_id)
        if user:
            user.elo_rating = new_val
            db.session.add(user)
