"""Regression tests for the incremental adoption of domain exceptions.

Follow-up #1 of the 2026-06 technical-debt review: services that previously
raised a generic ``ValueError`` for not-found / conflict / validation /
permission cases now raise the specific subclasses from ``models.exceptions``.

Because every subclass derives from ``DomainError(ValueError)`` the change is
backward compatible (legacy ``except ValueError`` keeps working); these tests
pin the *specific* type so the AJAX route layer maps to the right HTTP status
via ``http_status_for_exception``.
"""

import pytest

from models import db
from models.user.models import User
from models.user.role_enum import UserRole
from models.user.venue_manager_service import VenueManagerService
from models.competition.inscription_service import InscriptionService
from models.location.models import BilliardHall
from models.exceptions import (
    DomainError,
    NotFoundError,
    ConflictError,
    ValidationError,
    PermissionDeniedError,
    InvalidTransitionError,
    http_status_for_exception,
)


class TestHttpStatusMapping:
    """The taxonomy maps to the documented HTTP status codes."""

    @pytest.mark.parametrize(
        "exc, expected",
        [
            (NotFoundError("x"), 404),
            (PermissionDeniedError("x"), 403),
            (ConflictError("x"), 409),
            (InvalidTransitionError("x"), 409),  # ConflictError subclass
            (ValidationError("x"), 422),
            (DomainError("x"), 400),
            (ValueError("x"), 400),  # plain ValueError stays generic
        ],
    )
    def test_status_for_exception(self, exc, expected):
        assert http_status_for_exception(exc) == expected

    def test_all_domain_errors_are_value_errors(self):
        # Backward compatibility: legacy `except ValueError` must keep catching.
        for cls in (
            NotFoundError,
            ConflictError,
            ValidationError,
            PermissionDeniedError,
            InvalidTransitionError,
        ):
            assert issubclass(cls, ValueError)


class TestVenueManagerServiceExceptions:
    """VenueManagerService raises specific domain exceptions."""

    @pytest.fixture
    def venue(self, app, db_session):
        with app.app_context():
            v = BilliardHall(name="Hall", address="addr", city="city", postal_code="1")
            db.session.add(v)
            db.session.commit()
            yield v

    @pytest.fixture
    def player(self, app, db_session):
        with app.app_context():
            u = User(
                username="vm_player",
                email="vm_player@example.com",
                role=UserRole.PLAYER.value,
            )
            u.set_password("secure123")
            db.session.add(u)
            db.session.commit()
            yield u

    def test_create_request_missing_user_raises_not_found(self, app, db_session, venue):
        with app.app_context():
            with pytest.raises(NotFoundError):
                VenueManagerService.create_venue_manager_request(
                    user_id=999999, venue_id=venue.id, notes="please"
                )

    def test_create_request_empty_notes_raises_validation(
        self, app, db_session, venue, player
    ):
        with app.app_context():
            with pytest.raises(ValidationError):
                VenueManagerService.create_venue_manager_request(
                    user_id=player.id, venue_id=venue.id, notes="   "
                )

    def test_create_request_duplicate_raises_conflict(
        self, app, db_session, venue, player
    ):
        with app.app_context():
            VenueManagerService.create_venue_manager_request(
                user_id=player.id, venue_id=venue.id, notes="first"
            )
            with pytest.raises(ConflictError):
                VenueManagerService.create_venue_manager_request(
                    user_id=player.id, venue_id=venue.id, notes="second"
                )

    def test_process_request_by_non_admin_raises_permission_denied(
        self, app, db_session, player
    ):
        with app.app_context():
            with pytest.raises(PermissionDeniedError):
                VenueManagerService.process_venue_manager_request(
                    request_id=1, admin_user=player, approve=True
                )


class TestInscriptionServiceExceptions:
    """InscriptionService raises specific domain exceptions."""

    def test_open_inscriptions_missing_gara_raises_not_found(self, app, db_session):
        from datetime import datetime, timedelta

        with app.app_context():
            start = datetime(2030, 1, 1)
            end = start + timedelta(days=7)
            with pytest.raises(NotFoundError):
                InscriptionService.open_inscriptions(
                    gara_id=999999, inscription_start=start, inscription_end=end
                )
