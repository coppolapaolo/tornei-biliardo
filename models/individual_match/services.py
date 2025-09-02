"""
Module: models/individual_match/services.py
Purpose: Individual Match domain services for business logic
Requirements: SPECIFICHE.md - Individual match proposals and management
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime, timedelta

if TYPE_CHECKING:
    from ..user.models import User

from ..base import db
from .models import (
    MatchProposal,
    ProposalInvitation,
    IndividualMatch,
    IndividualRack,
    PlayerAvailability,
    ProposalType,
    ProposalStatus,
    MatchStatus,
)


class MatchProposalService:
    """Service for match proposal specific operations."""

    @staticmethod
    def create_proposal(
        proposer_id: int,
        proposal_type: ProposalType,
        location: str,
        scheduled_at: datetime,
        expires_at: datetime,
        discipline: str = "palla_8",
        distance: int = 5,
        best_of: bool = True,
        break_rule: str = "alternate",
        description: Optional[str] = None,
        entry_fee: Optional[float] = None,
        invited_user_ids: Optional[List[int]] = None,
    ) -> MatchProposal:
        """Create a match proposal with invitations if needed."""

        if proposal_type == ProposalType.DIRECT:
            return IndividualMatchService.create_direct_proposal(
                proposer_id=proposer_id,
                invited_user_ids=invited_user_ids or [],
                location=location,
                scheduled_at=scheduled_at,
                expires_at=expires_at,
                discipline=discipline,
                distance=distance,
                best_of=best_of,
                break_rule=break_rule,
                description=description,
                entry_fee=entry_fee,
            )
        else:
            return IndividualMatchService.create_open_proposal(
                proposer_id=proposer_id,
                location=location,
                scheduled_at=scheduled_at,
                expires_at=expires_at,
                discipline=discipline,
                distance=distance,
                best_of=best_of,
                break_rule=break_rule,
                description=description,
                entry_fee=entry_fee,
            )

    @staticmethod
    def get_user_proposals(user_id: int) -> Dict[str, List[MatchProposal]]:
        """Get proposals organized by user relationship."""
        return IndividualMatchService.get_user_proposals(user_id)

    @staticmethod
    def accept_proposal(proposal_id: int, user_id: int) -> IndividualMatch:
        """Accept a match proposal."""
        return IndividualMatchService.accept_proposal(user_id, proposal_id)

    @staticmethod
    def cancel_proposal(proposal_id: int, user_id: int) -> None:
        """Cancel a proposal."""
        return IndividualMatchService.cancel_proposal(user_id, proposal_id)

    @staticmethod
    def expire_proposals() -> int:
        """Mark expired proposals as expired. Returns count of expired proposals."""
        now = datetime.utcnow()

        expired_proposals = MatchProposal.query.filter(
            MatchProposal.status == ProposalStatus.PENDING,
            MatchProposal.expires_at <= now,
        ).all()

        count = 0
        for proposal in expired_proposals:
            proposal.expire()
            count += 1

        if count > 0:
            db.session.commit()

        return count


class IndividualMatchService:
    """Service for individual match management and business logic."""

    @staticmethod
    def create_direct_proposal(
        proposer_id: int,
        invited_user_ids: List[int],
        location: str,
        scheduled_at: datetime,
        expires_at: Optional[datetime] = None,
        discipline: Optional[str] = None,
        distance: Optional[int] = None,
        best_of: bool = False,
        break_rule: Optional[str] = None,
        description: Optional[str] = None,
        entry_fee: Optional[float] = None,
    ) -> MatchProposal:
        """Create a direct match proposal to specific players."""

        if expires_at is None:
            expires_at = scheduled_at - timedelta(
                hours=2
            )  # Default: expire 2 hours before match

        proposal = MatchProposal(
            proposer_id=proposer_id,
            proposal_type=ProposalType.DIRECT,
            location=location,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            discipline=discipline,
            distance=distance,
            best_of=best_of,
            break_rule=break_rule,
            description=description,
            entry_fee=entry_fee,
        )

        db.session.add(proposal)
        db.session.flush()  # Get the ID

        # Create invitations and send notifications
        from ..notification.services import NotificationService
        from ..user.models import User
        
        proposer = User.query.get(proposer_id)
        
        for user_id in invited_user_ids:
            if user_id != proposer_id:  # Don't invite yourself
                invitation = ProposalInvitation(
                    proposal_id=proposal.id, invited_user_id=user_id
                )
                db.session.add(invitation)
                
                # Send notification direttamente (come per le richieste direttore)
                from ..notification.models import NotificationType, NotificationPriority
                from flask import url_for
                
                try:
                    notification_result = NotificationService.create_notification(
                        user_id=user_id,
                        notification_type=NotificationType.MATCH_PROPOSAL,
                        title="Nuovo Invito Match",
                        message=(
                            f"{proposer.username if proposer else 'Un giocatore'} ti ha invitato "
                            f"per un match presso {location} il {scheduled_at.strftime('%d/%m/%Y alle %H:%M')}."
                        ),
                        priority=NotificationPriority.NORMAL,
                        action_url=url_for('player.match_proposals', _external=False),
                        action_text="Vedi Invito"
                    )
                    print(f"DEBUG: Notification created for user {user_id}: {notification_result}")
                except Exception as e:
                    print(f"DEBUG: Error creating notification for user {user_id}: {e}")
                    # Continue anyway - notification failure shouldn't block proposal creation

        db.session.commit()
        return proposal

    @staticmethod
    def create_open_proposal(
        proposer_id: int,
        location: str,
        scheduled_at: datetime,
        expires_at: Optional[datetime] = None,
        discipline: Optional[str] = None,
        distance: Optional[int] = None,
        best_of: bool = False,
        break_rule: Optional[str] = None,
        description: Optional[str] = None,
        entry_fee: Optional[float] = None,
    ) -> MatchProposal:
        """Create an open match proposal for all eligible players."""

        if expires_at is None:
            expires_at = scheduled_at - timedelta(hours=2)

        proposal = MatchProposal(
            proposer_id=proposer_id,
            proposal_type=ProposalType.OPEN,
            location=location,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            discipline=discipline,
            distance=distance,
            best_of=best_of,
            break_rule=break_rule,
            description=description,
            entry_fee=entry_fee,
        )

        db.session.add(proposal)
        db.session.commit()
        return proposal

    @staticmethod
    def get_user_proposals(
        user_id: int, include_expired: bool = False
    ) -> Dict[str, List[MatchProposal]]:
        """Get proposals organized by user relationship."""

        # First, expire any pending proposals that have passed their expiry time
        IndividualMatchService._expire_pending_proposals()

        query = MatchProposal.query

        if not include_expired:
            query = query.filter(
                db.and_(
                    MatchProposal.status != ProposalStatus.EXPIRED,
                    MatchProposal.expires_at > datetime.utcnow(),
                )
            )

        # Proposals created by user
        created = query.filter_by(proposer_id=user_id).all()

        # Direct invitations received
        received_invitations = (
            query.join(
                ProposalInvitation, MatchProposal.id == ProposalInvitation.proposal_id
            )
            .filter(ProposalInvitation.invited_user_id == user_id)
            .all()
        )

        # Open proposals available to user (exclude own proposals)
        available_open = query.filter(
            MatchProposal.proposal_type == ProposalType.OPEN,
            MatchProposal.proposer_id != user_id,
            MatchProposal.status == ProposalStatus.PENDING,
        ).all()

        # Filter open proposals by location availability
        user_locations = {
            av.location
            for av in PlayerAvailability.query.filter_by(
                user_id=user_id, is_available=True
            ).all()
        }

        # Also include locations where user has played before
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
            available_open = [
                p for p in available_open if p.location in eligible_locations
            ]

        return {
            "created": created,
            "received": received_invitations,
            "available": available_open,
        }

    @staticmethod
    def accept_proposal(user_id: int, proposal_id: int) -> IndividualMatch:
        """Accept a match proposal."""
        proposal = db.session.get(MatchProposal, proposal_id)
        if proposal is None:
            from flask import abort

            abort(404)

        if not proposal.can_be_accepted_by(user_id):
            raise ValueError("User cannot accept this proposal")

        individual_match = proposal.accept(user_id)
        db.session.commit()

        return individual_match

    @staticmethod
    def reject_invitation(user_id: int, proposal_id: int) -> None:
        """Reject a direct invitation."""
        invitation = ProposalInvitation.query.filter_by(
            proposal_id=proposal_id, invited_user_id=user_id
        ).first_or_404()

        invitation.reject()
        db.session.commit()

    @staticmethod
    def cancel_proposal(user_id: int, proposal_id: int) -> None:
        """Cancel a match proposal."""
        proposal = db.session.get(MatchProposal, proposal_id)
        if proposal is None:
            from flask import abort

            abort(404)

        # Verify user is the proposer
        if proposal.proposer_id != user_id:
            raise ValueError("Only the proposer can cancel the proposal")

        # Verify proposal can be cancelled
        if proposal.status != ProposalStatus.PENDING:
            raise ValueError("Proposal cannot be cancelled - it's not pending")

        proposal.cancel()
        db.session.commit()

    @staticmethod
    def get_user_dashboard_data(user_id: int) -> Dict[str, Any]:
        """Get comprehensive dashboard data for user."""
        proposals = IndividualMatchService.get_user_proposals(user_id)
        matches = IndividualMatchService.get_user_matches(user_id)
        availability = IndividualMatchService.get_user_availability(user_id)
        stats = IndividualMatchService.get_user_statistics(user_id)

        return {
            "proposals": proposals,
            "matches": matches,
            "availability": availability,
            "statistics": stats,
        }

    @staticmethod
    def get_user_availability(user_id: int) -> Dict[str, Any]:
        """Get user's availability settings and schedule."""
        availability_records = PlayerAvailability.query.filter_by(user_id=user_id).all()

        # Organize by location
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
    def submit_rack_result(
        match_id: int, user_id: int, winner_id: int, rack_number: int
    ) -> IndividualRack:
        """Submit result for a rack in individual match."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort

            abort(404)

        # Verify user is part of this match
        if user_id not in (match.player1_id, match.player2_id):
            raise ValueError("User is not part of this match")

        # Verify winner is valid
        if winner_id not in (match.player1_id, match.player2_id):
            raise ValueError("Invalid winner ID")

        # Check if rack already exists
        existing_rack = IndividualRack.query.filter_by(
            match_id=match_id, rack_number=rack_number
        ).first()

        if existing_rack:
            raise ValueError(f"Rack {rack_number} already recorded")

        # Create rack record
        rack = IndividualRack(
            match_id=match_id, rack_number=rack_number, winner_id=winner_id
        )

        db.session.add(rack)

        # Update match scores
        if winner_id == match.player1_id:
            match.player1_score += 1
        else:
            match.player2_score += 1

        # Check if match is complete
        if match.is_complete():
            match.status = MatchStatus.COMPLETED
            match.completed_at = datetime.utcnow()
            match.winner_id = (
                winner_id if match.player1_score != match.player2_score else None
            )

        db.session.commit()
        return rack

    @staticmethod
    def update_user_availability(
        user_id: int, availability_data: List[Dict[str, Any]]
    ) -> None:
        """Update user's availability settings."""
        # Clear existing availability
        PlayerAvailability.query.filter_by(user_id=user_id).delete()

        # Add new availability records
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

        db.session.commit()

    @staticmethod
    def get_admin_overview() -> Dict[str, Any]:
        """Get admin overview of all individual matches."""
        # Get counts by status
        status_counts = {}
        for status in MatchStatus:
            count = IndividualMatch.query.filter_by(status=status).count()
            status_counts[status.value] = count

        # Get recent matches
        recent_matches = (
            IndividualMatch.query.order_by(IndividualMatch.created_at.desc())
            .limit(10)
            .all()
        )

        # Get proposal counts
        proposal_counts = {}
        for status in ProposalStatus:
            count = MatchProposal.query.filter_by(status=status).count()
            proposal_counts[status.value] = count

        # Get active locations
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
            query = query.filter_by(status=status_filter)

        return query.order_by(IndividualMatch.scheduled_at.desc()).all()

    @staticmethod
    def start_match(match_id: int, user_id: int) -> IndividualMatch:
        """Start an individual match (must be one of the players)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can start the match")

        match.start_match()
        db.session.commit()

        return match

    @staticmethod
    def add_rack_result(match_id: int, winner_id: int, user_id: int) -> IndividualRack:
        """Add a rack result (must be one of the players)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can add rack results")

        rack = match.add_rack_result(winner_id)
        db.session.commit()

        return rack

    @staticmethod
    def complete_match(match_id: int, winner_id: int, user_id: int) -> IndividualMatch:
        """Complete a match (must be one of the players)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can complete the match")

        match.complete_match(winner_id)
        db.session.commit()

        return match

    @staticmethod
    def cancel_match(
        match_id: int, user_id: int, reason: Optional[str] = None
    ) -> IndividualMatch:
        """Cancel a match (must be one of the players)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can cancel the match")

        match.cancel_match(reason)
        db.session.commit()

        return match

    @staticmethod
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

        db.session.commit()
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

        # Players with explicit availability
        available_users = User.query.join(PlayerAvailability).filter(
            PlayerAvailability.location == location,
            PlayerAvailability.is_available.is_(True),
        )

        # Players who have played at this location before
        experienced_users = User.query.join(
            db.or_(
                IndividualMatch.player1_id == User.id,
                IndividualMatch.player2_id == User.id,
            )
        ).filter(IndividualMatch.location == location)

        # Combine and deduplicate
        all_users = available_users.union(experienced_users)

        if exclude_user_id:
            all_users = all_users.filter(User.id != exclude_user_id)

        return all_users.all()

    @staticmethod
    def expire_old_proposals() -> int:
        """Expire proposals that have passed their expiration time."""
        expired_proposals = MatchProposal.query.filter(
            MatchProposal.status == ProposalStatus.PENDING,
            MatchProposal.expires_at <= datetime.utcnow(),
        ).all()

        count = 0
        for proposal in expired_proposals:
            proposal.expire()
            count += 1

        db.session.commit()
        return count

    @staticmethod
    def get_user_statistics(user_id: int) -> Dict[str, Any]:
        """Get individual match statistics for a user."""
        matches = IndividualMatchService.get_user_matches(
            user_id, MatchStatus.COMPLETED
        )

        total_matches = len(matches)
        won_matches = sum(1 for m in matches if m.winner_id == user_id)
        lost_matches = total_matches - won_matches

        # Calculate rack statistics
        total_racks_won = sum(m.get_user_score(user_id) for m in matches)
        total_racks_played = sum(m.player1_score + m.player2_score for m in matches)

        # Location statistics
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
            "win_percentage": (won_matches / total_matches * 100)
            if total_matches > 0
            else 0,
            "total_racks_won": total_racks_won,
            "total_racks_played": total_racks_played,
            "rack_win_percentage": (total_racks_won / total_racks_played * 100)
            if total_racks_played > 0
            else 0,
            "locations_played": locations_played,
        }

    @staticmethod
    def _expire_pending_proposals() -> int:
        """Mark expired pending proposals as expired. Returns count of expired proposals."""
        now = datetime.utcnow()
        
        expired_proposals = MatchProposal.query.filter(
            MatchProposal.status == ProposalStatus.PENDING,
            MatchProposal.expires_at <= now,
        ).all()
        
        count = 0
        for proposal in expired_proposals:
            proposal.expire()
            count += 1
        
        if count > 0:
            db.session.commit()
        
        return count
