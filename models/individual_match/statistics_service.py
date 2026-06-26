"""
Module: models/individual_match/statistics_service.py
Purpose: Statistics and query service for individual matches
Sprint 13: IndividualMatchService decomposition
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any

from sqlalchemy import func, case
from ..base import db
from .models import (
    MatchProposal,
    IndividualMatch,
    PlayerAvailability,
    ProposalStatus,
)
from ..status_enum import MatchStatus
from ..user.models import User


class IndividualMatchStatisticsService:
    """Service for individual match statistics and queries."""

    @staticmethod
    def get_user_matches(
        user_id: int, status_filter: Optional[MatchStatus] = None
    ) -> List[IndividualMatch]:
        """Get individual matches for a user."""
        query = IndividualMatch.query.filter(
            db.or_(
                IndividualMatch.player1_id == user_id,
                IndividualMatch.player2_id == user_id,
            )
        )

        if status_filter:
            if isinstance(status_filter, (list, tuple, set)):
                values = [s.value if hasattr(s, "value") else s for s in status_filter]
                query = query.filter(IndividualMatch.status.in_(values))
            else:
                target_status = (
                    status_filter.value
                    if hasattr(status_filter, "value")
                    else status_filter
                )
                query = query.filter(IndividualMatch.status == target_status)

        return query.order_by(IndividualMatch.scheduled_at.desc()).all()

    @staticmethod
    def get_user_statistics(user_id: int) -> Dict[str, Any]:
        """Get individual match statistics for a user."""
        # Conta i match conclusi: COMPLETED (forfait/legacy) E VALIDATED
        # (conferma bilaterale, il flusso normale). Contare solo COMPLETED
        # escludeva la maggioranza dei match finiti dalle statistiche.
        matches = IndividualMatchStatisticsService.get_user_matches(
            user_id, [MatchStatus.COMPLETED, MatchStatus.VALIDATED]
        )

        total_matches = len(matches)
        won_matches = sum(1 for m in matches if m.winner_id == user_id)
        lost_matches = total_matches - won_matches

        total_racks_won = sum(m.get_user_score(user_id) for m in matches)
        total_racks_played = sum(m.player1_score + m.player2_score for m in matches)

        locations_played = {}
        for match in matches:
            # Use location_display property to prefer FK over legacy string
            loc = match.location_display
            if not loc:
                continue  # Skip matches without location
            if loc not in locations_played:
                locations_played[loc] = {"matches": 0, "wins": 0}
            locations_played[loc]["matches"] += 1
            if match.winner_id == user_id:
                locations_played[loc]["wins"] += 1

        return {
            "total_matches": total_matches,
            "won_matches": won_matches,
            "lost_matches": lost_matches,
            "win_percentage": (
                (won_matches / total_matches * 100) if total_matches > 0 else 0
            ),
            "total_racks_won": total_racks_won,
            "total_racks_played": total_racks_played,
            "rack_win_percentage": (
                (total_racks_won / total_racks_played * 100)
                if total_racks_played > 0
                else 0
            ),
            "locations_played": locations_played,
        }

    @staticmethod
    def get_admin_overview() -> Dict[str, Any]:
        """Get admin overview of all individual matches."""
        status_counts = {}
        for status in MatchStatus:
            count = IndividualMatch.query.filter_by(status=status).count()
            status_counts[status.value] = count

        recent_matches = (
            IndividualMatch.query.order_by(IndividualMatch.created_at.desc())
            .limit(10)
            .all()
        )

        proposal_counts = {}
        for status in ProposalStatus:
            count = MatchProposal.query.filter_by(status=status).count()
            proposal_counts[status.value] = count

        active_locations = (
            db.session.query(PlayerAvailability.location)
            .filter_by(is_available=True)
            .distinct()
            .all()
        )

        return {
            "status_counts": status_counts,
            "recent_matches": recent_matches,
            "proposal_counts": proposal_counts,
            "active_locations": [loc[0] for loc in active_locations],
            "total_users_with_availability": PlayerAvailability.query.with_entities(
                PlayerAvailability.user_id
            )
            .distinct()
            .count(),
        }

    @staticmethod
    def get_user_availability(user_id: int) -> Dict[str, Any]:
        """Get user's availability settings and schedule."""
        availability_records = PlayerAvailability.query.filter_by(user_id=user_id).all()

        by_location = {}
        for record in availability_records:
            if record.location not in by_location:
                by_location[record.location] = []
            by_location[record.location].append(record)

        return {
            "availability_records": availability_records,
            "by_location": by_location,
            "available_locations": [
                r.location for r in availability_records if r.is_available
            ],
        }

    @staticmethod
    def get_user_dashboard_data(user_id: int) -> Dict[str, Any]:
        """Get comprehensive dashboard data for user.

        Note: This method imports ProposalService to avoid circular imports.
        """
        from .proposal_service import ProposalService

        proposals = ProposalService.get_user_proposals(user_id)
        all_matches = IndividualMatchStatisticsService.get_user_matches(user_id)
        availability = IndividualMatchStatisticsService.get_user_availability(user_id)
        stats = IndividualMatchStatisticsService.get_user_statistics(user_id)

        active_matches = [
            m
            for m in all_matches
            if m.status in [MatchStatus.SCHEDULED, MatchStatus.IN_PROGRESS]
        ]
        completed_matches = [
            m
            for m in all_matches
            if m.status in (MatchStatus.COMPLETED, MatchStatus.VALIDATED)
        ]
        recent_matches = completed_matches[:5]

        return {
            "proposals": proposals,
            "matches": all_matches,
            "active_matches": active_matches,
            "recent_matches": recent_matches,
            "availability": availability,
            "statistics": stats,
        }

    @staticmethod
    def get_frequent_opponents(user_id: int, limit: int = 5) -> List[User]:
        """Get users this player has played most individual matches against.

        Returns users ordered by number of completed matches (most frequent first).
        Useful for suggesting opponents when creating new match proposals.

        Args:
            user_id: The user to find opponents for
            limit: Maximum number of opponents to return (default 5)

        Returns:
            List of User objects, ordered by match frequency (descending)
        """
        # Build a CASE expression to get the opponent's ID regardless of player position
        opponent_id_expr = case(
            (IndividualMatch.player1_id == user_id, IndividualMatch.player2_id),
            else_=IndividualMatch.player1_id,
        )

        # Query to count matches per opponent
        opponent_counts = (
            db.session.query(
                opponent_id_expr.label("opponent_id"),
                func.count().label("match_count"),
            )
            .filter(
                db.or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                ),
                IndividualMatch.status.in_(MatchStatus.finished_values()),
            )
            .group_by(opponent_id_expr)
            .order_by(func.count().desc())
            .limit(limit)
            .all()
        )

        if not opponent_counts:
            return []

        # Get the opponent IDs in order
        opponent_ids = [oc.opponent_id for oc in opponent_counts]

        # Fetch users and maintain the order
        users_by_id = {
            u.id: u
            for u in User.query.filter(
                User.id.in_(opponent_ids), User.deleted_at.is_(None)
            ).all()
        }

        # Return in frequency order
        return [users_by_id[oid] for oid in opponent_ids if oid in users_by_id]

    @staticmethod
    def _get_all_opponent_ids(user_id: int) -> set[int]:
        """Get IDs of all players user has played against.

        Includes opponents from:
        - Individual matches (completed/validated)
        - Tournament/gara matches (completed/validated)

        Args:
            user_id: The user to find opponents for

        Returns:
            Set of opponent user IDs
        """
        from ..match.models import Match

        opponent_ids_set: set[int] = set()

        # 1. Individual matches - opponent ID expression
        individual_opponent_expr = case(
            (IndividualMatch.player1_id == user_id, IndividualMatch.player2_id),
            else_=IndividualMatch.player1_id,
        )

        individual_opponents = (
            db.session.query(individual_opponent_expr.label("opponent_id"))
            .filter(
                db.or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                ),
                IndividualMatch.status.in_(
                    [
                        MatchStatus.COMPLETED.value,
                        MatchStatus.VALIDATED.value,
                    ]
                ),
            )
            .distinct()
            .all()
        )
        opponent_ids_set.update(
            oc.opponent_id for oc in individual_opponents if oc.opponent_id
        )

        # 2. Tournament/gara matches - opponent ID expression
        tournament_opponent_expr = case(
            (Match.player1_id == user_id, Match.player2_id),
            else_=Match.player1_id,
        )

        tournament_opponents = (
            db.session.query(tournament_opponent_expr.label("opponent_id"))
            .filter(
                db.or_(
                    Match.player1_id == user_id,
                    Match.player2_id == user_id,
                ),
                Match.status.in_(
                    [
                        MatchStatus.COMPLETED.value,
                        MatchStatus.VALIDATED.value,
                    ]
                ),
            )
            .distinct()
            .all()
        )
        opponent_ids_set.update(
            oc.opponent_id for oc in tournament_opponents if oc.opponent_id
        )

        return opponent_ids_set

    @staticmethod
    def get_eligible_opponents(user_id: int) -> List[User]:
        """Get all unique opponents who have unlocked individual matches.

        Uses can_access("create_match_direct") for consistency with menu visibility.
        This ensures that users who see the menu also appear in opponent lists,
        and users who don't have access to individual matches won't appear.

        Includes opponents from:
        - Individual matches (completed/validated)
        - Tournament/gara matches (completed/validated)

        Returns users ordered alphabetically by username.

        Args:
            user_id: The user to find opponents for

        Returns:
            List of User objects who have unlocked individual matches,
            ordered alphabetically by username
        """
        opponent_ids = IndividualMatchStatisticsService._get_all_opponent_ids(user_id)

        if not opponent_ids:
            return []

        # Fetch users and filter by feature access
        users = (
            User.query.filter(
                User.id.in_(list(opponent_ids)),
                User.deleted_at.is_(None),
            )
            .order_by(User.username)
            .all()
        )

        # Filter by feature access (consistent with menu visibility)
        return [u for u in users if u.can_access("create_match_direct")]

    @staticmethod
    def get_all_opponents(user_id: int, min_level: int = 5) -> List[User]:
        """Get all unique opponents this player has played any match against.

        DEPRECATED: Use get_eligible_opponents() instead for consistency
        with the gamification feature gating system.

        Includes opponents from:
        - Individual matches (completed/validated)
        - Tournament/gara matches (completed/validated)

        Returns users ordered alphabetically by username.
        Filters for users who have reached minimum level for individual matches.

        Args:
            user_id: The user to find opponents for
            min_level: Minimum gamification level required (default 5)

        Returns:
            List of User objects, ordered alphabetically by username
        """
        from ..gamification.models import UserLevel

        opponent_ids = IndividualMatchStatisticsService._get_all_opponent_ids(user_id)

        if not opponent_ids:
            return []

        # Fetch users with level filter, ordered alphabetically
        users = (
            User.query.join(UserLevel, User.id == UserLevel.user_id)
            .filter(
                User.id.in_(list(opponent_ids)),
                User.deleted_at.is_(None),
                UserLevel.current_level >= min_level,
            )
            .order_by(User.username)
            .all()
        )

        return users
