"""Unit test per l'onboarding obbligatorio (ADR-035).

Due livelli:
1. ``needs_onboarding_redirect`` — funzione pura di decisione (no Flask/DB).
2. ``OnboardingService.complete_onboarding`` — persiste flag/città/interessi/
   disponibilità sala.
"""

import uuid

import pytest

from utils.onboarding import (
    needs_onboarding_redirect,
    ONBOARDING_ENDPOINT,
    ONBOARDING_EXEMPT_ENDPOINTS,
)


class _FakeUser:
    def __init__(
        self,
        authenticated=True,
        is_admin=False,
        onboarding_completed=False,
    ):
        self.is_authenticated = authenticated
        self.is_admin = is_admin
        self.onboarding_completed = onboarding_completed


# ── Funzione pura di decisione ───────────────────────────────────────────────


def test_redirect_for_authenticated_player_not_onboarded():
    user = _FakeUser(onboarding_completed=False)
    assert needs_onboarding_redirect(user, "dashboard.dashboard") is True


def test_no_redirect_when_onboarding_completed():
    user = _FakeUser(onboarding_completed=True)
    assert needs_onboarding_redirect(user, "dashboard.dashboard") is False


def test_no_redirect_for_admin():
    user = _FakeUser(is_admin=True, onboarding_completed=False)
    assert needs_onboarding_redirect(user, "dashboard.dashboard") is False


def test_no_redirect_for_anonymous():
    user = _FakeUser(authenticated=False, onboarding_completed=False)
    assert needs_onboarding_redirect(user, "main.index") is False


@pytest.mark.parametrize(
    "endpoint",
    [ONBOARDING_ENDPOINT, "auth.logout", "i18n.set_language", "static"],
)
def test_no_redirect_on_exempt_endpoints(endpoint):
    user = _FakeUser(onboarding_completed=False)
    assert endpoint in ONBOARDING_EXEMPT_ENDPOINTS
    assert needs_onboarding_redirect(user, endpoint) is False


def test_no_redirect_on_none_endpoint():
    """Endpoint None (404 generato da Flask) non deve forzare un redirect."""
    user = _FakeUser(onboarding_completed=False)
    assert needs_onboarding_redirect(user, None) is False


# ── Service ──────────────────────────────────────────────────────────────────


def _make_user(db_session):
    from models import User
    from models.user.role_enum import UserRole

    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"onb_{uid}",
        email=f"onb_{uid}@test.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("x")
    db_session.add(user)
    db_session.commit()
    return user


def _make_venue(db_session, name="Sala Test", active=True):
    from models.location.models import BilliardHall

    venue = BilliardHall(name=name, city="Napoli", is_active=active)
    db_session.add(venue)
    db_session.commit()
    return venue


def test_complete_onboarding_sets_flag_and_fields(db_session):
    from models import User
    from models.user.onboarding_service import OnboardingService
    from models.location.models import UserLocationAvailability

    user = _make_user(db_session)
    venue = _make_venue(db_session)

    OnboardingService.complete_onboarding(
        user_id=user.id,
        home_city="  Napoli  ",
        venue_ids=[venue.id],
        interests=["match", "tornei", "bogus"],
    )

    refreshed = db_session.get(User, user.id)
    assert refreshed.onboarding_completed is True
    assert refreshed.home_city == "Napoli"
    # interessi filtrati sul set chiuso, ordine canonico (match prima di tornei)
    assert refreshed.interests_list == ["match", "tornei"]

    avail = UserLocationAvailability.query.filter_by(
        user_id=user.id, billiard_hall_id=venue.id
    ).first()
    assert avail is not None
    assert avail.is_available is True


def test_complete_onboarding_minimal_no_data(db_session):
    from models import User
    from models.user.onboarding_service import OnboardingService

    user = _make_user(db_session)
    OnboardingService.complete_onboarding(user_id=user.id)

    refreshed = db_session.get(User, user.id)
    assert refreshed.onboarding_completed is True
    assert refreshed.onboarding_interests is None
    assert refreshed.interests_list == []


def test_complete_onboarding_ignores_inactive_or_unknown_venues(db_session):
    from models.user.onboarding_service import OnboardingService
    from models.location.models import UserLocationAvailability

    user = _make_user(db_session)
    inactive = _make_venue(db_session, name="Sala Chiusa", active=False)

    OnboardingService.complete_onboarding(
        user_id=user.id,
        venue_ids=[inactive.id, 999999],  # inattiva + inesistente
    )

    rows = UserLocationAvailability.query.filter_by(user_id=user.id).all()
    assert rows == []


def test_complete_onboarding_unknown_user_raises(db_session):
    from models.user.onboarding_service import OnboardingService

    with pytest.raises(ValueError):
        OnboardingService.complete_onboarding(user_id=123456789)
