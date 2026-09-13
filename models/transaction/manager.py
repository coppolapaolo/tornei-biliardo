"""
Module: models/transaction/manager.py
Purpose: Advanced transaction management for domain services
Requirements: Ensure data consistency and proper transaction boundaries across domains
"""

from __future__ import annotations

from typing import Optional, Any, Dict, List, Callable, TypeVar
from contextlib import contextmanager
from functools import wraps
from dataclasses import dataclass
from enum import Enum
import logging
import time
from threading import local, Lock

from ..base import db
from sqlalchemy import text
from sqlalchemy.exc import ResourceClosedError
from sqlalchemy.orm import SessionTransaction

# Setup logging
logger = logging.getLogger(__name__)

# Thread-local storage for transaction context
_transaction_local = local()

T = TypeVar("T")


def _apri_transazione_sqlite() -> None:
    """Apre la transazione sul database prima di un savepoint, se non c'e'.

    Il driver `sqlite3` apre la transazione solo davanti a una scrittura: le
    letture girano fuori da ogni transazione. Se la sessione ha soltanto letto,
    un `SAVEPOINT` e' il primo comando della transazione per SQLite, e il suo
    `RELEASE` equivale a un commit — un annullamento successivo non troverebbe
    piu' niente.

    Dove serve davvero: `savepoint()` chiamato fuori da un `@transactional`
    (una route, un servizio non decorato). Dentro un decoratore il caso non
    capita, perche' il piu' esterno apre subito il proprio savepoint — con
    SQLAlchemy 2.0 `db.session.is_active` e' vero anche senza transazione,
    quindi prende sempre il ramo «pseudo-nested» — e SQLite e' gia' in
    transazione. Nel ramo annidato del gestore resta come difesa, per un
    decoratore esterno che trovasse la sessione non attiva.

    Il `BEGIN` e' quello che il driver emetterebbe comunque alla prima
    scrittura, e senza `IMMEDIATE`: i lock restano quelli di prima.
    """
    connessione = db.session.connection()
    if connessione.dialect.name != "sqlite":
        return
    dbapi = connessione.connection.dbapi_connection
    if dbapi is not None and not getattr(dbapi, "in_transaction", True):
        connessione.exec_driver_sql("BEGIN")


@contextmanager
def savepoint():
    """Un savepoint scritto a mano, al posto di ``db.session.begin_nested()``.

    Serve allo schema di ADR-025: far emergere al flush un ``IntegrityError``
    per tradurlo, senza rovinare la transazione del chiamante. Si comporta
    come ``with db.session.begin_nested():`` — rilascia all'uscita, annulla e
    propaga su un'eccezione — con in piu' l'apertura della transazione SQLite
    (`_apri_transazione_sqlite`): dopo sole letture, il ``RELEASE`` di un
    ``begin_nested`` nudo e' un commit, e l'annullamento del chiamante non
    troverebbe piu' niente (ADR-061). Presidio:
    ``tests/new/unit/test_savepoint_a_mano.py``.
    """
    _apri_transazione_sqlite()
    with db.session.begin_nested() as transazione:
        yield transazione


