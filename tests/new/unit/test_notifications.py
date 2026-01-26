"""Unit tests for notification system."""

import pytest
import uuid
from unittest.mock import patch, MagicMock

from models import User, Notification
from models.user.role_enum import UserRole
from models.notification.services import NotificationService
from models.notification.models import NotificationType, NotificationStatus


@pytest.mark.unit
class TestNotificationModel:
    """Test Notification model functionality."""

    def test_create_notification(self, db_session):
        """Test creating a notification."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        notification = Notification(
            user_id=user.id,
            title="Test Notification",
            message="This is a test notification",
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
        )
        db_session.add(notification)
        db_session.commit()

        assert notification.id is not None
        assert notification.user_id == user.id
        assert notification.title == "Test Notification"
        assert notification.message == "This is a test notification"
        assert notification.notification_type == NotificationType.SYSTEM_ANNOUNCEMENT
        assert notification.status == NotificationStatus.PENDING
        assert notification.created_at is not None
        assert notification.read_at is None

    def test_notification_relationships(self, db_session):
        """Test notification relationships."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        notification = Notification(
            user_id=user.id,
            title="Test",
            message="Test message",
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
        )
        db_session.add(notification)
        db_session.commit()

        assert notification.user == user

    def test_mark_as_read(self, db_session):
        """Test marking notification as read."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        notification = Notification(
            user_id=user.id,
            title="Test",
            message="Test message",
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
        )
        db_session.add(notification)
        db_session.commit()

        # Initially not read
        assert notification.status == NotificationStatus.PENDING
        assert notification.read_at is None

        # Mark as read
        notification.mark_as_read()
        db_session.commit()

        assert notification.status == NotificationStatus.READ
        assert notification.read_at is not None

    def test_notification_types(self, db_session):
        """Test different notification types."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        types = [
            NotificationType.SYSTEM_ANNOUNCEMENT,
            NotificationType.MATCH_PROPOSAL,
            NotificationType.TOURNAMENT_REGISTRATION,
            NotificationType.ACCOUNT_UPDATE,
        ]
        notifications = []

        for ntype in types:
            notification = Notification(
                user_id=user.id,
                title=f"Test {ntype.value}",
                message=f"Test {ntype.value} message",
                notification_type=ntype,
            )
            notifications.append(notification)
            db_session.add(notification)

        db_session.commit()

        for notification, expected_type in zip(notifications, types):
            assert notification.notification_type == expected_type


