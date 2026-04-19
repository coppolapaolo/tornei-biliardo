"""
Module: models/classification/encounter_service.py
Purpose: Player encounter tracking for anti-rematch logic
"""

from typing import List, Tuple, Dict, Any
from models.base import db
from .models import PlayerEncounter
from ..caching import cached, cache_invalidate


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

        For trio matches, records all 3 pairwise encounters (P1-P2, P1-P3, P2-P3).

        Args:
            match: Match object to record encounters from
        """
        if match.is_bye or not match.player2_id:
            return

        if match.is_trio and match.trio_match:
            trio = match.trio_match
            pairs = [
                (trio.player1_id, trio.player2_id),
                (trio.player1_id, trio.player3_id),
                (trio.player2_id, trio.player3_id),
            ]
            for p1, p2 in pairs:
                PlayerEncounter.record_encounter(
                    gara_id=match.gara_id,
                    player1_id=p1,
                    player2_id=p2,
                    round_number=match.round_number,
                )
        else:
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
    @cached(ttl_seconds=600, tags=["encounter", "gara"], key_generator="gara")
    def get_trio_counts(
        gara_id: int, exclude_walkover: bool = True
    ) -> Dict[int, int]:
        """Count contested trio matches per player in a gara.

        Cached 10 min with same invalidation scheme as encounter_matrix.
        Walkover trios (total_racks_played == 0) are excluded by default,
        so that survivors of a walkover are not penalized in trio rotation.

        Coherent with AmalfiStrategy._get_trio_counts (spec-walkover-side-effects-unified).

        Args:
            gara_id: ID of the gara
            exclude_walkover: If True (default), trios with 0 racks played are skipped

        Returns:
            Dict mapping player_id -> number of contested trio matches played
        """
        from ..match.models import Match, TrioMatch

        trio_matches = (
            db.session.query(TrioMatch)
            .join(Match)
            .filter(Match.gara_id == gara_id, Match.is_trio == True)  # noqa: E712
            .all()
        )

        counts: Dict[int, int] = {}
        for trio in trio_matches:
            if exclude_walkover and trio.total_racks_played == 0:
                continue
            counts[trio.player1_id] = counts.get(trio.player1_id, 0) + 1
            counts[trio.player2_id] = counts.get(trio.player2_id, 0) + 1
            counts[trio.player3_id] = counts.get(trio.player3_id, 0) + 1
        return counts

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
