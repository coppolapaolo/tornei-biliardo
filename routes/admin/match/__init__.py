"""
Admin match management routes package.

Split from single-file module for maintainability (Round 3 P3b).
"""

from flask import Blueprint

match_bp = Blueprint("match", __name__)

from . import detail  # noqa: E402, F401
from . import scoring  # noqa: E402, F401
from . import multi_set  # noqa: E402, F401
from . import challenges  # noqa: E402, F401

__all__ = ["match_bp"]
