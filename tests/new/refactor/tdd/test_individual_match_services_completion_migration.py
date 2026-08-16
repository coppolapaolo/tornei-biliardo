"""
TDD Tests for IndividualMatchServices Transaction Migration - Completion (Task 1.1 Final
    Phase)

Incremental migration strategy for remaining 14 commit calls in IndividualMatchServices:

Phase 1: Core Proposal Lifecycle (5 methods)
- accept_proposal() - line 423
- reject_invitation() - line 435
- cancel_proposal() - line 455
- invite_player_to_match() - line 307
- respond_to_invitation() - line 330

Phase 2: Match Execution Lifecycle (4 methods)
- start_match() - line 650
- add_rack_result() - line 667
- submit_rack_result() - line 553
- complete_match() - line 684
- cancel_match() - line 703

Phase 3: Utility/Batch/Availability (4 methods)
- set_player_availability() - line 735
- update_user_availability() - line 576
- expire_old_proposals() - line 785
- _expire_pending_proposals() - line 846

Strategy: Red-Green-Refactor TDD for each phase
"""

import pytest
from datetime import timedelta

from models import db
from models.user.models import User
from models.user.role_enum import UserRole
from models.individual_match.models import (
    MatchProposal,
    ProposalInvitation,
    IndividualMatch,
    IndividualRack,
    ProposalType,
    ProposalStatus,
    MatchStatus,
    InvitationStatus,
)
from models.individual_match.services import IndividualMatchService
from models.base import utc_now


class TestIndividualMatchServicesTransactionMigrationPhase1:
    """TDD tests for @transactional migration - Phase 1 (Core Proposal Lifecycle)."""

    @pytest.fixture
    def test_users_phase1(self, app):
        """Create test users for proposal lifecycle tests."""
        with app.app_context():
            proposer = User(
                username="test_proposer_phase1",
                email="proposer_p1@test.com",
                role=UserRole.PLAYER.value,
            )
            proposer.set_password("testpass")

            invitee = User(
                username="test_invitee_phase1",
                email="invitee_p1@test.com",
                role=UserRole.PLAYER.value,
            )
            invitee.set_password("testpass")

            db.session.add(proposer)
            db.session.add(invitee)
            db.session.commit()

            yield proposer, invitee

            db.session.delete(proposer)
            db.session.delete(invitee)
            db.session.commit()

    def test_accept_proposal_transaction_behavior(self, app, test_users_phase1):
        """
        RED: Test current accept_proposal behavior with direct commit.

        Expected behavior:
        - Accepts match proposal and creates IndividualMatch
        - Returns IndividualMatch object
        - Handles transaction internally (commit at line 423)
        """
        proposer, invitee = test_users_phase1

        with app.app_context():
            # Arrange: create test proposal with required invitation
            proposal = MatchProposal(
                proposer_id=proposer.id,
                proposal_type=ProposalType.DIRECT,
                location="Test Hall Phase1",
                discipline="8ball",
                distance=5,
                scheduled_at=utc_now() + timedelta(hours=2),
                expires_at=utc_now() + timedelta(hours=1),
                description="Test proposal for accept",
            )
            db.session.add(proposal)
            db.session.flush()

            # For DIRECT proposals, create required invitation
            invitation = ProposalInvitation(
                proposal_id=proposal.id,
                invited_user_id=invitee.id,
                status=InvitationStatus.PENDING,
            )
            db.session.add(invitation)
            db.session.commit()

            # Act: accept proposal
            individual_match = IndividualMatchService.accept_proposal(
                user_id=invitee.id, proposal_id=proposal.id
            )

            # Assert: match was created and committed
            assert individual_match is not None
            assert (
                individual_match.player1_id == proposer.id
                or individual_match.player2_id == proposer.id
            )
            assert (
                individual_match.player1_id == invitee.id
                or individual_match.player2_id == invitee.id
            )

            # Verify it exists in database (transaction was committed)
            db_match = db.session.get(IndividualMatch, individual_match.id)
            assert db_match is not None
            assert db_match.status == MatchStatus.SCHEDULED

            # Cleanup
            db.session.delete(individual_match)
            db.session.delete(invitation)
            db.session.delete(proposal)
            db.session.commit()

    def test_reject_invitation_transaction_behavior(self, app, test_users_phase1):
        """
        RED: Test current reject_invitation behavior with direct commit.

        Expected behavior:
        - Rejects direct invitation
        - Updates invitation status
        - Handles transaction internally (commit at line 435)
        """
        proposer, invitee = test_users_phase1

        with app.app_context():
            # Arrange: create proposal and invitation
            proposal = MatchProposal(
                proposer_id=proposer.id,
                proposal_type=ProposalType.DIRECT,
                location="Test Hall Reject",
                discipline="9ball",
                distance=3,
                scheduled_at=utc_now() + timedelta(hours=3),
                expires_at=utc_now() + timedelta(hours=1),
                description="Test proposal for rejection",
            )
            db.session.add(proposal)
            db.session.flush()

            invitation = ProposalInvitation(
                proposal_id=proposal.id,
                invited_user_id=invitee.id,
                status=InvitationStatus.PENDING,
            )
            db.session.add(invitation)
            db.session.commit()

            # Act: reject invitation
            IndividualMatchService.reject_invitation(
                user_id=invitee.id, proposal_id=proposal.id
            )

            # Assert: invitation was rejected and committed
            # Verify changes exist in database (transaction was committed)
            db_invitation = db.session.get(ProposalInvitation, invitation.id)
            assert db_invitation is not None
            assert db_invitation.status == InvitationStatus.REJECTED

            # Cleanup
            db.session.delete(invitation)
            db.session.delete(proposal)
            db.session.commit()