def _chiudi_savepoint(
    savepoint: Optional[SessionTransaction], transaction_id: str, salva: bool
) -> None:
    """Rilascia o annulla il savepoint, e soltanto quello.

    `db.session.commit()` e `db.session.rollback()` agiscono sulla transazione
    piu' esterna: e' il difetto corretto il 2026-09-13 (ADR-061).

    Un savepoint gia' chiuso vuol dire che il codice interno ha chiamato a mano
    `db.session.commit()` o `rollback()`, che il progetto vieta: non c'e' piu'
    niente da chiudere, e lo si scrive nel log invece di sollevare.
    """
    if savepoint is None:
        return
    try:
        if salva:
            savepoint.commit()
        else:
            savepoint.rollback()
    except ResourceClosedError:
        logger.warning(
            f"Savepoint of {transaction_id} already closed: the inner code "
            "committed or rolled back the session by hand"
        )


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
        # current_transaction e' thread-local, ma _next_transaction_id e
        # _metrics_history sono condivisi sull'istanza globale: in un server
        # WSGI multithread (PythonAnywhere) le mutazioni concorrenti darebbero
        # ID duplicati o una lista metriche corrotta. Proteggi con un lock.
        self._state_lock = Lock()

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
        with self._state_lock:
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

        # Check if we're in a nested transaction managed by TransactionManager
        is_true_nested = self.current_transaction is not None
        # Track if we created a savepoint due to autobegin (pseudo-nested)
        is_pseudo_nested = False
        parent_context = self.current_transaction

        logger.debug(
            f"Starting transaction {transaction_id} (true_nested: {is_true_nested})"
        )

        # Il savepoint di una transazione annidata. Si chiude e si annulla
        # **questo**, mai la sessione: `db.session.commit()` e `rollback()`
        # agiscono sulla transazione piu' esterna (vedi `_chiudi_savepoint`).
        savepoint: Optional[SessionTransaction] = None

        try:
            if is_true_nested:
                # Create savepoint for truly nested transaction
                savepoint_name = savepoint_name or f"sp_{transaction_id}"
                _apri_transazione_sqlite()
                savepoint = db.session.begin_nested()
                context.add_savepoint(savepoint_name)
                logger.debug(f"Created savepoint {savepoint_name}")
            else:
                # Check if there's already an active transaction (e.g., autobegin)
                if db.session.is_active:
                    # Session has autobegin - create savepoint but remember to
                    # commit parent transaction at the end
                    savepoint_name = savepoint_name or f"sp_{transaction_id}"
                    try:
                        db.session.begin_nested()
                        context.add_savepoint(savepoint_name)
                        logger.debug(
                            f"Created savepoint {savepoint_name} within "
                            "autobegin transaction"
                        )
                        is_pseudo_nested = True  # Need to commit parent at end
                    except Exception as e:
                        logger.warning(
                            f"Failed to create savepoint, proceeding without "
                            f"transaction boundaries: {e}"
                        )
                        # Continue without explicit transaction management
                else:
                    # Start new transaction
                    db.session.begin()

                    # Set isolation level if specified
                    if isolation_level:
                        # Check if we're using SQLite
                        # (doesn't support SET TRANSACTION ISOLATION LEVEL)
                        if "sqlite" not in str(db.engine.dialect).lower():
                            db.session.execute(
                                text(
                                    f"SET TRANSACTION ISOLATION LEVEL "
                                    f"{isolation_level.value}"
                                )
                            )
                            logger.debug(
                                f"Set isolation level to {isolation_level.value}"
                            )
                        else:
                            logger.debug("Skipping isolation level setting for SQLite")

                    # Set read-only if specified
                    if read_only:
                        # Check if we're using SQLite
                        # (doesn't support SET TRANSACTION READ ONLY)
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
            if is_true_nested:
                # Si rilascia il solo savepoint: il salvataggio vero lo fa il
                # decoratore piu' esterno. Fino al 2026-09-13 qui c'era
                # `db.session.commit()`, che da SQLAlchemy 1.4 chiude la
                # transazione esterna (ADR-061).
                try:
                    _chiudi_savepoint(savepoint, transaction_id, salva=True)
                    logger.debug(
                        f"Nested transaction (savepoint) {transaction_id} released"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to release nested transaction {transaction_id}: {e}"
                    )
                    # Re-raise: un commit fallito NON deve essere spacciato per
                    # successo. Senza questo il chiamante riceve un ritorno OK
                    # mentre il DB ha annullato i dati (perdita dati silenziosa).
                    # L'annullamento del savepoint lo fa l'except esterno.
                    raise
            elif is_pseudo_nested:
                # For pseudo-nested (autobegin), release savepoint AND commit parent
                # NOTE: First commit() releases the savepoint, second commits the
                # outer autobegin transaction. Both are required!
                try:
                    db.session.commit()  # Release savepoint
                    logger.debug(
                        f"Pseudo-nested transaction {transaction_id} savepoint released"
                    )
                    # If session is still active, commit the outer transaction
                    if db.session.is_active:
                        db.session.commit()  # Commit outer autobegin transaction
                        logger.debug(
                            f"Pseudo-nested transaction {transaction_id} "
                            "outer transaction committed"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to commit pseudo-nested transaction "
                        f"{transaction_id}: {e}"
                    )
                    try:
                        db.session.rollback()
                    except Exception as rollback_error:
                        logger.error(
                            f"Failed to rollback pseudo-nested transaction "
                            f"{transaction_id}: {rollback_error}"
                        )
                    # Re-raise: vedi nota nel ramo nested (no successo fittizio).
                    raise
            else:
                try:
                    db.session.commit()
                    logger.debug(f"Transaction {transaction_id} committed")
                except Exception as e:
                    logger.warning(
                        f"Failed to commit transaction {transaction_id}: {e}"
                    )
                    # Re-raise: un commit fallito (IntegrityError, DB locked, …)
                    # NON deve tornare come successo al chiamante. L'except
                    # esterno fa il rollback e propaga. Vedi nota ramo nested.
                    raise

            context.status = TransactionStatus.COMMITTED

        except Exception as e:
            # Rollback the transaction/savepoint
            context.rollback_reason = str(e)

            try:
                if is_true_nested:
                    # Solo il savepoint: il lavoro del chiamante resta, e decide
                    # lui se proseguire o propagare. Con `db.session.rollback()`
                    # si perdeva anche quello, in silenzio, quando il chiamante
                    # catturava l'eccezione e andava avanti (EventBus).
                    _chiudi_savepoint(savepoint, transaction_id, salva=False)
                    logger.warning(
                        f"Nested transaction {transaction_id} rolled back to "
                        f"savepoint: {str(e)}"
                    )
                elif is_pseudo_nested:
                    # Rollback to savepoint and parent: e' la transazione esterna
                    db.session.rollback()
                    logger.warning(
                        f"Pseudo-nested transaction {transaction_id} rolled back: "
                        f"{str(e)}"
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

        finally:
            # Restore parent context
            self.current_transaction = parent_context

            # Record metrics (lista condivisa: protetta dal lock per evitare
            # append/troncamento concorrenti corrotti)
            metrics = context.to_metrics()
            with self._state_lock:
                self._metrics_history.append(metrics)
                # Limit metrics history
                if len(self._metrics_history) > 1000:
                    self._metrics_history = self._metrics_history[-500:]

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
            "success_rate_percent": (
                round(committed / total * 100, 1) if total > 0 else 0
            ),
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
            ):
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