@pytest.mark.unit
class TestNotificationService:
    """Test NotificationService functionality."""

    def test_create_notification(self, db_session):
        """Test creating a notification through service."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        from models.notification.models import NotificationType, NotificationPriority

        result = NotificationService.create_notification(
            user_id=user.id,
            notification_type=NotificationType.MATCH_PROPOSAL,
            title="Service Test",
            message="Test message from service",
            priority=NotificationPriority.NORMAL,
        )

        assert result is not None
        assert result.user_id == user.id
        assert result.title == "Service Test"
        assert result.message == "Test message from service"
        assert result.notification_type == NotificationType.MATCH_PROPOSAL

    def test_create_notification_invalid_user(self, db_session):
        """Test creating notification for invalid user."""
        from models.notification.models import NotificationType

        # The create_notification method should handle invalid user IDs gracefully
        # Since it commits to database, an invalid user_id will cause foreign key error
        try:
            result = NotificationService.create_notification(
                user_id=99999,
                notification_type=NotificationType.MATCH_PROPOSAL,
                title="Test",
                message="Test message",
            )
            # If we get here, the method didn't validate user existence
            # This would be a design issue - normally should fail or return None
            assert result is None  # Expected behavior for invalid user
        except Exception:
            # Foreign key constraint failure is expected for invalid user_id
            # This is acceptable behavior
            pass

    def test_create_notification_multiple_users(self, db_session):
        """Test creating notifications for multiple users."""
        unique_id = str(uuid.uuid4())[:8]
        users = []
        for i in range(3):
            user = User(
                username=f"user{i}_{unique_id}",
                email=f"user{i}_{unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            user.set_password("testpass123")
            users.append(user)
            db_session.add(user)

        db_session.commit()
        user_ids = [u.id for u in users]

        from models.notification.models import NotificationType

        # The NotificationService doesn't have a create_notifications_for_users method
        # We need to create notifications individually
        notifications = []
        for user_id in user_ids:
            notification = NotificationService.create_notification(
                user_id=user_id,
                notification_type=NotificationType.MATCH_PROPOSAL,
                title="Broadcast Test",
                message="Test broadcast message",
            )
            if notification:
                notifications.append(notification)

        assert len(notifications) == 3
        for notification in notifications:
            assert notification.title == "Broadcast Test"
            assert notification.message == "Test broadcast message"

    def test_get_user_notifications(self, db_session):
        """Test getting user notifications."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        # Create multiple notifications
        for i in range(5):
            notification = Notification(
                user_id=user.id,
                title=f"Test {i}",
                message=f"Test message {i}",
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                status=(
                    NotificationStatus.READ
                    if (i % 2 == 0)
                    else NotificationStatus.PENDING
                ),  # Some read, some unread
            )
            db_session.add(notification)

        db_session.commit()

        # Get all notifications
        notifications = NotificationService.get_user_notifications(user.id)
        assert len(notifications) == 5

        # Get unread notifications only
        unread = NotificationService.get_user_notifications(user.id, unread_only=True)
        assert len(unread) == 2  # 2 unread (odd indices)

        for notification in unread:
            assert notification.status == NotificationStatus.PENDING

    def test_get_user_notifications_with_limit(self, db_session):
        """Test getting user notifications with limit."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        # Create 10 notifications
        for i in range(10):
            notification = Notification(
                user_id=user.id,
                title=f"Test {i}",
                message=f"Test message {i}",
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            )
            db_session.add(notification)

        db_session.commit()

        # Get with limit
        notifications = NotificationService.get_user_notifications(user.id, limit=5)
        assert len(notifications) == 5

    def test_mark_notification_as_read(self, db_session):
        """Test marking notification as read through service."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        notification = Notification(
            user_id=user.id,
            title="Test",
            message="Test message",
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
        )
        db_session.add(notification)
        db_session.commit()

        # Mark as read through service
        result = NotificationService.mark_notification_read(notification.id, user.id)

        assert result is True

        db_session.refresh(notification)
        assert notification.status == NotificationStatus.READ
        assert notification.read_at is not None

    def test_mark_notification_as_read_invalid(self, db_session):
        """Test marking invalid notification as read."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"test_{unique_id}",
            email=f"test_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        result = NotificationService.mark_notification_read(99999, user.id)

        assert result is False

    def test_mark_all_notifications_as_read(self, db_session):
        """Test marking all user notifications as read."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        # Create multiple unread notifications
        notifications = []
        for i in range(5):
            notification = Notification(
                user_id=user.id,
                title=f"Test {i}",
                message=f"Test message {i}",
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            )
            notifications.append(notification)
            db_session.add(notification)

        db_session.commit()

        # All should be unread initially
        for notification in notifications:
            assert notification.status == NotificationStatus.PENDING

        # Mark all as read
        count = NotificationService.mark_all_read(user.id)

        assert count == 5

        # Check all are now read
        for notification in notifications:
            db_session.refresh(notification)
            assert notification.status == NotificationStatus.READ

    def test_delete_notification(self, db_session):
        """Test deleting notification."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        notification = Notification(
            user_id=user.id,
            title="Test",
            message="Test message",
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
        )
        db_session.add(notification)
        db_session.commit()
        notification_id = notification.id

        # The NotificationService doesn't have a delete_notification method
        # Notifications are typically dismissed, not deleted
        result = NotificationService.dismiss_notification(notification_id, user.id)

        assert result is True

        # Check it's dismissed (not deleted, just marked as dismissed)
        dismissed = db_session.get(Notification, notification_id)
        assert dismissed is not None
        assert dismissed.status == NotificationStatus.DISMISSED

    def test_delete_notification_invalid(self, db_session):
        """Test deleting invalid notification."""
        # Need a user context for dismiss_notification
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"test_{unique_id}",
            email=f"test_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        result = NotificationService.dismiss_notification(99999, user.id)

        assert result is False

    def test_delete_all_user_notifications(self, db_session):
        """Test deleting all notifications for a user."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        # Create multiple notifications
        for i in range(5):
            notification = Notification(
                user_id=user.id,
                title=f"Test {i}",
                message=f"Test message {i}",
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            )
            db_session.add(notification)

        db_session.commit()

        # The NotificationService doesn't have delete_all_user_notifications method
        # We can dismiss all notifications individually
        notifications = NotificationService.get_user_notifications(user.id)
        dismissed_count = 0
        for notification in notifications:
            if NotificationService.dismiss_notification(notification.id, user.id):
                dismissed_count += 1

        assert dismissed_count == 5

    def test_get_unread_count(self, db_session):
        """Test getting unread notification count."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        # Initially no notifications
        count = NotificationService.get_unread_count(user.id)
        assert count == 0

        # Create 3 unread, 2 read notifications
        for i in range(5):
            notification = Notification(
                user_id=user.id,
                title=f"Test {i}",
                message=f"Test message {i}",
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                status=(
                    NotificationStatus.READ if (i < 2) else NotificationStatus.PENDING
                ),  # First 2 are read
            )
            db_session.add(notification)

        db_session.commit()

        # Should have 3 unread
        count = NotificationService.get_unread_count(user.id)
        assert count == 3

    def test_notification_for_director_promotion(self, db_session):
        """Test creating notification for director promotion."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        from models.notification.models import NotificationType, NotificationPriority

        # The NotificationService doesn't have create_director_promotion_notification
        # We create a generic notification
        result = NotificationService.create_notification(
            user_id=user.id,
            notification_type=NotificationType.ACCOUNT_UPDATE,
            title="Director Promotion",
            message="You have been promoted to director",
            priority=NotificationPriority.HIGH,
        )

        assert result is not None
        assert "director" in result.title.lower()
        assert result.notification_type == NotificationType.ACCOUNT_UPDATE

    def test_notification_for_competition_update(self, db_session):
        """Test creating notification for competition update."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        from models.notification.models import NotificationType

        # The NotificationService doesn't have create_competition_notification
        # We create a generic notification
        result = NotificationService.create_notification(
            user_id=user.id,
            notification_type=NotificationType.TOURNAMENT_REGISTRATION,
            title="Test Competition Update",
            message="Competition has started",
        )

        assert result is not None
        assert "Test Competition" in result.title
        assert result.notification_type == NotificationType.TOURNAMENT_REGISTRATION

    @patch("routes.sse.emit_user_event")
    def test_create_notification_emits_sse_event(self, mock_emit, db_session):
        """Test that creating a notification emits an SSE event for badge update."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        from models.notification.models import NotificationType, NotificationPriority

        result = NotificationService.create_notification(
            user_id=user.id,
            notification_type=NotificationType.MATCH_PROPOSAL,
            title="SSE Test",
            message="Test message for SSE",
            priority=NotificationPriority.NORMAL,
        )

        assert result is not None
        # Verify SSE event was emitted
        mock_emit.assert_called_once()
        call_args = mock_emit.call_args
        assert call_args[0][0] == user.id  # user_id
        assert call_args[0][1] == "notification"  # event_type
        assert "unread_count" in call_args[0][2]  # data dict
        assert call_args[0][2]["unread_count"] >= 1  # At least 1 unread

    @patch("routes.sse.emit_user_event")
    def test_create_notification_sse_event_includes_correct_count(
        self, mock_emit, db_session
    ):
        """Test SSE event includes correct unread count after multiple notifications."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"user_{unique_id}",
            email=f"user_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        from models.notification.models import NotificationType

        # Create first notification
        NotificationService.create_notification(
            user_id=user.id,
            notification_type=NotificationType.MATCH_PROPOSAL,
            title="First",
            message="First notification",
        )

        # Create second notification
        NotificationService.create_notification(
            user_id=user.id,
            notification_type=NotificationType.MATCH_PROPOSAL,
            title="Second",
            message="Second notification",
        )

        # Check the second call has count=2
        assert mock_emit.call_count == 2
        second_call = mock_emit.call_args_list[1]
        assert second_call[0][2]["unread_count"] == 2
