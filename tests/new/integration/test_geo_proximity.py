"""Integration tests for the geo-proximity discovery model (ADR-034).

Covers: venue ranking by distance, radius filtering, the "venues without
coordinates" section, the home_city centroid fallback, open-proposals-near-you,
and the persistence of home_city / venue coordinates.

Entities are created inside a nested app context kept open for the whole test
(the ``_ctx`` autouse fixture) — this gives a fresh scoped session per test and
avoids the Flask-Login DetachedInstanceError seen under parallel execution.
"""

import uuid

import pytest

from models import db, User
from models.user.role_enum import UserRole
from models.location.models import BilliardHall
from models.individual_match.availability_service import AvailabilityService


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    """Keep a fresh app context open for the whole test (db_session resets schema)."""
    with app.app_context():
        yield


def _make_user(role=UserRole.PLAYER, home_city=None):
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"u_{uid}",
        email=f"u_{uid}@test.com",
        role=role.value,
        home_city=home_city,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _make_venue(lat=None, lng=None, city=None):
    uid = str(uuid.uuid4())[:8]
    hall = BilliardHall(
        name=f"Sala_{uid}",
        city=city or f"City_{uid}",
        number_of_tables=4,
        is_active=True,
        latitude=lat,
        longitude=lng,
    )
    db.session.add(hall)
    db.session.commit()
    return hall


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


@pytest.mark.integration
class TestGeoProximity:

    # ---- service: get_venues_with_available_players ----

    def test_venues_with_available_players(self):
        searcher = _make_user()
        other = _make_user()
        venue = _make_venue(lat=45.0, lng=9.0)
        AvailabilityService.set_venue_availability(other.id, venue.id)

        result = AvailabilityService.get_venues_with_available_players(
            exclude_user_id=searcher.id
        )
        match = next((v for v in result if v["venue_id"] == venue.id), None)
        assert match is not None
        assert match["latitude"] == 45.0 and match["longitude"] == 9.0

    # ---- service: city_centroid_for ----

    def test_city_centroid_for_averages_coords(self):
        city = f"Centro_{uuid.uuid4().hex[:6]}"
        _make_venue(lat=45.0, lng=9.0, city=city)
        _make_venue(lat=47.0, lng=11.0, city=city)
        centroid = AvailabilityService.city_centroid_for(city)
        assert centroid == pytest.approx((46.0, 10.0))

    def test_city_centroid_none_when_no_coords(self):
        city = f"NoCoord_{uuid.uuid4().hex[:6]}"
        _make_venue(lat=None, lng=None, city=city)
        assert AvailabilityService.city_centroid_for(city) is None

    # ---- route: proximity ordering + radius ----

    def test_discover_orders_by_distance_and_filters_radius(self, client):
        searcher = _make_user()
        near_player = _make_user()
        far_player = _make_user()
        out_player = _make_user()

        near = _make_venue(lat=45.0, lng=9.0)  # 0 km
        far = _make_venue(lat=45.05, lng=9.0)  # ~5.5 km
        outside = _make_venue(lat=46.0, lng=9.0)  # ~111 km
        near_name, far_name, out_name = near.name, far.name, outside.name

        AvailabilityService.set_venue_availability(near_player.id, near.id)
        AvailabilityService.set_venue_availability(far_player.id, far.id)
        AvailabilityService.set_venue_availability(out_player.id, outside.id)

        _login(client, searcher)
        resp = client.get(
            "/match/availability/discover?near_lat=45.0&near_lng=9.0&radius_km=20"
        )
        assert resp.status_code == 200
        body = resp.data.decode()

        # Restrict to the results region (past the venue filter dropdown, which
        # lists every venue name regardless of proximity).
        results = body[body.index("Filtra") :]
        assert near_name in results
        assert far_name in results
        assert out_name not in results  # beyond 20 km → not a result card
        assert results.index(near_name) < results.index(far_name)

    def test_placeless_venue_shown_separately(self, client):
        searcher = _make_user()
        other = _make_user()
        placeless = _make_venue(lat=None, lng=None)
        placeless_name = placeless.name
        AvailabilityService.set_venue_availability(other.id, placeless.id)

        _login(client, searcher)
        resp = client.get(
            "/match/availability/discover?near_lat=45.0&near_lng=9.0&radius_km=20"
        )
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "senza posizione" in body.lower()
        assert placeless_name in body

    def test_home_city_fallback_without_gps(self, client):
        city = f"HomeCity_{uuid.uuid4().hex[:6]}"
        searcher = _make_user(home_city=city)
        other = _make_user()
        venue = _make_venue(lat=45.0, lng=9.0, city=city)
        venue_name = venue.name
        AvailabilityService.set_venue_availability(other.id, venue.id)

        _login(client, searcher)
        # No near_lat/near_lng → must fall back to the home-city centroid.
        resp = client.get("/match/availability/discover")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert venue_name in body
        assert "km" in body  # a distance badge was rendered → proximity active

    def test_open_proposal_near_listed(self, client):
        from datetime import timedelta
        from models.base import utc_now
        from models.individual_match.models import (
            MatchProposal,
            ProposalType,
            ProposalStatus,
        )

        searcher = _make_user()
        proposer = _make_user()
        venue = _make_venue(lat=45.0, lng=9.0)
        # searcher is eligible because available at the proposal's venue
        AvailabilityService.set_venue_availability(searcher.id, venue.id)

        # Raw insert: we exercise the proximity ranking, not create_open_proposal's
        # notification/gamification side effects.
        proposal = MatchProposal(
            proposer_id=proposer.id,
            proposal_type=ProposalType.OPEN,
            status=ProposalStatus.PENDING,
            billiard_hall_id=venue.id,
            location=venue.name,
            scheduled_at=utc_now() + timedelta(days=2),
            expires_at=utc_now() + timedelta(days=1),
            discipline="palla_8",
            distance=7,
        )
        db.session.add(proposal)
        db.session.commit()

        _login(client, searcher)
        resp = client.get(
            "/match/availability/discover?near_lat=45.0&near_lng=9.0&radius_km=20"
        )
        assert resp.status_code == 200
        assert "vicino a te" in resp.data.decode().lower()

    # ---- persistence: home_city + venue coords ----

    def test_profile_edit_saves_home_city(self, client):
        user = _make_user()
        user_id = user.id
        _login(client, user)
        resp = client.post(
            "/player/profile/edit",
            data={
                "username": user.username,
                "email": user.email,
                "phone": "",
                "home_city": "Udine",
            },
        )
        assert resp.status_code in (200, 302)
        assert db.session.get(User, user_id).home_city == "Udine"

    def test_venue_edit_saves_coordinates(self, client):
        admin = _make_user(role=UserRole.ADMIN)
        venue = _make_venue()
        venue_id = venue.id
        _login(client, admin)
        resp = client.post(
            f"/admin/venues/{venue_id}/edit",
            data={
                "name": venue.name,
                "number_of_tables": "4",
                "latitude": "46.0711",
                "longitude": "13.2346",
            },
        )
        assert resp.status_code in (200, 302)
        refreshed = db.session.get(BilliardHall, venue_id)
        assert refreshed.latitude == pytest.approx(46.0711)
        assert refreshed.longitude == pytest.approx(13.2346)
