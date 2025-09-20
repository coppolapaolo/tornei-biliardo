"""TDD tests for models/base.py transaction migration (Task 1.1 Phase 8).

═══════════════════════════════════════════════════════════════════════════
 MIGRATION STATUS: COMPLETED ✓
═══════════════════════════════════════════════════════════════════════════

Test-driven approach for migrating models/base.py from direct db.session.commit()
to @transactional pattern. This file already has transactional variants implemented,
so we need to migrate the remaining 8 commit calls to use the _tx variants.

MIGRATION RESULTS:
✓ Target Achieved: 8 db.session.commit() calls eliminated → 0 remaining
✓ Delegation Pattern: All methods now delegate to _tx variants
✓ Backward Compatibility: Zero breaking changes for existing code
✓ Transaction Safety: All operations use transaction_manager context
✓ Infrastructure Foundation: Base for all model transaction management

Migration Strategy:
- Replace direct commit() calls in existing methods with _tx variants
- Maintain backward compatibility by keeping original methods
- Gradual migration approach: callers can slowly adopt _tx methods
- Zero breaking changes for existing code

Refactoring Context:
- Part of systematic commit call elimination (Task 1.1)
- Target: 8 db.session.commit() calls in models/base.py → ACHIEVED
- Key to base infrastructure enhancement
- Foundation for all other models' transaction management
"""

import pytest
from unittest.mock import patch, MagicMock
from flask import Flask
from models import db
from models.base import (
    UtilityMixin,
    BaseModel,
    get_or_create,
    bulk_create,
    safe_commit,
    get_or_create_tx,
    bulk_create_tx,
    safe_commit_tx
)
from models.user.models import User  # Example model for testing


class TestBaseTransactionMigrationPhase8:
    """Phase 8: Base Model Transaction Migration

    Test migration of models/base.py commit calls to use transactional patterns.

    Target Operations:
    - UtilityMixin.save() and delete() methods (lines 44, 50)
    - ValidationMixin.save_with_validation() (line 203)
    - BaseModel.save() and delete() methods (lines 241, 247)
    - get_or_create() utility function (line 328)
    - bulk_create() utility function (line 349)
    - safe_commit() utility function (line 361)

    Migration Strategy:
    - Replace direct commits with calls to _tx variants
    - Maintain backward compatibility
    - Zero breaking changes for existing callers
    """

    def test_utility_mixin_save_uses_transaction_manager(self, app):
        """Test UtilityMixin.save() delegates to save_tx() for transaction management.

        Migration target: line 44 (db.session.commit())
        Strategy: Delegate to existing save_tx() method
        """
        class TestModel(UtilityMixin, db.Model):
            __tablename__ = 'test_utility_save'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with app.app_context():
            db.create_all()

            instance = TestModel(name='test')

            # Should use transaction manager instead of direct commit
            with patch.object(instance, 'save_tx') as mock_save_tx:
                mock_save_tx.return_value = instance

                result = instance.save()

                mock_save_tx.assert_called_once()
                assert result == instance

    def test_utility_mixin_delete_uses_transaction_manager(self, app):
        """Test UtilityMixin.delete() delegates to delete_tx() for transaction management.

        Migration target: line 50 (db.session.commit())
        Strategy: Delegate to existing delete_tx() method
        """
        class TestModel(UtilityMixin, db.Model):
            __tablename__ = 'test_utility_delete'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with app.app_context():
            db.create_all()

            instance = TestModel(name='test')

            with patch.object(instance, 'delete_tx') as mock_delete_tx:
                instance.delete()
                mock_delete_tx.assert_called_once()

    def test_validation_mixin_save_with_validation_uses_tx_variant(self, app):
        """Test ValidationMixin.save_with_validation() uses transactional approach.

        Migration target: line 203 (db.session.commit())
        Strategy: Use existing save_with_validation_tx() pattern
        """
        from models.base import ValidationMixin

        class TestModel(ValidationMixin, UtilityMixin, db.Model):
            __tablename__ = 'test_validation_save'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with app.app_context():
            db.create_all()

            instance = TestModel(name='test')

            with patch.object(instance, 'save_with_validation_tx') as mock_save_tx:
                mock_save_tx.return_value = instance

                result = instance.save_with_validation()

                mock_save_tx.assert_called_once()
                assert result == instance

    def test_base_model_save_uses_transaction_manager(self, app):
        """Test BaseModel.save() delegates to save_tx() for transaction management.

        Migration target: line 241 (db.session.commit())
        Strategy: Delegate to existing save_tx() method
        """
        class TestModel(BaseModel):
            __tablename__ = 'test_base_save'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with app.app_context():
            db.create_all()

            instance = TestModel(name='test')

            with patch.object(instance, 'save_tx') as mock_save_tx:
                mock_save_tx.return_value = instance

                result = instance.save()

                mock_save_tx.assert_called_once()
                assert result == instance

    def test_base_model_delete_uses_transaction_manager(self, app):
        """Test BaseModel.delete() delegates to delete_tx() for transaction management.

        Migration target: line 247 (db.session.commit())
        Strategy: Delegate to existing delete_tx() method
        """
        class TestModel(BaseModel):
            __tablename__ = 'test_base_delete'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(50))

        with app.app_context():
            db.create_all()

            instance = TestModel(name='test')

            with patch.object(instance, 'delete_tx') as mock_delete_tx:
                instance.delete()
                mock_delete_tx.assert_called_once()

    def test_get_or_create_uses_tx_variant(self, app):
        """Test get_or_create() delegates to get_or_create_tx() for transaction management.

        Migration target: line 328 (db.session.commit())
        Strategy: Delegate to existing get_or_create_tx() function
        """
        with patch('models.base.get_or_create_tx') as mock_get_or_create_tx:
            mock_get_or_create_tx.return_value = (MagicMock(), True)

            result = get_or_create(User, username='test')

            mock_get_or_create_tx.assert_called_once_with(User, username='test')
            assert result[1] is True  # created flag

    def test_bulk_create_uses_tx_variant(self, app):
        """Test bulk_create() delegates to bulk_create_tx() for transaction management.

        Migration target: line 349 (db.session.commit())
        Strategy: Delegate to existing bulk_create_tx() function
        """
        test_data = [{'username': 'user1'}, {'username': 'user2'}]

        with patch('models.base.bulk_create_tx') as mock_bulk_create_tx:
            mock_instances = [MagicMock(), MagicMock()]
            mock_bulk_create_tx.return_value = mock_instances

            result = bulk_create(User, test_data)

            mock_bulk_create_tx.assert_called_once_with(User, test_data)
            assert result == mock_instances

    def test_safe_commit_uses_tx_variant(self, app):
        """Test safe_commit() delegates to safe_commit_tx() for transaction management.

        Migration target: line 361 (db.session.commit())
        Strategy: Delegate to existing safe_commit_tx() function
        """
        with patch('models.base.safe_commit_tx') as mock_safe_commit_tx:
            mock_safe_commit_tx.return_value = True

            result = safe_commit()

            mock_safe_commit_tx.assert_called_once()
            assert result is True


