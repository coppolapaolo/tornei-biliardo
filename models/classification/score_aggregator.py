"""
Module: models/classification/score_aggregator.py
Purpose: Aggregates match/set/rack data into PlayerScore objects
Data Structures: ScoreAggregator
Dependencies: typing, .strategies.base, models.base
"""

from typing import List, Dict, Any, Optional
from .strategies.base import PlayerScore


class ScoreAggregator:
    """Aggregates match data into PlayerScore objects for classification.

    Separates data collection from ranking logic - the aggregator produces
    the raw stats, strategies decide how to rank them.

    Handles:
    - Regular matches (single and multi-set)
    - Bye matches (player1 gets automatic win)
    - Cumulative stats across multiple rounds
    """

    def aggregate_round_scores(
        self,
        gara_id: int,
        up_to_round: int,
    ) -> List[PlayerScore]:
        """Aggregate scores from matches up to specified round.

        Args:
            gara_id: ID of the gara
            up_to_round: Include matches up to and including this round

        Returns:
            List of PlayerScore objects for all players with matches
        """
        from models.match.models import Match
        from models.base import db

        # Include both 'completed' (admin) and 'validated' (bilateral player confirmation)
        matches = (
            db.session.query(Match)
            .filter(
                Match.gara_id == gara_id,
                Match.round_number <= up_to_round,
                Match.status.in_(["completed", "validated"]),
            )
            .all()
        )

        player_stats: Dict[int, Dict[str, int]] = {}

        for match in matches:
            if match.is_bye:
                self._process_bye_match(match, player_stats)
            elif match.is_trio and match.trio_match:
                self._process_trio_match(match, player_stats)
            else:
                self._process_regular_match(match, player_stats)

        # Convert to PlayerScore objects
        return [
            PlayerScore(
                player_id=pid,
                matches_won=stats.get("matches_won", 0),
                matches_lost=stats.get("matches_lost", 0),
                racks_won=stats.get("racks_won", 0),
                racks_lost=stats.get("racks_lost", 0),
                rack_difference=stats.get("racks_won", 0) - stats.get("racks_lost", 0),
                sets_won=stats.get("sets_won", 0),
                sets_lost=stats.get("sets_lost", 0),
            )
            for pid, stats in player_stats.items()
        ]

    def aggregate_campionato_scores(
        self,
        campionato_id: int,
    ) -> List[PlayerScore]:
        """Aggregate scores across all gare in a campionato.

        Args:
            campionato_id: ID of the campionato

        Returns:
            List of PlayerScore objects aggregated across all gare
        """
        from models.competition.models import Gara
        from models.base import db
        from sqlalchemy.orm import selectinload

        # selectinload avoids N+1: one IN-query loads all matches for all gare,
        # instead of one lazy-load per gara when accessing `gara.matches` below.
        gare = (
            db.session.query(Gara)
            .filter_by(campionato_id=campionato_id)
            .options(selectinload(Gara.matches))
            .all()
        )

        player_stats: Dict[int, Dict[str, int]] = {}

        for gara in gare:
            # Include both 'completed' and 'validated' as finished matches
            matches = [
                m
                for m in gara.matches
                if m.status in ["completed", "validated"] and not m.is_bye
            ]
            for match in matches:
                if match.is_trio and match.trio_match:
                    self._process_trio_match(match, player_stats)
                else:
                    self._process_regular_match(match, player_stats)

        return [
            PlayerScore(
                player_id=pid,
                matches_won=stats.get("matches_won", 0),
                matches_lost=stats.get("matches_lost", 0),
                racks_won=stats.get("racks_won", 0),
                racks_lost=stats.get("racks_lost", 0),
                rack_difference=stats.get("racks_won", 0) - stats.get("racks_lost", 0),
                sets_won=stats.get("sets_won", 0),
                sets_lost=stats.get("sets_lost", 0),
            )
            for pid, stats in player_stats.items()
        ]

    def aggregate_gara_final_scores(
        self,
        gara_id: int,
        spot_shot_results: Optional[Dict[int, int]] = None,
    ) -> List[PlayerScore]:
        """Aggregate final gara scores including tiebreaker data.

        Args:
            gara_id: ID of the gara
            spot_shot_results: Optional spot shot rally results (player_id -> wins)

        Returns:
            List of PlayerScore objects with spot_shot_wins populated
        """
        from models.competition.models import Gara
        from models.base import db

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        # Get all rounds stats
        scores = self.aggregate_round_scores(gara_id, gara.current_round or 1)

        # Enrich with spot shot results if provided
        if spot_shot_results:
            enriched = []
            for score in scores:
                spot_wins = spot_shot_results.get(score.player_id, 0)
                if spot_wins > 0:
                    # Create new PlayerScore with spot_shot_wins
                    enriched.append(
                        PlayerScore(
                            player_id=score.player_id,
                            matches_won=score.matches_won,
                            matches_lost=score.matches_lost,
                            racks_won=score.racks_won,
                            racks_lost=score.racks_lost,
                            rack_difference=score.rack_difference,
                            sets_won=score.sets_won,
                            sets_lost=score.sets_lost,
                            spot_shot_wins=spot_wins,
                        )
                    )
                else:
                    enriched.append(score)
            return enriched

        return scores

    def get_gara_position_results(
        self,
        campionato_id: int,
    ) -> Dict[int, List[int]]:
        """Get final positions for each player across all gare.

        Used for point-based campionato classification.

        Args:
            campionato_id: ID of the campionato

        Returns:
            Dict mapping player_id -> list of positions in each gara
        """
        from models.competition.models import Gara
        from .models import RoundClassification
        from models.base import db

        gare = db.session.query(Gara).filter_by(campionato_id=campionato_id).all()

        player_positions: Dict[int, List[int]] = {}

        for gara in gare:
            if not gara.current_round:
                continue

            # Get final round classification for this gara
            classifications = (
                db.session.query(RoundClassification)
                .filter_by(gara_id=gara.id, round_number=gara.current_round)
                .all()
            )

            for classification in classifications:
                if classification.user_id not in player_positions:
                    player_positions[classification.user_id] = []
                player_positions[classification.user_id].append(classification.position)

        return player_positions

    def _process_regular_match(
        self,
        match: Any,
        player_stats: Dict[int, Dict[str, int]],
    ) -> None:
        """Process a regular (non-bye) match.

        Args:
            match: Match model instance
            player_stats: Dict to accumulate stats into
        """
        # Initialize players if not seen
        for pid in [match.player1_id, match.player2_id]:
            if pid and pid not in player_stats:
                player_stats[pid] = {
                    "matches_won": 0,
                    "matches_lost": 0,
                    "racks_won": 0,
                    "racks_lost": 0,
                    "sets_won": 0,
                    "sets_lost": 0,
                }

        if not match.player1_id or not match.player2_id:
            return

        # Determine winner (handle ties - neither gets a win)
        if match.player1_score > match.player2_score:
            player_stats[match.player1_id]["matches_won"] += 1
            player_stats[match.player2_id]["matches_lost"] += 1
        elif match.player2_score > match.player1_score:
            player_stats[match.player2_id]["matches_won"] += 1
            player_stats[match.player1_id]["matches_lost"] += 1
        # else: tie - neither player gets a win

        # Process racks (handle multi-set)
        if match.is_multi_set:
            # Multi-set: player1_score/player2_score are SETS won, not racks
            # Sum racks from all sets
            for set_obj in match.sets:
                player_stats[match.player1_id]["racks_won"] += set_obj.player1_racks
                player_stats[match.player1_id]["racks_lost"] += set_obj.player2_racks
                player_stats[match.player2_id]["racks_won"] += set_obj.player2_racks
                player_stats[match.player2_id]["racks_lost"] += set_obj.player1_racks

            # Track sets won/lost
            player_stats[match.player1_id]["sets_won"] += match.player1_score
            player_stats[match.player1_id]["sets_lost"] += match.player2_score
            player_stats[match.player2_id]["sets_won"] += match.player2_score
            player_stats[match.player2_id]["sets_lost"] += match.player1_score
        else:
            # Single-set: player1_score/player2_score are racks won
            player_stats[match.player1_id]["racks_won"] += match.player1_score
            player_stats[match.player1_id]["racks_lost"] += match.player2_score
            player_stats[match.player2_id]["racks_won"] += match.player2_score
            player_stats[match.player2_id]["racks_lost"] += match.player1_score

    def _process_bye_match(
        self,
        match: Any,
        player_stats: Dict[int, Dict[str, int]],
    ) -> None:
        """Process a bye match (player gets automatic win).

        Args:
            match: Match model instance (with is_bye=True)
            player_stats: Dict to accumulate stats into
        """
        pid = match.player1_id
        if not pid:
            return

        if pid not in player_stats:
            player_stats[pid] = {
                "matches_won": 0,
                "matches_lost": 0,
                "racks_won": 0,
                "racks_lost": 0,
                "sets_won": 0,
                "sets_lost": 0,
            }

        # Bye player gets automatic win
        player_stats[pid]["matches_won"] += 1
        player_stats[pid]["racks_won"] += match.player1_score or 0
        # No rack_lost for bye matches

    def _process_trio_match(
        self,
        match: Any,
        player_stats: Dict[int, Dict[str, int]],
    ) -> None:
        """Process a trio match using round-robin format (ADR-005).

        In trio, 3 players play round-robin matches within "gironi" (rounds).
        Classification is based on total racks won, with bonus racks added
        to equalize with normal matches (bonus = 1 if distance is odd).

        Winner is optional - ties are allowed for rack-based classification.

        Args:
            match: Match model instance (with is_trio=True and trio_match)
            player_stats: Dict to accumulate stats into
        """
        trio = match.trio_match
        if not trio:
            return

        player_ids = [trio.player1_id, trio.player2_id, trio.player3_id]
        distance = match.gara.distance if match.gara else 5

        # Initialize all three players if not seen
        for pid in player_ids:
            if pid and pid not in player_stats:
                player_stats[pid] = {
                    "matches_won": 0,
                    "matches_lost": 0,
                    "racks_won": 0,
                    "racks_lost": 0,
                    "sets_won": 0,
                    "sets_lost": 0,
                }

        winner_id = match.winner_id

        # Walkover branch: completed trio with no racks played.
        # Credit the nominal winner with `distance` racks (parallel to 2-player
        # walkover where `Match.player1_score = round_distance`). Others get
        # matches_lost but no rack movement — they didn't play.
        if trio.is_completed and trio.total_racks_played == 0 and winner_id:
            for pid in player_ids:
                if not pid:
                    continue
                if pid == winner_id:
                    player_stats[pid]["matches_won"] += 1
                    player_stats[pid]["racks_won"] += distance
                else:
                    player_stats[pid]["matches_lost"] += 1
            return

        racks = [trio.player1_racks, trio.player2_racks, trio.player3_racks]
        bonus_racks = distance % 2  # 1 for distance 3,5; 0 for distance 2,4

        # Process each player
        for i, pid in enumerate(player_ids):
            if not pid:
                continue

            player_racks = racks[i]
            from models.match.trio_config import trio_racks_lost

            opponent_racks = trio_racks_lost(player_racks, distance)

            # Add bonus racks to each player (equalization with normal matches)
            player_stats[pid]["racks_won"] += player_racks + bonus_racks
            player_stats[pid]["racks_lost"] += opponent_racks

            # Winner exists: winner gets match_won, others get match_lost
            # No winner (tie): no one gets match_won or match_lost
            if winner_id:
                if pid == winner_id:
                    player_stats[pid]["matches_won"] += 1
                else:
                    player_stats[pid]["matches_lost"] += 1


__all__ = ["ScoreAggregator"]
