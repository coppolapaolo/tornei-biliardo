# models/exceptions.py
"""Shared exception classes for the campionati-biliardo application."""


class InvalidTransitionError(ValueError):
    """Error for invalid state transitions.

    This exception is raised when attempting to perform a state transition
    that is not allowed by the business rules.
    """
