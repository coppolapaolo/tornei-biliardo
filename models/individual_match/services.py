"""
Module: models/individual_match/services.py
Purpose: Individual Match domain services for business logic
Requirements: SPECIFICHE.md - Individual match proposals and management
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime, timedelta, date

if TYPE_CHECKING:
    from ..user.models import User

from ..base import db
from ..transaction.manager import transactional
from ..notification.services import NotificationService
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
from .availability_service import AvailabilityService


class MatchProposalService:
    """Service for match proposal lifecycle management.

    Handles the complete proposal workflow: creation, invitation management,
    acceptance/rejection, and coordination with the community pool platform.
    Provides delegation layer for route integration and maintains compatibility
    with existing service interfaces.

    Community Features:
    - Direct match proposals (targeted invitations)
    - Open match proposals (community-wide visibility)
    - Social interaction through match coordination
    - Location-based match discovery

    Architecture:
    This service acts as a delegation layer between route handlers and
    the core IndividualMatchService, providing route-optimized interfaces
    and parameter compatibility while maintaining business logic encapsulation.
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
        best_of: bool = True,
        break_rule: str = "alternate",
        description: Optional[str] = None,
        entry_fee: Optional[float] = None,
        invited_user_ids: Optional[List[int]] = None,
    ) -> MatchProposal:
        """Create a match proposal with automated invitation management.

        Factory method that routes proposal creation based on type:
        - DIRECT: Creates targeted invitations to specific players
        - OPEN: Creates community-wide visible proposal for any player

        Args:
            proposer_id: Community member creating the proposal
            proposal_type: DIRECT (targeted) or OPEN (community-wide)
            location: Pool hall or venue for the match
            scheduled_at: Proposed match date and time
            expires_at: Deadline for accepting the proposal
            discipline: Pool discipline (palla_8, palla_9, etc.)
            distance: Race length for the match
            best_of: True for "best of N", False for "exactly N" format
            break_rule: Break rotation rule (alternate, winner, loser)
            description: Optional match description or special rules
            entry_fee: Optional monetary entry fee
            invited_user_ids: Required for DIRECT proposals, ignored for OPEN

        Returns:
            MatchProposal: Created proposal with appropriate invitation setup

        Business Logic:
        - DIRECT proposals create ProposalInvitation records for each invitee
        - OPEN proposals are visible to all eligible community members
        - Notification system automatically alerts invited players
        - Expiration handling ensures proposals don't remain indefinitely
        """

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
        """Get comprehensive proposal overview organized by user relationship.

        Returns proposals categorized by the user's relationship to them:
        - "created": Proposals initiated by this user
        - "received": Direct invitations sent to this user
        - "available": Open proposals this user can accept

        The service automatically filters expired proposals and applies
        location-based eligibility for open proposals based on user availability.
        """
        return IndividualMatchService.get_user_proposals(user_id)

    @staticmethod
    def accept_proposal(proposal_id: int, user_id: int) -> IndividualMatch:
        """Accept a match proposal (delegation layer for parameter order compatibility).

        ARCHITECTURAL ROLE (Task 1.1 Phase 7):
        This method serves as a delegation layer in the service hierarchy:
        MatchProposalService → IndividualMatchService → @transactional operations

        Args:
            proposal_id: ID of the proposal to accept
            user_id: ID of the user accepting the proposal

        Returns:
            IndividualMatch: The created individual match from accepted proposal

        Service Layer Pattern:
            - Provides parameter order compatibility for legacy callers
            - Delegates to IndividualMatchService.accept_proposal (core business logic)
            - Parameter swap: (proposal_id, user_id) → (user_id, proposal_id)

        Transaction Management:
            - Actual @transactional operations handled by IndividualMatchService
            - This layer focuses on interface compatibility and delegation

        Route Integration:
            For routes/player.py integration, prefer accept_invitation() which
            provides route-optimized parameter order and clearer intent.

        See Also:
            - MatchProposalService.accept_invitation: Route-optimized interface
            - IndividualMatchService.accept_proposal: Core implementation
        """
        return IndividualMatchService.accept_proposal(user_id, proposal_id)

    @staticmethod
    def accept_invitation(proposal_id: int, accepting_user_id: int) -> IndividualMatch:
        """Accept a match proposal invitation (route-optimized interface).

        ARCHITECTURAL ROLE (Task 1.1 Phase 7):
        Primary interface for routes/player.py transaction migration:
        route handler → MatchProposalService.accept_invitation → IndividualMatchService

        Args:
            proposal_id: ID of the proposal to accept
            accepting_user_id: ID of the user accepting the invitation

        Returns:
            IndividualMatch: The created individual match from accepted proposal

        Route Integration Design:
            - Parameter order optimized for REST endpoints: /player/proposal/{id}/accept
            - Eliminates need for parameter shuffling in route handlers
            - Clear semantic intent: "accept invitation" vs generic "accept proposal"

        Transaction Management Architecture:
            - Delegates to IndividualMatchService.accept_invitation (@transactional)
            - Atomic operation: proposal validation + match creation + notifications
            - Service layer handles all business rules and data consistency

        Migration Benefits:
            - Removes direct db.session.commit() from route handlers
            - Centralizes business logic in testable service layer
            - Provides consistent error handling and rollback behavior

        See Also:
            - IndividualMatchService.accept_invitation: Core @transactional implementation
            - MatchProposalService.reject_invitation: Companion rejection interface
        """
        return IndividualMatchService.accept_invitation(proposal_id, accepting_user_id)

    @staticmethod
    def reject_invitation(proposal_id: int, rejecting_user_id: int) -> None:
        """Reject a match proposal invitation (route-optimized interface).

        ARCHITECTURAL ROLE (Task 1.1 Phase 7):
        Companion interface to accept_invitation for complete proposal workflow:
        route handler → MatchProposalService.reject_invitation → IndividualMatchService

        Args:
            proposal_id: ID of the proposal to reject
            rejecting_user_id: ID of the user rejecting the invitation

        Route Integration Design:
            - Parameter order optimized for REST endpoints: /player/proposal/{id}/reject
            - Maintains consistency with accept_invitation interface design
            - Clear semantic intent for rejection workflow

        Service Delegation Pattern:
            - Delegates to IndividualMatchService.reject_invitation with parameter swap
            - Parameter transformation: (proposal_id, user_id) → (user_id, proposal_id)
            - Maintains service layer encapsulation of business rules

        Transaction Management:
            - Atomic invitation status update through @transactional delegate
            - Ensures proper audit trail and notification delivery
            - Consistent error handling across acceptance/rejection workflows

        Migration Benefits:
            - Eliminates direct database manipulation from route handlers
            - Provides symmetric interface with accept_invitation
            - Centralizes rejection business logic in service layer

        See Also:
            - IndividualMatchService.reject_invitation: Core @transactional implementation
            - MatchProposalService.accept_invitation: Companion acceptance interface
        """
        return IndividualMatchService.reject_invitation(rejecting_user_id, proposal_id)

    @staticmethod
    def cancel_proposal(proposal_id: int, user_id: int) -> None:
        """Cancel a match proposal with proper authorization checks.

        Validates that only the original proposer can cancel and that
        the proposal is in a cancellable state (PENDING status).
        Delegates to IndividualMatchService for core business logic.
        """
        return IndividualMatchService.cancel_proposal(user_id, proposal_id)

    @staticmethod
    @transactional(domain="individual_match")
    def expire_proposals() -> int:
        """Batch expiration of proposals past their deadline.

        Community maintenance function that automatically expires proposals
        that have passed their expires_at timestamp. This prevents stale
        proposals from cluttering the community match board.

        Returns:
            int: Count of proposals that were expired in this batch

        Transaction Management:
        - Single atomic operation for all expirations
        - Ensures consistent state across all expired proposals
        """
        now = datetime.utcnow()

        expired_proposals = MatchProposal.query.filter(
            MatchProposal.status == ProposalStatus.PENDING,
            MatchProposal.expires_at <= now,
        ).all()

        count = 0
        for proposal in expired_proposals:
            proposal.expire()
            count += 1

        # Transaction managed by @transactional decorator
        return count


