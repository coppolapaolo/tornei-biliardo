"""Integration test del segnale-domanda → director (ADR-036).

Coprono la route di creazione e il consumo end-to-end via
``CompetitionCreatedEvent`` quando un director apre una gara con sala
geolocalizzata. App context tenuto aperto (fixture ``_ctx``) per evitare il
Flask-Login DetachedInstanceError sotto esecuzione parallela (cfr.
``test_geo_proximity.py``).
"""

import uuid
from datetime import date, timedelta

import pytest

from models import db, User
from models.user.role_enum import UserRole
from models.location.models import BilliardHall
from models.demand.models import DemandSignal, DemandSignalStatus
from models.demand.service import DemandSignalService

NAP_LAT, NAP_LNG = 40.8518, 14.2681


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _user(role=UserRole.PLAYER, home_city=None):
    uid = str(uuid.uuid4())[:8]
    u = User(
        username=f"u_{uid}",
        email=f"u_{uid}@test.com",
        role=role.value,
        home_city=home_city,
    )
    u.set_password("pw123456")
    db.session.add(u)
    db.session.commit()
    return u


def _napoli_venue():
    uid = str(uuid.uuid4())[:8]
    hall = BilliardHall(
        name=f"Sala_{uid}",
        city="Napoli",
        number_of_tables=4,
        is_active=True,
        latitude=NAP_LAT,
        longitude=NAP_LNG,
    )
    db.session.add(hall)
    db.session.commit()
    return hall


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


@pytest.mark.integration
class TestDemandSignalRoute:
    def test_create_signal_via_post(self, app):
        user = _user()
        uid = user.id
        client = app.test_client()
        _login(client, user)

        resp = client.post(
            "/demand/signal",
            json={"near_lat": NAP_LAT, "near_lng": NAP_LNG},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        signals = DemandSignal.query.filter_by(user_id=uid).all()
        assert len(signals) == 1
        assert signals[0].status == DemandSignalStatus.ACTIVE

    def test_create_signal_no_position_returns_error(self, app):
        user = _user(home_city=None)
        client = app.test_client()
        _login(client, user)

        resp = client.post("/demand/signal", json={})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False


@pytest.mark.integration
class TestDemandConsumptionOnGaraCreated:
    def test_gara_creation_consumes_nearby_signals(self, app):
        from models.competition.services import GaraService

        venue = _napoli_venue()
        director = _user(role=UserRole.DIRECTOR, home_city="Napoli")
        director_id, venue_id = director.id, venue.id

        # Segnali attivi vicino alla sala.
        players = [_user() for _ in range(2)]
        for p in players:
            DemandSignalService.create_signal(p.id, NAP_LAT, NAP_LNG)
        assert DemandSignalService.count_active_within(NAP_LAT, NAP_LNG, 30) == 2

        # Il director apre una gara in quella sala → evento → consumo.
        GaraService.create_gara(
            number=1,
            name="Gara Napoli",
            date=date.today() + timedelta(days=3),
            discipline="palla_8",
            distance=5,
            director_id=director_id,
            billiard_hall_id=venue_id,
        )

        assert DemandSignalService.count_active_within(NAP_LAT, NAP_LNG, 30) == 0
        for p in players:
            sigs = DemandSignal.query.filter_by(user_id=p.id).all()
            assert all(s.status == DemandSignalStatus.CONSUMED for s in sigs)


@pytest.mark.integration
class TestDemandRefreshRoute:
    def test_refresh_signal_via_post(self, app):
        from datetime import timedelta
        from models.base import utc_now

        user = _user()
        signal = DemandSignal(
            user_id=user.id,
            latitude=NAP_LAT,
            longitude=NAP_LNG,
            status=DemandSignalStatus.ACTIVE,
            expires_at=utc_now() + timedelta(days=2),
        )
        db.session.add(signal)
        db.session.commit()
        sid, old_exp = signal.id, signal.expires_at

        client = app.test_client()
        _login(client, user)
        resp = client.post(f"/demand/signal/{sid}/refresh", json={})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert db.session.get(DemandSignal, sid).expires_at > old_exp