class TestIndividualMatchServicesTransactionMigrationPhase2:
    """TDD tests for @transactional migration - Phase 2 (Match Execution Lifecycle)."""

    @pytest.fixture
    def test_users_phase2(self, app):
        """Create test users for match execution lifecycle tests."""
        with app.app_context():
            player1 = User(
                username="test_player1_phase2",
                email="player1_p2@test.com",
                role=UserRole.PLAYER.value,
            )
            player1.set_password("testpass")

            player2 = User(
                username="test_player2_phase2",
                email="player2_p2@test.com",
                role=UserRole.PLAYER.value,
            )
            player2.set_password("testpass")

            db.session.add(player1)
            db.session.add(player2)
            db.session.commit()

            yield player1, player2

            db.session.delete(player1)
            db.session.delete(player2)
            db.session.commit()

    @pytest.fixture
    def test_match_phase2(self, app, test_users_phase2):
        """Create test match for match execution tests."""
        player1, player2 = test_users_phase2

        with app.app_context():
            # Create accepted proposal and match
            proposal = MatchProposal(
                proposer_id=player1.id,
                proposal_type=ProposalType.OPEN,
                location="Test Hall Phase2",
                discipline="9ball",
                distance=7,
                scheduled_at=utc_now() + timedelta(hours=2),
                expires_at=utc_now() + timedelta(hours=1),
                description="Test match for execution",
            )
            db.session.add(proposal)
            db.session.flush()

            individual_match = IndividualMatch(
                proposal_id=proposal.id,
                player1_id=player1.id,
                player2_id=player2.id,
                location=proposal.location,
                scheduled_at=proposal.scheduled_at,
                discipline=proposal.discipline,
                distance=proposal.distance,
                is_race_to=proposal.is_race_to,
                break_rule=proposal.break_rule,
            )
            db.session.add(individual_match)
            db.session.commit()

            yield individual_match, proposal

            # Cleanup racks first due to foreign key constraints
            for rack in individual_match.racks:
                db.session.delete(rack)
            db.session.delete(individual_match)
            db.session.delete(proposal)
            db.session.commit()

    def test_start_match_transaction_behavior(self, app, test_match_phase2):
        """
        RED: Test current start_match behavior with direct commit.

        Expected behavior:
        - Updates match status to IN_PROGRESS
        - Sets started_at timestamp
        - Handles transaction internally (commit at line 650)
        """
        individual_match, proposal = test_match_phase2

        with app.app_context():
            assert individual_match.status == MatchStatus.SCHEDULED

            # Act: start match
            IndividualMatchService.start_match(
                individual_match.id, individual_match.player1_id
            )

            # Assert: match was started and committed
            # Verify changes exist in database (transaction was committed)
            db_match = db.session.get(IndividualMatch, individual_match.id)
            assert db_match is not None
            assert db_match.status == MatchStatus.IN_PROGRESS
            assert db_match.started_at is not None

    def test_add_rack_result_transaction_behavior(self, app, test_match_phase2):
        """
        RED: Test current add_rack_result behavior with direct commit.

        Expected behavior:
        - Creates IndividualRack record
        - Updates match scores
        - Returns IndividualRack object
        - Handles transaction internally (commit at line 667)
        """
        individual_match, proposal = test_match_phase2

        with app.app_context():
            # First start the match
            IndividualMatchService.start_match(
                individual_match.id, individual_match.player1_id
            )

            # Act: add rack result
            rack = IndividualMatchService.add_rack_result(
                match_id=individual_match.id,
                winner_id=individual_match.player1_id,
                user_id=individual_match.player1_id,
            )

            # Assert: rack was created and committed
            assert rack is not None
            assert rack.match_id == individual_match.id
            assert rack.winner_id == individual_match.player1_id
            assert rack.rack_number == 1

            # Verify it exists in database (transaction was committed)
            db_rack = db.session.get(IndividualRack, rack.id)
            assert db_rack is not None
            assert db_rack.winner_id == individual_match.player1_id

    def test_submit_rack_result_transaction_behavior(self, app, test_match_phase2):
        """
        RED: Test current submit_rack_result behavior with direct commit.

        Expected behavior:
        - Updates existing rack result
        - May update match completion
        - Handles transaction internally (commit at line 553)
        """
        individual_match, proposal = test_match_phase2

        with app.app_context():
            # Start match and create a rack
            IndividualMatchService.start_match(
                individual_match.id, individual_match.player1_id
            )
            IndividualMatchService.add_rack_result(
                match_id=individual_match.id,
                winner_id=individual_match.player1_id,
                user_id=individual_match.player1_id,
            )

            # Act: submit rack result (add a new rack)
            rack2 = IndividualMatchService.submit_rack_result(
                match_id=individual_match.id,
                user_id=individual_match.player1_id,
                winner_id=individual_match.player2_id,
                rack_number=2,
            )

            # Assert: new rack was created and committed
            # Verify changes exist in database (transaction was committed)
            db_rack2 = db.session.get(IndividualRack, rack2.id)
            assert db_rack2 is not None
            assert db_rack2.winner_id == individual_match.player2_id
            assert db_rack2.rack_number == 2

    def test_complete_match_transaction_behavior(self, app, test_match_phase2):
        """
        RED: Test current complete_match behavior with direct commit.

        Expected behavior:
        - Updates match status to COMPLETED
        - Sets ended_at timestamp
        - Sets winner_id
        - Handles transaction internally (commit at line 684)
        """
        individual_match, proposal = test_match_phase2

        with app.app_context():
            # Start match and play some racks to reach completion
            IndividualMatchService.start_match(
                individual_match.id, individual_match.player1_id
            )

            # Add racks to get close to completion (distance = 7, so add 6 wins)
            winner_id = individual_match.player1_id
            for i in range(6):
                IndividualMatchService.add_rack_result(
                    match_id=individual_match.id,
                    winner_id=winner_id,
                    user_id=individual_match.player1_id,
                )

            # Act: complete match explicitly with the final winning rack
            IndividualMatchService.complete_match(
                match_id=individual_match.id,
                winner_id=winner_id,
                user_id=individual_match.player1_id,
            )

            # Assert: match was completed and committed
            # Verify changes exist in database (transaction was committed)
            db_match = db.session.get(IndividualMatch, individual_match.id)
            assert db_match is not None
            assert db_match.status == MatchStatus.COMPLETED
            assert db_match.ended_at is not None
            assert db_match.winner_id == winner_id

    def test_cancel_match_transaction_behavior(self, app, test_match_phase2):
        """
        RED: Test current cancel_match behavior with direct commit.

        Expected behavior:
        - Updates match status to CANCELLED
        - May add cancellation notes
        - Handles transaction internally (commit at line 703)
        """
        individual_match, proposal = test_match_phase2

        with app.app_context():
            assert individual_match.status == MatchStatus.SCHEDULED

            # Act: cancel match
            IndividualMatchService.cancel_match(
                match_id=individual_match.id,
                user_id=individual_match.player1_id,
                reason="Player unavailable",
            )

            # Assert: match was cancelled and committed
            # Verify changes exist in database (transaction was committed)
            db_match = db.session.get(IndividualMatch, individual_match.id)
            assert db_match is not None
            assert db_match.status == MatchStatus.CANCELLED
            assert "Player unavailable" in (db_match.notes or "")

    def test_cancel_proposal_transaction_behavior(self, app, test_users_phase2):
        """
        RED: Test current cancel_proposal behavior with direct commit.

        Expected behavior:
        - Cancels pending proposal (only by proposer)
        - Updates proposal status
        - Handles transaction internally (commit at line 455)
        """
        proposer, invitee = test_users_phase2

        with app.app_context():
            # Arrange: create pending proposal
            proposal = MatchProposal(
                proposer_id=proposer.id,
                proposal_type=ProposalType.OPEN,
                location="Test Hall Cancel",
                discipline="10ball",
                distance=7,
                scheduled_at=utc_now() + timedelta(hours=4),
                expires_at=utc_now() + timedelta(hours=2),
                description="Test proposal for cancellation",
            )
            db.session.add(proposal)
            db.session.commit()

            assert proposal.status == ProposalStatus.PENDING

            # Act: cancel proposal (as proposer)
            IndividualMatchService.cancel_proposal(
                user_id=proposer.id, proposal_id=proposal.id
            )

            # Assert: proposal was cancelled and committed
            # Verify changes exist in database (transaction was committed)
            db_proposal = db.session.get(MatchProposal, proposal.id)
            assert db_proposal is not None
            assert db_proposal.status == ProposalStatus.CANCELLED

            # Cleanup
            db.session.delete(proposal)
            db.session.commit()

    def test_invite_player_to_match_transaction_behavior(self, app, test_users_phase2):
        """
        RED: Test current invite_player_to_match behavior with direct commit.

        Expected behavior:
        - Creates ProposalInvitation record
        - Returns ProposalInvitation object
        - Handles transaction internally (commit at line 307)
        """
        proposer, invitee = test_users_phase2

        with app.app_context():
            # Arrange: create proposal
            proposal = MatchProposal(
                proposer_id=proposer.id,
                proposal_type=ProposalType.DIRECT,
                location="Test Hall Invite",
                discipline="straight_pool",
                distance=100,
                scheduled_at=utc_now() + timedelta(hours=5),
                expires_at=utc_now() + timedelta(hours=2),
                description="Test proposal for invitation",
            )
            db.session.add(proposal)
            db.session.commit()

            # Act: invite player to match
            invitation = IndividualMatchService.invite_player_to_match(
                proposal_id=proposal.id, inviter_id=proposer.id, invitee_id=invitee.id
            )

            # Assert: invitation was created and committed
            assert invitation is not None
            assert invitation.proposal_id == proposal.id
            assert invitation.invited_user_id == invitee.id
            assert invitation.status == InvitationStatus.PENDING

            # Verify it exists in database (transaction was committed)
            db_invitation = db.session.get(ProposalInvitation, invitation.id)
            assert db_invitation is not None
            assert db_invitation.proposal_id == proposal.id

            # Cleanup - invitation created by service
            db.session.delete(invitation)
            db.session.delete(proposal)
            db.session.commit()

    def test_respond_to_invitation_transaction_behavior(self, app, test_users_phase2):
        """
        RED: Test current respond_to_invitation behavior with direct commit.

        Expected behavior:
        - Updates invitation status based on response
        - May create IndividualMatch if accepted
        - Returns boolean success
        - Handles transaction internally (commit at line 330)
        """
        proposer, invitee = test_users_phase2

        with app.app_context():
            # Arrange: create proposal and invitation
            proposal = MatchProposal(
                proposer_id=proposer.id,
                proposal_type=ProposalType.DIRECT,
                location="Test Hall Response",
                discipline="one_pocket",
                distance=5,
                scheduled_at=utc_now() + timedelta(hours=6),
                expires_at=utc_now() + timedelta(hours=3),
                description="Test proposal for response",
            )
            db.session.add(proposal)
            db.session.flush()

            invitation = ProposalInvitation(
                proposal_id=proposal.id,
                invited_user_id=invitee.id,
                status=InvitationStatus.PENDING,
            )
            db.session.add(invitation)
            db.session.commit()

            # Act: respond to invitation (rejected)
            result = IndividualMatchService.respond_to_invitation(
                invitation_id=invitation.id, invitee_id=invitee.id, response="rejected"
            )

            # Assert: response was processed and committed
            assert result is True

            # Verify changes exist in database (transaction was committed)
            db_invitation = db.session.get(ProposalInvitation, invitation.id)
            assert db_invitation is not None
            assert db_invitation.status == InvitationStatus.REJECTED

            # Cleanup
            db.session.delete(invitation)
            db.session.delete(proposal)
            db.session.commit()
