"""
Tests for the event system architecture.

This module tests the EventBus, DomainEvent classes, and event handlers
to ensure proper domain decoupling and notification generation.
"""

from unittest.mock import patch, MagicMock
from datetime import datetime

from models.events.base import EventBus
from models.events.user_events import (
    DirectorRequestCreatedEvent,
    DirectorRequestProcessedEvent,
    VenueManagerRequestCreatedEvent,
    VenueManagerRequestProcessedEvent,
)
from models.events.match_events import MatchProposalCreatedEvent, MatchAcceptedEvent
from models.events.notification_handlers import NotificationEventHandlers
from models.notification.models import NotificationType, NotificationPriority
from utils.lingua import componi
from flask_babel import force_locale


def _testo(valore):
    """Il testo come lo compone il servizio per un destinatario italiano (ADR-062)."""
    with force_locale("it"):
        return componi(valore)


class TestDomainEvent:
    """Test DomainEvent base functionality."""

    def test_event_creation_with_defaults(self):
        """Test that events are created with proper defaults."""
        event = DirectorRequestCreatedEvent(
            request_id=1, user_id=123, username="testuser", admin_user_ids=[1, 2]
        )

        assert event.request_id == 1
        assert event.user_id == 123
        assert event.username == "testuser"
        assert event.domain == "user"
        assert event.get_event_type() == "user.director_request_created"
        assert event.event_id.startswith("evt_")
        assert isinstance(event.occurred_at, datetime)

    def test_event_to_dict(self):
        """Test event serialization to dictionary."""
        event = DirectorRequestCreatedEvent(
            request_id=1, user_id=123, username="testuser", admin_user_ids=[1, 2]
        )
        event.source = "test_service"

        event_dict = event.to_dict()

        assert event_dict["event_type"] == "user.director_request_created"
        assert event_dict["domain"] == "user"
        assert event_dict["source"] == "test_service"
        assert event_dict["data"]["user_id"] == 123
        assert event_dict["data"]["username"] == "testuser"

    def test_match_event_creation(self):
        """Test match domain event creation."""
        event = MatchProposalCreatedEvent(
            proposal_id=456,
            proposer_id=123,
            proposer_name="Player1",
            target_user_id=789,
            target_username="Player2",
            location_name="Pool Hall",
            is_public=False,
        )

        assert event.proposal_id == 456
        assert event.domain == "match"
        assert event.get_event_type() == "match.proposal_created"
        assert not event.is_public


