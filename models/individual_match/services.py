"""
Module: models/individual_match/services.py
Purpose: Facade services for backward compatibility
Sprint 13: Refactored to delegate to specialized services

This module now acts as a FACADE, delegating to:
- ProposalService: Match proposal creation and management
- MatchLifecycleService: Match state management
- IndividualRackService: Rack operations
- IndividualMatchStatisticsService: Statistics and queries
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime, timedelta, date

if TYPE_CHECKING:
    from ..user.models import User

from ..base import db
from ..transaction.manager import transactional
from .models import (
    MatchProposal,
    ProposalInvitation,
    IndividualMatch,
    IndividualRack,
    PlayerAvailability,
    ProposalType,
    ProposalStatus,
)
from ..status_enum import MatchStatus

# Import specialized services
from .proposal_service import ProposalService
from .match_lifecycle_service import MatchLifecycleService
from .individual_rack_service import IndividualRackService
from .statistics_service import IndividualMatchStatisticsService


class MatchProposalService:
    """Service for match proposal specific operations.

    Note: This is a convenience facade that delegates to IndividualMatchService.
    """

    @staticmethod
    def create_proposal(
        proposer_id: int,
        proposal_type: ProposalType,
        location: str,
        scheduled_at: datetime,
        expires_at: datetime,
        discipline: str = "palla_8",
        distance: int = 5,
        is_race_to: bool = True,
        break_rule: str = "alternate",
        description: Optional[str] = None,
        entry_fee: Optional[float] = None,
        invited_user_ids: Optional[List[int]] = None,
        billiard_hall_id: Optional[int] = None,
    ) -> MatchProposal:
        """Create a match proposal with invitations if needed."""
        if proposal_type == ProposalType.DIRECT:
            return ProposalService.create_direct_proposal(
                proposer_id=proposer_id,
                invited_user_ids=invited_user_ids or [],
                location=location,
                scheduled_at=scheduled_at,
                expires_at=expires_at,
                discipline=discipline,
                distance=distance,
                is_race_to=is_race_to,
                break_rule=break_rule,
                description=description,
                entry_fee=entry_fee,
                billiard_hall_id=billiard_hall_id,
            )
        else:
            return ProposalService.create_open_proposal(
                proposer_id=proposer_id,
                location=location,
                scheduled_at=scheduled_at,
                expires_at=expires_at,
                discipline=discipline,
                distance=distance,
                is_race_to=is_race_to,
                break_rule=break_rule,
                description=description,
                entry_fee=entry_fee,
                billiard_hall_id=billiard_hall_id,
            )

    @staticmethod
    def get_user_proposals(user_id: int) -> Dict[str, List[MatchProposal]]:
        """Get proposals organized by user relationship."""
        return ProposalService.get_user_proposals(user_id)

    @staticmethod
    def accept_proposal(proposal_id: int, user_id: int) -> IndividualMatch:
        """Accept a match proposal."""
        return ProposalService.accept_proposal(user_id, proposal_id)

    @staticmethod
    def cancel_proposal(proposal_id: int, user_id: int) -> None:
        """Cancel a proposal."""
        return ProposalService.cancel_proposal(user_id, proposal_id)

    @staticmethod
    @transactional(domain="individual_match")
    def expire_proposals() -> int:
        """Mark expired proposals as expired. Returns count of expired proposals."""
        return ProposalService.expire_old_proposals()


class IndividualMatchService:
    """Facade for individual match management - delegates to specialized services.

    This class maintains backward compatibility by delegating to:
    - ProposalService: Proposal-related methods
    - MatchLifecycleService: Match state methods
    - IndividualRackService: Rack operations
    - IndividualMatchStatisticsService: Statistics and queries
    """

    # ========== Proposal Methods (delegate to ProposalService) ==========

    @staticmethod
    @transactional(domain="individual_match")
    def create_direct_proposal(
        proposer_id: int,
        invited_user_ids: List[int],
        location: str,
        scheduled_at: datetime,
        expires_at: Optional[datetime] = None,
        discipline: Optional[str] = None,
        distance: Optional[int] = None,
        is_race_to: bool = True,
        break_rule: Optional[str] = None,
        description: Optional[str] = None,
        entry_fee: Optional[float] = None,
        billiard_hall_id: Optional[int] = None,
    ) -> MatchProposal:
        """Create a direct match proposal to specific players."""
        return ProposalService.create_direct_proposal(
            proposer_id=proposer_id,
            invited_user_ids=invited_user_ids,
            location=location,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            break_rule=break_rule,
            description=description,
            entry_fee=entry_fee,
            billiard_hall_id=billiard_hall_id,
        )

    @staticmethod
    @transactional(domain="individual_match")
    def create_open_proposal(
        proposer_id: int,
        location: str,
        scheduled_at: datetime,
        expires_at: Optional[datetime] = None,
        discipline: Optional[str] = None,
        distance: Optional[int] = None,
        is_race_to: bool = True,
        break_rule: Optional[str] = None,
        description: Optional[str] = None,
        entry_fee: Optional[float] = None,
        billiard_hall_id: Optional[int] = None,
    ) -> MatchProposal:
        """Create an open match proposal for all eligible players."""
        return ProposalService.create_open_proposal(
            proposer_id=proposer_id,
            location=location,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            break_rule=break_rule,
            description=description,
            entry_fee=entry_fee,
            billiard_hall_id=billiard_hall_id,
        )

    @staticmethod
    def create_match_proposal(
        proposer_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        proposed_date: Optional[date] = None,
        proposed_time: Optional[str] = None,
        location: Optional[str] = None,
        discipline: Optional[str] = None,
        distance: Optional[int] = None,
        is_race_to: bool = True,
        entry_fee: Optional[float] = None,
        max_participants: Optional[int] = None,
        is_open_invitation: bool = False,
        **kwargs,
    ) -> MatchProposal:
        """Create a match proposal - unified method supporting both types."""
        return ProposalService.create_match_proposal(
            proposer_id=proposer_id,
            title=title,
            description=description,
            proposed_date=proposed_date,
            proposed_time=proposed_time,
            location=location,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            entry_fee=entry_fee,
            max_participants=max_participants,
            is_open_invitation=is_open_invitation,
            **kwargs,
        )

    @staticmethod
    @transactional(domain="individual_match")
    def invite_player_to_match(
        proposal_id: int, inviter_id: int, invitee_id: int
    ) -> ProposalInvitation:
        """Create an invitation for a specific player to join a match proposal."""
        return ProposalService.invite_player_to_match(proposal_id, inviter_id, invitee_id)

    @staticmethod
    @transactional(domain="individual_match")
    def respond_to_invitation(
        invitation_id: int, invitee_id: int, response: str
    ) -> bool:
        """Respond to a match invitation."""
        return ProposalService.respond_to_invitation(invitation_id, invitee_id, response)

    @staticmethod
    def get_user_proposals(
        user_id: int, include_expired: bool = False
    ) -> Dict[str, List[MatchProposal]]:
        """Get proposals organized by user relationship."""
        return ProposalService.get_user_proposals(user_id, include_expired)

    @staticmethod
    @transactional(domain="individual_match")
    def accept_proposal(user_id: int, proposal_id: int) -> IndividualMatch:
        """Accept a match proposal."""
        return ProposalService.accept_proposal(user_id, proposal_id)

    @staticmethod
    @transactional(domain="individual_match")
    def reject_invitation(user_id: int, proposal_id: int) -> None:
        """Reject a direct invitation."""
        return ProposalService.reject_invitation(user_id, proposal_id)

    @staticmethod
    @transactional(domain="individual_match")
    def cancel_proposal(user_id: int, proposal_id: int) -> None:
        """Cancel a match proposal."""
        return ProposalService.cancel_proposal(user_id, proposal_id)

    @staticmethod
    @transactional(domain="individual_match")
    def expire_old_proposals() -> int:
        """Expire proposals that have passed their expiration time."""
        return ProposalService.expire_old_proposals()

    @staticmethod
    @transactional(domain="individual_match")
    def _expire_pending_proposals() -> int:
        """Mark expired pending proposals as expired."""
        return ProposalService._expire_pending_proposals()

    @staticmethod
    @transactional(domain="individual_match")
    def express_interest_in_open_invitation(
        proposal_id: int, interested_player_id: int, message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Express interest in an open invitation."""
        return ProposalService.express_interest_in_open_invitation(
            proposal_id, interested_player_id, message
        )

    @staticmethod
    @transactional(domain="individual_match")
    def accept_interest_for_open_invitation(
        proposal_id: int, proposer_id: int, accepted_player_id: int
    ) -> Dict[str, Any]:
        """Accept an interest expressed for an open invitation."""
        return ProposalService.accept_interest_for_open_invitation(
            proposal_id, proposer_id, accepted_player_id
        )

    @staticmethod
    @transactional(domain="individual_match")
    def create_individual_match_from_accepted_invitation(
        invitation_id: int,
    ) -> IndividualMatch:
        """Create individual match from an accepted invitation."""
        return ProposalService.create_individual_match_from_accepted_invitation(
            invitation_id
        )

    # ========== Match Lifecycle Methods (delegate to MatchLifecycleService) ==========

    @staticmethod
    @transactional(domain="individual_match")
    def start_match(match_id: int, user_id: int) -> IndividualMatch:
        """Start an individual match (must be one of the players)."""
        return MatchLifecycleService.start_match(match_id, user_id)

    @staticmethod
    @transactional(domain="individual_match")
    def confirm_match_result(match_id: int, user_id: int) -> IndividualMatch:
        """Confirm match result by a player (new UX)."""
        return MatchLifecycleService.confirm_match_result(match_id, user_id)

    @staticmethod
    @transactional(domain="individual_match")
    def reject_match_result(match_id: int, user_id: int) -> IndividualMatch:
        """Reject match result - removes last rack (new UX)."""
        return MatchLifecycleService.reject_match_result(match_id, user_id)

    @staticmethod
    @transactional(domain="individual_match")
    def complete_match(match_id: int, winner_id: int, user_id: int) -> IndividualMatch:
        """Complete a match - legacy method for backward compatibility."""
        return MatchLifecycleService.complete_match(match_id, winner_id, user_id)

    @staticmethod
    @transactional(domain="individual_match")
    def complete_individual_match(
        match_id: int, winner_id: int, user_id: int
    ) -> IndividualMatch:
        """Complete an individual match - alias for complete_match."""
        return MatchLifecycleService.complete_individual_match(match_id, winner_id, user_id)

    @staticmethod
    @transactional(domain="individual_match")
    def cancel_match(
        match_id: int, user_id: int, reason: Optional[str] = None
    ) -> IndividualMatch:
        """Cancel a match (must be one of the players)."""
        return MatchLifecycleService.cancel_match(match_id, user_id, reason)

    @staticmethod
    @transactional(domain="individual_match")
    def report_result(
        match_id: int,
        reporter_id: int,
        winner_id: int,
        player1_racks: int,
        player2_racks: int,
    ) -> None:
        """Report final match result."""
        return MatchLifecycleService.report_result(
            match_id, reporter_id, winner_id, player1_racks, player2_racks
        )

    # ========== Rack Methods (delegate to IndividualRackService) ==========

    @staticmethod
    @transactional(domain="individual_match")
    def add_rack_for_player(
        match_id: int,
        user_id: int,
        winner_id: int,
    ) -> IndividualRack:
        """Add a rack won by specified player (new simplified UX)."""
        return IndividualRackService.add_rack_for_player(match_id, user_id, winner_id)

    @staticmethod
    @transactional(domain="individual_match")
    def remove_rack_for_player(
        match_id: int,
        user_id: int,
        player_id: int,
    ) -> None:
        """Remove last rack won by specified player (new simplified UX)."""
        return IndividualRackService.remove_rack_for_player(match_id, user_id, player_id)

    @staticmethod
    @transactional(domain="individual_match")
    def submit_rack_result(
        match_id: int,
        user_id: int,
        winner_id: int,
        rack_number: int,
        notes: Optional[str] = None,
    ) -> IndividualRack:
        """Submit result for a rack - legacy method for backward compatibility."""
        return IndividualRackService.submit_rack_result(
            match_id, user_id, winner_id, rack_number, notes
        )

    @staticmethod
    @transactional(domain="individual_match")
    def add_rack_result(
        match_id: int,
        rack_number: Optional[int] = None,
        winner_id: Optional[int] = None,
        reported_by_id: Optional[int] = None,
        break_player_id: Optional[int] = None,
        notes: Optional[str] = None,
        **kwargs,
    ) -> IndividualRack:
        """Add a rack result with flexible parameters for test compatibility."""
        return IndividualRackService.add_rack_result(
            match_id=match_id,
            rack_number=rack_number,
            winner_id=winner_id,
            reported_by_id=reported_by_id,
            break_player_id=break_player_id,
            notes=notes,
            **kwargs,
        )

    @staticmethod
    @transactional(domain="individual_match")
    def _add_rack_result_original(
        match_id: int, winner_id: int, user_id: int
    ) -> IndividualRack:
        """Original add_rack_result implementation."""
        return IndividualRackService._add_rack_result_original(match_id, winner_id, user_id)

    @staticmethod
    @transactional(domain="individual_match")
    def confirm_rack_result(rack_id: int, confirming_player_id: int) -> Dict[str, Any]:
        """Confirm a rack result."""
        return IndividualRackService.confirm_rack_result(rack_id, confirming_player_id)

    @staticmethod
    @transactional(domain="individual_match")
    def dispute_rack_result(
        rack_id: int, disputing_player_id: int, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Dispute a rack result."""
        return IndividualRackService.dispute_rack_result(rack_id, disputing_player_id, reason)

    @staticmethod
    @transactional(domain="individual_match")
    def resolve_rack_dispute(
        rack_id: int, admin_user_id: int, resolution: str, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve a rack result dispute."""
        return IndividualRackService.resolve_rack_dispute(
            rack_id, admin_user_id, resolution, reason
        )

    # ========== Statistics Methods (delegate to IndividualMatchStatisticsService) ==========

    @staticmethod
    def get_user_dashboard_data(user_id: int) -> Dict[str, Any]:
        """Get comprehensive dashboard data for user."""
        return IndividualMatchStatisticsService.get_user_dashboard_data(user_id)

    @staticmethod
    def get_user_availability(user_id: int) -> Dict[str, Any]:
        """Get user's availability settings and schedule."""
        return IndividualMatchStatisticsService.get_user_availability(user_id)

    @staticmethod
    def get_admin_overview() -> Dict[str, Any]:
        """Get admin overview of all individual matches."""
        return IndividualMatchStatisticsService.get_admin_overview()

    @staticmethod
    def get_user_matches(
        user_id: int, status_filter: Optional[MatchStatus] = None
    ) -> List[IndividualMatch]:
        """Get individual matches for a user."""
        return IndividualMatchStatisticsService.get_user_matches(user_id, status_filter)

    @staticmethod
    def get_user_statistics(user_id: int) -> Dict[str, Any]:
        """Get individual match statistics for a user."""
        return IndividualMatchStatisticsService.get_user_statistics(user_id)

    # ========== Availability Methods (kept here for now - could be extracted later) ==========

    @staticmethod
    @transactional(domain="individual_match")
    def update_user_availability(
        user_id: int, availability_data: List[Dict[str, Any]]
    ) -> None:
        """Update user's availability settings."""
        PlayerAvailability.query.filter_by(user_id=user_id).delete()

        for data in availability_data:
            availability = PlayerAvailability(
                user_id=user_id,
                location=data["location"],
                day_of_week=data["day_of_week"],
                start_time=data["start_time"],
                end_time=data["end_time"],
                is_available=data.get("is_available", True),
            )
            db.session.add(availability)

    @staticmethod
    @transactional(domain="individual_match")
    def set_player_availability(
        user_id: int,
        location: str,
        is_available: bool = True,
        preferred_days: Optional[str] = None,
        preferred_times: Optional[str] = None,
    ) -> PlayerAvailability:
        """Set player availability for a location."""
        availability = PlayerAvailability.query.filter_by(
            user_id=user_id, location=location
        ).first()

        if availability:
            availability.is_available = is_available
            availability.preferred_days = preferred_days
            availability.preferred_times = preferred_times
        else:
            availability = PlayerAvailability(
                user_id=user_id,
                location=location,
                is_available=is_available,
                preferred_days=preferred_days,
                preferred_times=preferred_times,
            )
            db.session.add(availability)

        return availability

    @staticmethod
    def get_player_availability(user_id: int) -> List[PlayerAvailability]:
        """Get all availability settings for a player."""
        return PlayerAvailability.query.filter_by(user_id=user_id).all()

    @staticmethod
    def get_eligible_players_for_location(
        location: str, exclude_user_id: Optional[int] = None
    ) -> List[User]:
        """Get players available for matches at a specific location."""
        from ..user.models import User

        available_users = User.query.join(PlayerAvailability).filter(
            PlayerAvailability.location == location,
            PlayerAvailability.is_available.is_(True),
        )

        experienced_users = User.query.join(
            db.or_(
                IndividualMatch.player1_id == User.id,
                IndividualMatch.player2_id == User.id,
            )
        ).filter(IndividualMatch.location == location)

        all_users = available_users.union(experienced_users)

        if exclude_user_id:
            all_users = all_users.filter(User.id != exclude_user_id)

        return all_users.all()
