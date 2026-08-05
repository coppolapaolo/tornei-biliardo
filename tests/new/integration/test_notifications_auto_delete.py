"""Bug 16: aprire la pagina notifiche deve cancellare TUTTE le notifiche
scadute rispetto alla finestra di auto-cancellazione globale (default 30
giorni se l'utente non l'ha mai configurata)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from models import Notification, db
from models.base import utc_now
from models.notification.models import NotificationType, NotificationStatus
from models.notification.services import NotificationService


def _old_read(db_session, user_id, ntype, days_old):
    n = Notification(
        user_id=user_id,
        title="t",
        message="m",
        notification_type=ntype,
        status=NotificationStatus.READ,
    )
    db_session.add(n)
    db_session.flush()
    n.created_at = utc_now() - timedelta(days=days_old)
    db_session.commit()
    return n


@pytest.mark.integration
def test_opening_page_deletes_expired_by_default(logged_in_client, db_session):
    client, user = logged_in_client(role="player")

    old = _old_read(db_session, user.id, NotificationType.PLAYOFF_INVITATION, 45)
    recent = _old_read(db_session, user.id, NotificationType.MATCH_PROPOSAL, 3)

    resp = client.get("/player/notifications")
    assert resp.status_code == 200

    # Default 30 giorni: la 45gg scade (qualsiasi tipo), la 3gg resta.
    assert db.session.get(Notification, old.id) is None
    assert db.session.get(Notification, recent.id) is not None


@pytest.mark.integration
def test_opening_page_respects_disabled(logged_in_client, db_session):
    client, user = logged_in_client(role="player")
    NotificationService.set_global_auto_delete_days(user.id, None)  # disattiva

    old = _old_read(db_session, user.id, NotificationType.SYSTEM_ANNOUNCEMENT, 120)

    resp = client.get("/player/notifications")
    assert resp.status_code == 200

    assert db.session.get(Notification, old.id) is not None
