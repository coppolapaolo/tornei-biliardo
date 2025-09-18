"""
TDD Tests for InscriptionService Transaction Migration (Task 1.1 - Fase 1.2)

Test migration from direct db.session.commit() calls to @transactional decorator.
This file tests the 4 methods in InscriptionService that need migration:
- inscribe_user() - line 101
- uninscribe_user() - line 184
- admin_uninscribe_user() - line 287
- modify_inscription_dates() - line 377

Strategy: Red-Green-Refactor TDD
1. Document current behavior (characterization tests)
2. Apply @transactional decorator
3. Remove direct commit calls
4. Verify behavior is preserved
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from models import db
from models.competition.models import Gara, Inscription
from models.competition.inscription_service import InscriptionService
from models.user.models import User
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus


class TestInscriptionServiceTransactionMigration:
    """TDD tests for @transactional migration."""

    @pytest.fixture
    def test_gara(self, app):
        """Create test gara for inscription tests."""
        with app.app_context():
            gara = Gara(
                number=1,  # Required field
                name="Test Gara",
                description="Test description",
                date=datetime.now().date() + timedelta(days=7),
                discipline="8ball",  # Required field
                distance=3,  # Required field (number of racks)
                max_participants=10,
                min_participants=4,
                inscription_start=datetime.now() - timedelta(hours=1),
                inscription_end=datetime.now() + timedelta(hours=24),
                status=GaraStatus.INSCRIPTION.value,
            )
            db.session.add(gara)
            db.session.commit()
            yield gara
            db.session.delete(gara)
            db.session.commit()

    @pytest.fixture
    def test_player(self, app):
        """Create test player for inscription tests."""
        with app.app_context():
            user = User(
                username="test_player",
                email="player@test.com",
                role=UserRole.PLAYER.value,
            )
            user.set_password("testpass")
            db.session.add(user)
            db.session.commit()
            yield user
            db.session.delete(user)
            db.session.commit()

    @pytest.fixture
    def test_admin(self, app):
        """Create test admin for admin operations."""
        with app.app_context():
            user = User(
                username="test_admin", email="admin@test.com", role=UserRole.ADMIN.value
            )
            user.set_password("testpass")
            db.session.add(user)
            db.session.commit()
            yield user
            db.session.delete(user)
            db.session.commit()

    def test_inscribe_user_transaction_behavior(self, app, test_gara, test_player):
        """
        RED: Test current inscribe_user behavior with direct commit.

        Expected behavior:
        - Creates inscription in database
        - Returns Inscription object
        - Handles transaction internally (commit at line 101)
        """
        with app.app_context():
            # Act: inscribe user to gara
            inscription = InscriptionService.inscribe_user(
                user_id=test_player.id, gara_id=test_gara.id
            )

            # Assert: inscription was created and committed
            assert inscription is not None
            assert inscription.user_id == test_player.id
            assert inscription.gara_id == test_gara.id
            assert inscription.is_waitlist is False

            # Verify it exists in database (transaction was committed)
            db_inscription = db.session.get(Inscription, inscription.id)
            assert db_inscription is not None
            assert db_inscription.user_id == test_player.id

            # Cleanup
            db.session.delete(inscription)
            db.session.commit()

    def test_uninscribe_user_transaction_behavior(self, app, test_gara, test_player):
        """
        RED: Test current uninscribe_user behavior with direct commit.

        Expected behavior:
        - Removes inscription from database
        - Returns True if found, False if not found
        - Handles transaction internally (commit at line 184)
        """
        with app.app_context():
            # Arrange: create inscription first
            inscription = Inscription(
                user_id=test_player.id, gara_id=test_gara.id, is_waitlist=False
            )
            db.session.add(inscription)
            db.session.commit()

            # Act: uninscribe user
            result = InscriptionService.uninscribe_user(
                user_id=test_player.id, gara_id=test_gara.id
            )

            # Assert: inscription was removed
            assert result is True

            # Verify it was deleted from database (transaction was committed)
            db_inscription = (
                db.session.query(Inscription)
                .filter_by(user_id=test_player.id, gara_id=test_gara.id)
                .first()
            )
            assert db_inscription is None

    def test_admin_uninscribe_user_transaction_behavior(
        self, app, test_gara, test_player, test_admin
    ):
        """
        RED: Test current admin_uninscribe_user behavior with direct commit.

        Expected behavior:
        - Removes inscription and sends notifications
        - Returns True if found, False if not found
        - Handles transaction internally (commit at line 287)
        """
        with app.app_context():
            # Arrange: create inscription first
            inscription = Inscription(
                user_id=test_player.id, gara_id=test_gara.id, is_waitlist=False
            )
            db.session.add(inscription)
            db.session.commit()

            # Act: admin uninscribe user (mock notifications to avoid dependencies)
            with patch(
                "models.notification.services.NotificationService.create_notification"
            ):
                result = InscriptionService.admin_uninscribe_user(
                    user_id=test_player.id,
                    gara_id=test_gara.id,
                    admin_user_id=test_admin.id,
                )

            # Assert: inscription was removed
            assert result is True

            # Verify it was deleted from database (transaction was committed)
            db_inscription = (
                db.session.query(Inscription)
                .filter_by(user_id=test_player.id, gara_id=test_gara.id)
                .first()
            )
            assert db_inscription is None

    def test_modify_inscription_dates_transaction_behavior(self, app, test_gara):
        """
        RED: Test current modify_inscription_dates behavior with direct commit.

        Expected behavior:
        - Updates inscription dates on gara
        - Returns updated Gara object
        - Handles transaction internally (commit at line 377)
        """
        with app.app_context():
            # Arrange: new dates
            new_start = datetime.now() + timedelta(hours=2)
            new_end = datetime.now() + timedelta(hours=48)

            # Act: modify inscription dates
            updated_gara = InscriptionService.modify_inscription_dates(
                gara_id=test_gara.id,
                inscription_start=new_start,
                inscription_end=new_end,
            )

            # Assert: dates were updated
            assert updated_gara is not None
            assert updated_gara.inscription_start.replace(
                microsecond=0
            ) == new_start.replace(microsecond=0)
            assert updated_gara.inscription_end.replace(
                microsecond=0
            ) == new_end.replace(microsecond=0)

            # Verify changes were committed to database
            db_gara = db.session.get(Gara, test_gara.id)
            assert db_gara.inscription_start.replace(
                microsecond=0
            ) == new_start.replace(microsecond=0)
            assert db_gara.inscription_end.replace(microsecond=0) == new_end.replace(
                microsecond=0
            )

    def test_inscribe_user_rollback_on_error(self, app, test_gara, test_player):
        """
        RED: Test current error handling in inscribe_user.

        This test documents current behavior and will be used to verify
        that @transactional provides equivalent error handling.
        """
        with app.app_context():
            # Test duplicate inscription error
            # Create first inscription
            first_inscription = InscriptionService.inscribe_user(
                user_id=test_player.id, gara_id=test_gara.id
            )

            # Try to create duplicate - should return existing
            second_inscription = InscriptionService.inscribe_user(
                user_id=test_player.id, gara_id=test_gara.id
            )

            # Should return same inscription (no duplicate created)
            assert second_inscription.id == first_inscription.id

            # Cleanup
            db.session.delete(first_inscription)
            db.session.commit()

    def test_transaction_isolation_current_behavior(self, app, test_gara, test_player):
        """
        RED: Test current transaction isolation behavior.

        This documents how transactions currently work and will be used
        to verify @transactional provides equivalent isolation.
        """
        with app.app_context():
            # Current behavior: each method call is its own transaction
            # This should be preserved after migration

            inscription = InscriptionService.inscribe_user(
                user_id=test_player.id, gara_id=test_gara.id
            )

            # Verify immediately visible (transaction committed)
            db_check = db.session.get(Inscription, inscription.id)
            assert db_check is not None

            # Remove inscription
            result = InscriptionService.uninscribe_user(
                user_id=test_player.id, gara_id=test_gara.id
            )
            assert result is True

            # Verify immediately gone (transaction committed)
            db_check = (
                db.session.query(Inscription)
                .filter_by(user_id=test_player.id, gara_id=test_gara.id)
                .first()
            )
            assert db_check is None
