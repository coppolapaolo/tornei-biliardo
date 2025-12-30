"""
Module: models/individual_match/statistics_service.py
Purpose: Statistics and query service for individual matches (extracted from IndividualMatchService)
Sprint 13: IndividualMatchService decomposition
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any

from sqlalchemy import func
from ..base import db
from .models import (
    MatchProposal,
    IndividualMatch,
    PlayerAvailability,
    ProposalStatus,
)
from ..status_enum import MatchStatus


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
            target_status = (
                status_filter.value if hasattr(status_filter, "value") else status_filter
            )
            query = query.filter(IndividualMatch.status == target_status)

        return query.order_by(IndividualMatch.scheduled_at.desc()).all()

    @staticmethod
    def get_user_statistics(user_id: int) -> Dict[str, Any]:
        """Get individual match statistics for a user."""
        matches = IndividualMatchStatisticsService.get_user_matches(
            user_id, MatchStatus.COMPLETED
        )

        total_matches = len(matches)
        won_matches = sum(1 for m in matches if m.winner_id == user_id)
        lost_matches = total_matches - won_matches

        total_racks_won = sum(m.get_user_score(user_id) for m in matches)
        total_racks_played = sum(m.player1_score + m.player2_score for m in matches)

        locations_played = {}
        for match in matches:
            loc = match.location
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
        completed_matches = [m for m in all_matches if m.status == MatchStatus.COMPLETED]
        recent_matches = completed_matches[:5]

        return {
            "proposals": proposals,
            "matches": all_matches,
            "active_matches": active_matches,
            "recent_matches": recent_matches,
            "availability": availability,
            "statistics": stats,
        }
