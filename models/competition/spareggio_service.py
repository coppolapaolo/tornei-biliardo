"""
Module: models/competition/spareggio_service.py
Purpose: Handle spot shot rally (SSR) tiebreakers for top 3 positions
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, TypedDict
from sqlalchemy import func
from models.base import db
from models.classification.models import RoundClassification, GaraClassification
from models.match.models import Match
from models.transaction.manager import transactional

if TYPE_CHECKING:
    from models.competition.models import Gara


class TiebreakerGroup(TypedDict):
    """A group of players tied for the same position."""
    position: int  # Starting position (1, 2, or 3)
    rack_totali: int  # Shared rack count
    players: List[Dict]  # List of {user_id, username, current_ssr_score}


class SpareggioService:
    """Service for detecting and resolving tiebreakers in top 3 positions."""

    @staticmethod
    def _get_effective_final_round(gara: Gara) -> int:
        """Get the effective final round for classification.

        For Random strategy, all rounds are created at startup so
        gara.current_round may lag behind. Use max(Match.round_number) instead.
        For other strategies, fall back to gara.current_round or gara.rounds_count.
        """
        max_round = db.session.query(func.max(Match.round_number)).filter(
            Match.gara_id == gara.id
        ).scalar()
        return max_round or gara.current_round or gara.rounds_count

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

        # Check if tiebreaker is enabled for this gara
        if not gara.tiebreaker_enabled:
            return []

        # Get the position limit for tiebreakers (default to 3 if not set)
        tiebreaker_limit = gara.tiebreaker_until_position or 3

        # Get final round classification
        final_round = SpareggioService._get_effective_final_round(gara)
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

            # Check if this group includes any position within tiebreaker limit
            if current_position <= tiebreaker_limit and len(group) > 1:
                # Check if any player in this group is within the tiebreaker limit
                # (position would be <= tiebreaker_limit based on current_position)
                end_position = current_position + len(group) - 1

                # If the group spans into top positions, it needs a tiebreaker
                if current_position <= tiebreaker_limit:
                    # Check existing SSR scores to see if already resolved
                    existing_gara_class = (
                        db.session.query(GaraClassification)
                        .filter(
                            GaraClassification.gara_id == gara_id,
                            GaraClassification.user_id.in_([c.user_id for c in group])
                        )
                        .all()
                    )
                    ssr_scores = {gc.user_id: gc.spot_shot_wins for gc in existing_gara_class}

                    # Build player list with SSR scores
                    players = []
                    for c in group:
                        user = c.user
                        players.append({
                            'user_id': c.user_id,
                            'username': user.username if user else f"User {c.user_id}",
                            'current_ssr_score': ssr_scores.get(c.user_id)  # None if not entered
                        })

                    # Check if this tiebreaker is already resolved
                    # All players must have a score AND all scores must be different
                    # 0 is a valid score, None means not entered
                    scores = [p['current_ssr_score'] for p in players]
                    all_scores_entered = all(s is not None for s in scores)
                    all_scores_different = len(scores) == len(set(scores))
                    is_resolved = all_scores_entered and all_scores_different

                    if not is_resolved:
                        tiebreaker_groups.append({
                            'position': current_position,
                            'rack_totali': rack_count,
                            'players': players
                        })

            current_position += len(group)

            # Stop if we've passed the tiebreaker position limit
            if current_position > tiebreaker_limit:
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
    def get_all_ssr_groups(gara_id: int) -> List[TiebreakerGroup]:
        """
        Get ALL tiebreaker groups (resolved and unresolved) for display.

        Unlike detect_tiebreakers() which only returns unresolved groups,
        this method returns all groups for showing SSR scores in the UI.

        Args:
            gara_id: ID of the gara

        Returns:
            List of TiebreakerGroup dictionaries (both resolved and unresolved)
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return []

        # Check if tiebreaker is enabled for this gara
        if not gara.tiebreaker_enabled:
            return []

        # Get the position limit for tiebreakers (default to 3 if not set)
        tiebreaker_limit = gara.tiebreaker_until_position or 3

        # Get final round classification
        final_round = SpareggioService._get_effective_final_round(gara)
        classifications = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=final_round)
            .order_by(RoundClassification.rack_difference.desc())
            .all()
        )

        if not classifications:
            return []

        # Group players by rack_difference
        groups_by_racks: Dict[int, List[RoundClassification]] = {}
        for c in classifications:
            rack_key = c.rack_difference
            if rack_key not in groups_by_racks:
                groups_by_racks[rack_key] = []
            groups_by_racks[rack_key].append(c)

        # Sort rack counts descending
        sorted_rack_counts = sorted(groups_by_racks.keys(), reverse=True)

        # Find ALL groups that affect top 3 positions (resolved or not)
        all_groups: List[TiebreakerGroup] = []
        current_position = 1

        for rack_count in sorted_rack_counts:
            group = groups_by_racks[rack_count]

            # Check if this group includes any position within tiebreaker limit AND has multiple players
            if current_position <= tiebreaker_limit and len(group) > 1:
                # Get existing SSR scores
                existing_gara_class = (
                    db.session.query(GaraClassification)
                    .filter(
                        GaraClassification.gara_id == gara_id,
                        GaraClassification.user_id.in_([c.user_id for c in group])
                    )
                    .all()
                )
                ssr_scores = {gc.user_id: gc.spot_shot_wins for gc in existing_gara_class}

                # Build player list with SSR scores
                players = []
                for c in group:
                    user = c.user
                    players.append({
                        'user_id': c.user_id,
                        'username': user.username if user else f"User {c.user_id}",
                        'current_ssr_score': ssr_scores.get(c.user_id)  # None if not entered
                    })

                all_groups.append({
                    'position': current_position,
                    'rack_totali': rack_count,
                    'players': players
                })

            current_position += len(group)

            # Stop if we've passed the tiebreaker position limit
            if current_position > tiebreaker_limit:
                break

        return all_groups

    @staticmethod
    def is_group_resolved(group: TiebreakerGroup) -> bool:
        """
        Check if a single tiebreaker group is resolved.

        A group is resolved when all SSR scores are different (0 is valid).
        """
        scores = [p['current_ssr_score'] for p in group['players']]
        return len(scores) == len(set(scores))

    @staticmethod
    def validate_ssr_scores_for_group(scores: Dict[int, int]) -> Tuple[bool, str]:
        """
        Validate SSR scores for a SINGLE tiebreaker group.

        Scores must be unique only within this group - different groups
        can have overlapping scores.

        Args:
            scores: Dict mapping user_id to SSR score for players in ONE group

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not scores:
            return False, "Nessun punteggio fornito"

        # Check all scores are non-negative integers
        for score in scores.values():
            if not isinstance(score, int) or score < 0:
                return False, "I punteggi devono essere numeri interi non negativi"

        # Check all scores are different within the group
        score_values = list(scores.values())
        if len(score_values) != len(set(score_values)):
            return False, "I punteggi devono essere diversi all'interno del gruppo"

        return True, ""

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

        # Check all scores are non-negative integers
        for score in scores.values():
            if not isinstance(score, int) or score < 0:
                return False, "Tutti i punteggi devono essere numeri interi non negativi"

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
        final_round = SpareggioService._get_effective_final_round(gara)

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
    def save_ssr_scores_for_group(
        gara_id: int,
        group_position: int,
        scores: Dict[int, int]
    ) -> Tuple[bool, str]:
        """
        Save SSR scores for a SINGLE tiebreaker group.

        This validates scores only within the specified group, allowing
        different groups to have overlapping SSR values.

        Args:
            gara_id: ID of the gara
            group_position: Position of the tiebreaker group (1, 2, or 3)
            scores: Dict mapping user_id to SSR score for this group

        Returns:
            Tuple of (success, message)
        """
        from models.competition.models import Gara

        # Validate scores for this group
        is_valid, error = SpareggioService.validate_ssr_scores_for_group(scores)
        if not is_valid:
            return False, error

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return False, "Gara non trovata"

        # Verify the group exists and contains the specified user_ids
        all_groups = SpareggioService.get_all_ssr_groups(gara_id)
        target_group: Optional[TiebreakerGroup] = None
        for group in all_groups:
            if group['position'] == group_position:
                target_group = group
                break

        if not target_group:
            return False, f"Gruppo di parimerito alla posizione {group_position} non trovato"

        # Verify all user_ids in scores belong to this group
        group_user_ids = {p['user_id'] for p in target_group['players']}
        for user_id in scores.keys():
            if user_id not in group_user_ids:
                return False, f"Giocatore {user_id} non appartiene a questo gruppo"

        # Get final round for stats lookup
        final_round = SpareggioService._get_effective_final_round(gara)

        # Save scores for this group
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
                    racks_won=round_class.rack_difference,
                    rack_difference=round_class.rack_difference,
                )
                db.session.add(gara_class)

            # Update SSR score
            gara_class.spot_shot_wins = ssr_score
            gara_class.tiebreaker_resolved = True

        return True, f"Punteggi SSR per posizione {group_position} salvati"

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

        final_round = SpareggioService._get_effective_final_round(gara)

        # Expire all to ensure we get fresh data from DB
        db.session.expire_all()

        # Get all round classifications
        round_classifications = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=final_round)
            .all()
        )

        # Build a map for quick lookup
        round_class_map = {rc.user_id: rc for rc in round_classifications}

        # Get existing gara classifications (with SSR scores)
        existing_gara_class = {
            gc.user_id: gc for gc in
            db.session.query(GaraClassification).filter_by(gara_id=gara_id).all()
        }

        # Build combined data for sorting
        player_data = []
        for rc in round_classifications:
            gc = existing_gara_class.get(rc.user_id)
            # SSR score: None means not entered, treat as -1 for sorting (lowest)
            ssr_score = gc.spot_shot_wins if gc and gc.spot_shot_wins is not None else -1
            player_data.append({
                'user_id': rc.user_id,
                'rack_totali': rc.rack_difference,
                'ssr_score': ssr_score,
                'matches_won': rc.matches_won,
            })

        # Sort by rack_totali DESC, then ssr_score DESC
        # -1 (not entered) will sort last among same rack_totali
        player_data.sort(key=lambda x: (-x['rack_totali'], -x['ssr_score']))

        # Update/create GaraClassification and RoundClassification with correct positions
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

            # Also update RoundClassification position so UI shows correct ordering
            round_class = round_class_map.get(data['user_id'])
            if round_class:
                round_class.position = position

        return True, "Classifica finale aggiornata"
