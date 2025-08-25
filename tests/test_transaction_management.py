"""
Unit tests for transaction management and user registration functionality.

Tests the transaction management fix for nested transactions (savepoints) and
ensures user registration works correctly with proper transaction handling.
"""

import pytest
from app import create_app
from models.user.services import UserService
from models.user.models import User
from models import db as _db


class TestTransactionManagement:
    """Test suite for transaction management functionality."""

    def test_user_registration_with_transaction_fix(self, db_session):
        """Test that user registration works correctly with the transaction fix."""
        # Create a user using the service layer
        user = UserService.create_user(
            username="testuser_transaction",
            email="test_transaction@example.com",
            password="securepassword123"
        )
        
        # Verify user was created and committed to database
        assert user.id is not None
        assert user.username == "testuser_transaction"
        assert user.email == "test_transaction@example.com"
        assert user.check_password("securepassword123") is True
        
        # Verify user exists in database
        db_user = db_session.query(User).filter_by(username="testuser_transaction").first()
        assert db_user is not None
        assert db_user.id == user.id

    def test_user_authentication_after_registration(self, db_session):
        """Test that users can authenticate after registration."""
        # Create a user
        user = UserService.create_user(
            username="auth_test_user",
            email="auth_test@example.com",
            password="authpassword123"
        )
        
        # Authenticate with correct credentials
        authenticated_user = UserService.authenticate_user("auth_test_user", "authpassword123")
        assert authenticated_user is not None
        assert authenticated_user.id == user.id
        assert authenticated_user.username == "auth_test_user"

    def test_user_authentication_with_wrong_password(self, db_session):
        """Test that authentication fails with wrong password."""
        # Create a user
        UserService.create_user(
            username="wrong_pass_user",
            email="wrong_pass@example.com",
            password="correctpassword"
        )
        
        # Authenticate with wrong password
        authenticated_user = UserService.authenticate_user("wrong_pass_user", "wrongpassword")
        assert authenticated_user is None

    def test_nested_transaction_handling(self, db_session):
        """Test that nested transactions (savepoints) are properly handled."""
        # This test verifies that our transaction management fix works
        # by ensuring that operations within nested transactions are properly committed
        
        # Create a user (this will use nested transactions in test environment)
        user = UserService.create_user(
            username="nested_transaction_user",
            email="nested@example.com",
            password="password123"
        )
        
        # Verify user was created and committed
        assert user.id is not None
        assert user.username == "nested_transaction_user"
        
        # Verify user exists in database
        db_user = db_session.query(User).filter_by(username="nested_transaction_user").first()
        assert db_user is not None
        assert db_user.id == user.id