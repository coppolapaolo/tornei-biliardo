"""
Individual Match domain routes package.

Split from single-file module for maintainability (Round 3 P3a).
"""

from flask import Blueprint

individual_match_bp = Blueprint("individual_match", __name__)

from . import proposals  # noqa: E402, F401
from . import matches  # noqa: E402, F401
from . import quick  # noqa: E402, F401
from . import availability  # noqa: E402, F401
from . import views  # noqa: E402, F401
from . import tpa  # noqa: E402, F401

__all__ = ["individual_match_bp"]
