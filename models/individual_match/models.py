"""
Module: models/individual_match/models.py
Purpose: Individual Match domain models for player-to-player match proposals
Requirements: SPECIFICHE.md - Individual match proposals between players
Data Structures: IndividualMatch, MatchProposal, PlayerAvailability
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from enum import Enum

from sqlalchemy import func

from ..base import db, BaseModel, TimestampMixin, utc_now
from ..status_enum import Discipline, MatchStatus
from ..match.base_match import BaseMatchMixin

if TYPE_CHECKING:
    from ..user.models import User


class ProposalType(Enum):
    """Types of match proposals."""

    DIRECT = "direct"  # Invitation to specific players
    OPEN = "open"  # Open to all eligible players


class ProposalStatus(Enum):
    """Status of match proposals."""

    PENDING = "pending"  # Waiting for responses
    ACCEPTED = "accepted"  # Someone accepted
    EXPIRED = "expired"  # Time limit reached
    CANCELLED = "cancelled"  # Cancelled by proposer


class MatchProposal(BaseModel, TimestampMixin):
    """A proposal for a match, either direct or open."""

    __tablename__ = "match_proposal"

    id = db.Column(db.Integer, primary_key=True)
    proposer_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # Proposal details
    proposal_type = db.Column(db.Enum(ProposalType), nullable=False)
    status = db.Column(
        db.Enum(ProposalStatus), nullable=False, default=ProposalStatus.PENDING
    )

    # Match details - Location
    # New: FK to BilliardHall (nullable for backward compatibility)
    billiard_hall_id = db.Column(
        db.Integer, db.ForeignKey("billiard_hall.id", ondelete="SET NULL"), nullable=True
    )
    # Legacy: string-based location (kept for backward compatibility, will be deprecated)
    location = db.Column(db.String(255), nullable=True)  # Made nullable - prefer billiard_hall_id
    scheduled_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

    # Optional game configuration
    discipline = db.Column(
        db.String(50), nullable=True, default=Discipline.EIGHT_BALL.value
    )  # Game discipline (usa Discipline enum)
    distance = db.Column(
        db.Integer, nullable=True, default=5
    )  # Number of racks per set
    is_race_to = db.Column(
        db.Boolean, nullable=True, default=True
    )  # Race-to vs exact racks
    break_rule = db.Column(
        db.String(20), nullable=True, default="alternate"
    )  # Break rule: alternate, winner, loser
    description = db.Column(db.Text, nullable=True)

    # Multi-set configuration (Phase 6: Frontend Integration)
    is_multi_set = db.Column(db.Boolean, default=False, nullable=True)
    match_distance = db.Column(db.Integer, nullable=True)  # Number of sets
    is_race_to_sets = db.Column(
        db.Boolean, default=True, nullable=True
    )  # Race-to vs exact sets

    # Result tracking
    accepted_by_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    accepted_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    proposer = db.relationship("User", foreign_keys=[proposer_id])
    accepted_by = db.relationship("User", foreign_keys=[accepted_by_id])
    billiard_hall = db.relationship("BilliardHall", foreign_keys=[billiard_hall_id])

    # Direct invitations (for DIRECT proposals)
    invitations = db.relationship(  # type: ignore[assignment]
        "ProposalInvitation", back_populates="proposal", cascade="all, delete-orphan"
    )

    # Resulting match (if accepted)
    individual_match = db.relationship(
        "IndividualMatch", back_populates="proposal", uselist=False
    )

    @property
    def location_display(self) -> str:
        """Get display name for location.

        Returns billiard_hall.name if available, otherwise falls back
        to legacy location string.

        Returns:
            str: Location name for display
        """
        if self.billiard_hall:
            return self.billiard_hall.name
        return self.location or ""

    @property
    def distance_config(self):
        """Get Distance value object for this proposal.

        Returns unified Distance abstraction supporting both single-set
        and multi-set configurations.

        Returns:
            Distance: Immutable distance configuration (None if not specified)
        """
        from models.match.distance import Distance

        if self.distance is None:
            return None

        if not self.is_multi_set:
            # Single-set configuration (backward compatible)
            return Distance(
                racks=self.distance,
                is_race_to_racks=self.is_race_to,
                is_multi_set=False,
                sets=1,
                is_race_to_sets=True,
            )
        else:
            # Multi-set configuration (Phase 6: Frontend Integration)
            return Distance(
                racks=self.distance,
                is_race_to_racks=self.is_race_to,
                is_multi_set=True,
                sets=self.match_distance if self.match_distance else 1,
                is_race_to_sets=self.is_race_to_sets,
            )

    def is_expired(self) -> bool:
        """Check if proposal has expired."""
        return utc_now() > self.expires_at

    def can_be_accepted_by(self, user_id: int) -> bool:
        """Check if user can accept this proposal."""
        if self.status != ProposalStatus.PENDING:
            return False

        if self.is_expired():
            return False

        if user_id == self.proposer_id:
            return False

        # For direct proposals, check if user was invited
        if self.proposal_type == ProposalType.DIRECT:
            invitation = (
                db.session.query(ProposalInvitation)
                .filter_by(proposal_id=self.id, invited_user_id=user_id)
                .first()
            )
            return (
                invitation is not None and invitation.status == InvitationStatus.PENDING
            )

        # For open proposals, any user can accept (subject to location availability)
        return True

    def accept(self, user_id: int) -> "IndividualMatch":
        """Accept the proposal and create an individual match."""
        if not self.can_be_accepted_by(user_id):
            raise ValueError("User cannot accept this proposal")

        self.status = ProposalStatus.ACCEPTED
        self.accepted_by_id = user_id
        self.accepted_at = utc_now()

        # Create the individual match
        individual_match = IndividualMatch(
            proposal_id=self.id,
            player1_id=self.proposer_id,
            player2_id=user_id,
            # Location: prefer FK, fallback to legacy string
            billiard_hall_id=self.billiard_hall_id,
            location=self.location,
            scheduled_at=self.scheduled_at,
            discipline=self.discipline,
            distance=self.distance,
            is_race_to=self.is_race_to,
            break_rule=self.break_rule,
            # Phase 6: Copy multi-set configuration
            is_multi_set=self.is_multi_set if self.is_multi_set is not None else False,
            match_distance=self.match_distance,
            is_race_to_sets=self.is_race_to_sets,
        )

        db.session.add(individual_match)

        # Cancel/reject other pending invitations
        if self.proposal_type == ProposalType.DIRECT:
            from typing import cast

            for invitation in cast(List["ProposalInvitation"], self.invitations):
                if (
                    invitation.status == InvitationStatus.PENDING
                    and invitation.invited_user_id != user_id
                ):
                    invitation.status = InvitationStatus.REJECTED

        return individual_match

    def cancel(self) -> None:
        """Cancel the proposal."""
        if self.status == ProposalStatus.PENDING:
            self.status = ProposalStatus.CANCELLED

            # Mark all pending invitations as cancelled
            from typing import cast

            for invitation in cast(List["ProposalInvitation"], self.invitations):
                if invitation.status == InvitationStatus.PENDING:
                    invitation.status = InvitationStatus.CANCELLED

    def expire(self) -> None:
        """Mark proposal as expired."""
        if self.status == ProposalStatus.PENDING:
            self.status = ProposalStatus.EXPIRED

            # Mark all pending invitations as expired
            from typing import cast

            for invitation in cast(List["ProposalInvitation"], self.invitations):
                if invitation.status == InvitationStatus.PENDING:
                    invitation.status = InvitationStatus.EXPIRED

    def get_invitation_for_user(self, user_id: int) -> Optional["ProposalInvitation"]:
        """Get the invitation for a specific user."""
        if self.proposal_type != ProposalType.DIRECT:
            return None

        from typing import cast

        for invitation in cast(List["ProposalInvitation"], self.invitations):
            if invitation.invited_user_id == user_id:
                return invitation
        return None

    def __repr__(self) -> str:
        return (
            f"<MatchProposal {self.proposer_id} -> "
            f"{self.proposal_type.value} at {self.location}>"
        )


class InvitationStatus(Enum):
    """Status of individual invitations within a proposal."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ProposalInvitation(BaseModel, TimestampMixin):
    """Individual invitation within a direct match proposal."""

    __tablename__ = "proposal_invitation"

    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(
        db.Integer,
        db.ForeignKey("match_proposal.id", ondelete="CASCADE"),
        nullable=False,
    )
    invited_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    status = db.Column(
        db.Enum(InvitationStatus), nullable=False, default=InvitationStatus.PENDING
    )
    responded_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    proposal = db.relationship("MatchProposal", back_populates="invitations")
    invited_user = db.relationship("User", foreign_keys=[invited_user_id])

    def accept(self) -> "IndividualMatch":
        """Accept this invitation."""
        if self.status != InvitationStatus.PENDING:
            raise ValueError("Invitation cannot be accepted")

        self.status = InvitationStatus.ACCEPTED
        self.responded_at = utc_now()

        return self.proposal.accept(self.invited_user_id)

    def reject(self) -> None:
        """Reject this invitation."""
        if self.status != InvitationStatus.PENDING:
            raise ValueError("Invitation cannot be rejected")

        self.status = InvitationStatus.REJECTED
        self.responded_at = utc_now()

    def __repr__(self) -> str:
        return (
            f"<ProposalInvitation {self.proposal_id} -> "
            f"{self.invited_user_id}: {self.status.value}>"
        )


