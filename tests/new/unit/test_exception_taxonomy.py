"""Unit tests for the domain exception taxonomy (models/exceptions.py).

Covers:
- The hierarchy is backward compatible (every DomainError IS-A ValueError),
  so legacy `except ValueError` handlers keep catching domain errors.
- `http_status_for_exception` maps each type to the right HTTP status.
"""

import pytest

from models.exceptions import (
    DomainError,
    ValidationError,
    NotFoundError,
    ConflictError,
    PermissionDeniedError,
    InvalidTransitionError,
    http_status_for_exception,
)


@pytest.mark.unit
class TestHierarchy:
    def test_domain_error_is_value_error(self):
        """Backward compat: DomainError must subclass ValueError."""
        assert issubclass(DomainError, ValueError)

    @pytest.mark.parametrize(
        "exc_type",
        [ValidationError, NotFoundError, ConflictError, PermissionDeniedError],
    )
    def test_subclasses_are_domain_and_value_errors(self, exc_type):
        assert issubclass(exc_type, DomainError)
        assert issubclass(exc_type, ValueError)

    def test_invalid_transition_is_conflict(self):
        """InvalidTransitionError is a ConflictError (and still a ValueError)."""
        assert issubclass(InvalidTransitionError, ConflictError)
        assert issubclass(InvalidTransitionError, DomainError)
        assert issubclass(InvalidTransitionError, ValueError)

    def test_legacy_except_value_error_catches_domain_errors(self):
        """A NotFoundError must be catchable by `except ValueError`."""
        with pytest.raises(ValueError):
            raise NotFoundError("missing")


@pytest.mark.unit
class TestHttpStatusMapping:
    @pytest.mark.parametrize(
        "exc, expected",
        [
            (NotFoundError("x"), 404),
            (PermissionDeniedError("x"), 403),
            (ConflictError("x"), 409),
            (InvalidTransitionError("x"), 409),
            (ValidationError("x"), 422),
            (DomainError("x"), 400),
            (ValueError("x"), 400),
            (PermissionError("x"), 403),
            (RuntimeError("x"), 500),
        ],
    )
    def test_mapping(self, exc, expected):
        assert http_status_for_exception(exc) == expected
