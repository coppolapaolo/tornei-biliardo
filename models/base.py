"""
Modular base models and mixins for the tournament billiards application.

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
from datetime import datetime

# Initialize SQLAlchemy instance
db = SQLAlchemy()


# Abilita le foreign key in SQLite (necessario per ON DELETE CASCADE nei test/dev)
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class UtilityMixin:
    """
    Mixin that provides common utility methods for models.

    Includes database operations and convenience methods without
    adding any additional database columns.
    """

    def save(self):
        """Save the model instance to database"""
        db.session.add(self)
        db.session.commit()
        return self

    def delete(self):
        """Delete the model instance from database"""
        db.session.delete(self)
        db.session.commit()

    def to_dict(self):
        """Convert model instance to dictionary"""
        result = {}
        # Only process if the model has a __table__ attribute (i.e., inherits from db.Model)
        table = getattr(self, '__table__', None)
        if table is not None:
            for column in table.columns:
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
        # Only process if the model has a query attribute (i.e., inherits from db.Model)
        query = getattr(cls, 'query', None)
        if query is not None:
            return query.all()
        return []

    def refresh(self):
        """Refresh model instance from database"""
        db.session.refresh(self)
        return self


class TimestampMixin:
    """
    Mixin for models that need timestamp tracking.

    Adds created_at and updated_at fields with automatic management.
    Use this only when you actually need timestamp tracking.
    """

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
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
        self.deleted_at = datetime.utcnow()

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
                db.session.commit()
                return self
        return None


# Base model classes for different use cases


class BaseModel(db.Model):
    """
    Full-featured base model with timestamps and utility methods.

    Use this for models that need both timestamp tracking and utility methods.
    Good for: Tournament, Match, etc. (business entities that need audit trail)
    """

    __abstract__ = True

    # Include both timestamp and utility functionality
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def save(self):
        """Save the model instance to database"""
        db.session.add(self)
        db.session.commit()
        return self

    def delete(self):
        """Delete the model instance from database"""
        db.session.delete(self)
        db.session.commit()

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
        return cls.query.all()


class SimpleModel(UtilityMixin, db.Model):
    """
    Simple base model with only utility methods, no timestamps.

    Use this for models that need utility methods but not timestamp tracking.
    Good for: User, simple lookup tables, etc.
    """

    __abstract__ = True


class TimestampedModel(TimestampMixin, UtilityMixin, db.Model):
    """
    Alternative to BaseModel with same functionality but different name.

    Use this when you want to be explicit about timestamp inclusion.
    """

    __abstract__ = True


# Utility functions for common database operations


def get_or_create(model_class, **kwargs):
    """
    Get existing instance or create new one if it doesn't exist.

    Args:
        model_class: The model class to query
        **kwargs: Field values to search for and create with

    Returns:
        tuple: (instance, created) where created is boolean
    """
    instance = model_class.query.filter_by(**kwargs).first()
    if instance:
        return instance, False
    else:
        instance = model_class(**kwargs)
        db.session.add(instance)
        db.session.commit()
        return instance, True


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
    db.session.commit()
    return instances


def safe_commit():
    """
    Safely commit database changes with error handling.

    Returns:
        bool: True if commit successful, False otherwise
    """
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Database commit failed: {str(e)}")
        return False


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
