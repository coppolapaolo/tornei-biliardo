"""Regression test for F9.2 — edit_gara silently discarded classification_system.

The gara edit form (`_gara_edit_form.html`) submits `classification_system`,
but the `edit_gara` POST handler never read it: it hand-rolled its own form
parsing (separate from `GaraFormParser` used by create), and simply forgot the
field. Result: a director changes the classification system, sees
"Gara aggiornata con successo!", but the value is NOT persisted.

The fix routes the edit handler through the single-source `GaraFormParser`
(same parser used by create), so the field set can no longer drift.

See docs/_archive/2026-06-technical-debt-oo-review.md (F9.2 / F7.5).
"""

import uuid
from datetime import date, timedelta

import pytest

from models import Gara
from models.user.role_enum import UserRole
from models.competition.models import WithdrawPolicy
from models.competition.services import GaraService


def _create_and_login_director(client, db_session):
    from models import User

    uid = str(uuid.uuid4())[:8]
    director = User(
        username=f"director_{uid}",
        email=f"director_{uid}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("testpass123")
    db_session.add(director)
    db_session.commit()
    client.post(
        "/auth/login",
        data={"username": director.username, "password": "testpass123"},
    )
    return director


def _edit_payload(gara_date, **overrides):
    payload = {
        "name": "Edit CS Test",
        "date": gara_date.isoformat(),
        "time": "20:00",
        "location": "Test Location",
        "discipline": "palla 9",
        "distance": "5",
        "rounds_count": "3",
        "min_participants": "2",
        "max_participants": "8",
        "entry_fee": "0",
        "withdraw_policy": WithdrawPolicy.EXCLUDE.value,
        "matchmaking_strategy": "amalfi",
        "first_round_policy": "random",
        "odd_number_policy": "bye",
        "anti_rematch_enabled": "on",  # amalfi requires anti-rematch
        "classification_system": "WINS",
    }
    payload.update(overrides)
    return payload


@pytest.mark.integration
def test_edit_standalone_gara_persists_classification_system(client, db_session):
    """Changing classification_system via the edit route must persist."""
    director = _create_and_login_director(client, db_session)
    gara_date = date.today() + timedelta(days=3)

    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Edit CS Test",
        date=gara_date,
        location="Test Location",
        rounds_count=3,
        min_participants=2,
        max_participants=8,
        entry_fee=0.0,
        discipline="palla 9",
        distance=5,
        is_race_to=True,
        withdraw_policy=WithdrawPolicy.EXCLUDE.value,
        matchmaking_strategy="amalfi",
        classification_system="WINS",
        director_id=director.id,
    )
    gara_id = gara.id
    assert gara.classification_system == "WINS"

    # RACK is incompatible with simple "bye" (0 rack penalty), so a valid
    # switch to RACK also requires a compatible odd-number policy (trio).
    resp = client.post(
        f"/admin/gara/{gara_id}/edit",
        data=_edit_payload(
            gara_date, classification_system="RACK", odd_number_policy="trio"
        ),
        follow_redirects=False,
    )
    assert resp.status_code in (
        301,
        302,
        303,
    ), f"Edit should redirect, got {resp.status_code}"

    db_session.expire_all()
    updated = db_session.get(Gara, gara_id)
    assert (
        updated.classification_system == "RACK"
    ), "classification_system change must persist (regression F9.2)"
