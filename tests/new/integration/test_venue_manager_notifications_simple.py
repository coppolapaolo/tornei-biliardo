"""
Simple integration test for venue manager request notification flow.

Tests that when a player or director requests to become a venue manager,
the admin receives the appropriate notification.

Author: Venue Management Refactoring
Created: 2025-09-11
"""

import pytest
from models.base import db
from models.user.models import User, VenueManagerRequest
from models.user.venue_manager_service import VenueManagerService
from models.notification.models import (
    Notification,
    NotificationType,
    NotificationPriority,
    NotificationStatus,
)
from models import BilliardHall
from models.location.services import LocationService


def test_player_venue_manager_request_creates_admin_notification(app, client):
    """Test that a player's venue manager request creates notification for admin."""
    with app.app_context():
        # Clear existing notifications and requests
        Notification.query.delete()
        VenueManagerRequest.query.delete()
        db.session.commit()

        # Create test users
        admin = User(username="test_admin", email="admin@test.com", role="admin")
        admin.set_password("password")
        db.session.add(admin)

        player = User(username="test_player", email="player@test.com", role="player")
        player.set_password("password")
        db.session.add(player)

        db.session.commit()

        # Create test venue
        test_venue = LocationService.create_billiard_hall(
            name="Test Notification Venue", address="123 Test Street", city="Test City"
        )

        # Count initial admin notifications
        initial_admin_notifications = Notification.query.filter_by(
            user_id=admin.id
        ).count()

        # Player makes venue manager request
        request = VenueManagerService.create_venue_manager_request(
            user_id=player.id,
            venue_id=test_venue.id,
            notes="I would like to manage this venue",
        )

        # Verify request was created
        assert request is not None
        assert request.user_id == player.id
        assert request.venue_id == test_venue.id
        assert request.status == "pending"

        # Check that admin received notification
        final_admin_notifications = Notification.query.filter_by(
            user_id=admin.id, notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).count()

        # Should have one new notification
        assert final_admin_notifications == initial_admin_notifications + 1

        # Get the new notification
        new_notification = (
            Notification.query.filter_by(
                user_id=admin.id, notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
            )
            .order_by(Notification.created_at.desc())
            .first()
        )

        # Verify notification content
        assert new_notification is not None
        assert (
            new_notification.notification_type == NotificationType.SYSTEM_ANNOUNCEMENT
        )
        assert new_notification.status == NotificationStatus.PENDING
        assert "Test Notification Venue" in new_notification.title
        assert "Richiesta Gestore Sala" in new_notification.title
        assert player.username in new_notification.message
        assert new_notification.priority == NotificationPriority.NORMAL  # Non-contested


def test_director_venue_manager_request_creates_admin_notification(app, client):
    """Test that a director's venue manager request creates notification for admin."""
    with app.app_context():
        # Clear existing notifications and requests
        Notification.query.delete()
        VenueManagerRequest.query.delete()
        db.session.commit()

        # Create test venue
        test_venue = LocationService.create_billiard_hall(
            name="Test Director Venue",
            address="456 Director Street",
            city="Director City",
        )

        # Create test users
        admin = User(username="test_admin2", email="admin2@test.com", role="admin")
        admin.set_password("password")
        db.session.add(admin)

        director = User(
            username="test_director", email="director@test.com", role="director"
        )
        director.set_password("password")
        db.session.add(director)

        db.session.commit()

        # Count initial admin notifications
        initial_admin_notifications = Notification.query.filter_by(
            user_id=admin.id, notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).count()

        # Director makes venue manager request
        request = VenueManagerService.create_venue_manager_request(
            user_id=director.id,
            venue_id=test_venue.id,
            notes="As a director, I can help manage this venue",
        )

        # Verify request was created
        assert request is not None
        assert request.user_id == director.id
        assert request.venue_id == test_venue.id
        assert request.status == "pending"

        # Check that admin received notification
        final_admin_notifications = Notification.query.filter_by(
            user_id=admin.id, notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).count()

        # Should have one new notification
        assert final_admin_notifications == initial_admin_notifications + 1

        # Get the new notification
        new_notification = (
            Notification.query.filter_by(
                user_id=admin.id, notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
            )
            .order_by(Notification.created_at.desc())
            .first()
        )

        # Verify notification content
        assert new_notification is not None
        assert (
            new_notification.notification_type == NotificationType.SYSTEM_ANNOUNCEMENT
        )
        assert new_notification.status == NotificationStatus.PENDING
        assert "Test Director Venue" in new_notification.title
        assert "Richiesta Gestore Sala" in new_notification.title
        assert director.username in new_notification.message
        assert new_notification.priority == NotificationPriority.NORMAL  # Non-contested


