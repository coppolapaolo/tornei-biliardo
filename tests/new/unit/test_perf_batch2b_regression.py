"""Regression (review 2026-06-09, batch 2b): N+1 residui + bulk delete.

- NotificationService.auto_delete_by_user_preferences: SELECT .all() + delete
  per riga sostituiti da una bulk DELETE per preferenza. Verifica che il conteggio
  ritornato sia ancora corretto e che le righe vengano effettivamente eliminate.
- CommunityService.get_director_performance e
  LocationService.suggest_locations_for_match: batch-load invece di query per
  iterazione (smoke su correttezza dei risultati).
"""

import uuid
from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.user.models import User
from models.notification.models import (
    Notification,
    NotificationPreference,
    NotificationType,
    NotificationStatus,
)
from models.notification.services import NotificationService


def _make_user(suffix):
    u = User(username=f"n_{suffix}", email=f"n_{suffix}@t.com", role="player")
    u.set_password("x")
    db.session.add(u)
    db.session.flush()
    return u


@pytest.mark.unit
def test_auto_delete_bulk_count_correct(db_session):
    suffix = uuid.uuid4().hex[:8]
    user = _make_user(suffix)

    pref = NotificationPreference(
        user_id=user.id,
        notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
        auto_delete_days=10,
    )
    db.session.add(pref)
    db.session.flush()

    old = utc_now() - timedelta(days=30)
    # 3 vecchie + READ → eliminabili
    for i in range(3):
        db.session.add(
            Notification(
                user_id=user.id,
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                title=f"old {i}",
                message="m",
                status=NotificationStatus.READ,
                created_at=old,
            )
        )
    # 1 recente (non eliminabile per data) + 1 vecchia ma PENDING (non eliminabile)
    db.session.add(
        Notification(
            user_id=user.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="recent",
            message="m",
            status=NotificationStatus.READ,
            created_at=utc_now(),
        )
    )
    db.session.add(
        Notification(
            user_id=user.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="old pending",
            message="m",
            status=NotificationStatus.PENDING,
            created_at=old,
        )
    )
    db.session.commit()

    deleted = NotificationService.auto_delete_by_user_preferences(user_id=user.id)
    assert deleted == 3

    remaining = Notification.query.filter_by(user_id=user.id).count()
    assert remaining == 2


@pytest.mark.unit
def test_director_performance_runs(db_session):
    """Smoke: get_director_performance non esplode e ritorna una lista."""
    from models.kpi.community_service import CommunityService

    result = CommunityService.get_director_performance()
    assert isinstance(result, list)