class IndividualMatch(BaseModel, TimestampMixin, BaseMatchMixin):
    """
    An individual match between two players (casual match).

    Inherits from BaseMatch to share validation/confirmation workflow
    with tournament matches (Match).
    """

    __tablename__ = "individual_match"

    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(
        db.Integer, db.ForeignKey("match_proposal.id"), nullable=True
    )

    # Players
    player1_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    player2_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # Match details - Location
    # Note: kept separate from proposal for matches created without proposal
    # New: FK to BilliardHall (nullable for backward compatibility)
    billiard_hall_id = db.Column(
        db.Integer, db.ForeignKey("billiard_hall.id", ondelete="SET NULL"), nullable=True
    )
    # Legacy: string-based location (kept for backward compatibility)
    location = db.Column(db.String(255), nullable=True)  # Made nullable - prefer billiard_hall_id
    scheduled_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(
        db.Enum(MatchStatus), nullable=False, default=MatchStatus.SCHEDULED
    )

    # Game configuration
    # Note: duplicated from proposal for matches created without proposal
    # or when proposal is deleted. This denormalization is intentional.
    discipline = db.Column(db.String(50), nullable=False, default="palla_8")
    # Distance: None = free format (no limit), players end match manually
    # Note: No default - service layer should set 5 for normal matches
    distance = db.Column(db.Integer, nullable=True)
    is_race_to = db.Column(db.Boolean, nullable=False, default=True)
    break_rule = db.Column(db.String(20), nullable=False, default="alternate")

    # Multi-set configuration (Phase 6: Frontend Integration)
    is_multi_set = db.Column(db.Boolean, default=False, nullable=False)
    match_distance = db.Column(db.Integer, nullable=True)  # Number of sets
    is_race_to_sets = db.Column(
        db.Boolean, default=True, nullable=True
    )  # Race-to vs exact sets

    # Optional
    notes = db.Column(db.Text, nullable=True)

    # Results
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)  # Renamed from completed_at
    # Scores: racks won (single-set) or sets won (multi-set)
    # See distance_config property for winning threshold logic
    player1_score = db.Column(db.Integer, nullable=False, default=0)
    player2_score = db.Column(db.Integer, nullable=False, default=0)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Validazione finale del risultato
    player1_confirmed = db.Column(db.Boolean, default=False, nullable=False)
    player2_confirmed = db.Column(db.Boolean, default=False, nullable=False)
    player1_confirmed_at = db.Column(db.DateTime, nullable=True)
    player2_confirmed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    proposal = db.relationship("MatchProposal", back_populates="individual_match")
    billiard_hall = db.relationship("BilliardHall", foreign_keys=[billiard_hall_id])
    player1 = db.relationship("User", foreign_keys=[player1_id])
    player2 = db.relationship("User", foreign_keys=[player2_id])
    winner = db.relationship("User", foreign_keys=[winner_id])

    # Individual racks within this match
    racks = db.relationship(  # type: ignore[assignment]
        "IndividualRack",
        back_populates="match",
        cascade="all, delete-orphan",
        order_by="IndividualRack.rack_number",
    )

    # Sets for multi-set matches
    sets = db.relationship(  # type: ignore[assignment]
        "IndividualSet",
        back_populates="match",
        cascade="all, delete-orphan",
        order_by="IndividualSet.set_number",
    )

    @property
    def distance_config(self):
        """Get Distance value object for this individual match.

        Returns unified Distance abstraction supporting both single-set
        and multi-set configurations.

        Returns:
            Distance: Immutable distance configuration, or None for free format
        """
        from models.match.distance import Distance

        # Free format: no distance limit
        if self.distance is None:
            return None

        if not self.is_multi_set:
            # Single-set configuration (backward compatible)
            return Distance(
                racks=self.distance,
                is_race_to_racks=self.is_race_to,
                is_multi_set=False,
                sets=1,
                is_race_to_sets=True,
            )
        else:
            # Multi-set configuration (Phase 6: Frontend Integration)
            return Distance(
                racks=self.distance,
                is_race_to_racks=self.is_race_to,
                is_multi_set=True,
                sets=self.match_distance if self.match_distance else 1,
                is_race_to_sets=self.is_race_to_sets,
            )

    @property
    def rack_score(self):
        """Get score value object for this match.

        For single-set matches, returns RackScore tracking racks won.
        For multi-set matches, returns MatchScore tracking sets won.
        For free format (distance=None), returns None.

        The returned object provides is_complete() and get_winner() methods
        used by BaseMatchMixin for validation workflow.

        Returns:
            RackScore, MatchScore, or None: Current scoring state
        """
        from models.match.score import RackScore, MatchScore

        # Free format: no distance limit, no scoring object
        if self.distance is None:
            return None

        if self.is_multi_set:
            # Multi-set: player1_score/player2_score are SETS won
            return MatchScore(
                distance=self.distance_config,
                player1_sets=self.player1_score,
                player2_sets=self.player2_score,
            )
        else:
            # Single-set: player1_score/player2_score are RACKS won
            return RackScore(
                distance=self.distance_config,
                player1_racks=self.player1_score,
                player2_racks=self.player2_score,
            )

    def can_add_rack(self) -> bool:
        """Check if a rack can be added to the match.

        Overrides BaseMatchMixin to handle free format matches (distance=None).

        Returns:
            bool: True if rack can be added
        """
        from models.status_enum import MatchStatus as SharedMatchStatus

        # Status-based validation
        status_val = self.status.value if hasattr(self.status, "value") else self.status

        allowed_states = [
            SharedMatchStatus.PENDING.value,
            SharedMatchStatus.PLAYING.value,
            SharedMatchStatus.IN_PROGRESS.value,
        ]

        if status_val not in allowed_states:
            return False

        # Free format: can always add racks while in progress
        if self.distance is None:
            return True

        # Normal match: cannot add rack if match is at validation stage
        return not self.is_ready_for_validation()

    def is_ready_for_validation(self) -> bool:
        """Check if match is ready for player confirmation.

        Overrides BaseMatchMixin to handle free format matches (distance=None).

        For free format:
          - Ready when at least one rack played (players end manually)

        For normal matches:
          - Ready when distance is reached

        Returns:
            bool: True if match can be validated
        """
        from models.status_enum import MatchStatus as SharedMatchStatus

        # Status-based validation
        status_val = self.status.value if hasattr(self.status, "value") else self.status

        active_states = [
            SharedMatchStatus.PLAYING.value,
            SharedMatchStatus.IN_PROGRESS.value,
        ]

        if status_val not in active_states:
            return False

        # Free format: ready when at least one rack played
        if self.distance is None:
            total_racks = self.player1_score + self.player2_score
            return total_racks > 0

        # Normal match: check using RackScore/MatchScore
        score = self.rack_score
        if score is None:
            return False
        return score.is_complete()

    def _complete_match_after_confirmation(self) -> None:
        """Complete the match after both players have confirmed.

        Overrides BaseMatchMixin to handle free format matches (distance=None).
        For free format, winner is the player with the higher score.
        """
        # Determine winner
        if self.distance is None:
            # Free format: winner is whoever has more racks
            if self.player1_score > self.player2_score:
                self.winner_id = self.player1_id
            elif self.player2_score > self.player1_score:
                self.winner_id = self.player2_id
            else:
                self.winner_id = None  # Tie
        else:
            # Normal match: use rack_score
            score = self.rack_score
            if score is None:
                self.winner_id = None
            else:
                winner_number = score.get_winner()
                if winner_number is None:
                    self.winner_id = None  # Tie
                else:
                    self.winner_id = (
                        self.player1_id if winner_number == 1 else self.player2_id
                    )

        # Update status to VALIDATED (bilateral confirmation complete)
        self.status = MatchStatus.VALIDATED

        if hasattr(self, "ended_at"):
            self.ended_at = utc_now()

    @property
    def location_display(self) -> str:
        """Get display name for location.

        Returns billiard_hall.name if available, otherwise falls back
        to legacy location string.

        Returns:
            str: Location name for display
        """
        if self.billiard_hall:
            return self.billiard_hall.name
        return self.location or ""

    def start_match(self) -> None:
        """Start the match.

        For multi-set matches, this also creates and starts the first set.
        """
        if self.status != MatchStatus.SCHEDULED:
            raise ValueError("Match cannot be started")

        self.status = MatchStatus.IN_PROGRESS
        self.started_at = utc_now()

        # For multi-set matches, create the first set
        if self.is_multi_set:
            self.start_first_set()

    def add_rack_result(
        self, winner_id: int, rack_number: Optional[int] = None
    ) -> "IndividualRack":
        """Add a rack result to the match.

        For multi-set matches, delegates to the current set which handles
        rack creation, set scores, set completion, and match score updates.

        For single-set matches, directly updates match scores.
        """
        if self.status != MatchStatus.IN_PROGRESS:
            raise ValueError("Cannot add rack result to non-active match")

        if not self.can_add_rack():
            raise ValueError(
                "Cannot add rack: match has reached maximum and needs validation"
            )

        if winner_id not in [self.player1_id, self.player2_id]:
            raise ValueError("Winner must be one of the match players")

        # Multi-set: delegate to current set
        if self.is_multi_set:
            current_set = self.get_current_set()
            if not current_set:
                raise ValueError("No active set in multi-set match")
            return current_set.add_rack_result(winner_id, rack_number)

        # Single-set: existing logic
        # Auto-assign rack number if not provided
        if rack_number is None:
            max_rack = (
                db.session.query(func.max(IndividualRack.rack_number))
                .filter_by(match_id=self.id)
                .scalar()
            )
            rack_number = (max_rack or 0) + 1

        rack = IndividualRack(
            match_id=self.id, rack_number=rack_number, winner_id=winner_id
        )

        db.session.add(rack)

        # Update scores for single-set matches
        if winner_id == self.player1_id:
            self.player1_score += 1
        else:
            self.player2_score += 1

        # Match no longer auto-completes when distance is reached.
        # Instead, is_ready_for_validation() returns True and players must
        # confirm the result via confirm_result(). When both confirm,
        # the match transitions to VALIDATED status.
        # This enables bilateral confirmation for casual matches.

        return rack

    def complete_match(self, winner_id: int) -> None:
        """Complete the match with a winner."""
        if self.status != MatchStatus.IN_PROGRESS:
            raise ValueError("Match is not in progress")

        self.status = MatchStatus.COMPLETED
        self.ended_at = utc_now()
        self.winner_id = winner_id

    def cancel_match(self, reason: Optional[str] = None) -> None:
        """Cancel the match."""
        if self.status == MatchStatus.COMPLETED:
            raise ValueError("Cannot cancel completed match")

        self.status = MatchStatus.CANCELLED
        if reason:
            self.notes = f"Cancelled: {reason}"

    def forfeit_match(self, user_id: int) -> None:
        """Forfeit the match - user loses, opponent wins.

        The forfeiting player keeps their current score (racks already won).
        The opponent receives the winning score (distance).

        Args:
            user_id: ID of player forfeiting

        Raises:
            ValueError: If user is not a player or match cannot be forfeited
        """
        # Validate user is a player
        if user_id not in [self.player1_id, self.player2_id]:
            raise ValueError("User is not a player in this match")

        # Validate match status
        if self.status not in [MatchStatus.SCHEDULED, MatchStatus.IN_PROGRESS]:
            raise ValueError("Can only forfeit scheduled or in-progress matches")

        # Determine winner (opponent of forfeiting player)
        if user_id == self.player1_id:
            self.winner_id = self.player2_id
            # Ensure winner has at least the winning score
            winning_score = self.distance_config.get_winning_racks()
            if self.player2_score < winning_score:
                self.player2_score = winning_score
            # Keep player1_score as-is (racks already won)
        else:
            self.winner_id = self.player1_id
            winning_score = self.distance_config.get_winning_racks()
            if self.player1_score < winning_score:
                self.player1_score = winning_score
            # Keep player2_score as-is (racks already won)

        # Complete the match
        self.status = MatchStatus.COMPLETED
        self.ended_at = utc_now()

    def get_opponent(self, user_id: int) -> Optional["User"]:
        """Get the opponent for a given user."""
        from typing import cast

        if user_id == self.player1_id:
            return cast("User", self.player2)
        elif user_id == self.player2_id:
            return cast("User", self.player1)
        return None

    def get_user_score(self, user_id: int) -> int:
        """Get score for a specific user."""
        if user_id == self.player1_id:
            return self.player1_score
        elif user_id == self.player2_id:
            return self.player2_score
        return 0

    def _remove_last_rack(self, user_id: int) -> None:
        """
        Implementation of BaseMatch abstract method.
        Remove last rack from match (soft delete).

        For multi-set matches, delegates to the current set.
        For single-set matches, directly removes the last rack.
        """
        # Multi-set: delegate to current set
        if self.is_multi_set:
            current_set = self.get_current_set()
            if current_set:
                current_set.remove_last_rack(user_id)
            return

        # Single-set: existing logic
        last_rack = (
            IndividualRack.query.filter_by(match_id=self.id, is_deleted=False)
            .order_by(IndividualRack.rack_number.desc())
            .first()
        )

        if last_rack:
            last_rack.is_deleted = True
            last_rack.removed_by_id = user_id
            last_rack.removed_at = utc_now()

            # Update scores
            if last_rack.winner_id == self.player1_id:
                self.player1_score = max(0, self.player1_score - 1)
            else:
                self.player2_score = max(0, self.player2_score - 1)

    # -------------------------
    # Multi-Set Methods
    # -------------------------
    def get_current_set(self) -> Optional["IndividualSet"]:
        """Get the current active set for multi-set matches.

        Returns:
            The currently playing set, or None if not multi-set or no active set.
        """
        if not self.is_multi_set:
            return None

        # Find the set that is currently playing, or the last completed set
        for s in self.sets:  # type: ignore
            if s.status == "playing":
                return s

        # No playing set - return None (need to start next set)
        return None

    def start_first_set(self) -> "IndividualSet":
        """Create and start the first set for a multi-set match.

        Called automatically when start_match() is invoked on a multi-set match.

        Returns:
            The newly created and started IndividualSet.
        """
        if not self.is_multi_set:
            raise ValueError("Cannot create set for single-set match")

        if len(self.sets) > 0:  # type: ignore
            raise ValueError("First set already exists")

        new_set = IndividualSet(
            match_id=self.id,
            set_number=1,
            distance=self.distance,
            is_race_to=self.is_race_to,
            status="playing",
            started_at=utc_now(),
        )
        # Append to collection to update relationship and cascade persist
        self.sets.append(new_set)  # type: ignore[union-attr]

        return new_set

    def start_next_set(self) -> "IndividualSet":
        """Start the next set in a multi-set match.

        Returns:
            The newly created and started IndividualSet.
        """
        if not self.is_multi_set:
            raise ValueError("Cannot create set for single-set match")

        # Check that current set is completed
        current_set = self.get_current_set()
        if current_set and current_set.status == "playing":
            raise ValueError(f"Set {current_set.set_number} is still in progress")

        # Check if match is already complete
        if self._is_multi_set_complete():
            raise ValueError("Match is already complete")

        # Determine next set number
        next_set_number = len(self.sets) + 1  # type: ignore

        new_set = IndividualSet(
            match_id=self.id,
            set_number=next_set_number,
            distance=self.distance,
            is_race_to=self.is_race_to,
            status="playing",
            started_at=utc_now(),
        )
        # Append to collection to update relationship and cascade persist
        self.sets.append(new_set)  # type: ignore[union-attr]

        return new_set

    def _is_multi_set_complete(self) -> bool:
        """Check if multi-set match is complete.

        Returns:
            True if a player has won enough sets.
        """
        if not self.is_multi_set:
            return False

        match_distance = self.match_distance or 1

        if self.is_race_to_sets:
            return (
                self.player1_score >= match_distance
                or self.player2_score >= match_distance
            )
        else:
            return (self.player1_score + self.player2_score) >= match_distance

    def _check_multi_set_completion(self) -> None:
        """Check and complete match if multi-set threshold is reached."""
        if not self._is_multi_set_complete():
            return

        # Determine winner
        if self.player1_score > self.player2_score:
            self.winner_id = self.player1_id
        else:
            self.winner_id = self.player2_id

        # Note: We don't auto-complete the match status here.
        # The match uses bilateral confirmation flow via is_ready_for_validation().

    def __repr__(self) -> str:
        return (
            f"<IndividualMatch {self.player1_id} vs "
            f"{self.player2_id} at {self.location}>"
        )