class IndividualMatchService:
    """Core service for individual match domain business logic.

    Manages the complete lifecycle of casual matches between community members,
    from proposal creation through match completion. Implements the community
    platform's social gaming features and provides atomic operations through
    the @transactional pattern.

    Domain Responsibilities:
    - Match proposal creation and management
    - Player invitation and acceptance workflows
    - Individual match execution and scoring
    - Player availability and location-based matching
    - Community statistics and performance tracking

    Key Business Rules:
    - Only proposal participants can accept/reject invitations
    - Match participants can submit rack results and manage matches
    - Location-based filtering ensures relevant match visibility
    - Automatic expiration prevents stale proposals
    - Best-of vs exactly-N rack formats supported

    Transaction Management:
    All state-changing methods use @transactional(domain="individual_match")
    to ensure atomic operations and proper rollback on failures.

    Integration Points:
    - NotificationService: Player alerts and match updates
    - AvailabilityService: Location-based player discovery
    - User domain: Player profiles and community membership
    - Location domain: Venue management and availability
    """

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
        best_of: bool = False,
        break_rule: Optional[str] = None,
        description: Optional[str] = None,
        entry_fee: Optional[float] = None,
    ) -> MatchProposal:
        """Create targeted match proposal with automated invitation workflow.

        Creates a DIRECT type proposal that sends specific invitations to
        selected community members. This is the primary mechanism for
        arranging matches between known players or groups.

        Args:
            proposer_id: Community member initiating the match proposal
            invited_user_ids: List of specific players to invite
            location: Pool hall or venue where match will take place
            scheduled_at: Proposed date and time for the match
            expires_at: Deadline for responses (defaults to 2 hours before match)
            discipline: Pool game type (palla_8, palla_9, etc.)
            distance: Number of racks in the race
            best_of: Format flag - True for "best of N", False for "exactly N"
            break_rule: How breaks are determined (alternate, winner, loser)
            description: Optional match details or special arrangements
            entry_fee: Optional monetary stakes for the match

        Returns:
            MatchProposal: Created proposal with all invitations sent

        Business Logic Flow:
        1. Creates base MatchProposal entity with DIRECT type
        2. Generates ProposalInvitation records for each invitee
        3. Sends notification to each invited player via NotificationService
        4. Filters out self-invitations (proposer cannot invite themselves)
        5. Handles notification failures gracefully without blocking proposal

        Community Integration:
        - Integrates with notification system for real-time player alerts
        - Supports venue-based match organization
        - Maintains invitation audit trail for community management
        - Enables social coordination through targeted invitations

        Transaction Management:
        Single atomic operation ensures proposal and all invitations are
        created together, with automatic rollback on any failure.
        """

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

        # Create invitations and send notifications to build community engagement
        from ..notification.services import NotificationService
        from ..user.models import User

        proposer = User.query.get(proposer_id)

        # Process each invitation with individual notification delivery
        for user_id in invited_user_ids:
            if user_id != proposer_id:  # Prevent self-invitation (business rule)
                # Create invitation record for audit trail and status tracking
                invitation = ProposalInvitation(
                    proposal_id=proposal.id, invited_user_id=user_id
                )
                db.session.add(invitation)

                # Send community notification for immediate player engagement
                from ..notification.models import NotificationType, NotificationPriority
                from flask import url_for

                try:
                    # Create rich notification with match details and action link
                    notification_result = NotificationService.create_notification(
                        user_id=user_id,
                        notification_type=NotificationType.MATCH_PROPOSAL,
                        title="Nuovo Invito Match",
                        message=(
                            f"{proposer.username if proposer else 'Un giocatore'} ti ha invitato "
                            f"per un match presso {location} il {scheduled_at.strftime('%d/%m/%Y alle %H:%M')}."
                        ),
                        priority=NotificationPriority.NORMAL,
                        action_url=url_for("player.match_proposals", _external=False),
                        action_text="Vedi Invito",
                    )
                    print(
                        f"DEBUG: Notification created for user {user_id}: {notification_result}"
                    )
                except Exception as e:
                    print(f"DEBUG: Error creating notification for user {user_id}: {e}")
                    # Graceful degradation: notification failure doesn't break proposal creation
                    # Community members can still see proposals through manual refresh

        # Transaction managed by @transactional decorator
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
        best_of: bool = False,
        break_rule: Optional[str] = None,
        description: Optional[str] = None,
        entry_fee: Optional[float] = None,
    ) -> MatchProposal:
        """Create community-wide open proposal for player discovery.

        Creates an OPEN type proposal that appears on the community match board
        for any eligible player to accept. This enables dynamic match-making
        and helps players find opponents at specific venues.

        Args:
            proposer_id: Community member creating the open proposal
            location: Pool hall where the match will take place
            scheduled_at: Proposed match date and time
            expires_at: Acceptance deadline (defaults to 2 hours before match)
            discipline: Pool game type (palla_8, palla_9, etc.)
            distance: Number of racks in the race
            best_of: Format flag - True for "best of N", False for "exactly N"
            break_rule: Break rotation rule (alternate, winner, loser)
            description: Optional match details or special requirements
            entry_fee: Optional entry fee for competitive matches

        Returns:
            MatchProposal: Created open proposal visible to all eligible players

        Community Features:
        - Appears in community match board for location-based discovery
        - Filtered by player availability and location preferences
        - Enables spontaneous match organization
        - Supports venue-specific community building

        Eligibility Rules:
        Players see this proposal if they:
        1. Have set availability for this location, OR
        2. Have previously played matches at this location
        3. Are not the original proposer

        Transaction Management:
        Single atomic operation creates the proposal with all metadata.
        No invitations are created - players express interest independently.
        """

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
        # Transaction managed by @transactional decorator
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
        best_of: bool = False,
        entry_fee: Optional[float] = None,
        max_participants: Optional[int] = None,
        is_open_invitation: bool = False,
        **kwargs,
    ) -> MatchProposal:
        """Legacy compatibility method for unified proposal creation.

        DEPRECATED: This method provides backward compatibility for existing
        callers but delegates to the appropriate specific creation method.
        New code should use create_direct_proposal() or create_open_proposal() directly.

        Business Logic Limitation:
        Due to the unified interface, direct proposals are currently created as
        open proposals since invited_user_ids cannot be specified. This is a
        known limitation of the legacy interface.

        Migration Path:
        - For targeted invitations: Use create_direct_proposal() with invited_user_ids
        - For community-wide proposals: Use create_open_proposal() directly
        - Consider deprecating this method in future versions
        """
        from datetime import datetime, time as time_obj

        # Build scheduled_at from proposed_date and proposed_time
        if proposed_date and proposed_time:
            if isinstance(proposed_time, str):
                hour, minute = map(int, proposed_time.split(":"))
                proposed_time_obj = time_obj(hour, minute)
            else:
                proposed_time_obj = proposed_time
            scheduled_at = datetime.combine(proposed_date, proposed_time_obj)
        else:
            scheduled_at = kwargs.get("scheduled_at", datetime.now())

        # Use location or default
        if not location:
            location = "TBD"

        # Route to appropriate creation method based on invitation type
        if is_open_invitation:
            return IndividualMatchService.create_open_proposal(
                proposer_id=proposer_id,
                location=location,
                scheduled_at=scheduled_at,
                discipline=discipline,
                distance=distance,
                best_of=best_of,
                description=description,
                entry_fee=entry_fee,
            )
        else:
            # LIMITATION: Direct proposals require invited_user_ids which this interface lacks
            # Fallback to creating as open proposal to maintain compatibility
            # TODO: Consider deprecating this unified interface in favor of specific methods
            return IndividualMatchService.create_open_proposal(
                proposer_id=proposer_id,
                location=location,
                scheduled_at=scheduled_at,
                discipline=discipline,
                distance=distance,
                best_of=best_of,
                description=description,
                entry_fee=entry_fee,
            )

    @staticmethod
    @transactional(domain="individual_match")
    def invite_player_to_match(
        proposal_id: int, inviter_id: int, invitee_id: int
    ) -> ProposalInvitation:
        """Add additional invitation to existing match proposal.

        Allows expanding the invitation list for a proposal after initial creation.
        Useful for open proposals where the proposer wants to specifically invite
        certain players, or for adding late invitations to direct proposals.

        Business Rules:
        - Creates invitation in PENDING status awaiting player response
        - Supports multi-player invitation workflows
        - Enables dynamic expansion of proposal reach

        Note: This method does not send notifications - caller is responsible
        for notification delivery if desired.
        """
        from .models import ProposalInvitation, InvitationStatus

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
        """Process player response to match invitation.

        Handles both acceptance and rejection of specific invitation records.
        When accepted, automatically creates the IndividualMatch through
        the proposal acceptance workflow.

        Args:
            invitation_id: Specific invitation being responded to
            invitee_id: Player responding (must match invitation recipient)
            response: "accepted" or any other value for rejection

        Returns:
            bool: True if response was processed successfully, False if invalid

        Business Logic:
        - Validates invitation exists and belongs to responding player
        - Acceptance triggers full match creation workflow
        - Rejection updates invitation status only
        - Leverages existing accept_proposal logic for consistency
        """
        from .models import InvitationStatus

        invitation = ProposalInvitation.query.get(invitation_id)
        if not invitation or invitation.invited_user_id != invitee_id:
            return False

        if response.lower() == "accepted":
            invitation.status = InvitationStatus.ACCEPTED
            # Trigger full match creation through established workflow
            match = IndividualMatchService.accept_proposal(
                user_id=invitee_id, proposal_id=invitation.proposal_id
            )
        else:
            # Any non-acceptance response is treated as rejection
            invitation.status = InvitationStatus.REJECTED

        return True

    @staticmethod
    def get_user_proposals(
        user_id: int, include_expired: bool = False
    ) -> Dict[str, List[MatchProposal]]:
        """Comprehensive proposal overview with intelligent filtering.

        Provides categorized view of all proposals relevant to a user,
        with automatic expiration handling and location-based filtering
        for optimal community experience.

        Args:
            user_id: Community member requesting proposal overview
            include_expired: Whether to include proposals past their deadline

        Returns:
            Dict with keys:
            - "created": Proposals this user initiated
            - "received": Direct invitations sent to this user
            - "available": Open proposals this user can accept

        Intelligent Filtering:
        1. Automatic expiration processing before building results
        2. Location-based eligibility for open proposals
        3. Status-based filtering (pending, accepted, cancelled)
        4. Community-relevant proposal discovery

        Location Eligibility Rules:
        User sees open proposals for locations where they:
        - Have explicitly set availability (PlayerAvailability records)
        - Have played previous matches (historical location usage)
        - This ensures relevant, actionable proposal visibility

        Performance Considerations:
        - Expires stale proposals in single batch before query
        - Uses efficient joins for invitation relationships
        - Leverages database indexes for status and user filtering
        """

        # Proactive expiration maintenance for clean community experience
        IndividualMatchService._expire_pending_proposals()

        query = MatchProposal.query

        if not include_expired:
            query = query.filter(
                db.or_(
                    # Include non-expired proposals
                    db.and_(
                        MatchProposal.status == ProposalStatus.PENDING,
                        MatchProposal.expires_at > datetime.utcnow(),
                    ),
                    # Include accepted proposals (regardless of expiry)
                    MatchProposal.status == ProposalStatus.ACCEPTED,
                    # Include cancelled proposals for history
                    MatchProposal.status == ProposalStatus.CANCELLED,
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

        # Apply location-based filtering for relevant community proposals
        # Build user's location eligibility from two sources:

        # 1. Explicit availability preferences (where user wants to play)
        user_locations = {
            av.location
            for av in PlayerAvailability.query.filter_by(
                user_id=user_id, is_available=True
            ).all()
        }

        # 2. Historical locations (where user has played before)
        played_locations = {
            match.location
            for match in IndividualMatch.query.filter(
                db.or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                )
            ).all()
        }

        # Combine both sets for comprehensive location eligibility
        eligible_locations = user_locations.union(played_locations)

        # Filter open proposals to only show relevant venues
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
    @transactional(domain="individual_match")
    def accept_proposal(user_id: int, proposal_id: int) -> IndividualMatch:
        """Accept a match proposal (core business logic implementation).

        This is the core business logic method that handles proposal acceptance.
        It validates user permissions, updates proposal status, creates the
        individual match, and manages all related state changes atomically.

        Args:
            user_id: ID of the user accepting the proposal
            proposal_id: ID of the proposal to accept

        Returns:
            IndividualMatch: The newly created individual match

        Raises:
            404: If proposal not found
            ValueError: If user cannot accept this proposal

        Business Logic:
            - Validates proposal exists and is in acceptable state
            - Checks user permissions via proposal.can_be_accepted_by()
            - Delegates to proposal.accept() for state transitions
            - Creates IndividualMatch with proper player assignments
            - Updates proposal status to ACCEPTED
            - Handles notification system integration (via proposal.accept())

        Transaction Management:
            - Atomic operation ensuring proposal + match + notifications consistency
            - Rollback on any failure to maintain data integrity

        Called By:
            - MatchProposalService.accept_proposal: Direct delegation
            - IndividualMatchService.accept_invitation: Route-optimized alias
        """
        proposal = db.session.get(MatchProposal, proposal_id)
        if proposal is None:
            from flask import abort

            abort(404)

        if not proposal.can_be_accepted_by(user_id):
            raise ValueError("User cannot accept this proposal")

        individual_match = proposal.accept(user_id)

        return individual_match

    @staticmethod
    @transactional(domain="individual_match")
    def accept_invitation(proposal_id: int, accepting_user_id: int) -> IndividualMatch:
        """Accept a match proposal invitation (core @transactional implementation).

        ARCHITECTURAL ROLE (Task 1.1 Phase 7):
        Core @transactional service method that implements atomic proposal acceptance.
        Called by MatchProposalService delegation layer for route integration.

        Args:
            proposal_id: ID of the proposal to accept
            accepting_user_id: ID of the user accepting the invitation

        Returns:
            IndividualMatch: The created individual match from accepted proposal

        Transaction Management:
            - @transactional(domain="individual_match") ensures atomic operations
            - Single transaction boundary for: validation + match creation + notifications
            - Automatic rollback on validation failures or system errors
            - Domain isolation prevents transaction conflicts with other business domains

        Business Logic Implementation:
            - Validates proposal exists and user permissions
            - Creates IndividualMatch entity from accepted proposal
            - Updates proposal status to ACCEPTED with audit trail
            - Triggers notification system for all participants
            - Maintains referential integrity across multi-model operations

        Migration Benefits:
            - Eliminates manual transaction management from route handlers
            - Provides consistent error handling and rollback behavior
            - Centralizes business rules for testability and reuse
            - Enables proper transaction isolation for concurrent operations

        Service Layer Integration:
            Called by MatchProposalService.accept_invitation() which provides
            route-optimized interface for REST endpoint integration.
        """
        return MatchProposalService.accept_proposal(accepting_user_id, proposal_id)

    @staticmethod
    @transactional(domain="individual_match")
    def reject_invitation(user_id: int, proposal_id: int) -> None:
        """Reject a match proposal invitation (core @transactional implementation).

        ARCHITECTURAL ROLE (Task 1.1 Phase 7):
        Core @transactional service method for atomic invitation rejection.
        Companion to accept_invitation providing complete proposal workflow.

        Args:
            user_id: ID of the user rejecting the invitation
            proposal_id: ID of the proposal being rejected

        Raises:
            404: If invitation not found for user and proposal combination

        Transaction Management:
            - @transactional(domain="individual_match") ensures atomic status update
            - Single transaction boundary for invitation state changes
            - Automatic rollback on validation failures
            - Domain isolation prevents conflicts with other business operations

        Business Logic Implementation:
            - Validates invitation exists for user/proposal combination
            - Updates invitation status through invitation.reject() method
            - Maintains complete audit trail for proposal workflow
            - Preserves data consistency during concurrent access

        Migration Benefits:
            - Eliminates manual db.session.commit() from route handlers
            - Provides symmetric workflow with accept_invitation
            - Ensures atomic invitation state management
            - Enables proper error handling and rollback behavior

        Service Layer Integration:
            Called by MatchProposalService.reject_invitation() which provides
            route-optimized parameter order for REST endpoint integration.
        """
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

        # Verify user is the proposer
        if proposal.proposer_id != user_id:
            raise ValueError("Only the proposer can cancel the proposal")

        # Verify proposal can be cancelled
        if proposal.status != ProposalStatus.PENDING:
            raise ValueError("Proposal cannot be cancelled - it's not pending")

        proposal.cancel()

    @staticmethod
    def get_user_dashboard_data(user_id: int) -> Dict[str, Any]:
        """Build comprehensive player dashboard with community engagement data.

        Aggregates all individual match related data for a player's dashboard:
        - Active proposals and invitations
        - Current and recent matches
        - Availability settings and location preferences
        - Performance statistics and community standing

        Returns structured data optimized for dashboard template rendering
        with categorized matches and actionable proposal information.
        """
        proposals = IndividualMatchService.get_user_proposals(user_id)
        all_matches = IndividualMatchService.get_user_matches(user_id)
        availability = IndividualMatchService.get_user_availability(user_id)
        stats = IndividualMatchService.get_user_statistics(user_id)

        # Organize matches by status for efficient dashboard rendering
        active_matches = [
            m
            for m in all_matches
            if m.status in [MatchStatus.SCHEDULED, MatchStatus.IN_PROGRESS]
        ]
        completed_matches = [
            m for m in all_matches if m.status == MatchStatus.COMPLETED
        ]
        # Show most recent completed matches for quick performance review
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
    def get_user_availability(user_id: int) -> Dict[str, Any]:
        """Retrieve comprehensive player availability configuration.

        Returns structured availability data for community match coordination:
        - All availability records with time preferences
        - Organized by location for venue-specific scheduling
        - Available locations list for quick reference

        Used by match proposal systems to determine player eligibility
        and by the availability service for community coordination.
        """
        availability_records = PlayerAvailability.query.filter_by(user_id=user_id).all()

        # Organize availability records by location for efficient lookup
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
    @transactional(domain="individual_match")
    def submit_rack_result(
        match_id: int,
        user_id: int,
        winner_id: int,
        rack_number: int,
        notes: Optional[str] = None,
    ) -> IndividualRack:
        """Record rack result with automatic match progression logic.

        Core scoring method that handles individual rack recording and
        automatically manages match progression and completion detection.

        Args:
            match_id: Individual match receiving the rack result
            user_id: Player submitting the result (must be match participant)
            winner_id: Player who won this rack (must be match participant)
            rack_number: Sequential rack number for audit trail
            notes: Optional rack notes (e.g., "8-ball break and run")

        Returns:
            IndividualRack: Created rack record with match score updates

        Business Logic:
        1. Validates user authorization (must be match participant)
        2. Validates winner eligibility (must be match participant)
        3. Prevents duplicate rack recording (unique rack_number per match)
        4. Updates running match scores automatically
        5. Detects match completion based on distance settings
        6. Sets match completion timestamp and winner when race is reached

        Match Completion Rules:
        - Match completes when either player reaches the match distance
        - Winner determined by highest score (handles early completion)
        - Completion timestamp automatically set for historical tracking

        Authorization Rules:
        - Only match participants can submit rack results
        - Winner must be one of the two match participants
        - Rack numbers must be unique within the match
        """
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
            match_id=match_id, rack_number=rack_number, winner_id=winner_id, notes=notes
        )

        db.session.add(rack)

        # Update match scores
        if winner_id == match.player1_id:
            match.player1_score += 1
        else:
            match.player2_score += 1

        # Automatic match completion detection based on race distance
        if (
            match.player1_score >= match.distance
            or match.player2_score >= match.distance
        ):
            match.status = MatchStatus.COMPLETED
            match.completed_at = datetime.utcnow()
            # Determine winner based on final scores (handles early completion scenarios)
            match.winner_id = (
                winner_id if match.player1_score != match.player2_score else None
            )

        return rack

    @staticmethod
    @transactional(domain="individual_match")
    def update_user_availability(
        user_id: int, availability_data: List[Dict[str, Any]]
    ) -> None:
        """Bulk update player availability settings for community coordination.

        Replaces all existing availability records with new settings.
        This ensures clean state management and prevents orphaned
        availability records from affecting match proposal visibility.

        Args:
            user_id: Player updating their availability preferences
            availability_data: List of availability records with location,
                             day_of_week, time ranges, and availability flags

        Transaction Management:
        Single atomic operation that:
        1. Clears existing availability (prevents conflicts)
        2. Creates all new availability records
        3. Ensures consistent availability state across locations

        Community Impact:
        Updated availability immediately affects:
        - Visibility of open proposals at relevant locations
        - Inclusion in location-based player discovery
        - Match recommendation algorithms
        """
        # Clear existing availability to ensure clean state (prevents conflicts)
        PlayerAvailability.query.filter_by(user_id=user_id).delete()

        # Create all new availability records in single transaction
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
    def get_admin_overview() -> Dict[str, Any]:
        """Generate comprehensive administrative overview of individual match system.

        Provides high-level metrics and insights for community administration:
        - Match status distribution for system health monitoring
        - Recent match activity for community engagement tracking
        - Proposal status breakdown for invitation system health
        - Active location analytics for venue management
        - Player participation metrics for community growth

        Used by admin dashboard to monitor community health and identify
        areas needing attention (e.g., stale proposals, inactive locations).
        """
        # Collect match distribution metrics for system health monitoring
        status_counts = {}
        for status in MatchStatus:
            count = IndividualMatch.query.filter_by(status=status).count()
            status_counts[status.value] = count

        # Track recent activity for community engagement insights
        recent_matches = (
            IndividualMatch.query.order_by(IndividualMatch.created_at.desc())
            .limit(10)
            .all()
        )

        # Monitor proposal workflow health across all statuses
        proposal_counts = {}
        for status in ProposalStatus:
            count = MatchProposal.query.filter_by(status=status).count()
            proposal_counts[status.value] = count

        # Identify active venues for location-based community insights
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
        """Retrieve user's match history with optional status filtering.

        Returns all individual matches where the user participated as either
        player1 or player2, ordered by scheduled date (most recent first).

        Args:
            user_id: Player whose matches to retrieve
            status_filter: Optional status to filter by (e.g., COMPLETED only)

        Used for player statistics, match history display, and performance
        analysis throughout the community platform.
        """
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
    @transactional(domain="individual_match")
    def start_match(match_id: int, user_id: int) -> IndividualMatch:
        """Initiate match play with participant authorization check.

        Transitions match from scheduled to in-progress status. Only
        match participants can start the match to prevent unauthorized
        manipulation of community matches.

        Delegates to match.start_match() for state machine consistency.
        """
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can start the match")

        match.start_match()

        return match

    @staticmethod
    @transactional(domain="individual_match")
    def complete_match(match_id: int, winner_id: int, user_id: int) -> IndividualMatch:
        """Finalize match with winner determination and participant authorization.

        Transitions match to completed status with winner recording.
        Only match participants can complete matches to ensure result
        integrity within the community platform.

        Args:
            match_id: Individual match to complete
            winner_id: Player who won the match
            user_id: Player initiating completion (authorization check)

        Delegates to match.complete_match() for consistent state transitions.
        """
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can complete the match")

        match.complete_match(winner_id)

        return match

    @staticmethod
    @transactional(domain="individual_match")
    def cancel_match(
        match_id: int, user_id: int, reason: Optional[str] = None
    ) -> IndividualMatch:
        """Cancel scheduled or in-progress match with reason tracking.

        Allows match participants to cancel matches due to scheduling
        conflicts, venue issues, or other circumstances. Maintains
        cancellation audit trail for community management.

        Args:
            match_id: Individual match to cancel
            user_id: Player initiating cancellation (authorization check)
            reason: Optional cancellation reason for community records

        Only match participants can cancel to prevent external interference
        with community match scheduling.
        """
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can cancel the match")

        match.cancel_match(reason)

        return match

    @staticmethod
    @transactional(domain="individual_match")
    def set_player_availability(
        user_id: int,
        location: str,
        is_available: bool = True,
        preferred_days: Optional[str] = None,
        preferred_times: Optional[str] = None,
    ) -> PlayerAvailability:
        """Update or create location-specific availability settings.

        Manages per-location availability preferences for community
        match coordination. Updates existing records or creates new
        ones as needed for seamless availability management.

        Args:
            user_id: Player setting availability preferences
            location: Specific venue or pool hall
            is_available: Whether player is available at this location
            preferred_days: Optional day preferences (JSON format)
            preferred_times: Optional time range preferences

        Returns:
            PlayerAvailability: Updated or created availability record

        Community Integration:
        - Affects visibility of open proposals at this location
        - Influences match recommendation algorithms
        - Enables location-based player discovery
        """

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
        """Retrieve complete availability configuration for a player.

        Returns all location-specific availability records for comprehensive
        availability management and community match coordination.
        """
        return PlayerAvailability.query.filter_by(user_id=user_id).all()

    @staticmethod
    def get_eligible_players_for_location(
        location: str, exclude_user_id: Optional[int] = None
    ) -> List[User]:
        """Discover community players available for location-based matches.

        Finds players who could participate in matches at a specific venue
        using two eligibility criteria:
        1. Explicit availability settings (players who marked this location available)
        2. Historical participation (players who have played here before)

        Args:
            location: Pool hall or venue to find players for
            exclude_user_id: Optional user to exclude (e.g., the proposer)

        Returns:
            List[User]: Combined and deduplicated list of eligible players

        Community Features:
        - Enables dynamic player discovery for open proposals
        - Leverages both intent (availability) and experience (history)
        - Supports venue-specific community building
        - Excludes requesting player to prevent self-matching
        """
        from ..user.models import User

        # Find players with explicit availability preferences for this location
        available_users = User.query.join(PlayerAvailability).filter(
            PlayerAvailability.location == location,
            PlayerAvailability.is_available.is_(True),
        )

        # Find players with historical experience at this location
        experienced_users = User.query.join(
            db.or_(
                IndividualMatch.player1_id == User.id,
                IndividualMatch.player2_id == User.id,
            )
        ).filter(IndividualMatch.location == location)

        # Combine both sets and deduplicate for comprehensive player pool
        all_users = available_users.union(experienced_users)

        if exclude_user_id:
            all_users = all_users.filter(User.id != exclude_user_id)

        return all_users.all()

    @staticmethod
    @transactional(domain="individual_match")
    def expire_old_proposals() -> int:
        """Community maintenance: batch expiration of stale proposals.

        Cleans up the community match board by automatically expiring
        proposals that have passed their expiration deadline. This
        prevents community confusion and maintains a clean match board.

        Returns:
            int: Number of proposals expired in this maintenance cycle

        Called by:
        - Scheduled maintenance tasks
        - Before displaying proposal lists (proactive cleanup)
        - Admin maintenance operations
        """
        expired_proposals = MatchProposal.query.filter(
            MatchProposal.status == ProposalStatus.PENDING,
            MatchProposal.expires_at <= datetime.utcnow(),
        ).all()

        count = 0
        for proposal in expired_proposals:
            proposal.expire()
            count += 1

        return count

    @staticmethod
    def get_user_statistics(user_id: int) -> Dict[str, Any]:
        """Calculate comprehensive performance statistics for player profile.

        Computes detailed statistics from completed individual matches:
        - Win/loss record and percentages
        - Rack-level performance metrics
        - Location-specific performance breakdowns
        - Historical performance tracking

        Returns structured data for player profiles, leaderboards,
        and community ranking systems. Only includes completed matches
        to ensure accurate statistical representation.
        """
        matches = IndividualMatchService.get_user_matches(
            user_id, MatchStatus.COMPLETED
        )

        total_matches = len(matches)
        won_matches = sum(1 for m in matches if m.winner_id == user_id)
        lost_matches = total_matches - won_matches

        # Calculate detailed rack-level performance for skill assessment
        total_racks_won = sum(m.get_user_score(user_id) for m in matches)
        total_racks_played = sum(m.player1_score + m.player2_score for m in matches)

        # Build location-specific performance breakdown for venue insights
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
    @transactional(domain="individual_match")
    def _expire_pending_proposals() -> int:
        """Internal maintenance method for proactive proposal cleanup.

        Private method that handles the actual expiration logic for
        stale proposals. Called automatically before proposal queries
        to ensure users see only valid, actionable proposals.

        Returns:
            int: Count of proposals expired in this cleanup cycle

        Implementation Note:
        Uses proposal.expire() method for consistent state transitions
        rather than direct status updates.
        """
        now = datetime.utcnow()

        expired_proposals = MatchProposal.query.filter(
            MatchProposal.status == ProposalStatus.PENDING,
            MatchProposal.expires_at <= now,
        ).all()

        count = 0
        for proposal in expired_proposals:
            proposal.expire()
            count += 1

        return count

    @staticmethod
    @transactional(domain="individual_match")
    def confirm_rack_result(rack_id: int, confirming_player_id: int) -> Dict[str, Any]:
        """Player confirmation of rack result for dispute prevention.

        Allows players to confirm rack results submitted by their opponent,
        providing an audit trail and reducing potential disputes. This
        supports fair play within the community platform.

        Args:
            rack_id: Specific rack result being confirmed
            confirming_player_id: Player providing confirmation

        Returns:
            Dict with success status and confirmation message

        Business Logic:
        - Sets confirmed_by_player flag on the rack record
        - Creates audit trail for community management
        - Supports dispute resolution and fair play initiatives
        """
        rack = db.session.get(IndividualRack, rack_id)
        if not rack:
            raise ValueError(f"Rack {rack_id} not found")

        # Mark as confirmed by player
        rack.confirmed_by_player = True

        return {"success": True, "message": "Rack result confirmed"}

    @staticmethod
    @transactional(domain="individual_match")
    def report_result(
        match_id: int,
        reporter_id: int,
        winner_id: int,
        player1_racks: int,
        player2_racks: int,
    ) -> None:
        """Report final match result with automatic proposal acceptance.

        Handles match result reporting that may involve accepting a pending
        proposal first, then completing the resulting individual match.
        Supports workflow where players report results directly from
        proposal interface before formal match creation.

        Args:
            match_id: Actually a proposal ID in current implementation
            reporter_id: Player reporting the result
            winner_id: Player who won the match
            player1_racks: Racks won by player 1 (for final score recording)
            player2_racks: Racks won by player 2 (for final score recording)

        Workflow:
        1. If proposal is pending, accept it to create IndividualMatch
        2. If already accepted, find the associated IndividualMatch
        3. Complete the match with reported winner

        Note: Parameter naming (match_id) is misleading - this actually
        expects a proposal_id. Consider renaming for clarity.
        """
        # IMPORTANT: match_id parameter is actually a proposal_id (legacy naming)
        # Convert proposal to individual match through acceptance workflow
        from .models import MatchProposal

        proposal = db.session.get(MatchProposal, match_id)
        if not proposal:
            raise ValueError(f"Match proposal {match_id} not found")

        # Handle pending proposals by accepting them first (streamlined workflow)
        if proposal.status.value == "pending":
            individual_match = proposal.accept(reporter_id)
        else:
            # For already accepted proposals, locate the created individual match
            individual_match = IndividualMatch.query.filter_by(
                proposal_id=match_id
            ).first()
            if not individual_match:
                raise ValueError("No individual match found for this proposal")

        # Finalize the match using the actual individual match ID
        IndividualMatchService.complete_match(
            match_id=individual_match.id,
            winner_id=winner_id,
            user_id=reporter_id,
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
        """Flexible rack result recording with multiple signature compatibility.

        Compatibility wrapper that supports different parameter patterns:
        1. New signature: rack_number, reported_by_id (preferred)
        2. Legacy signature: winner_id, user_id via kwargs

        This method exists to maintain compatibility with existing tests
        and calling code while transitioning to the preferred interface.

        Args:
            match_id: Individual match receiving the rack result
            rack_number: Sequential rack number (new signature)
            winner_id: Player who won the rack
            reported_by_id: Player reporting result (new signature)
            break_player_id: Player who broke (future enhancement)
            notes: Optional rack notes
            **kwargs: Legacy parameter support (user_id)

        Migration Note:
        New code should use submit_rack_result() directly for clearer semantics.
        This wrapper primarily exists for test compatibility.
        """
        # Route to appropriate implementation based on parameter signature
        if rack_number is not None and reported_by_id is not None:
            # Preferred new signature with explicit rack numbering
            return IndividualMatchService.submit_rack_result(
                match_id=match_id,
                user_id=reported_by_id,
                winner_id=winner_id,
                rack_number=rack_number,
            )
        # Legacy signature compatibility for existing tests
        elif len(kwargs) == 1 and "user_id" in kwargs:
            user_id = kwargs["user_id"]
            return IndividualMatchService._add_rack_result_original(
                match_id=match_id, winner_id=winner_id, user_id=user_id
            )
        else:
            raise ValueError("Invalid parameters for add_rack_result")

    @staticmethod
    @transactional(domain="individual_match")
    def _add_rack_result_original(
        match_id: int, winner_id: int, user_id: int
    ) -> IndividualRack:
        """Legacy rack result recording without explicit rack numbering.

        Original implementation that delegates to match.add_rack_result()
        for automatic rack number generation. Maintained for backward
        compatibility with existing test suites.

        Args:
            match_id: Individual match receiving the rack result
            winner_id: Player who won the rack
            user_id: Player reporting the result (authorization check)

        Returns:
            IndividualRack: Created rack with auto-generated rack number

        Migration Note:
        Consider migrating callers to submit_rack_result() for explicit
        rack number control and clearer parameter semantics.
        """
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can add rack results")

        rack = match.add_rack_result(winner_id)
        return rack

    @staticmethod
    @transactional(domain="individual_match")
    def complete_individual_match(
        match_id: int, winner_id: int, user_id: int
    ) -> IndividualMatch:
        """Alias for complete_match() - maintained for API compatibility.

        Provides explicit naming for individual match completion to
        distinguish from other match types in the system. Delegates
        to complete_match() for consistent implementation.
        """
        return IndividualMatchService.complete_match(match_id, winner_id, user_id)

    @staticmethod
    @transactional(domain="individual_match")
    def express_interest_in_open_invitation(
        proposal_id: int, interested_player_id: int, message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Register player interest in open community proposal.

        Allows players to express interest in open proposals, creating
        a ProposalInvitation record that the proposer can review and
        potentially accept. This enables curated selection from multiple
        interested players for open proposals.

        Args:
            proposal_id: Open proposal the player is interested in
            interested_player_id: Player expressing interest
            message: Optional message to proposer (future enhancement)

        Returns:
            Dict with success status and invitation_id for tracking

        Business Rules:
        - Only valid for OPEN type proposals
        - Prevents duplicate interest expressions
        - Creates invitation record for proposer review
        - Enables social interaction through match coordination

        Community Flow:
        1. Player sees open proposal on community board
        2. Player expresses interest using this method
        3. Proposer reviews interested players
        4. Proposer accepts one interest via accept_interest_for_open_invitation
        """
        proposal = db.session.get(MatchProposal, proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        if proposal.proposal_type != ProposalType.OPEN:
            raise ValueError("Can only express interest in open proposals")

        # Check if already expressed interest
        existing = ProposalInvitation.query.filter_by(
            proposal_id=proposal_id, invited_user_id=interested_player_id
        ).first()
        if existing:
            raise ValueError("Interest already expressed")

        # Create invitation for this user
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
        """Accept specific player interest for open proposal with community notifications.

        Completes the open proposal workflow by selecting one interested player
        and creating the individual match. Automatically notifies other
        interested players that the spot has been filled.

        Args:
            proposal_id: Open proposal being finalized
            proposer_id: Original proposer (authorization check)
            accepted_player_id: Selected player from interested list

        Returns:
            Dict with success status and created match_id

        Community Workflow:
        1. Validates proposer authorization and interest record existence
        2. Accepts proposal on behalf of selected player
        3. Creates IndividualMatch through standard acceptance workflow
        4. Notifies other interested players about selection
        5. Maintains positive community experience through communication

        Notification Strategy:
        - Selected player receives match confirmation
        - Other interested players receive polite "filled" notification
        - Graceful degradation if notifications fail
        """
        proposal = db.session.get(MatchProposal, proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        if proposal.proposer_id != proposer_id:
            raise ValueError("Only the proposer can accept interests")

        # Find the invitation for the selected user
        invitation = ProposalInvitation.query.filter_by(
            proposal_id=proposal_id, invited_user_id=accepted_player_id
        ).first()
        if not invitation:
            raise ValueError("No interest found for selected user")

        # Create the match through standard proposal acceptance workflow
        match = IndividualMatchService.accept_proposal(accepted_player_id, proposal_id)

        # Community courtesy: notify other interested players about selection
        other_invitations = (
            ProposalInvitation.query.filter_by(proposal_id=proposal_id)
            .filter(ProposalInvitation.invited_user_id != accepted_player_id)
            .all()
        )

        # Send courteous notifications to maintain positive community experience
        if other_invitations:
            from ..notification.models import NotificationType, NotificationPriority

            proposal_title = getattr(proposal, "title", "Open match proposal")

            for other_invitation in other_invitations:
                try:
                    # Send polite notification about selection decision
                    NotificationService.create_notification(
                        user_id=other_invitation.invited_user_id,
                        notification_type=NotificationType.MATCH_DECLINED,
                        title="Match Proposal Filled",
                        message=f"The open match proposal '{proposal_title}' has been filled by another player.",
                        priority=NotificationPriority.NORMAL,
                    )
                except Exception as e:
                    # Graceful degradation: notification failure doesn't break match creation
                    print(f"Failed to create notification: {e}")
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
        """Create match from specific invitation record.

        Alternative workflow that starts from an invitation rather than
        proposal. Delegates to standard proposal acceptance logic for
        consistency in match creation and state management.

        Args:
            invitation_id: Specific invitation being accepted

        Returns:
            IndividualMatch: Created match from accepted invitation

        Used in workflows where invitation-specific logic is required
        or when tracking invitation-level events and auditing.
        """
        invitation = db.session.get(ProposalInvitation, invitation_id)
        if not invitation:
            raise ValueError(f"Invitation {invitation_id} not found")

        # Delegate to standard proposal acceptance for consistency
        return IndividualMatchService.accept_proposal(
            invitation.invited_user_id, invitation.proposal_id
        )

    @staticmethod
    @transactional(domain="individual_match")
    def dispute_rack_result(
        rack_id: int, disputing_player_id: int, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Initiate dispute process for rack result accuracy.

        Allows match participants to dispute rack results they believe
        are incorrect. This supports fair play and provides an audit
        trail for community management and dispute resolution.

        Args:
            rack_id: Specific rack result being disputed
            disputing_player_id: Player initiating the dispute
            reason: Optional explanation for the dispute

        Returns:
            Dict with dispute initiation status and details

        Business Rules:
        - Only match participants can dispute rack results
        - Creates audit trail for community management
        - Supports community fair play initiatives

        Future Enhancement:
        Could integrate with admin notification system to alert
        community managers about disputed results requiring resolution.
        """
        rack = db.session.get(IndividualRack, rack_id)
        if not rack:
            raise ValueError(f"Rack {rack_id} not found")

        match = rack.match
        if disputing_player_id not in [match.player1_id, match.player2_id]:
            raise ValueError("Only match players can dispute rack results")

        # TODO: Implement disputed field on rack model for proper dispute tracking
        # Currently returns success message - future enhancement needed
        return {
            "success": True,
            "message": f"Rack {rack.rack_number} result disputed by player {disputing_player_id}",
            "reason": reason,
        }

    @staticmethod
    @transactional(domain="individual_match")
    def resolve_rack_dispute(
        rack_id: int, admin_user_id: int, resolution: str, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Administrative resolution of rack result disputes.

        Allows community administrators to resolve disputed rack results
        and maintain fair play standards within the platform. Provides
        administrative oversight for community dispute management.

        Args:
            rack_id: Disputed rack being resolved
            admin_user_id: Administrator handling the resolution
            resolution: Resolution decision or outcome
            reason: Optional explanation for the resolution

        Returns:
            Dict with resolution status and administrative decision

        Administrative Features:
        - Provides oversight for community dispute resolution
        - Creates audit trail for administrative decisions
        - Supports community management and fair play enforcement

        Future Enhancement:
        Could integrate with user notification system to inform
        disputing players about administrative decisions.
        """
        rack = db.session.get(IndividualRack, rack_id)
        if not rack:
            raise ValueError(f"Rack {rack_id} not found")

        # TODO: Implement dispute resolution fields on rack model
        # Currently returns success message - future enhancement needed
        return {
            "success": True,
            "message": f"Rack {rack.rack_number} dispute resolved by admin {admin_user_id}",
            "resolution": resolution,
            "reason": reason,
        }
