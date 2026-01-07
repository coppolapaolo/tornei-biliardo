"""
Unified soft delete filter for models with SoftDeleteMixin.

This module provides automatic query filtering to exclude soft-deleted records
from all SELECT queries. Models must use SoftDeleteMixin from models.base.

Usage:
    from models.soft_delete import register_soft_delete_filters
    from sqlalchemy.orm import Session as SASession

    # Register filters during app initialization
    register_soft_delete_filters(SASession)

    # Opt-out for specific queries (to include deleted records):
    query = db.session.execute(
        select(Gara).execution_options(include_deleted=True)
    )

Author: Soft Delete Feature - 2026-01-06
"""

from __future__ import annotations
from typing import Any, Callable, List, Type
from sqlalchemy import event
from sqlalchemy.orm import with_loader_criteria


def _create_not_deleted_clause(model_class: Type[Any]) -> Callable[[Type[Any]], Any]:
    """Create a 'not deleted' clause for a model class.

    Args:
        model_class: SQLAlchemy model class with SoftDeleteMixin

    Returns:
        Callable that returns SQL expression for deleted_at IS NULL
    """
    def clause(cls: Type[Any]) -> Any:
        if hasattr(cls, "deleted_at"):
            return cls.deleted_at.is_(None)
        # Fallback: no filter if schema is different
        return True

    return clause


def register_soft_delete_filters(
    db_session_class: Any,
    models: List[Type[Any]] | None = None
) -> None:
    """Register soft delete filters for multiple models.

    Installs a SQLAlchemy event listener that automatically adds
    'WHERE deleted_at IS NULL' to all SELECT queries for the specified models.

    Args:
        db_session_class: SQLAlchemy Session class (not instance)
        models: List of model classes to filter. If None, imports default models.

    Usage:
        from sqlalchemy.orm import Session as SASession
        from models.soft_delete import register_soft_delete_filters

        register_soft_delete_filters(SASession)  # Uses default models
        # or
        register_soft_delete_filters(SASession, [User, Gara, Campionato])
    """
    # Idempotent: prevent double installation
    flag_attr = "_unified_soft_delete_filter_installed"
    if getattr(db_session_class, flag_attr, False):
        return

    try:
        setattr(db_session_class, flag_attr, True)
    except Exception:
        pass  # If not writable, don't block listener installation

    # Import default models if not provided
    if models is None:
        # Lazy import to avoid circular dependencies
        from models.user.models import User
        from models.competition.models import Gara
        from models.campionato.models import Campionato

        models = [User, Gara, Campionato]

    @event.listens_for(db_session_class, "do_orm_execute")
    def _add_soft_delete_criteria(execute_state: Any) -> None:
        """Event listener that adds soft delete filtering to SELECT queries."""
        # Only filter SELECT queries
        if not execute_state.is_select:
            return

        # Opt-out: .execution_options(include_deleted=True)
        if execute_state.execution_options.get("include_deleted", False):
            return

        # Add filter for each registered model
        for model_class in models:
            if hasattr(model_class, "deleted_at"):
                execute_state.statement = execute_state.statement.options(
                    with_loader_criteria(
                        model_class,
                        _create_not_deleted_clause(model_class),
                        include_aliases=True
                    )
                )
