# models/exceptions.py
"""Shared domain exception taxonomy for the campionati-biliardo application.

All domain errors derive from :class:`DomainError`, which itself subclasses the
builtin :class:`ValueError`. This keeps the hierarchy **backward compatible**
with the many existing ``except ValueError`` handlers (route helpers, services)
while letting newer code raise/catch more specific types and let the route layer
map them to the correct HTTP status code.

Migration is incremental: services can keep raising plain ``ValueError`` and
gradually switch to the specific subclasses where the distinction matters
(not-found vs conflict vs validation vs permission).
"""

from typing import Final, List, Tuple, Type


class DomainError(ValueError):
    """Base class for expected, business-level errors.

    Subclasses ``ValueError`` so that legacy ``except ValueError`` handlers keep
    catching domain errors during the incremental migration.
    """


class ValidationError(DomainError):
    """Invalid input or a violated business rule (maps to HTTP 422)."""


class NotFoundError(DomainError):
    """A requested entity does not exist (maps to HTTP 404)."""


class ConflictError(DomainError):
    """Operation conflicts with the current state / uniqueness (HTTP 409)."""


class PermissionDeniedError(DomainError):
    """The actor is not allowed to perform the operation (HTTP 403)."""


class InvalidTransitionError(ConflictError):
    """Error for invalid state transitions.

    Raised when attempting a state transition that is not allowed by the
    business rules. Modelled as a :class:`ConflictError` (HTTP 409): an invalid
    transition is a conflict with the entity's current state. It remains a
    ``ValueError`` through the ``DomainError`` chain, so existing handlers keep
    working.
    """


# Exception type → HTTP status. DomainError (the base) must stay last so the
# more specific subclasses win.
_STATUS_BY_TYPE: Final[List[Tuple[Type[BaseException], int]]] = [
    (NotFoundError, 404),
    (PermissionDeniedError, 403),
    (ConflictError, 409),
    (ValidationError, 422),
    (DomainError, 400),
]


def http_status_for_exception(exc: BaseException) -> int:
    """Return the HTTP status code that best represents ``exc``.

    - ``DomainError`` subclasses map to their semantic code (404/403/409/422).
    - Builtin ``PermissionError`` → 403.
    - Any other ``ValueError`` → 400 (generic bad request).
    - Anything else → 500.
    """
    for exc_type, status in _STATUS_BY_TYPE:
        if isinstance(exc, exc_type):
            return status
    if isinstance(exc, PermissionError):
        return 403
    if isinstance(exc, ValueError):
        return 400
    return 500


__all__ = [
    "DomainError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "PermissionDeniedError",
    "InvalidTransitionError",
    "http_status_for_exception",
]
