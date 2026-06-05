"""Regression test for F9.1 — BilliardHall.is_active identity-comparison bug.

`User.get_managed_venues()` filtered with `BilliardHall.is_active is True`,
a Python identity check that evaluates to the constant `False` (not a SQL
expression). The resulting query was effectively `WHERE ... AND 0`, so the
method NEVER returned any venue for a non-admin venue manager.

See docs/_archive/2026-06-technical-debt-oo-review.md (F9.1).
"""

import uuid

import pytest

from models.user.models import User, VenueManagement
from models.user.role_enum import UserRole
from models.location.models import BilliardHall


@pytest.mark.unit
def test_get_managed_venues_returns_active_assigned_hall(db_session):
    """A venue manager must see the active hall they are assigned to."""
    uid = str(uuid.uuid4())[:8]

    admin = User(
        username=f"admin_{uid}",
        email=f"admin_{uid}@test.com",
        role=UserRole.ADMIN.value,
    )
    admin.set_password("testpass123")
    manager = User(
        username=f"mgr_{uid}",
        email=f"mgr_{uid}@test.com",
        role=UserRole.PLAYER.value,
    )
    manager.set_password("testpass123")
    hall = BilliardHall(name=f"Sala {uid}", is_active=True)
    db_session.add_all([admin, manager, hall])
    db_session.commit()

    assignment = VenueManagement(
        user_id=manager.id,
        venue_id=hall.id,
        assigned_by_id=admin.id,
        is_active=True,
    )
    db_session.add(assignment)
    db_session.commit()

    managed = manager.get_managed_venues()

    # Before the fix this list was always empty (identity comparison bug).
    assert hall.id in [
        v.id for v in managed
    ], "Venue manager must see the active hall they manage"


@pytest.mark.unit
def test_get_managed_venues_excludes_inactive_hall(db_session):
    """An inactive hall must NOT be returned even if assignment exists."""
    uid = str(uuid.uuid4())[:8]

    admin = User(
        username=f"admin_{uid}",
        email=f"admin_{uid}@test.com",
        role=UserRole.ADMIN.value,
    )
    admin.set_password("testpass123")
    manager = User(
        username=f"mgr_{uid}",
        email=f"mgr_{uid}@test.com",
        role=UserRole.PLAYER.value,
    )
    manager.set_password("testpass123")
    inactive_hall = BilliardHall(name=f"Chiusa {uid}", is_active=False)
    db_session.add_all([admin, manager, inactive_hall])
    db_session.commit()

    assignment = VenueManagement(
        user_id=manager.id,
        venue_id=inactive_hall.id,
        assigned_by_id=admin.id,
        is_active=True,
    )
    db_session.add(assignment)
    db_session.commit()

    managed = manager.get_managed_venues()

    assert inactive_hall.id not in [
        v.id for v in managed
    ], "Inactive halls must be filtered out by the is_active condition"