class IndividualSetStatus(Enum):
    """Status of an individual set within a multi-set match."""

    PENDING = "pending"
    PLAYING = "playing"
    COMPLETED = "completed"


class IndividualSet(BaseModel, TimestampMixin):
    """A single set within a multi-set individual match.

    Follows the same pattern as Set model for tournament matches.
    """

    __tablename__ = "individual_set"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer,
        db.ForeignKey("individual_match.id", ondelete="CASCADE"),
        nullable=False,
    )
    set_number = db.Column(db.Integer, nullable=False)

    # Configuration
    distance = db.Column(db.Integer, nullable=False)
    is_race_to = db.Column(db.Boolean, default=True, nullable=False)

    # Scores
    player1_racks = db.Column(db.Integer, default=0, nullable=False)
    player2_racks = db.Column(db.Integer, default=0, nullable=False)

    # Result
    status = db.Column(
        db.String(20), default="pending", nullable=False
    )  # pending, playing, completed
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    match = db.relationship("IndividualMatch", back_populates="sets")
    winner = db.relationship("User", foreign_keys=[winner_id])
    racks = db.relationship(
        "IndividualRack",
        back_populates="individual_set",
        cascade="all, delete-orphan",
        order_by="IndividualRack.rack_number",
    )

    __table_args__ = (
        db.UniqueConstraint("match_id", "set_number", name="uq_individual_match_set"),
    )

    def start_set(self) -> None:
        """Start the set."""
        if self.status != "pending":
            raise ValueError("Set can only be started from pending status")

        self.status = "playing"
        self.started_at = utc_now()

    def add_rack_result(
        self,
        winner_id: int,
        rack_number: Optional[int] = None,
    ) -> "IndividualRack":
        """Add a rack result to this set."""
        if self.status != "playing":
            raise ValueError("Cannot add rack result to non-playing set")

        if winner_id not in [self.match.player1_id, self.match.player2_id]:
            raise ValueError("Winner must be one of the match players")

        # Auto-assign rack number if not provided
        # Note: UNIQUE constraint is on (match_id, rack_number), so we must
        # find max across the entire match, not just this set
        if rack_number is None:
            max_rack = (
                db.session.query(func.max(IndividualRack.rack_number))
                .filter_by(match_id=self.match_id)
                .scalar()
            )
            rack_number = (max_rack or 0) + 1

        # Create rack record
        rack = IndividualRack(
            match_id=self.match_id,
            individual_set_id=self.id,
            rack_number=rack_number,
            winner_id=winner_id,
        )

        db.session.add(rack)

        # Update set scores
        if winner_id == self.match.player1_id:
            self.player1_racks += 1
        else:
            self.player2_racks += 1

        # Check if set is completed
        self._check_set_completion()

        return rack

    def _check_set_completion(self) -> None:
        """Check if set is completed based on scoring rules."""
        if self.is_race_to:
            # Race to X: first to reach distance wins
            if self.player1_racks >= self.distance:
                self._complete_set(self.match.player1_id)
            elif self.player2_racks >= self.distance:
                self._complete_set(self.match.player2_id)
        else:
            # Fixed distance: play exactly distance racks
            total_racks = self.player1_racks + self.player2_racks
            if total_racks >= self.distance:
                if self.player1_racks > self.player2_racks:
                    self._complete_set(self.match.player1_id)
                elif self.player2_racks > self.player1_racks:
                    self._complete_set(self.match.player2_id)
                # Tie - continue playing (sudden death)

    def _complete_set(self, winner_id: int) -> None:
        """Complete the set with a winner."""
        self.status = "completed"
        self.completed_at = utc_now()
        self.winner_id = winner_id

        # Update match set scores
        if winner_id == self.match.player1_id:
            self.match.player1_score += 1
        else:
            self.match.player2_score += 1

        # Check if match is completed
        self.match._check_multi_set_completion()

    def is_completed(self) -> bool:
        """Check if set is completed."""
        return self.status == "completed"

    def remove_last_rack(self, user_id: int) -> Optional["IndividualRack"]:
        """Remove the last rack from this set (soft delete).

        Args:
            user_id: ID of user removing the rack

        Returns:
            The removed rack, or None if no racks to remove
        """
        # Find last rack in this set
        last_rack = (
            IndividualRack.query.filter_by(individual_set_id=self.id, is_deleted=False)
            .order_by(IndividualRack.rack_number.desc())
            .first()
        )

        if not last_rack:
            return None

        # Soft delete the rack
        last_rack.is_deleted = True
        last_rack.removed_by_id = user_id
        last_rack.removed_at = utc_now()

        # Update set scores
        if last_rack.winner_id == self.match.player1_id:
            self.player1_racks = max(0, self.player1_racks - 1)
        else:
            self.player2_racks = max(0, self.player2_racks - 1)

        # If set was completed, reopen it
        if self.status == "completed":
            self.status = "playing"
            self.completed_at = None

            # Also revert the match set score that was incremented when set completed
            if self.winner_id == self.match.player1_id:
                self.match.player1_score = max(0, self.match.player1_score - 1)
            else:
                self.match.player2_score = max(0, self.match.player2_score - 1)

            self.winner_id = None

        return last_rack

    @property
    def distance_config(self):
        """Get Distance value object for this set."""
        from models.match.distance import Distance

        return Distance(
            racks=self.distance,
            is_race_to_racks=self.is_race_to,
            is_multi_set=False,
            sets=1,
            is_race_to_sets=True,
        )

    def __repr__(self) -> str:
        return f"<IndividualSet {self.match_id}-{self.set_number}: {self.player1_racks}-{self.player2_racks}>"


