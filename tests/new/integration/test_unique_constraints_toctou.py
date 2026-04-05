"""
Integration tests for UNIQUE constraints preventing TOCTOU race conditions.

Covers ECH-1 / ECH-6 (double-accept of same proposal) and ECH-21
(duplicate invitations). See spec-unique-constraints-toctou.md.
"""

import uuid
import pytest
from datetime import timedelta
from sqlalchemy.exc import IntegrityError

from models import db
from models.base import utc_now
from models.individual_match.models import (
    IndividualMatch,
    MatchProposal,
    ProposalInvitation,
    ProposalType,
    ProposalStatus,
    InvitationStatus,
)
from models.individual_match.match_lifecycle_service import MatchLifecycleService
from models.individual_match.proposal_service import ProposalService
from models.status_enum import MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _make_user(prefix: str) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"{prefix}_{unique}",
        email=f"{prefix}_{unique}@test.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("test123")
    db.session.add(user)
    db.session.commit()
    return user


def _make_open_proposal(proposer: User) -> MatchProposal:
    p = MatchProposal(
        proposer_id=proposer.id,
        proposal_type=ProposalType.OPEN,
        status=ProposalStatus.PENDING,
        location="Sala Test",
        scheduled_at=utc_now() + timedelta(days=1),
        expires_at=utc_now() + timedelta(days=2),
        discipline="palla_8",
        distance=5,
        is_race_to=True,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _make_match(proposer: User, accepter: User, proposal_id=None) -> IndividualMatch:
    m = IndividualMatch(
        proposal_id=proposal_id,
        player1_id=proposer.id,
        player2_id=accepter.id,
        location="Sala Test",
        scheduled_at=utc_now() + timedelta(days=1),
        status=MatchStatus.SCHEDULED,
        discipline="palla_8",
        distance=5,
    )
    db.session.add(m)
    return m


class TestUniqueConstraintsTOCTOU:
    """DB-level + service-level guards against TOCTOU duplicates."""

    def test_individual_match_proposal_id_unique_db_level(self, app):
        """Two matches with the same non-null proposal_id → IntegrityError."""
        with app.app_context():
            proposer = _make_user("p1")
            accepter1 = _make_user("a1")
            accepter2 = _make_user("a2")
            proposal = _make_open_proposal(proposer)

            _make_match(proposer, accepter1, proposal_id=proposal.id)
            db.session.commit()  # first match OK

            _make_match(proposer, accepter2, proposal_id=proposal.id)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_individual_match_null_proposal_id_allows_multiple(self, app):
        """Two matches with proposal_id=NULL are both allowed (direct matches)."""
        with app.app_context():
            proposer = _make_user("p2")
            other1 = _make_user("o1")
            other2 = _make_user("o2")

            _make_match(proposer, other1, proposal_id=None)
            _make_match(proposer, other2, proposal_id=None)
            db.session.commit()  # both OK — NULL does not collide

            count = IndividualMatch.query.filter_by(proposal_id=None).count()
            assert count >= 2

    def test_proposal_invitation_unique_pair_db_level(self, app):
        """Two invitations with same (proposal_id, invited_user_id) → IntegrityError."""
        with app.app_context():
            proposer = _make_user("p3")
            invitee = _make_user("i1")
            proposal = _make_open_proposal(proposer)

            inv1 = ProposalInvitation(
                proposal_id=proposal.id,
                invited_user_id=invitee.id,
                status=InvitationStatus.PENDING,
            )
            db.session.add(inv1)
            db.session.commit()

            inv2 = ProposalInvitation(
                proposal_id=proposal.id,
                invited_user_id=invitee.id,
                status=InvitationStatus.PENDING,
            )
            db.session.add(inv2)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_invite_player_duplicate_raises_value_error(self, app):
        """invite_player_to_match → ValueError on duplicate, not IntegrityError."""
        with app.app_context():
            proposer = _make_user("p4")
            invitee = _make_user("i2")
            proposal = _make_open_proposal(proposer)

            # First invite OK
            ProposalService.invite_player_to_match(proposal.id, proposer.id, invitee.id)

            # Second invite → ValueError (user-friendly)
            with pytest.raises(ValueError, match="già invitato"):
                ProposalService.invite_player_to_match(
                    proposal.id, proposer.id, invitee.id
                )

    def test_accept_proposal_race_raises_value_error(self, app):
        """Second accept against an already-consumed proposal → ValueError."""
        with app.app_context():
            proposer = _make_user("p5")
            first_accepter = _make_user("fa")
            second_accepter = _make_user("sa")
            proposal = _make_open_proposal(proposer)

            # Simulate a concurrent winner: a match already exists with
            # proposal.id but the proposal.status is still PENDING (TOCTOU).
            # This is the exact state the UNIQUE constraint must catch.
            _make_match(proposer, first_accepter, proposal_id=proposal.id)
            db.session.commit()

            # Second accept passes can_be_accepted_by (status still PENDING)
            # but flush() on the new IndividualMatch fires the constraint.
            with pytest.raises(ValueError, match="già accettata"):
                ProposalService.accept_proposal(
                    user_id=second_accepter.id, proposal_id=proposal.id
                )

    def test_report_result_race_raises_value_error(self, app):
        """report_result on pending proposal with concurrent match → ValueError."""
        with app.app_context():
            proposer = _make_user("p6")
            first_accepter = _make_user("fa2")
            second_reporter = _make_user("sr")
            proposal = _make_open_proposal(proposer)

            # Simulate a concurrent winner: an IndividualMatch already exists
            # bound to proposal.id but proposal.status is still PENDING
            # (exact TOCTOU state the UNIQUE constraint must catch).
            _make_match(proposer, first_accepter, proposal_id=proposal.id)
            db.session.commit()

            # report_result enters the pending branch and tries to accept()
            # → creates a second IndividualMatch with same proposal_id →
            # flush fires uq_individual_match_proposal → ValueError.
            with pytest.raises(ValueError, match="già accettata"):
                MatchLifecycleService.report_result(
                    match_id=proposal.id,
                    reporter_id=second_reporter.id,
                    winner_id=second_reporter.id,
                    player1_racks=5,
                    player2_racks=3,
                )

            # Ensure no second match was persisted
            matches = IndividualMatch.query.filter_by(proposal_id=proposal.id).all()
            assert len(matches) == 1

    def test_report_result_savepoint_only_catches_integrity_error(self, app):
        """Savepoint wrap must NOT intercept unrelated errors from the flow.

        Calls report_result on a pending proposal with no concurrent match.
        The savepoint wrapping around proposal.accept() should complete cleanly
        (no TOCTOU race) and let downstream errors propagate with their
        original message — it must not mask them as "Proposta già accettata".

        Note: the downstream complete_match step is known to fail on this path
        (SCHEDULED match vs required IN_PROGRESS, pre-existing, report_result
        pending branch is dead code from routes). What matters here is that
        the savepoint layer is semantically transparent to non-IntegrityError
        failures.
        """
        with app.app_context():
            proposer = _make_user("p7")
            reporter = _make_user("rr")
            proposal = _make_open_proposal(proposer)

            # No prior match → savepoint's flush succeeds → accept() persists
            # a new IndividualMatch. Only then complete_match fails on its own.
            with pytest.raises(ValueError) as exc_info:
                MatchLifecycleService.report_result(
                    match_id=proposal.id,
                    reporter_id=reporter.id,
                    winner_id=reporter.id,
                    player1_racks=5,
                    player2_racks=3,
                )
            # Savepoint didn't mis-translate a non-UNIQUE error: the
            # downstream complete_match raises "Match is not in progress"
            # with the ORIGINAL message intact.
            assert "già accettata" not in str(exc_info.value)
            assert "not in progress" in str(exc_info.value).lower()
