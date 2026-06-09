"""Regression: la revoca gestore sede non deve generare una notifica di "rifiuto".

Bug (code review 2026-06-09, HIGH correttezza) —
`models/events/notification_handlers.py:213`:

handle_venue_manager_request_processed aveva solo due rami:
`if event.status == "approved"` e un `else` etichettato "rejected".
VenueManagerService.revoke_venue_manager pubblica però status="revoked":
cadendo nell'else, al gestore arrivava un fuorviante "Richiesta Gestore '...'
Rifiutata" / "la tua richiesta ... è stata rifiutata" invece di un messaggio
di revoca.
"""

from __future__ import annotations

import uuid

import pytest

from models.user.models import User
from models.user.role_enum import UserRole
from models.events.notification_handlers import NotificationEventHandlers
from models.events.user_events import VenueManagerRequestProcessedEvent
from models.notification.models import Notification


def _make_user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    u = User(
        username=f"mgr_{uid}",
        email=f"mgr_{uid}@test.local",
        role=UserRole.PLAYER.value,
    )
    u.set_password("x")
    db_session.add(u)
    db_session.flush()
    return u


def _event(user, status: str) -> VenueManagerRequestProcessedEvent:
    return VenueManagerRequestProcessedEvent(
        request_id=0,
        user_id=user.id,
        username=user.username,
        venue_id=1,
        venue_name="Sala Test",
        status=status,
        processed_by_id=1,
        notes=None,
    )


def _latest_notification(db_session, user) -> Notification:
    return (
        Notification.query.filter_by(user_id=user.id)
        .order_by(Notification.id.desc())
        .first()
    )


@pytest.mark.unit
def test_revoked_does_not_produce_rejection_message(db_session):
    user = _make_user(db_session)

    NotificationEventHandlers.handle_venue_manager_request_processed(
        _event(user, "revoked")
    )

    notif = _latest_notification(db_session, user)
    assert notif is not None
    # Prima del fix: title "...Rifiutata", message "...è stata rifiutata".
    assert "Rifiutata" not in notif.title
    assert "rifiutat" not in notif.message.lower()
    # Deve parlare di revoca.
    assert "evocat" in notif.title or "evocat" in notif.message


@pytest.mark.unit
def test_rejected_still_produces_rejection_message(db_session):
    user = _make_user(db_session)

    NotificationEventHandlers.handle_venue_manager_request_processed(
        _event(user, "rejected")
    )

    notif = _latest_notification(db_session, user)
    assert notif is not None
    assert "Rifiutata" in notif.title


@pytest.mark.unit
def test_approved_still_produces_approval_message(db_session):
    user = _make_user(db_session)

    NotificationEventHandlers.handle_venue_manager_request_processed(
        _event(user, "approved")
    )

    notif = _latest_notification(db_session, user)
    assert notif is not None
    assert "Approvata" in notif.title
