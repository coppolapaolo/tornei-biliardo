"""
Tests for NotificationFactory.

This module tests the NotificationFactory class to ensure proper
standardization of notification creation patterns and error handling.
"""

from unittest.mock import patch, MagicMock
from models.notification.factory import NotificationFactory
from models.notification.models import NotificationType, NotificationPriority
from utils.lingua import componi


class TestNotificationFactory:
    """Test NotificationFactory functionality."""

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_admin_notification_success(self, mock_create):
        """Test successful admin notification creation."""
        mock_notification = MagicMock()
        mock_create.return_value = mock_notification

        admin_ids = [1, 2, 3]
        title = "Test Admin Notification"
        message = "Test message for admins"

        result = NotificationFactory.create_admin_notification(
            admin_user_ids=admin_ids,
            title=title,
            message=message,
            priority=NotificationPriority.HIGH,
        )

        assert len(result) == 3
        assert all(n == mock_notification for n in result)
        assert mock_create.call_count == 3

        # Verify correct parameters
        call_kwargs = mock_create.call_args_list[0][1]
        assert call_kwargs["user_id"] == 1
        assert call_kwargs["notification_type"] == NotificationType.SYSTEM_ANNOUNCEMENT
        assert call_kwargs["title"] == title
        assert call_kwargs["message"] == message
        assert call_kwargs["priority"] == NotificationPriority.HIGH

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_admin_notification_with_error(self, mock_create):
        """Test admin notification creation with some failures."""
        mock_notification = MagicMock()
        mock_create.side_effect = [
            mock_notification,
            Exception("Service error"),
            mock_notification,
        ]

        admin_ids = [1, 2, 3]
        result = NotificationFactory.create_admin_notification(
            admin_user_ids=admin_ids, title="Test", message="Test message"
        )

        assert len(result) == 3
        assert result[0] == mock_notification
        assert result[1] is None  # Failed
        assert result[2] == mock_notification

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_bulk_notification_success(self, mock_create):
        """Test successful bulk notification creation."""
        mock_notification = MagicMock()
        mock_create.return_value = mock_notification

        user_ids = [10, 20, 30]
        result = NotificationFactory.create_bulk_notification(
            user_ids=user_ids,
            notification_type=NotificationType.MATCH_PROPOSAL,
            title="Bulk Test",
            message="Bulk message",
        )

        assert len(result) == 3
        assert all(n == mock_notification for n in result)
        assert mock_create.call_count == 3

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_bulk_notification_with_errors(self, mock_create):
        """Test bulk notification creation with errors."""
        mock_notification = MagicMock()
        mock_create.side_effect = [
            mock_notification,
            Exception("Error"),
            Exception("Another error"),
        ]

        user_ids = [10, 20, 30]
        result = NotificationFactory.create_bulk_notification(
            user_ids=user_ids,
            notification_type=NotificationType.MATCH_PROPOSAL,
            title="Bulk Test",
            message="Bulk message",
            continue_on_error=True,
        )

        assert len(result) == 3
        assert result[0] == mock_notification
        assert result[1] is None
        assert result[2] is None

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_bulk_notification_stop_on_error(self, mock_create):
        """Test bulk notification creation that stops on first error."""
        mock_notification = MagicMock()
        mock_create.side_effect = [mock_notification, Exception("Error")]

        user_ids = [10, 20, 30]
        result = NotificationFactory.create_bulk_notification(
            user_ids=user_ids,
            notification_type=NotificationType.MATCH_PROPOSAL,
            title="Bulk Test",
            message="Bulk message",
            continue_on_error=False,
        )

        assert len(result) == 2  # Stopped after error
        assert result[0] == mock_notification
        assert result[1] is None
        assert mock_create.call_count == 2

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_tournament_notification(self, mock_create):
        """Test tournament notification creation."""
        mock_notification = MagicMock()
        mock_create.return_value = mock_notification

        user_ids = [1, 2]
        tournament_name = "Championship 2025"
        message_template = "New tournament: {tournament_name}"
        tournament_id = 123

        result = NotificationFactory.create_tournament_notification(
            user_ids=user_ids,
            tournament_name=tournament_name,
            message_template=message_template,
            tournament_id=tournament_id,
        )

        assert len(result) == 2
        assert mock_create.call_count == 2

        # Verify message formatting
        call_kwargs = mock_create.call_args_list[0][1]
        assert call_kwargs["message"] == "New tournament: Championship 2025"
        assert (
            call_kwargs["notification_type"] == NotificationType.TOURNAMENT_REGISTRATION
        )
        assert call_kwargs["action_url"] == "/gara/123"

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_match_notification_proposal(self, mock_create):
        """Test match notification creation for proposal."""
        mock_notification = MagicMock()
        mock_create.return_value = mock_notification

        result = NotificationFactory.create_match_notification(
            user_id=1,
            match_type="proposal",
            player_names=["Player1", "Player2"],
            location_name="Pool Hall",
            scheduled_time="2025-10-15 20:00",
            notes="Let's play!",
            proposal_id=456,
        )

        assert result == mock_notification
        mock_create.assert_called_once()

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["notification_type"] == NotificationType.MATCH_PROPOSAL
        assert call_kwargs["title"] == "Nuova Proposta di Partita"
        # Il messaggio arriva da comporre nella lingua del destinatario
        # (ADR-062): qui lo si compone come farebbe il servizio.
        messaggio = componi(call_kwargs["message"])
        assert "Player1 vs Player2" in messaggio
        assert "Pool Hall" in messaggio
        assert "Let's play!" in messaggio
        assert call_kwargs["action_url"] == "/match/proposals/456"

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_match_notification_accepted(self, mock_create):
        """Test match notification creation for accepted match."""
        mock_notification = MagicMock()
        mock_create.return_value = mock_notification

        result = NotificationFactory.create_match_notification(
            user_id=1, match_type="accepted", player_names=["Player1"], match_id=789
        )

        assert result == mock_notification
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["notification_type"] == NotificationType.MATCH_ACCEPTED
        assert call_kwargs["title"] == "Proposta Accettata!"
        assert call_kwargs["action_url"] == "/match/matches/789"

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_match_notification_error(self, mock_create):
        """Test match notification creation with error."""
        mock_create.side_effect = Exception("Service error")

        result = NotificationFactory.create_match_notification(
            user_id=1, match_type="proposal", player_names=["Player1"]
        )

        assert result is None

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_account_update_notification(self, mock_create):
        """Test account update notification creation."""
        mock_notification = MagicMock()
        mock_create.return_value = mock_notification

        result = NotificationFactory.create_account_update_notification(
            user_id=1,
            title="Account Updated",
            message="Your account has been updated",
            priority=NotificationPriority.HIGH,
            update_type="role_change",
        )

        assert result == mock_notification
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["notification_type"] == NotificationType.ACCOUNT_UPDATE
        assert call_kwargs["related_entities"]["update_type"] == "role_change"

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_system_announcement(self, mock_create):
        """Test system announcement creation."""
        mock_notification = MagicMock()
        mock_create.return_value = mock_notification

        user_ids = [1, 2]
        result = NotificationFactory.create_system_announcement(
            user_ids=user_ids,
            title="System Announcement",
            message="System maintenance scheduled",
            action_url="/maintenance",
            action_text="More Info",
        )

        assert len(result) == 2
        assert mock_create.call_count == 2

        call_kwargs = mock_create.call_args_list[0][1]
        assert call_kwargs["notification_type"] == NotificationType.SYSTEM_ANNOUNCEMENT
        assert call_kwargs["action_url"] == "/maintenance"
        assert call_kwargs["action_text"] == "More Info"

    def test_get_notification_stats(self):
        """Test notification statistics calculation."""
        mock_notification = MagicMock()
        notifications = [mock_notification, None, mock_notification, None]

        stats = NotificationFactory.get_notification_stats(notifications)

        assert stats["total"] == 4
        assert stats["successful"] == 2
        assert stats["failed"] == 2
        assert stats["success_rate"] == 50.0

    def test_get_notification_stats_empty(self):
        """Test notification statistics with empty list."""
        stats = NotificationFactory.get_notification_stats([])

        assert stats["total"] == 0
        assert stats["successful"] == 0
        assert stats["failed"] == 0
        assert stats["success_rate"] == 0

    def test_get_notification_stats_all_success(self):
        """Test notification statistics with all successful."""
        mock_notification = MagicMock()
        notifications = [mock_notification, mock_notification, mock_notification]

        stats = NotificationFactory.get_notification_stats(notifications)

        assert stats["total"] == 3
        assert stats["successful"] == 3
        assert stats["failed"] == 0
        assert stats["success_rate"] == 100.0

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_gara_inscription_notification_success(self, mock_create):
        """Test successful gara inscription notification creation."""
        mock_notification = MagicMock()
        mock_create.return_value = mock_notification

        result = NotificationFactory.create_gara_inscription_notification(
            user_id=1,
            gara_id=123,
            gara_name="Torneo Primavera",
            gara_date="15/03/2026",
            enrolled_by="Director Paolo",
        )

        assert result == mock_notification
        mock_create.assert_called_once()

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["user_id"] == 1
        assert (
            call_kwargs["notification_type"] == NotificationType.TOURNAMENT_REGISTRATION
        )
        # Title is i18n, check it's set
        assert call_kwargs["title"] is not None
        # Message contains key info (i18n formatted)
        assert "Director Paolo" in call_kwargs["message"]
        assert "Torneo Primavera" in call_kwargs["message"]
        assert "15/03/2026" in call_kwargs["message"]
        # No action button anymore
        assert "action_url" not in call_kwargs or call_kwargs.get("action_url") is None
        assert (
            "action_text" not in call_kwargs or call_kwargs.get("action_text") is None
        )
        # Related entities still present
        assert call_kwargs["related_entities"]["gara_id"] == 123
        assert call_kwargs["related_entities"]["gara_name"] == "Torneo Primavera"
        assert call_kwargs["related_entities"]["enrolled_by"] == "Director Paolo"

    @patch("models.notification.factory.NotificationService.create_notification")
    def test_create_gara_inscription_notification_error(self, mock_create):
        """Test gara inscription notification creation with error."""
        mock_create.side_effect = Exception("Service error")

        result = NotificationFactory.create_gara_inscription_notification(
            user_id=1,
            gara_id=123,
            gara_name="Torneo",
            gara_date="01/01/2026",
            enrolled_by="Director",
        )

        assert result is None
