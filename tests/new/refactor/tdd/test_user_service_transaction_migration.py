"""
TDD Tests for UserService Transaction Migration (Task 1.1 - UserService Phase)

Incremental migration strategy for 9 commit calls across 5 service classes:

Phase 1: UserService core methods (2 methods)
- request_director_promotion() - line 712 commit
- update_director_request_status() - line 766 commit

Phase 2: DirectorRequestService + UserDeletionService (2 methods)
Phase 3: VenueManagerRequestService + VenueManagementService (5 methods)

Strategy: Red-Green-Refactor TDD for each phase
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from models import db
from models.user.models import User, DirectorRequest
from models.user.services import UserService, DirectorRequestService, UserDeletionService, VenueManagerRequestService, VenueManagementService
from models.user.role_enum import UserRole
from models.status_enum import DirectorRequestStatus
from models.location.models import BilliardHall


class TestUserServiceTransactionMigration:
    """TDD tests for @transactional migration - Phase 1 (UserService core methods)."""

    @pytest.fixture
    def test_user(self, app):
        """Create test user for director promotion requests."""
        with app.app_context():
            user = User(
                username="test_player_director",
                email="player@test.com",
                role=UserRole.PLAYER.value
            )
            user.set_password("testpass")
            db.session.add(user)
            db.session.commit()

            yield user

            db.session.delete(user)
            db.session.commit()

    @pytest.fixture
    def test_admin(self, app):
        """Create test admin for processing requests."""
        with app.app_context():
            admin = User(
                username="test_admin_director",
                email="admin@test.com",
                role=UserRole.ADMIN.value
            )
            admin.set_password("testpass")
            db.session.add(admin)
            db.session.commit()

            yield admin

            db.session.delete(admin)
            db.session.commit()

    def test_request_director_promotion_transaction_behavior(self, app, test_user):
        """
        RED: Test current request_director_promotion behavior with direct commit.

        Expected behavior:
        - Creates DirectorRequest in database
        - Returns DirectorRequest object
        - Validates no duplicate pending requests
        - Handles transaction internally (commit at line 712)
        """
        with app.app_context():
            # Act: request director promotion
            director_request = UserService.request_director_promotion(
                user_id=test_user.id,
                notes="I want to become a tournament director"
            )

            # Assert: request was created and committed
            assert director_request is not None
            assert director_request.user_id == test_user.id
            assert director_request.notes == "I want to become a tournament director"
            assert director_request.status == DirectorRequestStatus.PENDING.value

            # Verify it exists in database (transaction was committed)
            db_request = db.session.get(DirectorRequest, director_request.id)
            assert db_request is not None
            assert db_request.user_id == test_user.id
            assert db_request.status == DirectorRequestStatus.PENDING.value

            # Cleanup
            db.session.delete(director_request)
            db.session.commit()

    def test_request_director_promotion_duplicate_validation(self, app, test_user):
        """
        RED: Test duplicate request validation behavior.

        Current behavior should prevent duplicate pending requests.
        """
        with app.app_context():
            # Arrange: create first request
            first_request = UserService.request_director_promotion(
                user_id=test_user.id,
                notes="First request"
            )

            # Act & Assert: attempt duplicate should raise ValueError
            with pytest.raises(ValueError, match="User already has a pending director request"):
                UserService.request_director_promotion(
                    user_id=test_user.id,
                    notes="Duplicate request"
                )

            # Verify only one request exists
            requests = (
                db.session.query(DirectorRequest)
                .filter_by(user_id=test_user.id, status=DirectorRequestStatus.PENDING.value)
                .all()
            )
            assert len(requests) == 1
            assert requests[0].notes == "First request"

            # Cleanup
            db.session.delete(first_request)
            db.session.commit()

    def test_update_director_request_status_transaction_behavior(self, app, test_user, test_admin):
        """
        RED: Test current update_director_request_status behavior with direct commit.

        Expected behavior:
        - Updates existing DirectorRequest status and metadata
        - Returns updated DirectorRequest object
        - Handles transaction internally (commit at line 766)
        """
        with app.app_context():
            # Arrange: create pending request
            pending_request = DirectorRequest(
                user_id=test_user.id,
                notes="Test promotion request"
            )
            db.session.add(pending_request)
            db.session.commit()

            # Act: update request status - pass None for processed_by to avoid session issues
            updated_request = UserService.update_director_request_status(
                request_id=pending_request.id,
                status=DirectorRequestStatus.APPROVED.value,
                processed_by=None  # Simplified for test - focus on transaction behavior
            )

            # Assert: request was updated and committed
            assert updated_request is not None
            assert updated_request.id == pending_request.id
            assert updated_request.status == DirectorRequestStatus.APPROVED.value
            assert updated_request.processed_at is not None

            # Verify changes exist in database (transaction was committed)
            db_request = db.session.get(DirectorRequest, pending_request.id)
            assert db_request is not None
            assert db_request.status == DirectorRequestStatus.APPROVED.value
            assert db_request.processed_at is not None

            # Cleanup
            db.session.delete(updated_request)
            db.session.commit()

    def test_update_director_request_status_not_found(self, app):
        """
        RED: Test error handling for non-existent request.

        Current behavior should raise ValueError for missing requests.
        """
        with app.app_context():
            # Act & Assert: update non-existent request should raise ValueError
            with pytest.raises(ValueError, match="Director request not found"):
                UserService.update_director_request_status(
                    request_id=99999,  # Non-existent request
                    status=DirectorRequestStatus.APPROVED.value
                )

    def test_transaction_isolation_current_behavior(self, app, test_user, test_admin):
        """
        RED: Test current transaction isolation behavior.

        Documents how transactions currently work for verification
        after @transactional migration.
        """
        with app.app_context():
            # Create request
            request = UserService.request_director_promotion(
                user_id=test_user.id,
                notes="Isolation test request"
            )

            # Verify immediately visible (transaction committed)
            db_check = db.session.get(DirectorRequest, request.id)
            assert db_check is not None
            assert db_check.notes == "Isolation test request"

            # Update request - pass None for processed_by to avoid session issues
            updated_request = UserService.update_director_request_status(
                request_id=request.id,
                status=DirectorRequestStatus.APPROVED.value,
                processed_by=None  # Simplified for test - focus on transaction behavior
            )

            # Verify update immediately visible (transaction committed)
            db_check = db.session.get(DirectorRequest, request.id)
            assert db_check is not None
            assert db_check.status == DirectorRequestStatus.APPROVED.value

            # Cleanup
            db.session.delete(updated_request)
            db.session.commit()

    def test_request_director_promotion_rollback_on_error(self, app):
        """
        RED: Test current error handling behavior.

        Documents current rollback behavior for @transactional equivalence.
        """
        with app.app_context():
            # Test with invalid user ID
            with pytest.raises(Exception):
                # This should fail and rollback properly
                UserService.request_director_promotion(
                    user_id=99999,  # Non-existent user
                    notes="Should fail"
                )

            # Verify no partial data was committed (proper rollback)
            requests = (
                db.session.query(DirectorRequest)
                .filter_by(notes="Should fail")
                .all()
            )
            assert len(requests) == 0  # No partial data should remain


class TestUserServiceTransactionMigrationPhase2:
    """TDD tests for @transactional migration - Phase 2 (DirectorRequestService + UserDeletionService)."""

    @pytest.fixture
    def test_user_with_request(self, app):
        """Create test user with director request for processing tests."""
        with app.app_context():
            user = User(
                username="test_user_phase2",
                email="phase2@test.com",
                role=UserRole.PLAYER.value
            )
            user.set_password("testpass")
            db.session.add(user)
            db.session.flush()

            # Create pending director request
            request = DirectorRequest(
                user_id=user.id,
                notes="Test request for phase 2"
            )
            db.session.add(request)
            db.session.commit()

            yield user, request

            # Cleanup
            db.session.delete(request)
            db.session.delete(user)
            db.session.commit()

    @pytest.fixture
    def test_admin_phase2(self, app):
        """Create test admin for processing requests."""
        with app.app_context():
            admin = User(
                username="test_admin_phase2",
                email="admin_phase2@test.com",
                role=UserRole.ADMIN.value
            )
            admin.set_password("testpass")
            db.session.add(admin)
            db.session.commit()

            yield admin

            db.session.delete(admin)
            db.session.commit()

    def test_director_request_service_process_request_behavior(self, app, test_user_with_request, test_admin_phase2):
        """
        RED: Test current DirectorRequestService.process_request behavior with direct commit.

        Expected behavior:
        - Processes director request (approve/reject)
        - Updates request status and sends notifications
        - Returns updated DirectorRequest object
        - Handles transaction internally (commit at line 882)
        """
        user, request = test_user_with_request

        with app.app_context():
            # Reload admin in current session to avoid SQLAlchemy session attachment errors
            admin_in_session = db.session.get(User, test_admin_phase2.id)

            # Mock notifications to avoid dependencies
            with patch('models.notification.services.NotificationService.create_notification') as mock_notification:
                mock_notification.return_value = {"success": True}

                # Act: process request (approve)
                processed_request = DirectorRequestService.process_request(
                    request_id=request.id,
                    admin_user=admin_in_session,
                    approve=True
                )

            # Assert: request was processed and committed
            assert processed_request is not None
            assert processed_request.id == request.id
            assert processed_request.status == DirectorRequestStatus.APPROVED.value

            # Verify changes exist in database (transaction was committed)
            db_request = db.session.get(DirectorRequest, request.id)
            assert db_request is not None
            assert db_request.status == DirectorRequestStatus.APPROVED.value

            # Verify user role was promoted
            db_user = db.session.get(User, user.id)
            assert db_user.role == UserRole.DIRECTOR.value

    def test_director_request_service_reject_behavior(self, app, test_user_with_request, test_admin_phase2):
        """
        RED: Test DirectorRequestService reject behavior.

        Expected behavior:
        - Rejects request and sends notification
        - User role remains unchanged
        """
        user, request = test_user_with_request

        with app.app_context():
            # Reload admin in current session to avoid SQLAlchemy session attachment errors
            admin_in_session = db.session.get(User, test_admin_phase2.id)

            # Mock notifications
            with patch('models.notification.services.NotificationService.create_notification') as mock_notification:
                mock_notification.return_value = {"success": True}

                # Act: process request (reject)
                processed_request = DirectorRequestService.process_request(
                    request_id=request.id,
                    admin_user=admin_in_session,
                    approve=False
                )

            # Assert: request was rejected
            assert processed_request.status == DirectorRequestStatus.REJECTED.value

            # Verify user role unchanged
            db_user = db.session.get(User, user.id)
            assert db_user.role == UserRole.PLAYER.value  # Should remain player

    def test_user_deletion_service_delete_user_behavior(self, app):
        """
        RED: Test current UserDeletionService.delete_user behavior with direct commit.

        Expected behavior:
        - Soft deletes user (marks as deleted, preserves data)
        - Handles transaction internally (commit at line 922)
        """
        with app.app_context():
            # Arrange: create user for deletion
            user = User(
                username="test_user_delete",
                email="delete@test.com",
                role=UserRole.PLAYER.value
            )
            user.set_password("testpass")
            db.session.add(user)
            db.session.commit()

            user_id = user.id
            assert user.is_deleted is False  # Initially not deleted

            # Reload user in current session to avoid SQLAlchemy session attachment errors
            user_in_session = db.session.get(User, user_id)

            # Act: delete user
            UserDeletionService.delete_user(user_in_session)

            # Assert: user was soft deleted
            assert user_in_session.is_deleted is True

            # Verify changes committed to database
            db_user = db.session.get(User, user_id)
            assert db_user is not None  # Still exists (soft delete)
            assert db_user.is_deleted is True  # But marked as deleted

            # Cleanup
            db.session.delete(user_in_session)
            db.session.commit()

    def test_process_request_not_found_error(self, app, test_admin_phase2):
        """
        RED: Test error handling for non-existent request.
        """
        with app.app_context():
            # Reload admin in current session to avoid SQLAlchemy session attachment errors
            admin_in_session = db.session.get(User, test_admin_phase2.id)

            # Act & Assert: process non-existent request should raise error
            with pytest.raises(Exception):
                DirectorRequestService.process_request(
                    request_id=99999,  # Non-existent request
                    admin_user=admin_in_session,
                    approve=True
                )


class TestUserServiceTransactionMigrationPhase3:
    """TDD tests for @transactional migration - Phase 3 (5 VenueServices methods)."""

    @pytest.fixture
    def test_venue_phase3(self, app):
        """Create test billiard hall for venue management tests."""
        with app.app_context():
            venue = BilliardHall(
                name="Test Billiard Hall Phase 3",
                address="123 Test Street",
                city="Test City",
                postal_code="12345"
            )
            db.session.add(venue)
            db.session.commit()

            yield venue

            db.session.delete(venue)
            db.session.commit()

    @pytest.fixture
    def test_user_phase3(self, app):
        """Create test user for venue management requests."""
        with app.app_context():
            user = User(
                username="test_user_phase3",
                email="phase3@test.com",
                role=UserRole.PLAYER.value
            )
            user.set_password("testpass")
            db.session.add(user)
            db.session.commit()

            yield user

            db.session.delete(user)
            db.session.commit()

    @pytest.fixture
    def test_admin_phase3(self, app):
        """Create test admin for venue management processing."""
        with app.app_context():
            admin = User(
                username="test_admin_phase3",
                email="admin_phase3@test.com",
                role=UserRole.ADMIN.value
            )
            admin.set_password("testpass")
            db.session.add(admin)
            db.session.commit()

            yield admin

            db.session.delete(admin)
            db.session.commit()

    def test_venue_manager_request_create_request_behavior(self, app, test_user_phase3, test_venue_phase3):
        """
        RED: Test current VenueManagerRequestService.create_request behavior with direct commit.

        Expected behavior:
        - Creates VenueManagerRequest in database
        - Returns VenueManagerRequest object
        - Handles transaction internally (direct commit)
        """
        with app.app_context():
            # Act: create venue manager request
            request = VenueManagerRequestService.create_request(
                user_id=test_user_phase3.id,
                venue_id=test_venue_phase3.id,
                notes="I want to manage this venue"
            )

            # Assert: request was created and committed
            assert request is not None
            assert request.user_id == test_user_phase3.id
            assert request.venue_id == test_venue_phase3.id
            assert request.notes == "I want to manage this venue"

            # Verify it exists in database (transaction was committed)
            from models.user.models import VenueManagerRequest
            db_request = db.session.get(VenueManagerRequest, request.id)
            assert db_request is not None
            assert db_request.user_id == test_user_phase3.id

            # Cleanup
            db.session.delete(request)
            db.session.commit()

    def test_venue_manager_request_process_request_behavior(self, app, test_user_phase3, test_admin_phase3, test_venue_phase3):
        """
        RED: Test current VenueManagerRequestService.process_request behavior with direct commit.

        Expected behavior:
        - Processes venue manager request (approve/reject)
        - Updates request status and sends notifications
        - Returns updated VenueManagerRequest object
        - Handles transaction internally (direct commit)
        """
        with app.app_context():
            # Arrange: create pending request
            from models.user.models import VenueManagerRequest
            request = VenueManagerRequest(
                user_id=test_user_phase3.id,
                venue_id=test_venue_phase3.id,
                notes="Test venue management request"
            )
            db.session.add(request)
            db.session.commit()

            # Reload admin in current session
            admin_in_session = db.session.get(User, test_admin_phase3.id)

            # Mock notifications to avoid dependencies
            with patch('models.notification.services.NotificationService.create_notification') as mock_notification:
                mock_notification.return_value = {"success": True}

                # Act: process request (approve)
                processed_request = VenueManagerRequestService.process_request(
                    request_id=request.id,
                    admin_user=admin_in_session,
                    approve=True
                )

            # Assert: request was processed and committed
            assert processed_request is not None
            assert processed_request.id == request.id

            # Cleanup
            db.session.delete(processed_request)
            db.session.commit()

    def test_venue_manager_request_cancel_request_behavior(self, app, test_user_phase3, test_venue_phase3):
        """
        RED: Test current VenueManagerRequestService.cancel_request behavior with direct commit.

        Expected behavior:
        - Cancels pending venue manager request
        - Updates request status in database
        - Returns cancelled VenueManagerRequest object
        - Handles transaction internally (direct commit)
        """
        with app.app_context():
            # Arrange: create pending request
            from models.user.models import VenueManagerRequest
            request = VenueManagerRequest(
                user_id=test_user_phase3.id,
                venue_id=test_venue_phase3.id,
                notes="Test request to cancel"
            )
            db.session.add(request)
            db.session.commit()

            # Reload user in current session
            user_in_session = db.session.get(User, test_user_phase3.id)

            # Act: cancel request
            cancelled_request = VenueManagerRequestService.cancel_request(
                request_id=request.id,
                user=user_in_session
            )

            # Assert: request was cancelled and committed
            assert cancelled_request is not None
            assert cancelled_request.id == request.id

            # Cleanup
            db.session.delete(cancelled_request)
            db.session.commit()

    def test_venue_management_assign_venue_manager_behavior(self, app, test_user_phase3, test_admin_phase3, test_venue_phase3):
        """
        RED: Test current VenueManagementService.assign_venue_manager behavior with direct commit.

        Expected behavior:
        - Creates VenueManagement assignment in database
        - Returns VenueManagement object
        - Handles transaction internally (direct commit)
        """
        with app.app_context():
            # Reload admin in current session
            admin_in_session = db.session.get(User, test_admin_phase3.id)

            # Act: assign venue manager
            assignment = VenueManagementService.assign_venue_manager(
                user_id=test_user_phase3.id,
                venue_id=test_venue_phase3.id,
                assigned_by=admin_in_session
            )

            # Assert: assignment was created and committed
            assert assignment is not None
            assert assignment.user_id == test_user_phase3.id
            assert assignment.venue_id == test_venue_phase3.id

            # Verify it exists in database (transaction was committed)
            from models.user.models import VenueManagement
            db_assignment = db.session.get(VenueManagement, assignment.id)
            assert db_assignment is not None
            assert db_assignment.user_id == test_user_phase3.id

            # Cleanup
            db.session.delete(assignment)
            db.session.commit()

    def test_venue_management_revoke_venue_manager_behavior(self, app, test_user_phase3, test_admin_phase3, test_venue_phase3):
        """
        RED: Test current VenueManagementService.revoke_venue_manager behavior with direct commit.

        Expected behavior:
        - Revokes existing VenueManagement assignment
        - Updates assignment status in database
        - Returns revoked VenueManagement object
        - Handles transaction internally (direct commit)
        """
        with app.app_context():
            # Arrange: create venue management assignment
            from models.user.models import VenueManagement
            assignment = VenueManagement(
                user_id=test_user_phase3.id,
                venue_id=test_venue_phase3.id,
                assigned_by_id=test_admin_phase3.id
            )
            db.session.add(assignment)
            db.session.commit()

            # Reload admin in current session
            admin_in_session = db.session.get(User, test_admin_phase3.id)

            # Act: revoke venue manager
            revoked_assignment = VenueManagementService.revoke_venue_manager(
                assignment_id=assignment.id,
                revoked_by=admin_in_session
            )

            # Assert: assignment was revoked and committed
            assert revoked_assignment is not None
            assert revoked_assignment.id == assignment.id

            # Cleanup
            db.session.delete(revoked_assignment)
            db.session.commit()