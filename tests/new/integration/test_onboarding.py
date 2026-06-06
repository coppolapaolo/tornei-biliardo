"""Integration test per l'onboarding obbligatorio (ADR-035).

Coprono: rendering della pagina, completamento via POST, ed enforcement
server-side (redirect/esenzioni). L'enforcement è disattivato di default nei
test (``ONBOARDING_ENFORCED=False``); qui lo riattiviamo localmente con una
fixture che ripristina il valore dopo il test.

Come in ``test_geo_proximity.py``, un app context resta aperto per tutto il test
(fixture ``_ctx``) e usiamo helper locali ``_make_user``/``_login`` per evitare
il Flask-Login DetachedInstanceError visto sotto esecuzione parallela.
"""

import uuid

import pytest

from models import db, User
from models.user.role_enum import UserRole
from models.location.models import BilliardHall, UserLocationAvailability


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


@pytest.fixture
def onboarding_enforced(app):
    """Riattiva temporaneamente l'enforcement onboarding per il test."""
    prev = app.config.get("ONBOARDING_ENFORCED")
    app.config["ONBOARDING_ENFORCED"] = True
    try:
        yield
    finally:
        app.config["ONBOARDING_ENFORCED"] = prev


def _make_user(role=UserRole.PLAYER, onboarding_completed=False):
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"u_{uid}",
        email=f"u_{uid}@test.com",
        role=role.value,
        onboarding_completed=onboarding_completed,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _make_venue(name="Sala Test"):
    uid = str(uuid.uuid4())[:8]
    hall = BilliardHall(
        name=f"{name}_{uid}", city="Napoli", number_of_tables=4, is_active=True
    )
    db.session.add(hall)
    db.session.commit()
    return hall


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


@pytest.mark.integration
class TestOnboardingPage:
    def test_get_renders_form(self, app):
        user = _make_user()
        client = app.test_client()
        _login(client, user)

        resp = client.get("/onboarding")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'name="home_city"' in body
        assert 'name="interests"' in body

    def test_post_completes_onboarding(self, app):
        user = _make_user()
        venue = _make_venue()
        user_id, venue_id = user.id, venue.id
        client = app.test_client()
        _login(client, user)

        resp = client.post(
            "/onboarding",
            data={
                "home_city": "Napoli",
                "venue_ids": [str(venue_id)],
                "interests": ["drill", "match"],
            },
        )
        assert resp.status_code == 302
        assert "dashboard" in resp.headers["Location"]

        refreshed = db.session.get(User, user_id)
        assert refreshed.onboarding_completed is True
        assert refreshed.home_city == "Napoli"
        assert set(refreshed.interests_list) == {"drill", "match"}
        assert (
            UserLocationAvailability.query.filter_by(
                user_id=user_id, billiard_hall_id=venue_id
            ).first()
            is not None
        )


@pytest.mark.integration
class TestOnboardingEnforcement:
    def test_not_onboarded_player_redirected(self, app, onboarding_enforced):
        user = _make_user(onboarding_completed=False)
        client = app.test_client()
        _login(client, user)

        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/onboarding")

    def test_onboarding_page_itself_not_redirected(self, app, onboarding_enforced):
        user = _make_user(onboarding_completed=False)
        client = app.test_client()
        _login(client, user)

        resp = client.get("/onboarding", follow_redirects=False)
        assert resp.status_code == 200

    def test_logout_not_redirected(self, app, onboarding_enforced):
        user = _make_user(onboarding_completed=False)
        client = app.test_client()
        _login(client, user)

        resp = client.get("/auth/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert not resp.headers["Location"].endswith("/onboarding")

    def test_completed_player_not_redirected(self, app, onboarding_enforced):
        user = _make_user(onboarding_completed=True)
        client = app.test_client()
        _login(client, user)

        resp = client.get("/dashboard", follow_redirects=False)
        location = resp.headers.get("Location", "")
        assert not location.endswith("/onboarding")

    def test_admin_not_redirected(self, app, onboarding_enforced):
        user = _make_user(role=UserRole.ADMIN, onboarding_completed=False)
        client = app.test_client()
        _login(client, user)

        resp = client.get("/dashboard", follow_redirects=False)
        location = resp.headers.get("Location", "")
        assert not location.endswith("/onboarding")
