from __future__ import annotations
from typing import Any, Callable
from sqlalchemy import event
from sqlalchemy.orm import with_loader_criteria

from models.user.models import User


def _user_not_deleted_clause() -> Callable[[type[User]], Any]:
    """Condizione SQLA 'utente NON cancellato' (schema: SoftDeleteMixin.deleted_at)."""
    def clause(UserCls: type[User]):
        if hasattr(UserCls, "deleted_at"):
            return UserCls.deleted_at.is_(None)  # SQL expression
        # Fallback: nessun filtro se lo schema fosse diverso
        return True
    return clause


def register_soft_delete_filter_for(db_session_or_class: Any) -> None:
    """
    Registra un filtro globale sulle SELECT: esclude gli User soft-deleted.
    Idempotente: evita doppie installazioni.
    Supporta sia una Session istanza che la classe SQLAlchemy Session.
    """
    flag_attr = "_user_soft_delete_filter_installed"
    if getattr(db_session_or_class, flag_attr, False):
        return
    try:
        setattr(db_session_or_class, flag_attr, True)
    except Exception:
        pass  # se non scrivibile, non blocchiamo l’installazione del listener

    @event.listens_for(db_session_or_class, "do_orm_execute")
    def _add_user_not_deleted_criteria(execute_state):
        if not execute_state.is_select:
            return
        # Opt-out per audit/report: .execution_options(include_deleted=True)
        if execute_state.execution_options.get("include_deleted", False):
            return
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(User, _user_not_deleted_clause(), include_aliases=True)
        )
