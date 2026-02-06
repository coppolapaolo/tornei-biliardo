"""
Test module for models/notification/services.py
"""

# pytest not used in this file
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from models.notification.services import NotificationService
from models.notification.models import (
    NotificationType,
    NotificationPriority,
)
from models.base import utc_now


class TestNotificationService:
    """Test cases for NotificationService class."""

    def test_create_notification_success(self, db_session):
        """Test creating a notification successfully."""
        with patch(
            "models.notification.services.NotificationPreference"
        ) as mock_pref_class:
            # Mock preference to allow notifications
            mock_preference = Mock()
            mock_preference.can_send_notification.return_value = True
            mock_pref_class.get_user_preference.return_value = mock_preference
            mock_pref_class.is_notification_enabled.return_value = True

            with patch("models.notification.services.db") as mock_db:
                mock_notification = Mock()
                mock_notification.id = 1

                with patch(
                    "models.notification.services.Notification"
                ) as mock_notification_class:
                    mock_notification_class.return_value = mock_notification

                    result = NotificationService.create_notification(
                        user_id=1,
                        notification_type=NotificationType.MATCH_PROPOSAL,
                        title="Test Notification",
                        message="This is a test notification",
                    )

                    # Verify the notification was created
                    mock_notification_class.assert_called_once_with(
                        user_id=1,
                        notification_type=NotificationType.MATCH_PROPOSAL,
                        title="Test Notification",
                        message="This is a test notification",
                        priority=NotificationPriority.NORMAL,
                        action_url=None,
                        action_text=None,
                        expires_at=None,
                    )

                    # Verify database operations
                    mock_db.session.add.assert_called_once_with(mock_notification)
                    mock_db.session.commit.assert_called_once()

                    # Verify the result
                    assert result == mock_notification

    def test_create_notification_preference_disabled(self, db_session):
        """Test creating a notification when user preference is disabled."""
        with patch(
            "models.notification.services.NotificationPreference"
        ) as mock_pref_class:
            # Mock preference to disable notifications
            mock_pref_class.is_notification_enabled.return_value = False

            result = NotificationService.create_notification(
                user_id=1,
                notification_type=NotificationType.MATCH_PROPOSAL,
                title="Test Notification",
                message="This is a test notification",
            )

            # Should return None when notifications are disabled
            assert result is None

    def test_create_notification_cannot_send(self, db_session):
        """Test creating a notification when user preference doesn't allow sending."""
        with patch(
            "models.notification.services.NotificationPreference"
        ) as mock_pref_class:
            # Mock preference that doesn't allow sending
            mock_preference = Mock()
            mock_preference.can_send_notification.return_value = False
            mock_pref_class.get_user_preference.return_value = mock_preference
            mock_pref_class.is_notification_enabled.return_value = True

            result = NotificationService.create_notification(
                user_id=1,
                notification_type=NotificationType.MATCH_PROPOSAL,
                title="Test Notification",
                message="This is a test notification",
            )

            # Should return None when notifications can't be sent
            assert result is None

    def test_create_notification_with_related_entities(self, db_session):
        """Test creating a notification with related entities."""
        with patch(
            "models.notification.services.NotificationPreference"
        ) as mock_pref_class:
            # Mock preference to allow notifications
            mock_preference = Mock()
            mock_preference.can_send_notification.return_value = True
            mock_pref_class.get_user_preference.return_value = mock_preference
            mock_pref_class.is_notification_enabled.return_value = True

            with patch("models.notification.services.db") as mock_db:
                mock_notification = Mock()
                mock_notification.id = 1

                with patch(
                    "models.notification.services.Notification"
                ) as mock_notification_class:
                    mock_notification_class.return_value = mock_notification

                    related_entities = {"match_id": 123, "proposer_id": 456}
                    result = NotificationService.create_notification(
                        user_id=1,
                        notification_type=NotificationType.MATCH_PROPOSAL,
                        title="Test Notification",
                        message="This is a test notification",
                        related_entities=related_entities,
                    )

                    # Verify the notification was created with related entities
                    mock_notification_class.assert_called_once_with(
                        user_id=1,
                        notification_type=NotificationType.MATCH_PROPOSAL,
                        title="Test Notification",
                        message="This is a test notification",
                        priority=NotificationPriority.NORMAL,
                        action_url=None,
                        action_text=None,
                        expires_at=None,
                    )

                    # Verify related entities were set
                    mock_notification.set_related_entities.assert_called_once_with(
                        related_entities
                    )

                    # Verify database operations
                    mock_db.session.add.assert_called_once_with(mock_notification)
                    mock_db.session.commit.assert_called_once()

                    # Verify the result
                    assert result == mock_notification

    def test_create_from_template_success(self, db_session):
        """Test creating a notification from template successfully."""
        # Mock template
        mock_template = Mock()
        mock_template.render_notification.return_value = {
            "title": "Rendered Title",
            "message": "Rendered Message",
            "action_url": "/test",
            "action_text": "Test Action",
        }
        mock_template.default_priority = NotificationPriority.NORMAL
        mock_template.get_expiry_datetime.return_value = utc_now() + timedelta(
            hours=24
        )

        with patch(
            "models.notification.services.NotificationTemplate"
        ) as mock_template_class:
            mock_template_class.query.filter_by.return_value.first.return_value = (
                mock_template
            )

            with patch(
                "models.notification.services.NotificationService.create_notification"
            ) as mock_create_notification:
                mock_notification = Mock()
                mock_create_notification.return_value = mock_notification

                context = {"variable": "value"}
                result = NotificationService.create_from_template(
                    user_id=1,
                    notification_type=NotificationType.MATCH_PROPOSAL,
                    context=context,
                )

                # Verify template was queried
                mock_template_class.query.filter_by.assert_called_once_with(
                    notification_type=NotificationType.MATCH_PROPOSAL
                )

                # Verify template was rendered
                mock_template.render_notification.assert_called_once_with(context)

                # Verify notification was created
                mock_create_notification.assert_called_once_with(
                    user_id=1,
                    notification_type=NotificationType.MATCH_PROPOSAL,
                    title="Rendered Title",
                    message="Rendered Message",
                    priority=NotificationPriority.NORMAL,
                    related_entities=context,
                    action_url="/test",
                    action_text="Test Action",
                    expires_at=mock_template.get_expiry_datetime.return_value,
                )

                # Verify the result
                assert result == mock_notification

    def test_create_from_template_no_template(self, db_session):
        """Test creating a notification from template when no template exists."""
        with patch(
            "models.notification.services.NotificationTemplate"
        ) as mock_template_class:
            mock_template_class.query.filter_by.return_value.first.return_value = None

            result = NotificationService.create_from_template(
                user_id=1, notification_type=NotificationType.MATCH_PROPOSAL, context={}
            )

            # Should return None when no template exists
            assert result is None

    def test_get_user_notifications(self, db_session):
        """Test getting user notifications."""
        mock_notifications = [Mock(), Mock(), Mock()]

        with patch(
            "models.notification.services.Notification"
        ) as mock_notification_class:
            # Mock the query chain
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_ordered_query = Mock()
            mock_limited_query = Mock()

            # Set up the chain of return values
            mock_notification_class.query.filter_by.return_value = mock_query
            mock_query.filter.return_value = mock_filtered_query
            mock_filtered_query.order_by.return_value = mock_ordered_query
            mock_ordered_query.limit.return_value = mock_limited_query
            mock_limited_query.all.return_value = mock_notifications

            result = NotificationService.get_user_notifications(
                user_id=1, unread_only=True, limit=10
            )

            # Verify the query chain was called correctly
            mock_notification_class.query.filter_by.assert_called_once_with(user_id=1)
            mock_query.filter.assert_called_once()
            mock_filtered_query.order_by.assert_called_once()
            mock_ordered_query.limit.assert_called_once_with(10)
            mock_limited_query.all.assert_called_once()

            # Verify the result
            assert result == mock_notifications

    def test_mark_notification_read_success(self, db_session):
        """Test marking a notification as read successfully."""
        mock_notification = Mock()

        with patch(
            "models.notification.services.Notification"
        ) as mock_notification_class:
            mock_query = Mock()
            mock_query.first.return_value = mock_notification
            mock_notification_class.query.filter_by.return_value = mock_query

            with patch("models.notification.services.db") as mock_db:
                result = NotificationService.mark_notification_read(
                    notification_id=1, user_id=2
                )

                # Verify the notification was queried
                mock_notification_class.query.filter_by.assert_called_once_with(
                    id=1, user_id=2
                )

                # Verify the notification was marked as read
                mock_notification.mark_as_read.assert_called_once()

                # Verify database commit
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result is True

    def test_mark_notification_read_not_found(self, db_session):
        """Test marking a notification as read when notification is not found."""
        with patch(
            "models.notification.services.Notification"
        ) as mock_notification_class:
            mock_query = Mock()
            mock_query.first.return_value = None
            mock_notification_class.query.filter_by.return_value = mock_query

            result = NotificationService.mark_notification_read(
                notification_id=1, user_id=2
            )

            # Should return False when notification is not found
            assert result is False

    def test_dismiss_notification_success(self, db_session):
        """Test dismissing a notification successfully."""
        mock_notification = Mock()

        with patch(
            "models.notification.services.Notification"
        ) as mock_notification_class:
            mock_query = Mock()
            mock_query.first.return_value = mock_notification
            mock_notification_class.query.filter_by.return_value = mock_query

            with patch("models.notification.services.db") as mock_db:
                result = NotificationService.dismiss_notification(
                    notification_id=1, user_id=2
                )

                # Verify the notification was queried
                mock_notification_class.query.filter_by.assert_called_once_with(
                    id=1, user_id=2
                )

                # Verify the notification was dismissed
                mock_notification.dismiss.assert_called_once()

                # Verify database commit
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result is True

    def test_dismiss_notification_not_found(self, db_session):
        """Test dismissing a notification when notification is not found."""
        with patch(
            "models.notification.services.Notification"
        ) as mock_notification_class:
            mock_query = Mock()
            mock_query.first.return_value = None
            mock_notification_class.query.filter_by.return_value = mock_query

            result = NotificationService.dismiss_notification(
                notification_id=1, user_id=2
            )

            # Should return False when notification is not found
            assert result is False

    def test_mark_all_read(self, db_session):
        """Test marking all notifications as read for a user."""
        mock_notifications = [Mock(), Mock(), Mock()]

        with patch(
            "models.notification.services.Notification"
        ) as mock_notification_class:
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_notification_class.query.filter_by.return_value = mock_query
            mock_query.filter.return_value = mock_filtered_query
            mock_filtered_query.all.return_value = mock_notifications

            with patch("models.notification.services.db") as mock_db:
                result = NotificationService.mark_all_read(user_id=1)

                # Verify the notifications were queried
                mock_notification_class.query.filter_by.assert_called_once_with(
                    user_id=1
                )
                mock_query.filter.assert_called_once()
                mock_filtered_query.all.assert_called_once()

                # Verify each notification was marked as read
                for notification in mock_notifications:
                    notification.mark_as_read.assert_called_once()

                # Verify database commit
                mock_db.session.commit.assert_called_once()

                # Verify the result (count of notifications marked as read)
                assert result == 3

    def test_get_unread_count(self, db_session):
        """Test getting unread notification count for a user."""
        with patch(
            "models.notification.services.Notification"
        ) as mock_notification_class:
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_notification_class.query.filter_by.return_value = mock_query
            mock_query.filter.return_value = mock_filtered_query
            mock_filtered_query.count.return_value = 5

            result = NotificationService.get_unread_count(user_id=1)

            # Verify the notifications were queried
            mock_notification_class.query.filter_by.assert_called_once_with(user_id=1)
            mock_query.filter.assert_called_once()
            mock_filtered_query.count.assert_called_once()

            # Verify the result
            assert result == 5

    def test_set_user_preference_new(self, db_session):
        """Test setting a new user preference."""
        with patch(
            "models.notification.services.NotificationPreference"
        ) as mock_pref_class:
            # Mock query to return None (no existing preference)
            mock_query = Mock()
            mock_query.first.return_value = None
            mock_pref_class.get_user_preference.return_value = None
            mock_pref_class.query.filter_by.return_value = mock_query

            with patch("models.notification.services.db") as mock_db:
                mock_preference = Mock()
                mock_pref_class.return_value = mock_preference

                result = NotificationService.set_user_preference(
                    user_id=1,
                    notification_type=NotificationType.MATCH_PROPOSAL,
                    enabled=True,
                    email_enabled=False,
                    quiet_hours_start="22:00",
                    quiet_hours_end="08:00",
                    max_per_day=10,
                    min_interval_minutes=30,
                )

                # Verify the preference was created
                mock_pref_class.assert_called_once_with(
                    user_id=1,
                    notification_type=NotificationType.MATCH_PROPOSAL,
                    enabled=True,
                    email_enabled=False,
                    max_per_day=10,
                    min_interval_minutes=30,
                )

                # Verify time parsing
                assert mock_preference.quiet_hours_start is not None
                assert mock_preference.quiet_hours_end is not None

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_preference)
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result == mock_preference

    def test_set_user_preference_existing(self, db_session):
        """Test updating an existing user preference."""
        mock_preference = Mock()
        mock_preference.enabled = False
        mock_preference.email_enabled = False
        mock_preference.max_per_day = None
        mock_preference.min_interval_minutes = None

        with patch(
            "models.notification.services.NotificationPreference"
        ) as mock_pref_class:
            # Mock query to return existing preference
            mock_pref_class.get_user_preference.return_value = mock_preference

            with patch("models.notification.services.db") as mock_db:
                result = NotificationService.set_user_preference(
                    user_id=1,
                    notification_type=NotificationType.MATCH_PROPOSAL,
                    enabled=True,
                    email_enabled=True,
                    max_per_day=5,
                    min_interval_minutes=15,
                )

                # Verify the preference was updated
                assert mock_preference.enabled is True
                assert mock_preference.email_enabled is True
                assert mock_preference.max_per_day == 5
                assert mock_preference.min_interval_minutes == 15

                # Verify database operations
                mock_db.session.add.assert_not_called()  # No new record added
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result == mock_preference

    def test_get_user_preferences(self, db_session):
        """Test getting all user preferences."""
        mock_preferences = [
            Mock(notification_type=Mock(value="match_proposal")),
            Mock(notification_type=Mock(value="campionato_registration")),
        ]

        with patch(
            "models.notification.services.NotificationPreference"
        ) as mock_pref_class:
            mock_query = Mock()
            mock_pref_class.query.filter_by.return_value = mock_query
            mock_query.all.return_value = mock_preferences

            result = NotificationService.get_user_preferences(user_id=1)

            # Verify the preferences were queried
            mock_pref_class.query.filter_by.assert_called_once_with(user_id=1)
            mock_query.all.assert_called_once()

            # Verify the result is a dictionary with preference type as key
            assert isinstance(result, dict)
            assert len(result) == 2
            assert "match_proposal" in result
            assert "campionato_registration" in result

    def test_expire_old_notifications(self, db_session):
        """Test expiring old notifications."""
        mock_notifications = [Mock(), Mock()]

        with patch(
            "models.notification.services.Notification"
        ) as mock_notification_class:
            # Mock the model attributes with proper comparison support
            mock_expires_at = Mock()
            mock_expires_at.__le__ = Mock(return_value=True)
            mock_notification_class.expires_at = mock_expires_at

            mock_status = Mock()
            mock_status_in_result = []
            mock_status.in_ = Mock(return_value=mock_status_in_result)
            mock_notification_class.status = mock_status

            # Directly mock the filter chain result
            mock_filter_result = Mock()
            mock_filter_result.all.return_value = mock_notifications
            mock_notification_class.query.filter.return_value = mock_filter_result

            with patch("models.notification.services.db") as mock_db:
                with patch("models.notification.services.datetime") as mock_datetime:
                    mock_utc_now.return_value = datetime(2023, 1, 1, 12, 0, 0)

                    result = NotificationService.expire_old_notifications()

                    # Verify the notifications were queried
                    mock_notification_class.query.filter.assert_called_once()
                    mock_filter_result.all.assert_called_once()

                    # Verify each notification was expired
                    for notification in mock_notifications:
                        notification.expire.assert_called_once()

                    # Verify database commit
                    mock_db.session.commit.assert_called_once()

                    # Verify the result (count of expired notifications)
                    assert result == 2

    def test_cleanup_old_notifications(self, db_session):
        """Test cleaning up old notifications."""
        mock_notifications = [Mock(), Mock(), Mock()]

        with patch(
            "models.notification.services.Notification"
        ) as mock_notification_class:
            # Mock the model attributes with proper comparison support
            mock_created_at = Mock()
            mock_created_at.__le__ = Mock(return_value=True)
            mock_notification_class.created_at = mock_created_at

            mock_status = Mock()
            mock_status_in_result = []
            mock_status.in_ = Mock(return_value=mock_status_in_result)
            mock_notification_class.status = mock_status

            # Directly mock the filter chain result
            mock_filter_result = Mock()
            mock_filter_result.all.return_value = mock_notifications
            mock_notification_class.query.filter.return_value = mock_filter_result

            with patch("models.notification.services.db") as mock_db:
                with patch("models.notification.services.datetime") as mock_datetime:
                    mock_utc_now.return_value = datetime(2023, 1, 1, 12, 0, 0)

                    with patch(
                        "models.notification.services.timedelta"
                    ) as mock_timedelta:
                        mock_timedelta.return_value = timedelta(days=30)

                        result = NotificationService.cleanup_old_notifications(
                            days_old=30
                        )

                    # Verify the notifications were queried
                    mock_notification_class.query.filter.assert_called_once()
                    mock_filter_result.all.assert_called_once()

                    # Verify each notification was deleted
                    for notification in mock_notifications:
                        mock_db.session.delete.assert_any_call(notification)

                    # Verify database commit
                    mock_db.session.commit.assert_called_once()

                    # Verify the result (count of deleted notifications)
                    assert result == 3

    def test_notify_match_proposal(self, db_session):
        """Test notifying about a match proposal."""
        with patch(
            "models.notification.services.NotificationService.create_from_template"
        ) as mock_create_from_template:
            mock_notification = Mock()
            mock_create_from_template.return_value = mock_notification

            match_details = {
                "proposer_name": "John Doe",
                "location": "Test Hall",
                "scheduled_time": "2023-01-01 14:00",
                "proposal_id": 123,
            }

            result = NotificationService.notify_match_proposal(
                proposer_id=1, target_user_id=2, match_details=match_details
            )

            # Verify the notification was created from template
            mock_create_from_template.assert_called_once_with(
                user_id=2,
                notification_type=NotificationType.MATCH_PROPOSAL,
                context=match_details,
            )

            # Verify the result
            assert result == mock_notification

    def test_notify_match_accepted(self, db_session):
        """Test notifying about a match acceptance."""
        with patch(
            "models.notification.services.NotificationService.create_from_template"
        ) as mock_create_from_template:
            mock_notification = Mock()
            mock_create_from_template.return_value = mock_notification

            match_details = {
                "location": "Test Hall",
                "scheduled_time": "2023-01-01 14:00",
                "match_id": 456,
            }

            result = NotificationService.notify_match_accepted(
                proposer_id=1, accepter_name="Jane Smith", match_details=match_details
            )

            # Verify the notification was created from template
            mock_create_from_template.assert_called_once_with(
                user_id=1,
                notification_type=NotificationType.MATCH_ACCEPTED,
                context={
                    "accepter_name": "Jane Smith",
                    "location": "Test Hall",
                    "scheduled_time": "2023-01-01 14:00",
                    "match_id": 456,
                },
            )

            # Verify the result
            assert result == mock_notification

    def test_notify_campionato_registration(self, db_session):
        """Test notifying about campionato registration."""
        with patch(
            "models.notification.services.NotificationService.create_from_template"
        ) as mock_create_from_template:
            mock_notification1 = Mock()
            mock_notification2 = Mock()
            mock_create_from_template.side_effect = [
                mock_notification1,
                mock_notification2,
            ]

            result = NotificationService.notify_campionato_registration(
                user_ids=[1, 2], campionato_name="Test Campionato", campionato_id=123
            )

            # Verify the notifications were created from template
            assert mock_create_from_template.call_count == 2
            mock_create_from_template.assert_any_call(
                user_id=1,
                notification_type=NotificationType.TOURNAMENT_REGISTRATION,
                context={"campionato_name": "Test Campionato", "campionato_id": 123},
            )
            mock_create_from_template.assert_any_call(
                user_id=2,
                notification_type=NotificationType.TOURNAMENT_REGISTRATION,
                context={"campionato_name": "Test Campionato", "campionato_id": 123},
            )

            # Verify the result
            assert result == [mock_notification1, mock_notification2]

    def test_notify_playoff_invitation(self, db_session):
        """Test notifying about playoff invitation."""
        with patch(
            "models.notification.services.NotificationService.create_from_template"
        ) as mock_create_from_template:
            mock_notification = Mock()
            mock_create_from_template.return_value = mock_notification

            deadline = datetime(2023, 1, 1, 12, 0, 0)

            result = NotificationService.notify_playoff_invitation(
                user_id=1,
                playoff_name="Test Playoff",
                campionato_name="Test Campionato",
                deadline=deadline,
            )

            # Verify the notification was created from template
            mock_create_from_template.assert_called_once_with(
                user_id=1,
                notification_type=NotificationType.PLAYOFF_INVITATION,
                context={
                    "playoff_name": "Test Playoff",
                    "campionato_name": "Test Campionato",
                    "deadline": "2023-01-01 12:00",
                },
                expires_override=deadline,
            )

            # Verify the result
            assert result == mock_notification

    def test_create_default_templates(self, db_session):
        """Test creating default notification templates."""
        with patch(
            "models.notification.services.NotificationTemplate"
        ) as mock_template_class:
            # Mock query to return None (no existing templates)
            mock_query = Mock()
            mock_query.first.return_value = None
            mock_template_class.query.filter_by.return_value = mock_query

            with patch("models.notification.services.db") as mock_db:
                result = NotificationService.create_default_templates()

                # Verify templates were created
                assert mock_db.session.add.call_count == 4  # 4 default templates
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert len(result) == 4
