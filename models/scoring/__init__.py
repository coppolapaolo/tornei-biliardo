# models/scoring/__init__.py
"""Scoring module for campionato classifications."""

from .policies import ScoringPolicy
from .strategies import (
    ClassicScoringPolicy,
    FargoRatingScoringPolicy,
    EloRatingScoringPolicy,
)

__all__ = [
    "ScoringPolicy",
    "ClassicScoringPolicy",
    "FargoRatingScoringPolicy",
    "EloRatingScoringPolicy",
]