def test_admin_rejection_notifies_requester(app, client):
    """Test that when admin rejects a request, the requester gets notified."""
    with app.app_context():
        # Clear existing notifications and requests
        Notification.query.delete()
        VenueManagerRequest.query.delete()
        db.session.commit()

        # Create test users
        admin = User(
            username="test_admin_reject", email="admin_reject@test.com", role="admin"
        )
        admin.set_password("password")
        db.session.add(admin)

        player = User(
            username="test_player_reject", email="player_reject@test.com", role="player"
        )
        player.set_password("password")
        db.session.add(player)

        db.session.commit()

        # Create test venue
        test_venue = LocationService.create_billiard_hall(
            name="Test Rejection Venue", address="789 Reject Street", city="Reject City"
        )

        # Player makes venue manager request
        request = VenueManagerService.create_venue_manager_request(
            user_id=player.id, venue_id=test_venue.id, notes="Please approve my request"
        )

        # Clear existing notifications to focus on rejection notification
        Notification.query.delete()
        db.session.commit()

        # Admin rejects the request
        VenueManagerService.process_venue_manager_request(
            request_id=request.id,
            admin_user=admin,
            approve=False,
            notes="Not qualified at this time",
        )

        # Check that player received rejection notification
        player_notifications = Notification.query.filter_by(
            user_id=player.id, notification_type=NotificationType.ACCOUNT_UPDATE
        ).all()

        assert len(player_notifications) == 1

        rejection_notification = player_notifications[0]
        assert rejection_notification.status == NotificationStatus.PENDING
        assert "rifiutata" in rejection_notification.title.lower()
        assert "Not qualified at this time" in rejection_notification.message
        assert rejection_notification.priority == NotificationPriority.NORMAL


def test_admin_approval_notifies_requester(app, client):
    """Test that when admin approves a request, the requester gets notified."""
    with app.app_context():
        # Clear existing notifications and requests
        Notification.query.delete()
        VenueManagerRequest.query.delete()
        db.session.commit()

        # Create test users
        admin = User(
            username="test_admin_approve", email="admin_approve@test.com", role="admin"
        )
        admin.set_password("password")
        db.session.add(admin)

        player = User(
            username="test_player_approve",
            email="player_approve@test.com",
            role="player",
        )
        player.set_password("password")
        db.session.add(player)

        db.session.commit()

        # Create test venue
        test_venue = LocationService.create_billiard_hall(
            name="Test Approval Venue",
            address="321 Approve Street",
            city="Approve City",
        )

        # Player makes venue manager request
        request = VenueManagerService.create_venue_manager_request(
            user_id=player.id, venue_id=test_venue.id, notes="Please approve my request"
        )

        # Clear existing notifications to focus on approval notification
        Notification.query.delete()
        db.session.commit()

        # Admin approves the request
        VenueManagerService.process_venue_manager_request(
            request_id=request.id,
            admin_user=admin,
            approve=True,
            notes="Welcome to venue management!",
        )

        # Check that player received approval notification
        player_notifications = Notification.query.filter_by(
            user_id=player.id, notification_type=NotificationType.ACCOUNT_UPDATE
        ).all()

        assert len(player_notifications) == 1

        approval_notification = player_notifications[0]
        assert approval_notification.status == NotificationStatus.PENDING
        assert "approvata" in approval_notification.title.lower()
        assert "Welcome to venue management!" in approval_notification.message
        assert approval_notification.priority == NotificationPriority.HIGH


def test_web_request_integration(app, client):
    """Test notification creation through actual web request (integration test)."""
    with app.app_context():
        # Clear existing notifications and requests
        Notification.query.delete()
        VenueManagerRequest.query.delete()
        db.session.commit()

        # Create test users
        admin = User(
            username="test_admin_web", email="admin_web@test.com", role="admin"
        )
        admin.set_password("password")
        db.session.add(admin)

        player = User(
            username="test_player_web", email="player_web@test.com", role="player"
        )
        player.set_password("password")
        db.session.add(player)

        db.session.commit()

        # Create test venue
        test_venue = LocationService.create_billiard_hall(
            name="Web Test Venue", address="999 Web Street", city="Web City"
        )

        # Login as player
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player.id)
            sess["_fresh"] = True

        # Count admin notifications before request
        initial_count = Notification.query.filter_by(
            user_id=admin.id, notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).count()

        # Make venue manager request via web form
        response = client.post(
            "/player/request_venue_manager",
            data={"venue_id": test_venue.id, "notes": "Web request test"},
            follow_redirects=True,
        )

        # Should redirect successfully
        assert response.status_code == 200

        # Check that admin received notification
        final_count = Notification.query.filter_by(
            user_id=admin.id, notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).count()

        assert final_count == initial_count + 1

        # Verify the notification
        new_notification = (
            Notification.query.filter_by(
                user_id=admin.id, notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
            )
            .order_by(Notification.created_at.desc())
            .first()
        )

        assert new_notification is not None
        assert "Web Test Venue" in new_notification.title
        assert player.username in new_notification.message
