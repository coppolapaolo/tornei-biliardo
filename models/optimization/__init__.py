"""
Module: models/optimization/__init__.py
Purpose: Database optimization helpers (caching decorator + eager loading).
"""

from .query_optimizer import (
    optimized_query,
    bulk_load_relationships,
)

__all__ = [
    "optimized_query",
    "bulk_load_relationships",
]
