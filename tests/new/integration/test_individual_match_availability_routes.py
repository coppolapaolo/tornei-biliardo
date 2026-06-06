"""Integration tests for the consolidated availability surface (ADR-032).

The player-availability and discovery routes were moved from the legacy
``player`` blueprint onto the ``individual_match`` blueprint and unified on
``AvailabilityService`` (location strings + billiard-hall venues + discovery).
These tests exercise the new HTTP endpoints end-to-end.
"""

import uuid

import pytest

from models import db, User
from models.user.role_enum import UserRole
from models.individual_match.models import PlayerAvailability, MatchProposal
from models.location.models import BilliardHall, UserLocationAvailability


@pytest.mark.integration
class TestAvailabilitySurfaceRoutes:
    """HTTP-level tests for individual_match availability + discovery."""

    @pytest.fixture
    def player(self, app) -> User:
        with app.app_context():
            uid = str(uuid.uuid4())[:8]
            user = User(
                username=f"player_{uid}",
                email=f"player_{uid}@test.com",
                role=UserRole.PLAYER.value,
            )
            user.set_password("player123")
            db.session.add(user)
            db.session.commit()
            yield user

    @pytest.fixture
    def other_player(self, app) -> User:
        with app.app_context():
            uid = str(uuid.uuid4())[:8]
            user = User(
                username=f"other_{uid}",
                email=f"other_{uid}@test.com",
                role=UserRole.PLAYER.value,
            )
            user.set_password("player123")
            db.session.add(user)
            db.session.commit()
            yield user

    @pytest.fixture
    def venue(self, app) -> BilliardHall:
        with app.app_context():
            uid = str(uuid.uuid4())[:8]
            hall = BilliardHall(
                name=f"Sala Centro {uid}",
                address="Via Roma 1",
                city="Udine",
                number_of_tables=6,
                is_active=True,
            )
            db.session.add(hall)
            db.session.commit()
            yield hall

    @staticmethod
    def _login(client, user):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

    # ---- manage_availability (GET) ----

    def test_manage_availability_requires_login(self, client):
        resp = client.get("/match/availability")
        assert resp.status_code in (302, 401)

    def test_manage_availability_renders(self, client, player):
        self._login(client, player)
        resp = client.get("/match/availability")
        assert resp.status_code == 200
        assert b"Disponibilit" in resp.data

    # ---- set location availability ----

    def test_set_location_availability_creates_and_updates(
        self, client, player, db_session
    ):
        self._login(client, player)
        resp = client.post(
            "/match/availability/location",
            data={
                "location": "Bar Sport",
                "preferred_days": ["1", "3"],
                "preferred_times": "18:00-22:00",
                "is_available": "true",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        records = PlayerAvailability.query.filter_by(
            user_id=player.id, location="Bar Sport"
        ).all()
        assert len(records) == 1
        assert records[0].is_available is True

        # Posting the same location again must UPDATE, not duplicate
        client.post(
            "/match/availability/location",
            data={"location": "Bar Sport", "preferred_times": "20:00-23:00"},
        )
        records = PlayerAvailability.query.filter_by(
            user_id=player.id, location="Bar Sport"
        ).all()
        assert len(records) == 1
        assert records[0].preferred_times == "20:00-23:00"

    def test_set_location_availability_requires_location(self, client, player):
        self._login(client, player)
        resp = client.post("/match/availability/location", data={"location": "  "})
        assert resp.status_code == 302  # flashed error + redirect

    # ---- set venue availability ----

    def test_set_venue_availability_creates(self, client, player, venue, db_session):
        self._login(client, player)
        resp = client.post(
            "/match/availability/venue",
            data={
                "venue_id": str(venue.id),
                "available_days": ["1"],
                "preferred_times": "19:00-21:00",
                "is_available": "true",
            },
        )
        assert resp.status_code == 302
        record = UserLocationAvailability.query.filter_by(
            user_id=player.id, billiard_hall_id=venue.id
        ).first()
        assert record is not None
        assert record.is_available is True

    # ---- remove availability ----

    def test_remove_location_availability(self, client, player, db_session):
        self._login(client, player)
        from models.individual_match.availability_service import AvailabilityService

        rec = AvailabilityService.set_player_availability(
            user_id=player.id, location="Bar Sport"
        )
        rec_id = rec.id
        resp = client.post(f"/match/availability/location/{rec_id}/remove")
        assert resp.status_code == 302
        assert db_session.get(PlayerAvailability, rec_id) is None

    def test_remove_other_users_availability_is_not_found(
        self, client, player, other_player, db_session
    ):
        self._login(client, player)
        from models.individual_match.availability_service import AvailabilityService

        rec = AvailabilityService.set_player_availability(
            user_id=other_player.id, location="Bar Sport"
        )
        # JSON request to assert the 404 status code clearly
        resp = client.post(
            f"/match/availability/location/{rec.id}/remove",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 404
        assert db_session.get(PlayerAvailability, rec.id) is not None

    # ---- discover ----

    def test_discover_players_renders(self, client, player, other_player, db_session):
        self._login(client, player)
        from models.individual_match.availability_service import AvailabilityService

        AvailabilityService.set_player_availability(
            user_id=other_player.id, location="Bar Sport"
        )
        resp = client.get("/match/availability/discover?location=Bar+Sport")
        assert resp.status_code == 200
        assert other_player.username.encode() in resp.data

    # ---- request match ----

    def test_request_availability_match_creates_proposal(
        self, client, player, other_player, db_session
    ):
        self._login(client, player)
        resp = client.post(
            f"/match/availability/request-match/{other_player.id}",
            data={"location": "Bar Sport", "message": "Giochiamo?"},
        )
        assert resp.status_code == 302
        proposal = MatchProposal.query.filter_by(proposer_id=player.id).first()
        assert proposal is not None

    def test_request_availability_match_requires_location(
        self, client, player, other_player
    ):
        self._login(client, player)
        resp = client.post(
            f"/match/availability/request-match/{other_player.id}",
            data={"location": ""},
        )
        assert resp.status_code == 302  # flashed error + redirect


@pytest.mark.integration
def test_legacy_player_availability_endpoints_removed(app):
    """The legacy player.* availability endpoints must no longer exist."""
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    legacy = {
        "player.availability_preferences",
        "player.set_location_availability",
        "player.set_venue_availability",
        "player.discover_available_players",
        "player.request_availability_match",
    }
    still_present = legacy & endpoints
    assert not still_present, f"legacy endpoints still registered: {still_present}"
