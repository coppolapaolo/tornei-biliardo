"""Integration tests for Use Case 6: Individual match proposals.

Tests focused workflow aspects:
- Player can propose individual match to another player
- Proposal creation with invitations
- Match proposal cancellation and rejection
- Basic proposal querying

Note: Full accept/play workflow has session isolation issues with @transactional
and SQLite parallel testing. Those workflows are tested via unit tests.
"""

import pytest
from datetime import datetime, timedelta
import uuid

from models import User
from models.user.role_enum import UserRole
from models.individual_match.models import (
    MatchProposal,
    ProposalInvitation,
    ProposalType,
    ProposalStatus,
    InvitationStatus,
)
from models.individual_match.services import IndividualMatchService


@pytest.mark.integration
class TestUseCaseIndividualMatchProposal:
    """Test Use Case 6: Individual match proposal workflow."""

    @pytest.fixture
    def player1(self, db_session) -> User:
        """Create first player for test."""
        unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player1_{unique_id}",
            email=f"player1_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        db_session.add(player)
        db_session.commit()
        return player

    @pytest.fixture
    def player2(self, db_session) -> User:
        """Create second player for test."""
        unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player2_{unique_id}",
            email=f"player2_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        db_session.add(player)
        db_session.commit()
        return player

    @pytest.fixture
    def director_user(self, db_session) -> User:
        """Create director user for test."""
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()
        return director

    def test_player_can_propose_individual_match(
        self, player1: User, player2: User, db_session
    ):
        """Test player can propose individual match to another player.

        UC6: Player invites another player to individual match.
        """
        # Create direct proposal
        proposal = IndividualMatchService.create_direct_proposal(
            proposer_id=player1.id,
            invited_user_ids=[player2.id],
            location="Test Billiard Hall",
            scheduled_at=datetime.utcnow() + timedelta(days=1),
            discipline="palla_8",
            distance=5,
            is_race_to=True,
            description="Friendly match",
        )

        db_session.commit()

        assert proposal is not None
        assert proposal.proposer_id == player1.id
        assert proposal.proposal_type == ProposalType.DIRECT
        assert proposal.status == ProposalStatus.PENDING

        # Check invitation was created
        invitation = ProposalInvitation.query.filter_by(
            proposal_id=proposal.id,
            invited_user_id=player2.id,
        ).first()

        assert invitation is not None
        assert invitation.status == InvitationStatus.PENDING

    def test_proposal_has_correct_configuration(
        self, player1: User, player2: User, db_session
    ):
        """Test proposal stores game configuration correctly.

        UC6: Proposal includes discipline, distance, and other settings.
        """
        scheduled_time = datetime.utcnow() + timedelta(days=2)
        proposal = IndividualMatchService.create_direct_proposal(
            proposer_id=player1.id,
            invited_user_ids=[player2.id],
            location="Championship Venue",
            scheduled_at=scheduled_time,
            discipline="palla_9",
            distance=7,
            is_race_to=True,
            description="Practice for tournament",
        )

        db_session.commit()

        # Verify configuration
        assert proposal.discipline == "palla_9"
        assert proposal.distance == 7
        assert proposal.is_race_to is True
        assert proposal.location == "Championship Venue"
        assert proposal.description == "Practice for tournament"

    def test_director_can_propose_match(
        self, director_user: User, player1: User, player2: User, db_session
    ):
        """Test director can propose match between players.

        UC6 variant: Director proposes match.
        """
        # Director creates direct proposal inviting both players
        proposal = IndividualMatchService.create_direct_proposal(
            proposer_id=director_user.id,
            invited_user_ids=[player1.id, player2.id],
            location="Competition Venue",
            scheduled_at=datetime.utcnow() + timedelta(days=1),
            discipline="palla_9",
            distance=7,
            is_race_to=True,
            description="Director arranged match",
        )

        db_session.commit()

        assert proposal is not None
        assert proposal.proposer_id == director_user.id

        # Both players should have invitations
        inv1 = ProposalInvitation.query.filter_by(
            proposal_id=proposal.id,
            invited_user_id=player1.id,
        ).first()
        inv2 = ProposalInvitation.query.filter_by(
            proposal_id=proposal.id,
            invited_user_id=player2.id,
        ).first()

        assert inv1 is not None
        assert inv2 is not None


@pytest.mark.integration
class TestUseCaseIndividualMatchCancellation:
    """Test Use Case 6: Match cancellation scenarios."""

    @pytest.fixture
    def player1(self, db_session) -> User:
        """Create first player for test."""
        unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player1_{unique_id}",
            email=f"player1_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        db_session.add(player)
        db_session.commit()
        return player

    @pytest.fixture
    def player2(self, db_session) -> User:
        """Create second player for test."""
        unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player2_{unique_id}",
            email=f"player2_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        db_session.add(player)
        db_session.commit()
        return player

    def test_proposer_can_cancel_proposal(
        self, player1: User, player2: User, db_session
    ):
        """Test proposer can cancel pending proposal."""
        # Create proposal
        proposal = IndividualMatchService.create_direct_proposal(
            proposer_id=player1.id,
            invited_user_ids=[player2.id],
            location="Test Venue",
            scheduled_at=datetime.utcnow() + timedelta(days=1),
            discipline="palla_8",
            distance=5,
            is_race_to=True,
        )

        db_session.commit()

        # Proposer cancels
        IndividualMatchService.cancel_proposal(
            user_id=player1.id,
            proposal_id=proposal.id,
        )

        db_session.commit()

        # Check proposal cancelled
        db_session.refresh(proposal)
        assert proposal.status == ProposalStatus.CANCELLED

    def test_proposal_expiration_check(
        self, player1: User, player2: User, db_session
    ):
        """Test proposal correctly identifies expired status."""
        # Create proposal with past expiration
        proposal = IndividualMatchService.create_direct_proposal(
            proposer_id=player1.id,
            invited_user_ids=[player2.id],
            location="Test Venue",
            scheduled_at=datetime.utcnow() + timedelta(days=1),
            expires_at=datetime.utcnow() - timedelta(hours=1),  # Already expired
            discipline="palla_8",
            distance=5,
            is_race_to=True,
        )

        db_session.commit()

        # Check expiration
        assert proposal.is_expired() is True
        # User should not be able to accept expired proposal
        assert proposal.can_be_accepted_by(player2.id) is False


@pytest.mark.integration
class TestUseCaseOpenProposal:
    """Test Use Case 6: Open match proposals."""

    @pytest.fixture
    def player1(self, db_session) -> User:
        """Create player for test."""
        unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player1_{unique_id}",
            email=f"player1_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        db_session.add(player)
        db_session.commit()
        return player

    def test_player_can_create_open_proposal(
        self, player1: User, db_session
    ):
        """Test player can create open proposal for any opponent.

        UC6 variant: Open proposal visible to community.
        """
        proposal = IndividualMatchService.create_open_proposal(
            proposer_id=player1.id,
            location="Community Hall",
            scheduled_at=datetime.utcnow() + timedelta(days=1),
            discipline="palla_8",
            distance=5,
            is_race_to=True,
            description="Looking for opponent",
        )

        db_session.commit()

        assert proposal is not None
        assert proposal.proposer_id == player1.id
        assert proposal.proposal_type == ProposalType.OPEN
        assert proposal.status == ProposalStatus.PENDING

        # Open proposals should have no invitations
        invitations = ProposalInvitation.query.filter_by(
            proposal_id=proposal.id
        ).all()
        assert len(invitations) == 0