class TestEventBus:
    """Test EventBus functionality."""

    def setup_method(self):
        """Snapshot e azzera gli handler per testare l'EventBus isolato."""
        # NON usare clear_handlers() senza ripristino: cancellerebbe gli
        # handler reali dell'app (rating/notification/gamification) per tutti
        # i test successivi dello stesso worker xdist. Vedi CLAUDE.md.
        self._original_handlers = {k: list(v) for k, v in EventBus._handlers.items()}
        EventBus.clear_handlers()
        EventBus.enable()

    def teardown_method(self):
        """Ripristina gli handler reali dell'app (non lasciare il bus vuoto)."""
        EventBus._handlers = self._original_handlers
        EventBus.enable()

    def test_handler_registration(self):
        """Test registering and retrieving event handlers."""

        def test_handler(event):
            pass

        EventBus.register_handler(DirectorRequestCreatedEvent, test_handler)
        handlers = EventBus.get_handlers(DirectorRequestCreatedEvent)

        assert len(handlers) == 1
        assert handlers[0].handler_func == test_handler

    def test_handler_registration_with_decorator(self):
        """Test registering handlers with decorator syntax."""

        @EventBus.subscribe(DirectorRequestCreatedEvent, priority=5)
        def test_handler(event):
            pass

        handlers = EventBus.get_handlers(DirectorRequestCreatedEvent)

        assert len(handlers) == 1
        assert handlers[0].priority == 5

    def test_event_publishing(self):
        """Test event publishing to registered handlers."""
        handler_calls = []

        def test_handler(event):
            handler_calls.append(event)

        EventBus.register_handler(DirectorRequestCreatedEvent, test_handler)

        event = DirectorRequestCreatedEvent(
            request_id=1, user_id=123, username="testuser", admin_user_ids=[1]
        )

        EventBus.publish(event)

        assert len(handler_calls) == 1
        assert handler_calls[0] == event

    def test_multiple_handlers_with_priority(self):
        """Test that handlers are called in priority order."""
        call_order = []

        def handler_low(event):
            call_order.append("low")

        def handler_high(event):
            call_order.append("high")

        def handler_medium(event):
            call_order.append("medium")

        EventBus.register_handler(DirectorRequestCreatedEvent, handler_low, priority=1)
        EventBus.register_handler(
            DirectorRequestCreatedEvent, handler_high, priority=10
        )
        EventBus.register_handler(
            DirectorRequestCreatedEvent, handler_medium, priority=5
        )

        event = DirectorRequestCreatedEvent(
            request_id=1, user_id=123, username="testuser", admin_user_ids=[1]
        )

        EventBus.publish(event)

        assert call_order == ["high", "medium", "low"]

    def test_event_bus_disable_enable(self):
        """Test disabling and enabling the event bus."""
        handler_calls = []

        def test_handler(event):
            handler_calls.append(event)

        EventBus.register_handler(DirectorRequestCreatedEvent, test_handler)

        event = DirectorRequestCreatedEvent(
            request_id=1, user_id=123, username="testuser", admin_user_ids=[1]
        )

        # Disable and publish
        EventBus.disable()
        EventBus.publish(event)
        assert len(handler_calls) == 0

        # Enable and publish
        EventBus.enable()
        EventBus.publish(event)
        assert len(handler_calls) == 1

    def test_handler_error_isolation(self):
        """Test that handler errors don't affect other handlers."""
        handler_calls = []

        def failing_handler(event):
            raise Exception("Handler error")

        def working_handler(event):
            handler_calls.append("success")

        EventBus.register_handler(
            DirectorRequestCreatedEvent, failing_handler, priority=10
        )
        EventBus.register_handler(
            DirectorRequestCreatedEvent, working_handler, priority=5
        )

        event = DirectorRequestCreatedEvent(
            request_id=1, user_id=123, username="testuser", admin_user_ids=[1]
        )

        # Should not raise exception, working handler should still be called
        EventBus.publish(event)
        assert handler_calls == ["success"]

    def test_handler_error_captured_by_sentry(self):
        """Failing handler triggers sentry_sdk.capture_exception with extra context."""

        def failing_handler(event):
            raise RuntimeError("boom")

        EventBus.register_handler(DirectorRequestCreatedEvent, failing_handler)

        event = DirectorRequestCreatedEvent(
            request_id=1, user_id=123, username="testuser", admin_user_ids=[1]
        )

        fake_scope = MagicMock()
        scope_cm = MagicMock()
        scope_cm.__enter__.return_value = fake_scope
        scope_cm.__exit__.return_value = False

        with patch("models.events.base._sentry_available", True), patch(
            "models.events.base._sentry_sdk"
        ) as mock_sdk:
            mock_sdk.push_scope.return_value = scope_cm
            EventBus.publish(event)

            assert mock_sdk.capture_exception.call_count == 1
            captured_exc = mock_sdk.capture_exception.call_args[0][0]
            assert isinstance(captured_exc, RuntimeError)

            extras = {
                call.args[0]: call.args[1]
                for call in fake_scope.set_extra.call_args_list
            }
            assert extras["event_type"] == "user.director_request_created"
            assert extras["event_id"] == event.event_id
            assert extras["handler_name"].endswith("failing_handler")
            assert extras["event_domain"] == "user"

    def test_publish_adds_breadcrumb(self):
        """Successful publish emits an event_bus breadcrumb with handler_count."""

        def handler_one(event):
            pass

        def handler_two(event):
            pass

        EventBus.register_handler(DirectorRequestCreatedEvent, handler_one)
        EventBus.register_handler(DirectorRequestCreatedEvent, handler_two)

        event = DirectorRequestCreatedEvent(
            request_id=1, user_id=123, username="testuser", admin_user_ids=[1]
        )

        with patch("models.events.base._sentry_available", True), patch(
            "models.events.base._sentry_sdk"
        ) as mock_sdk:
            EventBus.publish(event)

            assert mock_sdk.add_breadcrumb.call_count == 1
            kwargs = mock_sdk.add_breadcrumb.call_args.kwargs
            assert kwargs["category"] == "event_bus"
            assert kwargs["level"] == "info"
            assert kwargs["data"]["handler_count"] == 2
            assert kwargs["data"]["event_type"] == "user.director_request_created"
            assert kwargs["data"]["event_id"] == event.event_id

    def test_capture_failure_does_not_break_publish(self):
        """Sentry client errors must not propagate out of publish()."""
        handler_calls = []

        def failing_handler(event):
            raise RuntimeError("handler boom")

        def working_handler(event):
            handler_calls.append("ok")

        EventBus.register_handler(
            DirectorRequestCreatedEvent, failing_handler, priority=10
        )
        EventBus.register_handler(
            DirectorRequestCreatedEvent, working_handler, priority=5
        )

        event = DirectorRequestCreatedEvent(
            request_id=1, user_id=123, username="testuser", admin_user_ids=[1]
        )

        with patch("models.events.base._sentry_available", True), patch(
            "models.events.base._sentry_sdk"
        ) as mock_sdk:
            mock_sdk.push_scope.side_effect = RuntimeError("sentry exploded")
            # Must not raise
            EventBus.publish(event)

        assert handler_calls == ["ok"]

    def test_sentry_not_available_skips_capture(self):
        """_sentry_available=False: no Sentry API invoked even on failure."""

        def failing_handler(event):
            raise RuntimeError("boom")

        EventBus.register_handler(DirectorRequestCreatedEvent, failing_handler)

        event = DirectorRequestCreatedEvent(
            request_id=1, user_id=123, username="testuser", admin_user_ids=[1]
        )

        with patch("models.events.base._sentry_available", False), patch(
            "models.events.base._sentry_sdk"
        ) as mock_sdk:
            # Must not raise and must not touch sentry
            EventBus.publish(event)

            mock_sdk.add_breadcrumb.assert_not_called()
            mock_sdk.capture_exception.assert_not_called()
            mock_sdk.push_scope.assert_not_called()

    def test_eventbus_logger_is_ignored_by_sentry_logging_integration(self):
        """The EventBus logger is excluded from Sentry's LoggingIntegration
        so that logger.error calls in publish() / EventHandler.__call__ do
        NOT produce duplicate Sentry events on top of our explicit
        capture_exception in _capture_handler_exception().
        """
        from sentry_sdk.integrations.logging import _IGNORED_LOGGERS

        assert "models.events.base" in _IGNORED_LOGGERS

    def test_clear_handlers(self):
        """Test clearing event handlers."""

        def test_handler(event):
            pass

        EventBus.register_handler(DirectorRequestCreatedEvent, test_handler)
        EventBus.register_handler(MatchProposalCreatedEvent, test_handler)

        # Clear specific event type
        EventBus.clear_handlers(DirectorRequestCreatedEvent)
        assert len(EventBus.get_handlers(DirectorRequestCreatedEvent)) == 0
        assert len(EventBus.get_handlers(MatchProposalCreatedEvent)) == 1

        # Clear all handlers
        EventBus.clear_handlers()
        assert len(EventBus.get_handlers(MatchProposalCreatedEvent)) == 0

    def test_event_bus_stats(self):
        """Test EventBus statistics."""

        def test_handler(event):
            pass

        EventBus.register_handler(DirectorRequestCreatedEvent, test_handler)
        EventBus.register_handler(MatchProposalCreatedEvent, test_handler)

        stats = EventBus.get_stats()

        assert stats["enabled"] is True
        assert stats["event_types"] == 2
        assert stats["total_handlers"] == 2
        assert "DirectorRequestCreatedEvent" in stats["handlers_by_type"]
        assert "MatchProposalCreatedEvent" in stats["handlers_by_type"]


