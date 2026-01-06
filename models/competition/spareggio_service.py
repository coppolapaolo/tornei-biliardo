"""
Module: models/competition/spareggio_service.py
Purpose: Handle spot shot rally (SSR) tiebreakers for top 3 positions
"""

from typing import Dict, List, Optional, Tuple, TypedDict
from models.base import db
from models.classification.models import RoundClassification, GaraClassification
from models.transaction.manager import transactional


class TiebreakerGroup(TypedDict):
    """A group of players tied for the same position."""
    position: int  # Starting position (1, 2, or 3)
    rack_totali: int  # Shared rack count
    players: List[Dict]  # List of {user_id, username, current_ssr_score}


class SpareggioService:
    """Service for detecting and resolving tiebreakers in top 3 positions."""

    @staticmethod
    def detect_tiebreakers(gara_id: int) -> List[TiebreakerGroup]:
        """
        Detect tiebreaker groups in the top 3 positions.

        A tiebreaker is needed when multiple players have the same rack count
        and at least one of them would be in the top 3.

        Args:
            gara_id: ID of the gara

        Returns:
            List of TiebreakerGroup dictionaries, empty if no tiebreakers needed
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return []

        # Get final round classification
        final_round = gara.current_round or gara.rounds_count
        classifications = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=final_round)
            .order_by(RoundClassification.rack_difference.desc())
            .all()
        )

        if not classifications:
            return []

        # Group players by rack_difference (which stores total racks for Random strategy)
        # For other strategies, this is rack_difference
        groups_by_racks: Dict[int, List[RoundClassification]] = {}
        for c in classifications:
            rack_key = c.rack_difference
            if rack_key not in groups_by_racks:
                groups_by_racks[rack_key] = []
            groups_by_racks[rack_key].append(c)

        # Sort rack counts descending
        sorted_rack_counts = sorted(groups_by_racks.keys(), reverse=True)

        # Find groups that affect top 3 positions
        tiebreaker_groups: List[TiebreakerGroup] = []
        current_position = 1

        for rack_count in sorted_rack_counts:
            group = groups_by_racks[rack_count]

            # Check if this group includes any position <= 3
            if current_position <= 3 and len(group) > 1:
                # Check if any player in this group is in top 3
                # (position would be <= 3 based on current_position)
                end_position = current_position + len(group) - 1

                # If the group spans into top 3, it needs a tiebreaker
                if current_position <= 3:
                    # Check existing SSR scores to see if already resolved
                    existing_gara_class = (
                        db.session.query(GaraClassification)
                        .filter(
                            GaraClassification.gara_id == gara_id,
                            GaraClassification.user_id.in_([c.user_id for c in group])
                        )
                        .all()
                    )
                    ssr_scores = {gc.user_id: gc.spot_shot_wins or 0 for gc in existing_gara_class}

                    # Build player list with SSR scores
                    players = []
                    for c in group:
                        user = c.user
                        players.append({
                            'user_id': c.user_id,
                            'username': user.display_name if user else f"User {c.user_id}",
                            'current_ssr_score': ssr_scores.get(c.user_id, 0)
                        })

                    # Check if this tiebreaker is already resolved
                    # (all SSR scores must be different and non-zero)
                    scores = [p['current_ssr_score'] for p in players]
                    is_resolved = (
                        len(scores) == len(set(scores)) and
                        all(s > 0 for s in scores)
                    )

                    if not is_resolved:
                        tiebreaker_groups.append({
                            'position': current_position,
                            'rack_totali': rack_count,
                            'players': players
                        })

            current_position += len(group)

            # Stop if we've passed position 3
            if current_position > 3:
                break

        return tiebreaker_groups

    @staticmethod
    def has_unresolved_tiebreakers(gara_id: int) -> bool:
        """
        Check if there are any unresolved tiebreakers in top 3.

        Args:
            gara_id: ID of the gara

        Returns:
            True if there are unresolved tiebreakers
        """
        return len(SpareggioService.detect_tiebreakers(gara_id)) > 0

    @staticmethod
    def validate_ssr_scores(scores: Dict[int, int]) -> Tuple[bool, str]:
        """
        Validate SSR scores for a tiebreaker group.

        Args:
            scores: Dict mapping user_id to SSR score

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not scores:
            return False, "Nessun punteggio inserito"

        # Check all scores are positive integers
        for user_id, score in scores.items():
            if not isinstance(score, int) or score <= 0:
                return False, "Tutti i punteggi devono essere numeri interi positivi"

        # Check all scores are different
        score_values = list(scores.values())
        if len(score_values) != len(set(score_values)):
            return False, "I punteggi devono essere tutti diversi per risolvere il parimerito"

        return True, ""

    @staticmethod
    @transactional(domain="competition")
    def save_ssr_scores(gara_id: int, scores: Dict[int, int]) -> Tuple[bool, str]:
        """
        Save SSR scores for tiebreaker resolution.

        Args:
            gara_id: ID of the gara
            scores: Dict mapping user_id to SSR score

        Returns:
            Tuple of (success, message)
        """
        from models.competition.models import Gara

        # Validate scores
        is_valid, error = SpareggioService.validate_ssr_scores(scores)
        if not is_valid:
            return False, error

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return False, "Gara non trovata"

        # Get or create GaraClassification entries for all players
        # First, ensure all players in the tiebreaker have GaraClassification entries
        final_round = gara.current_round or gara.rounds_count

        for user_id, ssr_score in scores.items():
            # Get round classification to get stats
            round_class = (
                db.session.query(RoundClassification)
                .filter_by(gara_id=gara_id, round_number=final_round, user_id=user_id)
                .first()
            )

            if not round_class:
                continue

            # Get or create gara classification
            gara_class = (
                db.session.query(GaraClassification)
                .filter_by(gara_id=gara_id, user_id=user_id)
                .first()
            )

            if not gara_class:
                gara_class = GaraClassification(
                    gara_id=gara_id,
                    user_id=user_id,
                    position=round_class.position,
                    matches_won=round_class.matches_won,
                    racks_won=round_class.rack_difference,  # For Random, this is total racks
                    rack_difference=round_class.rack_difference,
                )
                db.session.add(gara_class)

            # Update SSR score
            gara_class.spot_shot_wins = ssr_score
            gara_class.tiebreaker_resolved = True

        return True, "Punteggi spareggio salvati con successo"

    @staticmethod
    @transactional(domain="competition")
    def finalize_classification(gara_id: int) -> Tuple[bool, str]:
        """
        Finalize classification after SSR scores are saved.

        Recalculates positions based on (rack_totali DESC, spot_shot_wins DESC).

        Args:
            gara_id: ID of the gara

        Returns:
            Tuple of (success, message)
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return False, "Gara non trovata"

        final_round = gara.current_round or gara.rounds_count

        # Get all round classifications
        round_classifications = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=final_round)
            .all()
        )

        # Get existing gara classifications (with SSR scores)
        existing_gara_class = {
            gc.user_id: gc for gc in
            db.session.query(GaraClassification).filter_by(gara_id=gara_id).all()
        }

        # Build combined data for sorting
        player_data = []
        for rc in round_classifications:
            gc = existing_gara_class.get(rc.user_id)
            ssr_score = gc.spot_shot_wins if gc else 0
            player_data.append({
                'user_id': rc.user_id,
                'rack_totali': rc.rack_difference,
                'ssr_score': ssr_score or 0,
                'matches_won': rc.matches_won,
            })

        # Sort by rack_totali DESC, then ssr_score DESC
        player_data.sort(key=lambda x: (-x['rack_totali'], -x['ssr_score']))

        # Update/create GaraClassification with correct positions
        for position, data in enumerate(player_data, 1):
            gara_class = existing_gara_class.get(data['user_id'])

            if not gara_class:
                gara_class = GaraClassification(
                    gara_id=gara_id,
                    user_id=data['user_id'],
                    racks_won=data['rack_totali'],
                    rack_difference=data['rack_totali'],
                    matches_won=data['matches_won'],
                )
                db.session.add(gara_class)

            gara_class.position = position

        return True, "Classifica finale aggiornata"
