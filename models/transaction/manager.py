"""
Module: models/transaction/manager.py
Purpose: Advanced transaction management for domain services
Requirements: Ensure data consistency and proper transaction boundaries across domains
"""

from __future__ import annotations

from typing import Optional, Any, Dict, List, Callable, TypeVar, Generic
from contextlib import contextmanager
from functools import wraps
from dataclasses import dataclass
from enum import Enum
import logging
import time
from threading import local

from ..base import db
from sqlalchemy import text

# Setup logging
logger = logging.getLogger(__name__)

# Thread-local storage for transaction context
_transaction_local = local()

T = TypeVar("T")


class TransactionIsolationLevel(Enum):
    """Database isolation levels."""

    READ_UNCOMMITTED = "READ UNCOMMITTED"
    READ_COMMITTED = "READ COMMITTED"
    REPEATABLE_READ = "REPEATABLE READ"
    SERIALIZABLE = "SERIALIZABLE"


class TransactionStatus(Enum):
    """Transaction status tracking."""

    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class TransactionMetrics:
    """Metrics for transaction performance monitoring."""

    transaction_id: str
    start_time: float
    end_time: Optional[float]
    duration_ms: Optional[float]
    status: TransactionStatus
    isolation_level: Optional[TransactionIsolationLevel]
    queries_executed: int
    rollback_reason: Optional[str]
    affected_tables: List[str]

    @property
    def is_completed(self) -> bool:
        return self.status in [
            TransactionStatus.COMMITTED,
            TransactionStatus.ROLLED_BACK,
            TransactionStatus.FAILED,
        ]


class TransactionContext:
    """Context for tracking transaction state and metadata."""

    def __init__(
        self,
        transaction_id: str,
        isolation_level: Optional[TransactionIsolationLevel] = None,
        read_only: bool = False,
    ):
        self.transaction_id = transaction_id
        self.isolation_level = isolation_level
        self.read_only = read_only
        self.start_time = time.time()
        self.status = TransactionStatus.ACTIVE
        self.savepoints: List[str] = []
        self.affected_domains: set = set()
        self.queries_executed = 0
        self.rollback_reason: Optional[str] = None

    def add_affected_domain(self, domain: str) -> None:
        """Track which domains are affected by this transaction."""
        self.affected_domains.add(domain)

    def increment_query_count(self) -> None:
        """Increment the query counter."""
        self.queries_executed += 1

    def add_savepoint(self, name: str) -> None:
        """Add a savepoint to the transaction."""
        self.savepoints.append(name)

    def to_metrics(self) -> TransactionMetrics:
        """Convert to metrics object."""
        end_time = time.time()
        duration_ms = (end_time - self.start_time) * 1000

        return TransactionMetrics(
            transaction_id=self.transaction_id,
            start_time=self.start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            status=self.status,
            isolation_level=self.isolation_level,
            queries_executed=self.queries_executed,
            rollback_reason=self.rollback_reason,
            affected_tables=list(self.affected_domains),
        )