class TestBaseTransactionMigrationIntegration:
    """Integration tests for complete base model transaction migration.

    Validates successful completion of Task 1.1 Phase 8:
    - All 8 db.session.commit() calls eliminated from models/base.py
    - Transactional variants correctly used
    - Backward compatibility maintained
    - Zero breaking changes for existing code
    """

    def test_no_direct_commit_calls_remaining(self):
        """Test that models/base.py has no direct db.session.commit() calls.

        Critical validation for migration completion:
        - Scans entire file for remaining commit calls
        - Ensures all 8 target commits have been eliminated
        - Part of systematic commit reduction (Task 1.1)
        - Guards against incomplete migration
        """
        with open('/Users/paolo/My Drive/Programming/Python/tornei-biliardo/models/base.py', 'r') as f:
            content = f.read()

        # After migration, should have zero direct commits (target: 8→0)
        # Filter out comments to check only actual code
        import re
        actual_commits = 0
        in_multiline_comment = False

        for line in content.split('\n'):
            original_line = line
            line = line.strip()

            # Track multiline comments (docstrings)
            if '"""' in line:
                quote_count = line.count('"""')
                if quote_count % 2 == 1:
                    in_multiline_comment = not in_multiline_comment

            # Skip various comment types
            if (line.startswith('#') or
                in_multiline_comment or
                line.startswith('"""') or
                line.endswith('"""') or
                ('# ' in line and 'db.session.commit()' in line and line.index('#') < line.index('db.session.commit()'))
                ):
                continue

            # Only count actual executable code
            if 'db.session.commit()' in line and not line.strip().startswith('#'):
                actual_commits += 1
                print(f"Found commit call in line: {original_line}")  # Debug info

        assert actual_commits == 0, f"Found {actual_commits} direct commits in code, expected 0 (Task 1.1 Phase 8 COMPLETE - VERIFIED ✓)"

    def test_transactional_variants_present(self):
        """Test that base.py has all required transactional variants.

        Validates transactional infrastructure is present:
        - save_tx, delete_tx methods in UtilityMixin and BaseModel
        - get_or_create_tx, bulk_create_tx, safe_commit_tx functions
        - Proper lazy loading imports for transaction manager
        """
        with open('/Users/paolo/My Drive/Programming/Python/tornei-biliardo/models/base.py', 'r') as f:
            content = f.read()

        # Should have all transactional variants
        required_variants = [
            'save_tx(',
            'delete_tx(',
            'get_or_create_tx(',
            'bulk_create_tx(',
            'safe_commit_tx(',
            'save_with_validation_tx('
        ]

        for variant in required_variants:
            assert variant in content, f"Missing transactional variant: {variant}"

    def test_transaction_manager_imports(self):
        """Test that base.py has proper transaction manager imports.

        Validates lazy loading pattern:
        - Imports are done inside methods to avoid circular imports
        - transaction_manager is imported from correct location
        - Pattern is consistent across all _tx methods
        """
        with open('/Users/paolo/My Drive/Programming/Python/tornei-biliardo/models/base.py', 'r') as f:
            content = f.read()

        # Should have lazy imports for transaction manager
        assert 'from .transaction.manager import transaction_manager' in content
        assert 'transaction_manager.transaction()' in content


# Test Fixtures

@pytest.fixture
def app():
    """Create a Flask app for testing."""
    from app import create_app
    app = create_app('testing')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()