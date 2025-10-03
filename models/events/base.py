"""
Base event system classes for domain decoupling.

This module provides the core event-driven architecture components:
- DomainEvent: Base class for all domain events
- EventBus: Central event dispatcher using publish-subscribe pattern
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Type, TypeVar, Optional
from datetime import datetime
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

EventType = TypeVar('EventType', bound='DomainEvent')


@dataclass
class DomainEvent(ABC):
    """
    Base class for all domain events.

    Domain events represent significant business occurrences that other
    parts of the system might be interested in. They enable loose coupling
    between domains by using publish-subscribe patterns.

    Attributes:
        event_id: Unique identifier for this event instance
        occurred_at: Timestamp when the event occurred
        domain: Business domain that generated the event
        source: Component/service that published the event
        correlation_id: Optional ID to correlate related events
        metadata: Additional event context data
    """

    event_id: str = field(init=False)
    occurred_at: datetime = field(init=False)
    domain: str = field(init=False)
    source: Optional[str] = field(init=False, default=None)
    correlation_id: Optional[str] = field(init=False, default=None)
    metadata: Dict[str, Any] = field(init=False)

    def __post_init__(self):
        """Initialize base event fields."""
        # Initialize base fields
        timestamp = datetime.utcnow()
        self.event_id = f"evt_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"
        self.occurred_at = timestamp
        self.metadata = {}

    @abstractmethod
    def get_event_type(self) -> str:
        """Return the event type identifier."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            'event_id': self.event_id,
            'event_type': self.get_event_type(),
            'occurred_at': self.occurred_at.isoformat(),
            'domain': self.domain,
            'source': self.source,
            'correlation_id': self.correlation_id,
            'metadata': self.metadata,
            'data': self._get_event_data()
        }

    @abstractmethod
    def _get_event_data(self) -> Dict[str, Any]:
        """Return event-specific data for serialization."""
        pass


class EventHandler:
    """
    Wrapper for event handler functions with metadata.
    """

    def __init__(self, handler_func: Callable[[DomainEvent], None], priority: int = 0):
        self.handler_func = handler_func
        self.priority = priority
        self.handler_name = f"{handler_func.__module__}.{handler_func.__name__}"

    def __call__(self, event: DomainEvent) -> None:
        """Execute the handler function."""
        try:
            self.handler_func(event)
        except Exception as e:
            logger.error(f"Error in event handler {self.handler_name}: {e}", exc_info=True)
            raise

    def __repr__(self) -> str:
        return f"EventHandler(handler={self.handler_name}, priority={self.priority})"


class EventBus:
    """
    Central event dispatcher using publish-subscribe pattern.

    The EventBus enables loose coupling between domains by allowing:
    - Publishers to emit events without knowing who will handle them
    - Subscribers to register interest in specific event types
    - Asynchronous event processing (when needed)

    Usage:
        # Register a handler
        @EventBus.subscribe(UserRegisteredEvent)
        def handle_user_registered(event):
            # Create welcome notification
            pass

        # Or register manually
        EventBus.register_handler(UserRegisteredEvent, handle_user_registered)

        # Publish an event
        event = UserRegisteredEvent(user_id=123, email="user@example.com")
        EventBus.publish(event)
    """

    _handlers: Dict[Type[DomainEvent], List[EventHandler]] = {}
    _enabled: bool = True

    @classmethod
    def register_handler(
        cls,
        event_type: Type[EventType],
        handler: Callable[[EventType], None],
        priority: int = 0
    ) -> None:
        """
        Register an event handler for a specific event type.

        Args:
            event_type: Type of event to handle
            handler: Function to call when event is published
            priority: Handler priority (higher = earlier execution)
        """
        if event_type not in cls._handlers:
            cls._handlers[event_type] = []

        event_handler = EventHandler(handler, priority)
        cls._handlers[event_type].append(event_handler)

        # Sort handlers by priority (descending)
        cls._handlers[event_type].sort(key=lambda h: h.priority, reverse=True)

        logger.debug(f"Registered handler {event_handler.handler_name} for {event_type.__name__}")

    @classmethod
    def subscribe(cls, event_type: Type[EventType], priority: int = 0):
        """
        Decorator to register an event handler.

        Args:
            event_type: Type of event to handle
            priority: Handler priority (higher = earlier execution)

        Usage:
            @EventBus.subscribe(UserRegisteredEvent)
            def handle_user_registered(event):
                pass
        """
        def decorator(handler: Callable[[EventType], None]) -> Callable[[EventType], None]:
            cls.register_handler(event_type, handler, priority)
            return handler
        return decorator

    @classmethod
    def publish(cls, event: DomainEvent) -> None:
        """
        Publish an event to all registered handlers.

        Args:
            event: Domain event to publish
        """
        if not cls._enabled:
            logger.debug(f"EventBus disabled, skipping event {event.get_event_type()}")
            return

        event_type = type(event)
        handlers = cls._handlers.get(event_type, [])

        logger.debug(f"Publishing {event.get_event_type()} to {len(handlers)} handlers")

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    f"Error in event handler {handler.handler_name} "
                    f"for event {event.get_event_type()}: {e}",
                    exc_info=True
                )
                # Continue with other handlers despite individual failures

        logger.debug(f"Completed publishing {event.get_event_type()}")

    @classmethod
    def get_handlers(cls, event_type: Type[DomainEvent]) -> List[EventHandler]:
        """Get all handlers for a specific event type."""
        return cls._handlers.get(event_type, []).copy()

    @classmethod
    def clear_handlers(cls, event_type: Optional[Type[DomainEvent]] = None) -> None:
        """
        Clear event handlers.

        Args:
            event_type: Specific event type to clear, or None to clear all
        """
        if event_type:
            cls._handlers.pop(event_type, None)
            logger.debug(f"Cleared handlers for {event_type.__name__}")
        else:
            cls._handlers.clear()
            logger.debug("Cleared all event handlers")

    @classmethod
    def disable(cls) -> None:
        """Disable event publishing (useful for testing)."""
        cls._enabled = False
        logger.debug("EventBus disabled")

    @classmethod
    def enable(cls) -> None:
        """Enable event publishing."""
        cls._enabled = True
        logger.debug("EventBus enabled")

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if EventBus is enabled."""
        return cls._enabled

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Get EventBus statistics for monitoring."""
        total_handlers = sum(len(handlers) for handlers in cls._handlers.values())
        return {
            'enabled': cls._enabled,
            'event_types': len(cls._handlers),
            'total_handlers': total_handlers,
            'handlers_by_type': {
                event_type.__name__: len(handlers)
                for event_type, handlers in cls._handlers.items()
            }
        }