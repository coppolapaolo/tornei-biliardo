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

from ..base import db, BaseModel, TimestampMixin

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


class MatchStatus(Enum):
    """Status of individual matches."""

    SCHEDULED = "scheduled"  # Match is scheduled
    IN_PROGRESS = "in_progress"  # Match is being played
    COMPLETED = "completed"  # Match is finished
    CANCELLED = "cancelled"  # Match was cancelled


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

    # Match details
    location = db.Column(db.String(255), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

    # Game configuration
    discipline = db.Column(db.String(50), nullable=False, default="palla_8")
    distance = db.Column(db.Integer, nullable=False, default=5)  # Racks to win
    best_of = db.Column(db.Boolean, nullable=False, default=True)
    break_rule = db.Column(db.String(20), nullable=False, default="alternate")

    # Optional details
    description = db.Column(db.Text, nullable=True)
    entry_fee = db.Column(db.Numeric(10, 2), nullable=True)

    # Result tracking
    accepted_by_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    accepted_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    proposer = db.relationship("User", foreign_keys=[proposer_id])
    accepted_by = db.relationship("User", foreign_keys=[accepted_by_id])

    # Direct invitations (for DIRECT proposals)
    invitations = db.relationship(  # type: ignore[assignment]
        "ProposalInvitation", back_populates="proposal", cascade="all, delete-orphan"
    )

    # Resulting match (if accepted)
    individual_match = db.relationship(
        "IndividualMatch", back_populates="proposal", uselist=False
    )

    def is_expired(self) -> bool:
        """Check if proposal has expired."""
        return datetime.utcnow() > self.expires_at

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
        self.accepted_at = datetime.utcnow()

        # Create the individual match
        individual_match = IndividualMatch(
            proposal_id=self.id,
            player1_id=self.proposer_id,
            player2_id=user_id,
            location=self.location,
            scheduled_at=self.scheduled_at,
            discipline=self.discipline,
            distance=self.distance,
            best_of=self.best_of,
            break_rule=self.break_rule,
            entry_fee=self.entry_fee,
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
        return f"<MatchProposal {self.proposer_id} -> {self.proposal_type.value} at {self.location}>"


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
        self.responded_at = datetime.utcnow()

        return self.proposal.accept(self.invited_user_id)

    def reject(self) -> None:
        """Reject this invitation."""
        if self.status != InvitationStatus.PENDING:
            raise ValueError("Invitation cannot be rejected")

        self.status = InvitationStatus.REJECTED
        self.responded_at = datetime.utcnow()

    def __repr__(self) -> str:
        return f"<ProposalInvitation {self.proposal_id} -> {self.invited_user_id}: {self.status.value}>"


class IndividualMatch(BaseModel, TimestampMixin):
    """An individual match between two players."""

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

    # Match details
    location = db.Column(db.String(255), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(
        db.Enum(MatchStatus), nullable=False, default=MatchStatus.SCHEDULED
    )

    # Game configuration
    discipline = db.Column(db.String(50), nullable=False, default="palla_8")
    distance = db.Column(db.Integer, nullable=False, default=5)
    best_of = db.Column(db.Boolean, nullable=False, default=True)
    break_rule = db.Column(db.String(20), nullable=False, default="alternate")

    # Optional
    entry_fee = db.Column(db.Numeric(10, 2), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Results
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    player1_score = db.Column(db.Integer, nullable=False, default=0)
    player2_score = db.Column(db.Integer, nullable=False, default=0)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Relationships
    proposal = db.relationship("MatchProposal", back_populates="individual_match")
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

    def start_match(self) -> None:
        """Start the match."""
        if self.status != MatchStatus.SCHEDULED:
            raise ValueError("Match cannot be started")

        self.status = MatchStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()

    def add_rack_result(
        self, winner_id: int, rack_number: Optional[int] = None
    ) -> "IndividualRack":
        """Add a rack result to the match."""
        if self.status != MatchStatus.IN_PROGRESS:
            raise ValueError("Cannot add rack result to non-active match")

        if winner_id not in [self.player1_id, self.player2_id]:
            raise ValueError("Winner must be one of the match players")

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

        # Update scores
        if winner_id == self.player1_id:
            self.player1_score += 1
        else:
            self.player2_score += 1

        # Check if match is completed
        if self.best_of:
            # Best of X: first to reach distance wins
            target_score = self.distance
        else:
            # Fixed distance: play exactly distance racks
            target_score = (self.distance + 1) // 2  # Majority

        if self.player1_score >= target_score:
            self.complete_match(self.player1_id)
        elif self.player2_score >= target_score:
            self.complete_match(self.player2_id)
        elif (
            not self.best_of
            and self.player1_score + self.player2_score >= self.distance
        ):
            # Fixed distance completed
            winner = (
                self.player1_id
                if self.player1_score > self.player2_score
                else self.player2_id
            )
            self.complete_match(winner)

        return rack

    def complete_match(self, winner_id: int) -> None:
        """Complete the match with a winner."""
        if self.status != MatchStatus.IN_PROGRESS:
            raise ValueError("Match is not in progress")

        self.status = MatchStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.winner_id = winner_id

    def cancel_match(self, reason: Optional[str] = None) -> None:
        """Cancel the match."""
        if self.status == MatchStatus.COMPLETED:
            raise ValueError("Cannot cancel completed match")

        self.status = MatchStatus.CANCELLED
        if reason:
            self.notes = f"Cancelled: {reason}"

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

    def __repr__(self) -> str:
        return f"<IndividualMatch {self.player1_id} vs {self.player2_id} at {self.location}>"


class IndividualRack(BaseModel, TimestampMixin):
    """A single rack within an individual match."""

    __tablename__ = "individual_rack"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(
        db.Integer,
        db.ForeignKey("individual_match.id", ondelete="CASCADE"),
        nullable=False,
    )
    rack_number = db.Column(db.Integer, nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Optional details
    break_player_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Relationships
    match = db.relationship("IndividualMatch", back_populates="racks")
    winner = db.relationship("User", foreign_keys=[winner_id])
    break_player = db.relationship("User", foreign_keys=[break_player_id])

    # Unique constraint: one rack per number per match
    __table_args__ = (
        db.UniqueConstraint("match_id", "rack_number", name="uq_match_rack"),
    )

    def __repr__(self) -> str:
        return f"<IndividualRack {self.match_id}-{self.rack_number}: winner={self.winner_id}>"


class PlayerAvailability(BaseModel, TimestampMixin):
    """Player availability preferences for match locations."""

    __tablename__ = "player_availability"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
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
        return f"<PlayerAvailability {self.user_id} -> {self.location}: {self.is_available}>"