class TestNotificationEventHandlers:
    """Test notification event handlers."""

    def setup_method(self):
        """Setup for each test."""
        # Snapshot e ripristino: non lasciare il bus vuoto per i test
        # successivi dello stesso worker (vedi CLAUDE.md / TestEventBus).
        self._original_handlers = {k: list(v) for k, v in EventBus._handlers.items()}
        EventBus.clear_handlers()
        # Re-register handlers
        NotificationEventHandlers.register_all_handlers()

    def teardown_method(self):
        """Ripristina gli handler reali dell'app."""
        EventBus._handlers = self._original_handlers
        EventBus.enable()

    @patch(
        "models.events.notification_handlers.NotificationService.create_notification"
    )
    def test_director_request_created_handler(self, mock_create_notification):
        """Test director request created event handler."""
        event = DirectorRequestCreatedEvent(
            request_id=1, user_id=123, username="testuser", admin_user_ids=[1, 2]
        )

        EventBus.publish(event)

        # Should create notifications for both admins
        assert mock_create_notification.call_count == 2
        calls = mock_create_notification.call_args_list

        # Verify first admin notification
        first_call = calls[0][1]  # kwargs
        assert first_call["user_id"] == 1
        assert first_call["notification_type"] == NotificationType.SYSTEM_ANNOUNCEMENT
        assert _testo(first_call["title"]) == "Nuova Richiesta Direttore"
        assert "testuser" in _testo(first_call["message"])
        assert first_call["priority"] == NotificationPriority.HIGH

        # Verify second admin notification
        second_call = calls[1][1]  # kwargs
        assert second_call["user_id"] == 2

    @patch(
        "models.events.notification_handlers.NotificationService.create_notification"
    )
    def test_director_request_processed_approved_handler(
        self, mock_create_notification
    ):
        """Test director request approved event handler."""
        event = DirectorRequestProcessedEvent(
            request_id=1,
            user_id=123,
            username="testuser",
            status="approved",
            processed_by_id=999,
            notes="Well qualified",
        )

        EventBus.publish(event)

        # Should create notification for the user
        mock_create_notification.assert_called_once()
        call_kwargs = mock_create_notification.call_args[1]

        assert call_kwargs["user_id"] == 123
        assert call_kwargs["notification_type"] == NotificationType.ACCOUNT_UPDATE
        assert "Approvata" in _testo(call_kwargs["title"])
        assert "Congratulazioni" in _testo(call_kwargs["message"])
        assert "Well qualified" in _testo(call_kwargs["message"])
        assert call_kwargs["priority"] == NotificationPriority.HIGH

    @patch(
        "models.events.notification_handlers.NotificationService.create_notification"
    )
    def test_director_request_processed_rejected_handler(
        self, mock_create_notification
    ):
        """Test director request rejected event handler."""
        event = DirectorRequestProcessedEvent(
            request_id=1,
            user_id=123,
            username="testuser",
            status="rejected",
            processed_by_id=999,
            notes="Insufficient experience",
        )

        EventBus.publish(event)

        # Should create notification for the user
        mock_create_notification.assert_called_once()
        call_kwargs = mock_create_notification.call_args[1]

        assert call_kwargs["user_id"] == 123
        assert call_kwargs["notification_type"] == NotificationType.ACCOUNT_UPDATE
        assert "Rifiutata" in _testo(call_kwargs["title"])
        assert "rifiutata" in _testo(call_kwargs["message"])
        assert "Insufficient experience" in _testo(call_kwargs["message"])
        assert call_kwargs["priority"] == NotificationPriority.NORMAL

    @patch(
        "models.events.notification_handlers.NotificationService.create_notification"
    )
    def test_venue_manager_request_processed_handler(self, mock_create_notification):
        """Test venue manager request processed event handler."""
        event = VenueManagerRequestProcessedEvent(
            request_id=1,
            user_id=123,
            username="testuser",
            venue_id=456,
            venue_name="Test Pool Hall",
            status="approved",
            processed_by_id=789,
            notes="Great candidate",
        )

        EventBus.publish(event)

        # Should create notification for the user
        mock_create_notification.assert_called_once()
        call_kwargs = mock_create_notification.call_args[1]

        assert call_kwargs["user_id"] == 123
        assert call_kwargs["notification_type"] == NotificationType.ACCOUNT_UPDATE
        assert "Approvata" in _testo(call_kwargs["title"])
        assert "Test Pool Hall" in _testo(call_kwargs["title"])
        assert "Congratulazioni" in _testo(call_kwargs["message"])
        assert call_kwargs["priority"] == NotificationPriority.HIGH

    @patch(
        "models.events.notification_handlers.NotificationService.create_notification"
    )
    def test_venue_manager_request_contested_handler(self, mock_create_notification):
        """Test contested venue manager request creates high priority notification."""
        event = VenueManagerRequestCreatedEvent(
            request_id=1,
            user_id=123,
            username="testuser",
            venue_id=456,
            venue_name="Test Pool Hall",
            motivation="I want to manage this venue",
            admin_user_ids=[1],
            is_contested=True,
        )

        EventBus.publish(event)

        mock_create_notification.assert_called_once()
        call_kwargs = mock_create_notification.call_args[1]

        assert call_kwargs["priority"] == NotificationPriority.HIGH
        assert "(CONTESA)" in _testo(call_kwargs["title"])
        assert "ATTENZIONE" in _testo(call_kwargs["message"])

    @patch(
        "models.events.notification_handlers.NotificationService.create_notification"
    )
    def test_match_proposal_created_handler(self, mock_create_notification):
        """Test match proposal created event handler."""
        event = MatchProposalCreatedEvent(
            proposal_id=456,
            proposer_id=123,
            proposer_name="Player1",
            target_user_id=789,
            target_username="Player2",
            location_name="Pool Hall",
            scheduled_time=datetime(2025, 10, 15, 20, 0),
            notes="Let's play!",
        )

        EventBus.publish(event)

        mock_create_notification.assert_called_once()
        call_kwargs = mock_create_notification.call_args[1]

        assert call_kwargs["user_id"] == 789
        assert call_kwargs["notification_type"] == NotificationType.MATCH_PROPOSAL
        assert _testo(call_kwargs["title"]) == "Nuova Proposta di Partita"
        assert "Player1" in _testo(call_kwargs["message"])
        assert "Pool Hall" in _testo(call_kwargs["message"])
        assert "Let's play!" in _testo(call_kwargs["message"])

    @patch(
        "models.events.notification_handlers.NotificationService.create_notification"
    )
    def test_match_proposal_public_no_notification(self, mock_create_notification):
        """Test that public match proposals don't create notifications."""
        event = MatchProposalCreatedEvent(
            proposal_id=456,
            proposer_id=123,
            proposer_name="Player1",
            target_user_id=None,  # No specific target
            is_public=True,
        )

        EventBus.publish(event)

        # Should not create any notifications for public proposals
        mock_create_notification.assert_not_called()

    @patch(
        "models.events.notification_handlers.NotificationService.create_notification"
    )
    def test_match_accepted_handler(self, mock_create_notification):
        """Test match accepted event handler."""
        event = MatchAcceptedEvent(
            proposal_id=456,
            match_id=789,
            proposer_id=123,
            proposer_name="Player1",
            accepter_id=456,
            accepter_name="Player2",
            location_name="Pool Hall",
            scheduled_time=datetime(2025, 10, 15, 20, 0),
        )

        EventBus.publish(event)

        mock_create_notification.assert_called_once()
        call_kwargs = mock_create_notification.call_args[1]

        assert call_kwargs["user_id"] == 123  # Notify proposer
        assert call_kwargs["notification_type"] == NotificationType.MATCH_ACCEPTED
        assert _testo(call_kwargs["title"]) == "Proposta di Partita Accettata!"
        assert "Player2" in _testo(call_kwargs["message"])
        assert "accettato" in _testo(call_kwargs["message"])
