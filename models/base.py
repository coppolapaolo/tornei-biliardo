"""
Base models and mixins for the tournament billiards application.

This module provides base classes and common functionality for all models
in the application, following the Domain-Driven Design pattern.

Author: Refactoring Phase 1
Created: 2025-01-31
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Initialize SQLAlchemy instance
db = SQLAlchemy()


class BaseModel(db.Model):
    """
    Base model class that provides common functionality for all models.
    
    This abstract base class includes:
    - Common timestamp fields (created_at, updated_at)
    - Common query methods
    - Consistent table naming conventions
    
    All domain models should inherit from this class.
    """
    __abstract__ = True
    
    # Common timestamp fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
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
        return cls.query.get(id)
    
    @classmethod
    def find_all(cls):
        """Find all instances of the model"""
        return cls.query.all()


class TimestampMixin:
    """
    Mixin class for models that need timestamp tracking.
    
    Provides created_at and updated_at fields with automatic management.
    Use this when you don't want to inherit from BaseModel but still need timestamps.
    """
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SoftDeleteMixin:
    """
    Mixin class for models that need soft deletion capability.
    
    Soft deletion marks records as deleted without actually removing them
    from the database, useful for audit trails and data recovery.
    """
    deleted_at = db.Column(db.DateTime, nullable=True)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    
    def soft_delete(self):
        """Mark the record as soft deleted"""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        db.session.commit()
    
    def restore(self):
        """Restore a soft deleted record"""
        self.is_deleted = False
        self.deleted_at = None
        db.session.commit()
    
    @classmethod
    def active_only(cls):
        """Query filter to get only non-deleted records"""
        return cls.query.filter(cls.is_deleted == False)
    
    @classmethod
    def deleted_only(cls):
        """Query filter to get only soft-deleted records"""
        return cls.query.filter(cls.is_deleted == True)


class AuditMixin:
    """
    Mixin class for models that need audit trail functionality.
    
    Tracks who created and last modified each record.
    """
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # These relationships will be properly configured when User model is in place
    # created_by = db.relationship('User', foreign_keys=[created_by_id])
    # updated_by = db.relationship('User', foreign_keys=[updated_by_id])
    
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
    Mixin class that provides common validation functionality.
    
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
            return self.save()
        return None


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
    """
    Initialize database with Flask app.
    
    Args:
        app: Flask application instance
    """
    db.init_app(app)
    
    # Create tables if they don't exist
    with app.app_context():
        db.create_all()


def reset_db():
    """
    Reset database by dropping and recreating all tables.
    
    WARNING: This will delete all data!
    """
    db.drop_all()
    db.create_all()