"""Integration tests for the consolidated availability surface (ADR-032/033).

ADR-033 removed the free-text "location" availability: the surface is now
venue-only (``UserLocationAvailability`` / ``BilliardHall``). These tests
exercise the HTTP endpoints end-to-end.
"""

import uuid

import pytest

from models import db, User
from models.user.role_enum import UserRole
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
            sess["_user_id"] = user.get_id()
            sess["_fresh"] = True

    # ---- manage_availability (GET) ----

    def test_manage_availability_requires_login(self, client):
        resp = client.get("/match/availability")
        assert resp.status_code in (302, 401)

    def test_manage_availability_renders(self, client, player):
        self._login(client, player)
        resp = client.get("/match/availability")
        assert resp.status_code == 200
        # L'invariante e' che la pagina offra di aggiungere una sala: il titolo
        # e' cambiato con la conversione 7c ("Le mie disponibilita'").
        assert b"/match/availability/venue" in resp.data
        assert b"disponibilit" in resp.data.lower()

    # ---- set venue availability ----

    def test_set_venue_availability_creates_and_updates(
        self, client, player, venue, db_session
    ):
        self._login(client, player)
        resp = client.post(
            "/match/availability/venue",
            data={
                "venue_id": str(venue.id),
                "available_days": ["1", "3"],
                "preferred_times": "18:00-22:00",
                "is_available": "true",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        records = UserLocationAvailability.query.filter_by(
            user_id=player.id, billiard_hall_id=venue.id
        ).all()
        assert len(records) == 1
        assert records[0].is_available is True

        # Posting the same venue again must UPDATE, not duplicate
        client.post(
            "/match/availability/venue",
            data={"venue_id": str(venue.id), "preferred_times": "20:00-23:00"},
        )
        records = UserLocationAvailability.query.filter_by(
            user_id=player.id, billiard_hall_id=venue.id
        ).all()
        assert len(records) == 1

    def test_unchecked_availability_is_saved_as_unavailable(
        self, client, player, venue, db_session
    ):
        """An omitted is_available (unchecked checkbox) must mean NOT available."""
        self._login(client, player)
        # No is_available key in the body == checkbox left unchecked
        client.post("/match/availability/venue", data={"venue_id": str(venue.id)})
        rec = UserLocationAvailability.query.filter_by(
            user_id=player.id, billiard_hall_id=venue.id
        ).first()
        assert rec is not None
        assert rec.is_available is False

    def test_set_venue_availability_requires_venue(self, client, player):
        self._login(client, player)
        resp = client.post("/match/availability/venue", data={"venue_id": ""})
        assert resp.status_code == 302  # flashed error + redirect

    # ---- remove availability ----

    def test_remove_venue_availability(self, client, player, venue, db_session):
        self._login(client, player)
        from models.individual_match.availability_service import AvailabilityService

        rec = AvailabilityService.set_venue_availability(
            user_id=player.id, billiard_hall_id=venue.id
        )
        rec_id = rec.id
        resp = client.post(f"/match/availability/venue/{rec_id}/remove")
        assert resp.status_code == 302
        assert db_session.get(UserLocationAvailability, rec_id) is None

    def test_remove_other_users_availability_is_not_found(
        self, client, player, other_player, venue, db_session
    ):
        self._login(client, player)
        from models.individual_match.availability_service import AvailabilityService

        rec = AvailabilityService.set_venue_availability(
            user_id=other_player.id, billiard_hall_id=venue.id
        )
        # JSON request to assert the 404 status code clearly
        resp = client.post(
            f"/match/availability/venue/{rec.id}/remove",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 404
        assert db_session.get(UserLocationAvailability, rec.id) is not None

    # ---- discover ----

    def test_discover_players_renders(
        self, client, player, other_player, venue, db_session
    ):
        self._login(client, player)
        from models.individual_match.availability_service import AvailabilityService

        AvailabilityService.set_venue_availability(
            user_id=other_player.id, billiard_hall_id=venue.id
        )
        resp = client.get(f"/match/availability/discover?venue_id={venue.id}")
        assert resp.status_code == 200
        assert other_player.username.encode() in resp.data

    # ---- request match ----

    def test_request_availability_match_creates_proposal(
        self, client, player, other_player, db_session
    ):
        from models.individual_match.models import MatchProposal

        self._login(client, player)
        resp = client.post(
            f"/match/availability/request-match/{other_player.id}",
            data={"location": "Sala Centro", "message": "Giochiamo?"},
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


@pytest.mark.integration
def test_free_text_location_availability_endpoints_removed(app):
    """ADR-033: the free-text location availability endpoints are gone."""
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    removed = {
        "individual_match.set_location_availability",
        "individual_match.remove_location_availability",
    }
    assert not (removed & endpoints)
