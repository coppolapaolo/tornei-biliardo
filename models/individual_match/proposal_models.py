"""
Module: models/individual_match/proposal_models.py
Purpose: Proposal-related models for individual match system
Split from: models/individual_match/models.py (P3a refactoring)
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING
from enum import Enum

from ..base import db, BaseModel, TimestampMixin, utc_now
from ..status_enum import Discipline

if TYPE_CHECKING:
    from .match_models import IndividualMatch


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


class InvitationStatus(Enum):
    """Status of individual invitations within a proposal."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class MatchProposal(BaseModel):
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
        db.Integer,
        db.ForeignKey("billiard_hall.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Legacy: string-based location (kept for backward compatibility, will be deprecated)
    location = db.Column(
        db.String(255), nullable=True
    )  # Made nullable - prefer billiard_hall_id
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
        """Accept the proposal and create an individual match.

        WARNING — Contract (ADR-025): this is a raw model-layer method. It
        creates an ``IndividualMatch`` row subject to the
        ``uq_individual_match_proposal`` UNIQUE constraint. In a TOCTOU race
        (two acceptances of the same proposal) the constraint fires at flush
        time and surfaces as ``sqlalchemy.exc.IntegrityError`` here.

        Callers are responsible for wrapping this call in the savepoint +
        ``ValueError`` translation pattern (see
        ``ProposalService.accept_proposal`` for a reference
        implementation). The savepoint pattern is intentionally NOT applied
        inside this model method to keep session/transaction machinery out of
        the domain layer.
        """
        from .match_models import IndividualMatch

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


class ProposalInvitation(BaseModel):
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

    # Prevents duplicate invites of same user to same proposal (TOCTOU guard).
    __table_args__ = (
        db.UniqueConstraint(
            "proposal_id", "invited_user_id", name="uq_proposal_invitation_user"
        ),
    )

    def accept(self) -> "IndividualMatch":
        """Accept this invitation.

        WARNING — Contract (ADR-025): this is a raw model-layer method. It
        delegates to ``MatchProposal.accept()`` which creates an
        ``IndividualMatch`` row subject to the ``uq_individual_match_proposal``
        UNIQUE constraint. In a TOCTOU race (two acceptances of the same
        proposal) the constraint fires at flush time and surfaces as
        ``sqlalchemy.exc.IntegrityError`` here.

        Callers are responsible for wrapping this call in the savepoint +
        ``ValueError`` translation pattern (see
        ``ProposalService.accept_proposal`` for a reference
        implementation). The savepoint pattern is intentionally NOT applied
        inside this model method to keep session/transaction machinery out of
        the domain layer.
        """

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
