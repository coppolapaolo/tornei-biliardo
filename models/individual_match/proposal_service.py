"""
Module: models/individual_match/proposal_service.py
Purpose: Match proposal management service (extracted from IndividualMatchService)
Sprint 13: IndividualMatchService decomposition
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, date, time as time_obj

from sqlalchemy import func
from ..base import db
from ..transaction.manager import transactional
from .models import (
    MatchProposal,
    ProposalInvitation,
    IndividualMatch,
    PlayerAvailability,
    ProposalType,
    ProposalStatus,
    InvitationStatus,
)


class ProposalService:
    """Service for match proposal creation and management."""

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
        is_multi_set: bool = False,
        match_distance: Optional[int] = None,
    ) -> MatchProposal:
        """Create a direct match proposal to specific players.

        Args:
            distance: Racks per set (or None for free format)
            is_multi_set: Whether match is multi-set
            match_distance: Number of sets to win (only for multi-set)
        """

        if expires_at is None:
            expires_at = scheduled_at - timedelta(hours=2)

        proposal = MatchProposal(
            proposer_id=proposer_id,
            proposal_type=ProposalType.DIRECT,
            billiard_hall_id=billiard_hall_id,
            location=location,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            break_rule=break_rule,
            description=description,
            entry_fee=entry_fee,
            is_multi_set=is_multi_set,
            match_distance=match_distance,
        )

        db.session.add(proposal)
        db.session.flush()

        from ..user.models import User
        from ..notification.factory import NotificationFactory

        proposer = User.query.get(proposer_id)

        for user_id in invited_user_ids:
            if user_id != proposer_id:
                invitation = ProposalInvitation(
                    proposal_id=proposal.id, invited_user_id=user_id
                )
                db.session.add(invitation)

                try:
                    proposer_name = proposer.username if proposer else "Un giocatore"
                    scheduled_time_str = (
                        scheduled_at.strftime("%d/%m/%Y alle %H:%M")
                        if scheduled_at
                        else None
                    )

                    NotificationFactory.create_match_notification(
                        user_id=user_id,
                        match_type="proposal",
                        player_names=[proposer_name],
                        location_name=location,
                        scheduled_time=scheduled_time_str,
                        proposal_id=proposal.id,
                    )
                except Exception:
                    pass  # Notification failure shouldn't block proposal creation

        return proposal

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
        is_multi_set: bool = False,
        match_distance: Optional[int] = None,
    ) -> MatchProposal:
        """Create an open match proposal for all eligible players.

        Args:
            distance: Racks per set (or None for free format)
            is_multi_set: Whether match is multi-set
            match_distance: Number of sets to win (only for multi-set)
        """
        from flask_babel import _
        from ..user.models import User
        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationType, NotificationPriority
        from .availability_service import AvailabilityService

        if expires_at is None:
            expires_at = scheduled_at - timedelta(hours=2)

        proposal = MatchProposal(
            proposer_id=proposer_id,
            proposal_type=ProposalType.OPEN,
            billiard_hall_id=billiard_hall_id,
            location=location,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            break_rule=break_rule,
            description=description,
            entry_fee=entry_fee,
            is_multi_set=is_multi_set,
            match_distance=match_distance,
        )

        db.session.add(proposal)
        db.session.flush()  # Get proposal.id for action_url

        # Notify eligible players about the open proposal
        try:
            proposer = db.session.get(User, proposer_id)
            proposer_name = proposer.username if proposer else _("Un giocatore")
            location_text = location or ""

            # Find eligible players based on venue or location
            eligible_user_ids: List[int] = []

            if billiard_hall_id:
                # Venue-based: find players available at this venue
                venue_players = AvailabilityService.get_available_players_at_venue(
                    billiard_hall_id=billiard_hall_id,
                    exclude_user_id=proposer_id
                )
                eligible_user_ids = [p["user_id"] for p in venue_players]
            elif location:
                # Location-based: find players available at this location string
                location_players = AvailabilityService.get_available_players_at_location(
                    location=location,
                    exclude_user_id=proposer_id
                )
                eligible_user_ids = [p["user_id"] for p in location_players]

            if eligible_user_ids:
                scheduled_str = scheduled_at.strftime("%d/%m/%Y alle %H:%M")
                NotificationFactory.create_bulk_notification(
                    user_ids=eligible_user_ids,
                    notification_type=NotificationType.MATCH_PROPOSAL,
                    title=_("Nuova proposta di match"),
                    message=_("%(username)s propone un match aperto%(location)s il %(date)s",
                              username=proposer_name,
                              location=f" a {location_text}" if location_text else "",
                              date=scheduled_str),
                    priority=NotificationPriority.NORMAL,
                    action_url=f"/match/proposals/{proposal.id}",
                    action_text=_("Visualizza"),
                    continue_on_error=True,
                )
        except Exception:
            pass  # Notification failure shouldn't block proposal creation

        return proposal

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

        if proposed_date and proposed_time:
            if isinstance(proposed_time, str):
                hour, minute = map(int, proposed_time.split(":"))
                proposed_time_obj = time_obj(hour, minute)
            else:
                proposed_time_obj = proposed_time
            scheduled_at = datetime.combine(proposed_date, proposed_time_obj)
        else:
            scheduled_at = kwargs.get("scheduled_at", datetime.now())

        if not location:
            location = "TBD"

        return ProposalService.create_open_proposal(
            proposer_id=proposer_id,
            location=location,
            scheduled_at=scheduled_at,
            discipline=discipline,
            distance=distance,
            is_race_to=is_race_to,
            description=description,
            entry_fee=entry_fee,
        )

    @staticmethod
    @transactional(domain="individual_match")
    def invite_player_to_match(
        proposal_id: int, inviter_id: int, invitee_id: int
    ) -> ProposalInvitation:
        """Create an invitation for a specific player to join a match proposal."""

        invitation = ProposalInvitation(
            proposal_id=proposal_id,
            invited_user_id=invitee_id,
            status=InvitationStatus.PENDING,
        )

        db.session.add(invitation)
        return invitation

    @staticmethod
    @transactional(domain="individual_match")
    def respond_to_invitation(
        invitation_id: int, invitee_id: int, response: str
    ) -> bool:
        """Respond to a match invitation."""

        invitation = ProposalInvitation.query.get(invitation_id)
        if not invitation or invitation.invited_user_id != invitee_id:
            return False

        if response.lower() == "accepted":
            invitation.status = InvitationStatus.ACCEPTED
            ProposalService.accept_proposal(
                user_id=invitee_id, proposal_id=invitation.proposal_id
            )
        else:
            invitation.status = InvitationStatus.REJECTED

        return True

    @staticmethod
    def get_user_proposals(
        user_id: int, include_expired: bool = True
    ) -> Dict[str, List[MatchProposal]]:
        """Get proposals organized by user relationship.

        Args:
            user_id: The user to get proposals for
            include_expired: Whether to include expired proposals in sent/received
                           (default True to show full history)

        Returns:
            Dict with keys matching template expectations:
            - sent_proposals: Proposals created by this user
            - received_proposals: Direct invitations to this user
            - open_proposals: Open proposals from others (only PENDING, not expired)
        """
        ProposalService._expire_pending_proposals()

        # For sent and received: show all proposals (including expired) for history
        # User wants to see their full proposal history
        if include_expired:
            sent_proposals = (
                MatchProposal.query.filter_by(proposer_id=user_id)
                .order_by(MatchProposal.created_at.desc())
                .all()
            )

            received_proposals = (
                MatchProposal.query.join(
                    ProposalInvitation,
                    MatchProposal.id == ProposalInvitation.proposal_id,
                )
                .filter(ProposalInvitation.invited_user_id == user_id)
                .order_by(MatchProposal.created_at.desc())
                .all()
            )
        else:
            # Filter to only active proposals
            active_filter = db.or_(
                db.and_(
                    MatchProposal.status == ProposalStatus.PENDING,
                    MatchProposal.expires_at > datetime.utcnow(),
                ),
                MatchProposal.status == ProposalStatus.ACCEPTED,
                MatchProposal.status == ProposalStatus.CANCELLED,
            )

            sent_proposals = (
                MatchProposal.query.filter_by(proposer_id=user_id)
                .filter(active_filter)
                .order_by(MatchProposal.created_at.desc())
                .all()
            )

            received_proposals = (
                MatchProposal.query.join(
                    ProposalInvitation,
                    MatchProposal.id == ProposalInvitation.proposal_id,
                )
                .filter(ProposalInvitation.invited_user_id == user_id)
                .filter(active_filter)
                .order_by(MatchProposal.created_at.desc())
                .all()
            )

        # For open proposals: always show only PENDING and not expired
        # (users can't accept expired proposals)
        open_proposals = (
            MatchProposal.query.filter(
                MatchProposal.proposal_type == ProposalType.OPEN,
                MatchProposal.proposer_id != user_id,
                MatchProposal.status == ProposalStatus.PENDING,
                MatchProposal.expires_at > datetime.utcnow(),
            )
            .order_by(MatchProposal.created_at.desc())
            .all()
        )

        # Filter open proposals by user's eligible locations
        user_locations = {
            av.location
            for av in PlayerAvailability.query.filter_by(
                user_id=user_id, is_available=True
            ).all()
        }

        played_locations = {
            match.location
            for match in IndividualMatch.query.filter(
                db.or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                )
            ).all()
        }

        eligible_locations = user_locations.union(played_locations)

        if eligible_locations:
            open_proposals = [
                p for p in open_proposals if p.location in eligible_locations
            ]

        return {
            "sent_proposals": sent_proposals,
            "received_proposals": received_proposals,
            "open_proposals": open_proposals,
        }

    @staticmethod
    @transactional(domain="individual_match")
    def accept_proposal(user_id: int, proposal_id: int) -> IndividualMatch:
        """Accept a match proposal."""
        from flask_babel import _
        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationType, NotificationPriority
        from ..user.models import User

        proposal = db.session.get(MatchProposal, proposal_id)
        if proposal is None:
            from flask import abort
            abort(404)

        if not proposal.can_be_accepted_by(user_id):
            raise ValueError("User cannot accept this proposal")

        individual_match = proposal.accept(user_id)

        # Notify proposer that their proposal was accepted
        try:
            accepter = db.session.get(User, user_id)
            accepter_name = accepter.username if accepter else _("Un giocatore")
            location_text = proposal.location_display or ""

            NotificationFactory.create_bulk_notification(
                user_ids=[proposal.proposer_id],
                notification_type=NotificationType.MATCH_ACCEPTED,
                title=_("Proposta accettata!"),
                message=_("%(player)s ha accettato la tua proposta di match%(location)s",
                          player=accepter_name,
                          location=f" a {location_text}" if location_text else ""),
                priority=NotificationPriority.HIGH,
                action_url=f"/match/matches/{individual_match.id}",
                action_text=_("Vai al match"),
            )
        except Exception:
            pass  # Notification failure shouldn't block acceptance

        return individual_match

    @staticmethod
    @transactional(domain="individual_match")
    def reject_invitation(user_id: int, proposal_id: int) -> None:
        """Reject a direct invitation."""
        invitation = ProposalInvitation.query.filter_by(
            proposal_id=proposal_id, invited_user_id=user_id
        ).first_or_404()

        invitation.reject()

    @staticmethod
    @transactional(domain="individual_match")
    def cancel_proposal(user_id: int, proposal_id: int) -> None:
        """Cancel a match proposal."""
        proposal = db.session.get(MatchProposal, proposal_id)
        if proposal is None:
            from flask import abort
            abort(404)

        if proposal.proposer_id != user_id:
            raise ValueError("Only the proposer can cancel the proposal")

        if proposal.status != ProposalStatus.PENDING:
            raise ValueError("Proposal cannot be cancelled - it's not pending")

        proposal.cancel()

    @staticmethod
    @transactional(domain="individual_match")
    def expire_old_proposals() -> int:
        """Expire proposals that have passed their expiration time."""
        from flask_babel import _
        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationType, NotificationPriority

        expired_proposals = MatchProposal.query.filter(
            MatchProposal.status == ProposalStatus.PENDING,
            MatchProposal.expires_at <= datetime.utcnow(),
        ).all()

        count = 0
        for proposal in expired_proposals:
            proposal.expire()
            count += 1

            # Notify proposer that their proposal expired
            try:
                location_text = proposal.location or ""
                NotificationFactory.create_bulk_notification(
                    user_ids=[proposal.proposer_id],
                    notification_type=NotificationType.MATCH_DECLINED,
                    title=_("Proposta scaduta"),
                    message=_("La tua proposta di match%(location)s è scaduta senza accettazioni.",
                              location=f" a {location_text}" if location_text else ""),
                    priority=NotificationPriority.NORMAL,
                    action_url=f"/match/proposals/{proposal.id}",
                    action_text=_("Visualizza"),
                    continue_on_error=True,
                )
            except Exception:
                pass  # Notification failure shouldn't block expiration

        return count

    @staticmethod
    @transactional(domain="individual_match")
    def _expire_pending_proposals() -> int:
        """Mark expired pending proposals as expired."""
        from flask_babel import _
        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationType, NotificationPriority

        now = datetime.utcnow()

        expired_proposals = MatchProposal.query.filter(
            MatchProposal.status == ProposalStatus.PENDING,
            MatchProposal.expires_at <= now,
        ).all()

        count = 0
        for proposal in expired_proposals:
            proposal.expire()
            count += 1

            # Notify proposer that their proposal expired
            try:
                location_text = proposal.location or ""
                NotificationFactory.create_bulk_notification(
                    user_ids=[proposal.proposer_id],
                    notification_type=NotificationType.MATCH_DECLINED,
                    title=_("Proposta scaduta"),
                    message=_("La tua proposta di match%(location)s è scaduta senza accettazioni.",
                              location=f" a {location_text}" if location_text else ""),
                    priority=NotificationPriority.NORMAL,
                    action_url=f"/match/proposals/{proposal.id}",
                    action_text=_("Visualizza"),
                    continue_on_error=True,
                )
            except Exception:
                pass  # Notification failure shouldn't block expiration

        return count

    @staticmethod
    @transactional(domain="individual_match")
    def express_interest_in_open_invitation(
        proposal_id: int, interested_player_id: int, message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Express interest in an open invitation."""
        proposal = db.session.get(MatchProposal, proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        if proposal.proposal_type != ProposalType.OPEN:
            raise ValueError("Can only express interest in open proposals")

        existing = ProposalInvitation.query.filter_by(
            proposal_id=proposal_id, invited_user_id=interested_player_id
        ).first()
        if existing:
            raise ValueError("Interest already expressed")

        invitation = ProposalInvitation(
            proposal_id=proposal_id, invited_user_id=interested_player_id
        )
        db.session.add(invitation)

        return {
            "success": True,
            "invitation_id": invitation.id,
            "message": "Interest expressed successfully",
        }

    @staticmethod
    @transactional(domain="individual_match")
    def accept_interest_for_open_invitation(
        proposal_id: int, proposer_id: int, accepted_player_id: int
    ) -> Dict[str, Any]:
        """Accept an interest expressed for an open invitation."""
        proposal = db.session.get(MatchProposal, proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        if proposal.proposer_id != proposer_id:
            raise ValueError("Only the proposer can accept interests")

        invitation = ProposalInvitation.query.filter_by(
            proposal_id=proposal_id, invited_user_id=accepted_player_id
        ).first()
        if not invitation:
            raise ValueError("No interest found for selected user")

        match = ProposalService.accept_proposal(accepted_player_id, proposal_id)

        other_invitations = (
            ProposalInvitation.query.filter_by(proposal_id=proposal_id)
            .filter(ProposalInvitation.invited_user_id != accepted_player_id)
            .all()
        )

        if other_invitations:
            from ..notification.factory import NotificationFactory
            from ..notification.models import NotificationPriority, NotificationType

            proposal_title = getattr(proposal, "title", "Open match proposal")
            invited_user_ids = [inv.invited_user_id for inv in other_invitations]

            try:
                NotificationFactory.create_bulk_notification(
                    user_ids=invited_user_ids,
                    notification_type=NotificationType.MATCH_DECLINED,
                    title="Proposta Match Conclusa",
                    message=f"La proposta di match '{proposal_title}' è stata accettata da un altro giocatore.",
                    priority=NotificationPriority.NORMAL,
                    continue_on_error=True,
                )
            except Exception:
                pass

        return {
            "success": True,
            "match_id": match.id,
            "message": "Interest accepted successfully",
        }

    @staticmethod
    @transactional(domain="individual_match")
    def create_individual_match_from_accepted_invitation(
        invitation_id: int,
    ) -> IndividualMatch:
        """Create individual match from an accepted invitation."""
        invitation = db.session.get(ProposalInvitation, invitation_id)
        if not invitation:
            raise ValueError(f"Invitation {invitation_id} not found")

        return ProposalService.accept_proposal(
            invitation.invited_user_id, invitation.proposal_id
        )