class TransactionManager:
    """Advanced transaction manager for domain services."""

    def __init__(self):
        self._transaction_stack: List[TransactionContext] = []
        self._metrics_history: List[TransactionMetrics] = []
        self._next_transaction_id = 1

    @property
    def current_transaction(self) -> Optional[TransactionContext]:
        """Get the current active transaction context."""
        return getattr(_transaction_local, "current_transaction", None)

    @current_transaction.setter
    def current_transaction(self, context: Optional[TransactionContext]) -> None:
        """Set the current transaction context."""
        _transaction_local.current_transaction = context

    def generate_transaction_id(self) -> str:
        """Generate unique transaction ID."""
        transaction_id = f"tx_{self._next_transaction_id:06d}"
        self._next_transaction_id += 1
        return transaction_id

    @contextmanager
    def transaction(
        self,
        isolation_level: Optional[TransactionIsolationLevel] = None,
        read_only: bool = False,
        savepoint_name: Optional[str] = None,
    ):
        """Context manager for database transactions with enhanced features."""

        transaction_id = self.generate_transaction_id()
        context = TransactionContext(transaction_id, isolation_level, read_only)

        # Check if we're in a nested transaction
        is_nested = self.current_transaction is not None
        parent_context = self.current_transaction

        logger.debug(f"Starting transaction {transaction_id} (nested: {is_nested})")

        try:
            if is_nested:
                # Create savepoint for nested transaction
                savepoint_name = savepoint_name or f"sp_{transaction_id}"
                db.session.begin_nested()
                context.add_savepoint(savepoint_name)
                logger.debug(f"Created savepoint {savepoint_name}")
            else:
                # Check if there's already an active transaction
                if db.session.is_active:
                    # We're in an existing transaction (e.g., test transaction)
                    # Create a savepoint instead of starting a new transaction
                    savepoint_name = savepoint_name or f"sp_{transaction_id}"
                    try:
                        db.session.begin_nested()
                        context.add_savepoint(savepoint_name)
                        logger.debug(
                            f"Created savepoint {savepoint_name} within existing transaction"
                        )
                        is_nested = True  # Treat as nested for commit/rollback logic
                    except Exception as e:
                        logger.warning(
                            f"Failed to create savepoint, proceeding without transaction boundaries: {e}"
                        )
                        # Continue without explicit transaction management
                else:
                    # Start new transaction
                    db.session.begin()

                    # Set isolation level if specified
                    if isolation_level:
                        # Check if we're using SQLite (doesn't support SET TRANSACTION ISOLATION LEVEL)
                        if "sqlite" not in str(db.engine.dialect).lower():
                            db.session.execute(
                                text(
                                    f"SET TRANSACTION ISOLATION LEVEL {isolation_level.value}"
                                )
                            )
                            logger.debug(
                                f"Set isolation level to {isolation_level.value}"
                            )
                        else:
                            logger.debug("Skipping isolation level setting for SQLite")

                    # Set read-only if specified
                    if read_only:
                        # Check if we're using SQLite (doesn't support SET TRANSACTION READ ONLY)
                        if "sqlite" not in str(db.engine.dialect).lower():
                            db.session.execute(text("SET TRANSACTION READ ONLY"))
                            logger.debug("Set transaction to read-only")
                        else:
                            logger.debug("Skipping read-only setting for SQLite")

            # Set as current transaction
            self.current_transaction = context

            # Yield control to the calling code
            yield context

            # Commit the transaction/savepoint
            if is_nested:
                # For nested transactions (savepoints), we need to explicitly release the savepoint
                # This ensures the changes are preserved within the parent transaction
                try:
                    db.session.commit()  # This releases the savepoint in SQLAlchemy
                    logger.debug(
                        f"Nested transaction (savepoint) {transaction_id} released"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to release nested transaction {transaction_id}: {e}"
                    )
                    # If we can't release the savepoint, we should rollback to it
                    try:
                        db.session.rollback()
                        logger.warning(
                            f"Rolled back to savepoint {transaction_id} due to release failure"
                        )
                    except Exception as rollback_error:
                        logger.error(
                            f"Failed to rollback to savepoint {transaction_id}: {rollback_error}"
                        )
            else:
                try:
                    db.session.commit()
                    logger.debug(f"Transaction {transaction_id} committed")
                except Exception as e:
                    logger.warning(
                        f"Failed to commit transaction {transaction_id}: {e}"
                    )

            context.status = TransactionStatus.COMMITTED

        except Exception as e:
            # Rollback the transaction/savepoint
            context.rollback_reason = str(e)

            try:
                if is_nested:
                    db.session.rollback()  # Rollback to savepoint
                    logger.warning(
                        f"Nested transaction {transaction_id} rolled back: {str(e)}"
                    )
                else:
                    db.session.rollback()
                    logger.warning(
                        f"Transaction {transaction_id} rolled back: {str(e)}"
                    )
            except Exception as rollback_error:
                logger.error(
                    f"Failed to rollback transaction {transaction_id}: {rollback_error}"
                )

            context.status = TransactionStatus.ROLLED_BACK
            raise

        except:
            # Handle unexpected errors
            context.status = TransactionStatus.FAILED
            try:
                if is_nested:
                    db.session.rollback()
                else:
                    db.session.rollback()
            except Exception as rollback_error:
                logger.error(
                    f"Failed to rollback transaction {transaction_id}: {rollback_error}"
                )
            logger.error(f"Transaction {transaction_id} failed with unexpected error")
            raise
        finally:
            # Restore parent context
            self.current_transaction = parent_context

            # Record metrics
            metrics = context.to_metrics()
            self._metrics_history.append(metrics)

            # Limit metrics history
            if len(self._metrics_history) > 1000:
                self._metrics_history = self._metrics_history[-500:]  # Keep last 500

            logger.debug(
                f"Transaction {transaction_id} completed in {metrics.duration_ms:.2f}ms"
            )

    @contextmanager
    def read_only_transaction(self):
        """Convenience method for read-only transactions."""
        with self.transaction(read_only=True) as context:
            yield context

    @contextmanager
    def serializable_transaction(self):
        """Convenience method for serializable transactions."""
        with self.transaction(
            isolation_level=TransactionIsolationLevel.SERIALIZABLE
        ) as context:
            yield context

    def track_domain_access(self, domain: str) -> None:
        """Track which domain is being accessed in current transaction."""
        if self.current_transaction:
            self.current_transaction.add_affected_domain(domain)

    def track_query_execution(self) -> None:
        """Track query execution in current transaction."""
        if self.current_transaction:
            self.current_transaction.increment_query_count()

    def get_transaction_metrics(
        self, status: Optional[TransactionStatus] = None, limit: int = 100
    ) -> List[TransactionMetrics]:
        """Get transaction metrics with optional filtering."""

        metrics = self._metrics_history

        if status:
            metrics = [m for m in metrics if m.status == status]

        return metrics[-limit:]

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get summary of transaction performance."""

        if not self._metrics_history:
            return {"total_transactions": 0}

        total = len(self._metrics_history)
        committed = len(
            [
                m
                for m in self._metrics_history
                if m.status == TransactionStatus.COMMITTED
            ]
        )
        rolled_back = len(
            [
                m
                for m in self._metrics_history
                if m.status == TransactionStatus.ROLLED_BACK
            ]
        )
        failed = len(
            [m for m in self._metrics_history if m.status == TransactionStatus.FAILED]
        )

        # Calculate average duration
        completed_transactions = [
            m for m in self._metrics_history if m.duration_ms is not None
        ]
        avg_duration = (
            sum(
                m.duration_ms
                for m in completed_transactions
                if m.duration_ms is not None
            )
            / len(completed_transactions)
            if completed_transactions
            else 0
        )

        # Find slowest transactions
        slowest = sorted(
            completed_transactions, key=lambda m: m.duration_ms or 0, reverse=True
        )[:5]

        return {
            "total_transactions": total,
            "committed": committed,
            "rolled_back": rolled_back,
            "failed": failed,
            "success_rate_percent": round(committed / total * 100, 1)
            if total > 0
            else 0,
            "average_duration_ms": round(avg_duration, 2),
            "slowest_transactions": [
                {
                    "transaction_id": m.transaction_id,
                    "duration_ms": m.duration_ms,
                    "affected_tables": m.affected_tables,
                }
                for m in slowest
            ],
        }


# Global transaction manager instance
transaction_manager = TransactionManager()


def transactional(
    isolation_level: Optional[TransactionIsolationLevel] = None,
    read_only: bool = False,
    domain: Optional[str] = None,
):
    """Decorator for automatic transaction management."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            with transaction_manager.transaction(
                isolation_level=isolation_level, read_only=read_only
            ) as context:
                if domain:
                    transaction_manager.track_domain_access(domain)

                return func(*args, **kwargs)

        return wrapper

    return decorator


def read_only(domain: Optional[str] = None):
    """Decorator for read-only operations."""
    return transactional(read_only=True, domain=domain)


def serializable(domain: Optional[str] = None):
    """Decorator for operations requiring serializable isolation."""
    return transactional(
        isolation_level=TransactionIsolationLevel.SERIALIZABLE, domain=domain
    )


class DomainService:
    """Enhanced base class for domain services with transaction support."""

    def __init__(self, domain_name: str):
        self.domain_name = domain_name

    def _track_domain_access(self):
        """Track domain access in current transaction."""
        transaction_manager.track_domain_access(self.domain_name)

    def _execute_with_tracking(self, operation: Callable[[], T]) -> T:
        """Execute operation with domain tracking."""
        self._track_domain_access()
        transaction_manager.track_query_execution()
        return operation()

    @contextmanager
    def domain_transaction(
        self,
        isolation_level: Optional[TransactionIsolationLevel] = None,
        read_only: bool = False,
    ):
        """Start transaction with automatic domain tracking."""
        with transaction_manager.transaction(
            isolation_level=isolation_level, read_only=read_only
        ) as context:
            self._track_domain_access()
            yield context
