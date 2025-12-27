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

    # Match details
    location = db.Column(
        db.String(255), nullable=False
    )  # TODO: da modificare con un riferimento alle location nel DB
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
    )  # TODO: verificare impatto funzionamento app
    description = db.Column(db.Text, nullable=True)
    entry_fee = db.Column(db.Numeric(10, 2), nullable=True, default=0)

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

    # Direct invitations (for DIRECT proposals)
    invitations = db.relationship(  # type: ignore[assignment]
        "ProposalInvitation", back_populates="proposal", cascade="all, delete-orphan"
    )

    # Resulting match (if accepted)
    individual_match = db.relationship(
        "IndividualMatch", back_populates="proposal", uselist=False
    )

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
            is_race_to=self.is_race_to,
            break_rule=self.break_rule,
            entry_fee=self.entry_fee,
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
        self.responded_at = datetime.utcnow()

        return self.proposal.accept(self.invited_user_id)

    def reject(self) -> None:
        """Reject this invitation."""
        if self.status != InvitationStatus.PENDING:
            raise ValueError("Invitation cannot be rejected")

        self.status = InvitationStatus.REJECTED
        self.responded_at = datetime.utcnow()

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

    # Match details
    # TODO: e' necessario? non puo' fare riferimento alla location di proposal?
    location = db.Column(db.String(255), nullable=False)
    # TODO: anche questo, credo, puo' fare riferimento al relativo
    # campo di proposal
    scheduled_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(
        db.Enum(MatchStatus), nullable=False, default=MatchStatus.SCHEDULED
    )

    # Game configuration
    # TODO: tutti questi sei da discipline fino a notes possono fare
    # riferimento a proposal. perche' duplicare?
    discipline = db.Column(db.String(50), nullable=False, default="palla_8")
    distance = db.Column(db.Integer, nullable=False, default=5)
    is_race_to = db.Column(db.Boolean, nullable=False, default=True)
    break_rule = db.Column(db.String(20), nullable=False, default="alternate")

    # Multi-set configuration (Phase 6: Frontend Integration)
    is_multi_set = db.Column(db.Boolean, default=False, nullable=False)
    match_distance = db.Column(db.Integer, nullable=True)  # Number of sets
    is_race_to_sets = db.Column(
        db.Boolean, default=True, nullable=True
    )  # Race-to vs exact sets

    # Optional
    entry_fee = db.Column(db.Numeric(10, 2), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Results
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    # TODO: lo score, se la distanza diventa un oggetto complesso con i set,
    # diventa anch'esso un oggetto complesso? Questo vale in generale,
    # non solo per i match individuali
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

    @property
    def distance_config(self):
        """Get Distance value object for this individual match.

        Returns unified Distance abstraction supporting both single-set
        and multi-set configurations.

        Returns:
            Distance: Immutable distance configuration
        """
        from models.match.distance import Distance

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
        """Get RackScore value object for this match.

        Returns current rack scoring.

        Returns:
            RackScore: Current rack scoring
        """
        from models.match.score import RackScore

        return RackScore(
            distance=self.distance_config,
            player1_racks=self.player1_score,
            player2_racks=self.player2_score,
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

        if not self.can_add_rack():
            raise ValueError(
                "Cannot add rack: match has reached maximum and needs validation"
            )

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
        # TODO: forse questo va delegato ad un servizio che astrae
        # il punteggio, ma non mi e' chiaro come modellare
        if winner_id == self.player1_id:
            self.player1_score += 1
        else:
            self.player2_score += 1

        # Check if match is completed
        # Use Distance object logic for unified behavior
        dist = self.distance_config
        target_racks = dist.get_winning_racks()

        if self.player1_score >= target_racks:
            self.complete_match(self.player1_id)
        elif self.player2_score >= target_racks:
            self.complete_match(self.player2_id)
        elif not dist.is_race_to_racks and (self.player1_score + self.player2_score >= dist.racks):
            # Exactly N mode completed (use majority as winner for now if not already decided)
            winner = self.player1_id if self.player1_score > self.player2_score else self.player2_id
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

    def _remove_last_rack(self, user_id: int) -> None:
        """
        Implementation of BaseMatch abstract method.
        Remove last rack from match (soft delete).
        """
        # Remove last rack (logically delete it)
        last_rack = (
            IndividualRack.query.filter_by(match_id=self.id, is_deleted=False)
            .order_by(IndividualRack.rack_number.desc())
            .first()
        )

        if last_rack:
            last_rack.is_deleted = True
            last_rack.removed_by_id = user_id
            last_rack.removed_at = datetime.utcnow()

            # Update scores
            if last_rack.winner_id == self.player1_id:
                self.player1_score = max(0, self.player1_score - 1)
            else:
                self.player2_score = max(0, self.player2_score - 1)

    def __repr__(self) -> str:
        return (
            f"<IndividualMatch {self.player1_id} vs "
            f"{self.player2_id} at {self.location}>"
        )


# TODO: non sono convintissimo che serva questo e non sia sufficiente
# un Rack normale
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

    # Log delle operazioni per tracciare chi ha aggiunto/rimosso rack
    added_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    added_at = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)
    removed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    removed_at = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(
        db.Boolean, default=False, nullable=False
    )  # Soft delete per il log

    # Relationships
    match = db.relationship("IndividualMatch", back_populates="racks")
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
    """Player availability preferences for match locations."""

    __tablename__ = "player_availability"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    location = db.Column(
        db.String(255), nullable=False
    )  # TODO: deve essere collegato alle location, non una stringa libera

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
