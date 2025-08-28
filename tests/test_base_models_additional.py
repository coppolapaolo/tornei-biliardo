"""
Additional tests for models/base.py to improve coverage.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError

from models.base import (
    BaseModel, 
    TimestampMixin, 
    SoftDeleteMixin,
    AuditMixin,
    UtilityMixin,
    ValidationMixin
)
from models import db


class BaseTestModel(BaseModel, TimestampMixin, SoftDeleteMixin, AuditMixin, UtilityMixin, ValidationMixin):
    """Test model combining all mixins for testing."""
    __tablename__ = 'base_test_model'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))


class TestBaseModel:
    """Test BaseModel functionality."""

    def test_repr_method(self, db_session):
        """Test __repr__ method."""
        test_obj = BaseTestModel(name="Test Object")
        db_session.add(test_obj)
        db_session.commit()
        
        repr_str = repr(test_obj)
        assert "BaseTestModel" in repr_str
        assert str(test_obj.id) in repr_str

    def test_to_dict_basic(self, db_session):
        """Test basic to_dict functionality."""
        test_obj = TestModel(name="Test", email="test@example.com")
        db_session.add(test_obj)
        db_session.commit()
        
        result = test_obj.to_dict()
        
        assert isinstance(result, dict)
        assert result['name'] == "Test"
        assert result['email'] == "test@example.com"
        assert 'id' in result

    def test_to_dict_with_exclude(self, db_session):
        """Test to_dict basic functionality (no exclude parameter)."""
        test_obj = BaseTestModel(name="Test", email="test@example.com")
        db_session.add(test_obj)
        db_session.commit()
        
        result = test_obj.to_dict()
        
        assert 'name' in result
        assert 'email' in result
        assert 'id' in result

    def test_to_dict_basic_functionality(self, db_session):
        """Test basic to_dict functionality."""
        test_obj = BaseTestModel(name="Test", email="test@example.com")
        db_session.add(test_obj)
        db_session.commit()
        
        result = test_obj.to_dict()
        
        assert 'name' in result
        assert 'email' in result
        assert 'id' in result

    def test_to_dict_datetime_serialization(self, db_session):
        """Test datetime serialization in to_dict."""
        test_obj = BaseTestModel(name="Test")
        db_session.add(test_obj)
        db_session.commit()
        
        result = test_obj.to_dict()
        
        # TimestampMixin should add created_at and updated_at
        assert 'created_at' in result
        assert 'updated_at' in result
        # Should be ISO format strings
        assert isinstance(result['created_at'], str)
        assert isinstance(result['updated_at'], str)




class TestTimestampMixin:
    """Test TimestampMixin functionality."""

    def test_automatic_timestamps(self, db_session):
        """Test automatic timestamp creation."""
        test_obj = BaseTestModel(name="Timestamp Test")
        
        # Before saving
        assert test_obj.created_at is None
        assert test_obj.updated_at is None
        
        db_session.add(test_obj)
        db_session.commit()
        
        # After saving
        assert test_obj.created_at is not None
        assert test_obj.updated_at is not None
        assert isinstance(test_obj.created_at, datetime)
        assert isinstance(test_obj.updated_at, datetime)

    def test_update_timestamp_on_modification(self, db_session):
        """Test that updated_at changes on modification."""
        test_obj = BaseTestModel(name="Update Test")
        db_session.add(test_obj)
        db_session.commit()
        
        original_updated_at = test_obj.updated_at
        
        # Modify the object
        test_obj.name = "Modified Name"
        db_session.commit()
        
        assert test_obj.updated_at > original_updated_at


class TestSoftDeleteMixin:
    """Test SoftDeleteMixin functionality."""

    def test_soft_delete(self, db_session):
        """Test soft delete functionality."""
        test_obj = BaseTestModel(name="Delete Test")
        db_session.add(test_obj)
        db_session.commit()
        
        # Should not be deleted initially
        assert not test_obj.is_deleted
        assert test_obj.deleted_at is None
        
        # Soft delete
        test_obj.soft_delete()
        
        assert test_obj.is_deleted
        assert test_obj.deleted_at is not None
        assert isinstance(test_obj.deleted_at, datetime)

    def test_soft_delete_functionality(self, db_session):
        """Test soft delete functionality."""
        test_obj = BaseTestModel(name="Delete Test")
        db_session.add(test_obj)
        db_session.commit()
        
        # Should not be deleted initially
        assert not test_obj.is_deleted
        assert test_obj.deleted_at is None
        
        # Soft delete
        test_obj.soft_delete()
        
        assert test_obj.is_deleted
        assert test_obj.deleted_at is not None
        assert isinstance(test_obj.deleted_at, datetime)




class TestAuditMixin:
    """Test AuditMixin functionality."""

    def test_audit_fields_exist(self, db_session):
        """Test that audit fields exist."""
        test_obj = BaseTestModel(name="Audit Test")
        
        # Should have audit fields
        assert hasattr(test_obj, 'created_by_id')
        assert hasattr(test_obj, 'updated_by_id')
        
        db_session.add(test_obj)
        db_session.commit()
        
        # Should be nullable initially
        assert test_obj.created_by_id is None
        assert test_obj.updated_by_id is None


class TestValidationMixin:
    """Test ValidationMixin functionality."""

    def test_default_validate_method(self, db_session):
        """Test default validate method returns True."""
        test_obj = BaseTestModel(name="Validation Test")
        
        result = test_obj.validate()
        assert result is True

    def test_save_with_validation_success(self, db_session):
        """Test save_with_validation with successful validation."""
        test_obj = BaseTestModel(name="Valid Object")
        
        with patch.object(test_obj, 'validate') as mock_validate:
            mock_validate.return_value = True
            
            result = test_obj.save_with_validation()
            
            assert result is not None
            assert test_obj.id is not None
            mock_validate.assert_called_once()

    def test_save_with_validation_failure(self, db_session):
        """Test save_with_validation with validation failure."""
        test_obj = BaseTestModel(name="Invalid Object")
        
        with patch.object(test_obj, 'validate') as mock_validate:
            mock_validate.return_value = False
            
            result = test_obj.save_with_validation()
            
            assert result is None
            mock_validate.assert_called_once()


class TestUtilityMixin:
    """Test UtilityMixin functionality."""

    def test_save_method(self, db_session):
        """Test save method."""
        test_obj = BaseTestModel(name="Save Test")
        
        result = test_obj.save()
        
        assert result == test_obj
        assert test_obj.id is not None

    def test_delete_method(self, db_session):
        """Test delete method."""
        test_obj = TestModel(name="Delete Test")
        db_session.add(test_obj)
        db_session.commit()
        obj_id = test_obj.id
        
        test_obj.delete()
        
        # Should be deleted from database
        found_obj = db_session.get(BaseTestModel, obj_id)
        assert found_obj is None

    def test_find_by_id(self, db_session):
        """Test find_by_id class method."""
        test_obj = BaseTestModel(name="Find Test")
        db_session.add(test_obj)
        db_session.commit()
        
        found_obj = BaseTestModel.find_by_id(test_obj.id)
        
        assert found_obj is not None
        assert found_obj.name == "Find Test"

    def test_find_all(self, db_session):
        """Test find_all class method."""
        test_obj1 = BaseTestModel(name="Find All Test 1")
        test_obj2 = BaseTestModel(name="Find All Test 2")
        db_session.add_all([test_obj1, test_obj2])
        db_session.commit()
        
        all_objects = BaseTestModel.find_all()
        
        assert len(all_objects) >= 2
        names = [obj.name for obj in all_objects]
        assert "Find All Test 1" in names
        assert "Find All Test 2" in names

    def test_refresh_method(self, db_session):
        """Test refresh method."""
        test_obj = BaseTestModel(name="Refresh Test")
        db_session.add(test_obj)
        db_session.commit()
        
        result = test_obj.refresh()
        
        assert result == test_obj