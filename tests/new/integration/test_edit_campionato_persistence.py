"""Anti-drift regression test for the campionato edit route.

Guards against the create/edit form↔model drift called out in the tech-debt
review (F7.5): editing a campionato must persist the full shared field set
(default classification system + the default-gare settings block). The edit and
wizard-create paths now share `CampionatoFormParser` for the settings block, so
a future divergence would surface here.
"""

import uuid

import pytest

from models import Campionato
from models.user.models import User, DirectorAssignment
from models.user.role_enum import UserRole


def _create_and_login_director(client, db_session):
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


def _campionato_with_director(db_session, director):
    uid = str(uuid.uuid4())[:8]
    c = Campionato(
        name=f"Camp {uid}",
        campionato_type="amalfi",
        is_active=True,
        default_classification_system="WINS",
        default_rounds_count=3,
    )
    db_session.add(c)
    db_session.flush()
    db_session.add(
        DirectorAssignment(
            entity_type="campionato",
            entity_id=c.id,
            user_id=director.id,
            assigned_by_id=director.id,
        )
    )
    db_session.commit()
    return c


@pytest.mark.integration
def test_edit_campionato_persists_shared_fields(client, db_session):
    director = _create_and_login_director(client, db_session)
    campionato = _campionato_with_director(db_session, director)
    cid = campionato.id

    resp = client.post(
        f"/admin/campionato/{cid}/edit",
        data={
            "name": "Camp Renamed",
            "campionato_type": "amalfi",
            "planned_gare_count": "8",
            "challenge_mode": "on",
            # classification + default-settings block (shared parser)
            "default_classification_system": "RACK",
            "default_entry_fee": "15",
            "default_rounds_count": "5",
            "default_odd_policy": "trio",
            "default_anti_rematch": "on",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (301, 302, 303)

    db_session.expire_all()
    updated = db_session.get(Campionato, cid)
    assert updated.name == "Camp Renamed"
    assert updated.default_classification_system == "RACK"
    assert updated.default_rounds_count == 5
    assert updated.default_entry_fee == 15
    assert updated.default_odd_policy == "trio"
    assert updated.default_anti_rematch is True