class IndividualRack(BaseModel, TimestampMixin):
    """A single rack within an individual match.

    For multi-set matches, racks belong to a specific IndividualSet.
    For single-set matches, individual_set_id is NULL.
    """

    __tablename__ = "individual_rack"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer,
        db.ForeignKey("individual_match.id", ondelete="CASCADE"),
        nullable=False,
    )
    # FK to set (nullable for backward compatibility with single-set matches)
    individual_set_id = db.Column(
        db.Integer,
        db.ForeignKey("individual_set.id", ondelete="CASCADE"),
        nullable=True,
    )
    rack_number = db.Column(db.Integer, nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Optional details
    break_player_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Log delle operazioni per tracciare chi ha aggiunto/rimosso rack
    added_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    added_at = db.Column(db.DateTime, nullable=True, default=utc_now)
    removed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    removed_at = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(
        db.Boolean, default=False, nullable=False
    )  # Soft delete per il log

    # Relationships
    match = db.relationship("IndividualMatch", back_populates="racks")
    individual_set = db.relationship("IndividualSet", back_populates="racks")
    winner = db.relationship("User", foreign_keys=[winner_id])
    break_player = db.relationship("User", foreign_keys=[break_player_id])
    added_by = db.relationship("User", foreign_keys=[added_by_id])
    removed_by = db.relationship("User", foreign_keys=[removed_by_id])

    # Unique constraint: one rack per number per match
    __table_args__ = (
        db.UniqueConstraint("match_id", "rack_number", name="uq_match_rack"),
    )

    def __repr__(self) -> str:
        return (
            f"<IndividualRack {self.match_id}-{self.rack_number}: "
            f"winner={self.winner_id}>"
        )


class PlayerAvailability(BaseModel, TimestampMixin):
    """Player availability preferences for match locations.

    DEPRECATED: This model uses string-based location for legacy compatibility.
    For new features, use UserLocationAvailability from models/location/models.py
    which uses proper billiard_hall_id FK reference.

    Migration path:
    1. Use UserLocationAvailability for new availability records
    2. Gradually migrate existing data via admin tools
    3. Eventually deprecate this table
    """

    __tablename__ = "player_availability"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    # Legacy: string-based location. Prefer UserLocationAvailability.billiard_hall_id
    location = db.Column(db.String(255), nullable=False)

    # Availability preferences
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    preferred_days = db.Column(
        db.String(20), nullable=True
    )  # JSON array of weekday numbers
    preferred_times = db.Column(db.String(50), nullable=True)  # e.g., "18:00-22:00"

    # Relationships
    user = db.relationship("User")

    # Unique constraint: one availability record per user per location
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "location", name="uq_user_location_availability"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PlayerAvailability {self.user_id} -> {self.location}: "
            f"{self.is_available}>"
        )
