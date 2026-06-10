"""
Modular base models and mixins for the campionato billiards application.

This module provides modular base classes allowing models to pick only
the functionality they need (utility methods vs timestamps vs other features).

Author: Refactoring Phase 1 - Task 1.4 Update
Created: 2025-08-01
"""

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return current UTC time as a naive datetime (no tzinfo).

    Uses the non-deprecated datetime.now(timezone.utc) API internally,
    but strips tzinfo for compatibility with SQLite and existing naive
    datetime columns. Drop-in replacement for utc_now().
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Initialize SQLAlchemy instance FIRST (before importing transactional)
# This is required because transaction/manager.py imports db
db = SQLAlchemy()

# Initialize Flask-Mail
try:
    from flask_mail import Mail

    mail = Mail()
except ImportError:
    mail = None
    import logging

    logging.warning("Flask-Mail not installed. Email features will be disabled.")

# Import transactional decorator - now db is available when transaction/manager imports it
try:
    from .transaction.manager import transactional
except ImportError as e:
    # Fallback if transaction manager is not available
    # WARNING: This fallback is a no-op! Transactions won't be managed!
    import logging

    logging.warning(
        f"Failed to import transactional from transaction.manager: {e}. "
        "Using no-op fallback - database transactions will NOT be managed!"
    )

    def transactional(domain=None):
        def decorator(func):
            return func

        return decorator


# Abilita le foreign key in SQLite (necessario per ON DELETE CASCADE nei test/dev)
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


class TimestampMixin:
    """
    Mixin for models that need timestamp tracking.

    Adds created_at and updated_at fields with automatic management.
    Use this only when you actually need timestamp tracking.
    """

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class SoftDeleteMixin:
    """
    Mixin for models that need soft deletion capability.

    Soft deletion marks records as deleted without actually removing them
    from the database, useful for audit trails and data recovery.
    """

    deleted_at = db.Column(db.DateTime, nullable=True)

    def soft_delete(self) -> None:
        """Mark the record as soft deleted"""
        self.deleted_at = utc_now()

    @property
    def is_deleted(self) -> bool:
        """
        Safe anche su istanze detached: evita lazy-load se l'oggetto
        non è legato a una Session.
        - Se l'istanza è detached, legge dal __dict__ senza I/O DB.
        - Se l'attributo è già presente, evita refresh.
        - Se l'istanza è session-bound ma l'attributo è expired, l'accesso è lecito.
        """
        state = sa_inspect(self)

        # Se l'oggetto non ha stato o non è legato a nessuna sessione → non fare I/O
        if state is None or state.session is None:
            return self.__dict__.get("deleted_at") is not None

        # Attributo già materializzato → non forzare refresh
        if "deleted_at" in self.__dict__:
            return self.__dict__["deleted_at"] is not None

        # Session-bound: accesso lecito (se expired, SQLAlchemy gestisce il refresh)
        return bool(getattr(self, "deleted_at", None))


class AuditMixin:
    """
    Mixin for models that need audit trail functionality.

    Tracks who created and last modified each record.
    Requires User model to exist for foreign key relationships.
    """

    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    def set_created_by(self, user):
        """Set the user who created this record"""
        if user:
            self.created_by_id = user.id

    def set_updated_by(self, user):
        """Set the user who last updated this record"""
        if user:
            self.updated_by_id = user.id


class ValidationMixin:
    """
    Mixin that provides common validation functionality.

    Models can override validate() method to implement custom validation logic.
    """

    def validate(self):
        """
        Validate the model instance.

        Override this method in subclasses to implement custom validation.
        Should raise ValueError with descriptive message if validation fails.

        Returns:
            bool: True if validation passes

        Raises:
            ValueError: If validation fails with descriptive message
        """
        return True

    @transactional(domain="base")
    def save_with_validation(self):
        """Save the model after validation"""
        if self.validate():
            # Check if save method exists and call it safely
            save_method = getattr(self, "save", None)
            if save_method and callable(save_method):
                return save_method()
            else:
                # Fallback: manual save to database if no save method
                db.session.add(self)
                return self
        return None


# Base model classes for different use cases


class BaseModel(db.Model):
    """
    Full-featured base model with timestamps and utility methods.

    Use this for models that need both timestamp tracking and utility methods.
    Good for: Campionato, Match, etc. (business entities that need audit trail)
    """

    __abstract__ = True

    # Include both timestamp and utility functionality
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    @transactional(domain="base")
    def save(self):
        """Save the model instance to database"""
        db.session.add(self)
        return self

    @transactional(domain="base")
    def delete(self):
        """Delete the model instance from database"""
        db.session.delete(self)

    def to_dict(self):
        """Convert model instance to dictionary"""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result

    @classmethod
    def find_by_id(cls, id):
        """Find model instance by ID"""
        return db.session.get(cls, id)

    @classmethod
    def find_all(cls):
        """Find all instances of the model"""
        return db.session.query(cls).all()


def get_or_create(model_class, **kwargs):
    """
    Get existing instance or create new one if it doesn't exist.
    Handles race conditions during concurrent creation.

    Args:
        model_class: The model class to query
        **kwargs: Field values to search for and create with

    Returns:
        tuple: (instance, created) where created is boolean
    """
    instance = db.session.query(model_class).filter_by(**kwargs).first()
    if instance:
        return instance, False
    else:
        from sqlalchemy.exc import IntegrityError

        # Use a savepoint to protect the outer transaction from the IntegrityError
        try:
            with db.session.begin_nested():
                instance = model_class(**kwargs)
                db.session.add(instance)
            return instance, True
        except IntegrityError:
            instance = db.session.query(model_class).filter_by(**kwargs).first()
            if not instance:
                raise
            return instance, False


@transactional(domain="base")
def bulk_create(model_class, instances_data):
    """
    Create multiple instances efficiently.

    Args:
        model_class: The model class to create instances of
        instances_data: List of dictionaries with instance data

    Returns:
        list: Created instances
    """
    instances = []
    for data in instances_data:
        instance = model_class(**data)
        instances.append(instance)

    db.session.add_all(instances)
    return instances


# Database initialization helpers
def init_db(app):
    """Initialize database with Flask app"""
    db.init_app(app)

    with app.app_context():
        db.create_all()


def reset_db():
    """Reset database - WARNING: Deletes all data!"""
    db.drop_all()
    db.create_all()
