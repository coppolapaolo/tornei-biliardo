"""
Module: models/notification/__init__.py
Purpose: Notification domain initialization and exports
Requirements: SPECIFICHE.md - Notification system
"""

from .models import (
    Notification,
    NotificationPreference,
    NotificationTemplate,
    NotificationType,
    NotificationPriority,
    NotificationStatus,
)
from .services import NotificationService

__all__ = [
    # Models
    "Notification",
    "NotificationPreference",
    "NotificationTemplate",
    # Enums
    "NotificationType",
    "NotificationPriority",
    "NotificationStatus",
    # Services
    "NotificationService",
]
