"""
TDD Tests for IndividualMatchService Transaction Migration (Task 1.1 - Fase 1.3)

Incremental migration strategy for 17 commit calls:
Phase 1: Migrate 3 business-critical methods
- create_direct_proposal() - line 190
- create_open_proposal() - line 226
- expire_proposals() - line 107

Strategy: Red-Green-Refactor TDD for each method
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from models import db
from models.individual_match.models import MatchProposal, ProposalInvitation
from models.individual_match.services import (
    IndividualMatchService,
    MatchProposalService,
)
from models.user.models import User
from models.user.role_enum import UserRole


class TestIndividualMatchServiceTransactionMigration:
    """TDD tests for @transactional migration - Phase 1 (3 critical methods)."""

    @pytest.fixture
    def test_users(self, app):
        """Create test users for match proposals."""
        with app.app_context():
            proposer = User(
                username="test_proposer",
                email="proposer@test.com",
                role=UserRole.PLAYER.value,
            )
            proposer.set_password("testpass")

            invitee = User(
                username="test_invitee",
                email="invitee@test.com",
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

    def test_create_direct_proposal_transaction_behavior(self, app, test_users):
        """
        RED: Test current create_direct_proposal behavior with direct commit.

        Expected behavior:
        - Creates proposal and invitations in database
        - Sends notifications to invited users
        - Returns MatchProposal object
        - Handles transaction internally (commit at line 190)
        """
        proposer, invitee = test_users

        with app.app_context():
            # Mock notifications to avoid dependencies
            with patch(
                "models.notification.services.NotificationService.create_notification"
            ) as mock_notification:
                mock_notification.return_value = {"success": True}

                # Act: create direct proposal
                scheduled_time = datetime.now() + timedelta(hours=2)
                expires_time = datetime.now() + timedelta(hours=1)

                proposal = IndividualMatchService.create_direct_proposal(
                    proposer_id=proposer.id,
                    invited_user_ids=[invitee.id],
                    location="Test Hall",
                    scheduled_at=scheduled_time,
                    expires_at=expires_time,
                    discipline="8ball",
                    distance=3,
                    description="Test match",
                )

            # Assert: proposal was created and committed
            assert proposal is not None
            assert proposal.proposer_id == proposer.id
            assert proposal.location == "Test Hall"

            # Verify it exists in database (transaction was committed)
            db_proposal = db.session.get(MatchProposal, proposal.id)
            assert db_proposal is not None
            assert db_proposal.proposer_id == proposer.id

            # Verify invitation was created
            invitation = (
                db.session.query(ProposalInvitation)
                .filter_by(proposal_id=proposal.id, invited_user_id=invitee.id)
                .first()
            )
            assert invitation is not None

            # Cleanup
            if invitation:
                db.session.delete(invitation)
            db.session.delete(proposal)
            db.session.commit()

    def test_create_open_proposal_transaction_behavior(self, app, test_users):
        """
        RED: Test current create_open_proposal behavior with direct commit.

        Expected behavior:
        - Creates open proposal in database
        - No specific invitations (open to all)
        - Returns MatchProposal object
        - Handles transaction internally (commit at line 226)
        """
        proposer, _ = test_users

        with app.app_context():
            # Act: create open proposal
            scheduled_time = datetime.now() + timedelta(hours=3)
            expires_time = datetime.now() + timedelta(hours=1)

            proposal = IndividualMatchService.create_open_proposal(
                proposer_id=proposer.id,
                location="Test Hall Open",
                scheduled_at=scheduled_time,
                expires_at=expires_time,
                discipline="9ball",
                distance=5,
                description="Open match for all",
            )

            # Assert: proposal was created and committed
            assert proposal is not None
            assert proposal.proposer_id == proposer.id
            assert proposal.location == "Test Hall Open"

            # Verify it exists in database (transaction was committed)
            db_proposal = db.session.get(MatchProposal, proposal.id)
            assert db_proposal is not None

            # Cleanup
            db.session.delete(proposal)
            db.session.commit()

    def test_expire_proposals_transaction_behavior(self, app, test_users):
        """
        RED: Test current expire_proposals behavior with direct commit.

        Expected behavior:
        - Finds and expires pending proposals past expiry date
        - Updates their status in database
        - Returns count of expired proposals
        - Handles transaction internally (commit at line 107)
        """
        proposer, _ = test_users

        with app.app_context():
            # Arrange: create proposal that's already expired
            past_time = datetime.now() - timedelta(hours=1)

            expired_proposal = MatchProposal(
                proposer_id=proposer.id,
                location="Expired Hall",
                discipline="8ball",
                distance=3,
                expires_at=past_time,
            )
            db.session.add(expired_proposal)
            db.session.commit()

            # Act: run expire function
            count = MatchProposalService.expire_proposals()

            # Assert: proposal was expired
            assert count >= 1  # At least our test proposal was expired

            # Verify proposal was processed in database (transaction was committed)
            db_proposal = db.session.get(MatchProposal, expired_proposal.id)
            assert db_proposal is not None
            # Note: expire() method should have updated the proposal status

            # Cleanup
            db.session.delete(expired_proposal)
            db.session.commit()

    def test_create_direct_proposal_rollback_on_error(self, app, test_users):
        """
        RED: Test current error handling in create_direct_proposal.

        Documents current behavior for rollback testing after migration.
        """
        proposer, invitee = test_users

        with app.app_context():
            # Test with invalid user ID to trigger error
            with pytest.raises(Exception):
                # This should fail and rollback properly
                scheduled_time = datetime.now() + timedelta(hours=2)
                expires_time = datetime.now() + timedelta(hours=1)

                IndividualMatchService.create_direct_proposal(
                    proposer_id=proposer.id,
                    invited_user_ids=[99999],  # Non-existent user
                    location="Test Hall",
                    scheduled_at=scheduled_time,
                    expires_at=expires_time,
                    discipline="8ball",
                    distance=3,
                    description="Should fail",
                )

            # Verify no partial data was committed (proper rollback)
            proposals = (
                db.session.query(MatchProposal)
                .filter_by(proposer_id=proposer.id, description="Should fail")
                .all()
            )
            assert len(proposals) == 0  # No partial data should remain

    def test_transaction_isolation_current_behavior(self, app, test_users):
        """
        RED: Test current transaction isolation behavior.

        Documents how transactions currently work for verification
        after @transactional migration.
        """
        proposer, invitee = test_users

        with app.app_context():
            # Mock notifications to avoid dependencies
            with patch(
                "models.notification.services.NotificationService.create_notification"
            ):
                # Create proposal
                scheduled_time = datetime.now() + timedelta(hours=4)
                expires_time = datetime.now() + timedelta(hours=1)

                proposal = IndividualMatchService.create_direct_proposal(
                    proposer_id=proposer.id,
                    invited_user_ids=[invitee.id],
                    location="Isolation Test Hall",
                    scheduled_at=scheduled_time,
                    expires_at=expires_time,
                    discipline="8ball",
                    distance=3,
                    description="Isolation test",
                )

            # Verify immediately visible (transaction committed)
            db_check = db.session.get(MatchProposal, proposal.id)
            assert db_check is not None
            assert db_check.description == "Isolation test"

            # Cleanup
            invitations = (
                db.session.query(ProposalInvitation)
                .filter_by(proposal_id=proposal.id)
                .all()
            )
            for inv in invitations:
                db.session.delete(inv)
            db.session.delete(proposal)
            db.session.commit()
