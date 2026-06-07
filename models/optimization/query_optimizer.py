"""
Module: models/optimization/query_optimizer.py
Purpose: Lightweight query-optimization helpers (caching + eager loading).

History: this module previously also hosted an always-on N+1 monitoring layer
(``QueryAnalyzer``/``QueryOptimizer`` with global SQLAlchemy event listeners and
a performance dashboard). That machinery recorded every executed query into an
in-memory store but had **no production consumer** (only legacy tests read the
dashboard), so it added per-query overhead with zero payoff and was removed. The
genuinely useful optimization primitives — the ``optimized_query`` caching
decorator and the ``bulk_load_relationships`` eager-loading helper — are kept.
"""

from __future__ import annotations

from typing import Callable, List, Optional, TypeVar
from functools import wraps
import logging

from sqlalchemy.orm import Query

from ..caching import cache_manager

logger = logging.getLogger(__name__)

T = TypeVar("T")


def optimized_query(
    eager_load: Optional[List[str]] = None,
    cache_ttl: Optional[int] = None,
    cache_tags: Optional[List[str]] = None,
):
    """Decorator for optimized database queries (transparent result caching)."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            cache_key = None

            # Apply caching if specified
            if cache_ttl:
                cache_key = (
                    f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
                )
                cached_result = cache_manager.get(cache_key)
                if cached_result is not None:
                    return cached_result

            # Execute function
            result = func(*args, **kwargs)

            # Cache result if specified
            if cache_ttl and cache_key is not None:
                cache_manager.set(
                    key=cache_key,
                    value=result,
                    ttl_seconds=cache_ttl,
                    tags=cache_tags or [],
                )

            return result

        return wrapper

    return decorator


def bulk_load_relationships(query: Query, *relationships) -> Query:
    """Helper to bulk load relationships and avoid N+1 problems.

    Args:
        query: SQLAlchemy Query object
        *relationships: Relationship attributes (not strings) or option objects

    Example:
        query = bulk_load_relationships(
            session.query(User),
            User.profile,
            User.orders
        )
    """
    from sqlalchemy.orm import selectinload
    from sqlalchemy.orm.attributes import InstrumentedAttribute

    for relationship in relationships:
        if isinstance(relationship, InstrumentedAttribute):
            # SQLAlchemy relationship attribute
            query = query.options(selectinload(relationship))
        elif hasattr(relationship, "_sa_class_manager"):
            # Another type of SQLAlchemy attribute
            query = query.options(selectinload(relationship))
        else:
            # Assume it's already an option object (joinedload, selectinload, etc.)
            query = query.options(relationship)

    return query
