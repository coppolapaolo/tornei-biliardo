"""Gli invitati scartati di un match vengono avvisati (Fase 3.6).

Fix a sé stante, utile a prescindere dagli esami. ``MatchProposal.accept()``
porta a ``REJECTED`` gli altri inviti pendenti, ma ``accept_proposal``
notificava **solo il proponente**: per gli altri invitati la proposta spariva
dall'elenco senza una parola. L'unico percorso che li avvisava era
``accept_interest_for_open_invitation``, cioè le proposte aperte.

È la stessa lacuna che il dominio esame chiude con US-E4b. Dove il difetto
riguarda anche i match individuali si estende quel dominio, non si clona il fix.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.individual_match.models import (
    InvitationStatus,
    MatchProposal,
    ProposalInvitation,
    ProposalStatus,
    ProposalType,
)
from models.individual_match.proposal_service import ProposalService
from models.notification.models import Notification, NotificationType
from models.user.models import User
from models.user.role_enum import UserRole


def _make_user() -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"player_{suffix}",
        email=f"player_{suffix}@test.local",
        role=UserRole.PLAYER.value,
        is_verified=True,
    )
    user.set_password("test1234")
    db.session.add(user)
    db.session.flush()
    return user


def _declined_notifications(user_id: int) -> int:
    return Notification.query.filter_by(
        user_id=user_id, notification_type=NotificationType.MATCH_DECLINED
    ).count()


@pytest.fixture
def direct_proposal(db_session):
    """Una proposta diretta a due giocatori: uno accetterà, l'altro no."""
    proposer = _make_user()
    first = _make_user()
    second = _make_user()
    db_session.commit()

    proposal = MatchProposal(
        proposer_id=proposer.id,
        proposal_type=ProposalType.DIRECT,
        status=ProposalStatus.PENDING,
        location="Sala Test",
        scheduled_at=utc_now() + timedelta(days=1),
        expires_at=utc_now() + timedelta(days=2),
        discipline="8_ball",
        distance=5,
        is_race_to=True,
    )
    db_session.add(proposal)
    db_session.flush()
    for invitee in (first, second):
        db_session.add(
            ProposalInvitation(
                proposal_id=proposal.id,
                invited_user_id=invitee.id,
                status=InvitationStatus.PENDING,
            )
        )
    db_session.commit()

    return {
        "proposal": proposal,
        "proposer": proposer,
        "accepter": first,
        "discarded": second,
    }


def test_the_discarded_invitee_is_told_the_proposal_is_closed(
    db_session, direct_proposal
):
    ProposalService.accept_proposal(
        user_id=direct_proposal["accepter"].id,
        proposal_id=direct_proposal["proposal"].id,
    )
    db_session.commit()

    assert _declined_notifications(direct_proposal["discarded"].id) == 1
    # Il proponente riceve la sua, di tipo diverso: la proposta è accettata.
    assert (
        Notification.query.filter_by(
            user_id=direct_proposal["proposer"].id,
            notification_type=NotificationType.MATCH_ACCEPTED,
        ).count()
        == 1
    )


def test_whoever_accepted_is_not_told_the_proposal_is_closed(
    db_session, direct_proposal
):
    ProposalService.accept_proposal(
        user_id=direct_proposal["accepter"].id,
        proposal_id=direct_proposal["proposal"].id,
    )
    db_session.commit()

    assert _declined_notifications(direct_proposal["accepter"].id) == 0


def test_the_notification_matches_the_rejected_invitations(db_session, direct_proposal):
    """Avvisati esattamente quelli che il modello ha chiuso, né più né meno."""
    ProposalService.accept_proposal(
        user_id=direct_proposal["accepter"].id,
        proposal_id=direct_proposal["proposal"].id,
    )
    db_session.commit()

    rejected = ProposalInvitation.query.filter_by(
        proposal_id=direct_proposal["proposal"].id,
        status=InvitationStatus.REJECTED,
    ).all()
    assert [inv.invited_user_id for inv in rejected] == [
        direct_proposal["discarded"].id
    ]


def test_the_open_path_still_notifies_once(db_session):
    """Nessun doppione: sulle proposte aperte avvisa già l'altro percorso."""
    proposer = _make_user()
    interested = _make_user()
    other = _make_user()
    db_session.commit()

    proposal = MatchProposal(
        proposer_id=proposer.id,
        proposal_type=ProposalType.OPEN,
        status=ProposalStatus.PENDING,
        location="Sala Test",
        scheduled_at=utc_now() + timedelta(days=1),
        expires_at=utc_now() + timedelta(days=2),
        discipline="8_ball",
        distance=5,
        is_race_to=True,
    )
    db_session.add(proposal)
    db_session.commit()

    ProposalService.express_interest_in_open_invitation(proposal.id, interested.id)
    ProposalService.express_interest_in_open_invitation(proposal.id, other.id)
    db_session.commit()

    ProposalService.accept_interest_for_open_invitation(
        proposal.id, proposer.id, interested.id
    )
    db_session.commit()

    assert _declined_notifications(other.id) == 1
