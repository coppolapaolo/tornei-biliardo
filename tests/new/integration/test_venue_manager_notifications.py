"""
Integration test for venue manager request notification flow.

Tests that when a player or director requests to become a venue manager,
the admin receives the appropriate notification.

Author: Venue Management Refactoring
Created: 2025-09-11
"""

import pytest
from flask import url_for
from models.base import db
from models.user.models import User, VenueManagerRequest
from models.user.services import VenueManagerRequestService
from models.notification.models import (
    Notification,
    NotificationType, 
    NotificationPriority,
    NotificationStatus
)
from models import BilliardHall
from models.location.services import LocationService


class TestVenueManagerNotifications:
    """Test suite for venue manager request notifications."""

    @pytest.fixture(autouse=True)
    def setup_test_data(self, app, client):
        """Set up test data for each test."""
        with app.app_context():
            # Clear existing notifications and requests
            Notification.query.delete()
            VenueManagerRequest.query.delete()
            
            # Create test venue
            self.test_venue = LocationService.create_billiard_hall(
                name="Test Venue Notifications",
                address="123 Test Street",
                city="Test City"
            )
            
            # Get test users
            self.admin = User.query.filter_by(role='admin').first()
            self.player = User.query.filter_by(role='player').first() 
            self.director = User.query.filter_by(role='director').first()
            
            # Ensure we have required users
            if not self.admin:
                self.admin = User(
                    username='test_admin',
                    email='admin@test.com',
                    role='admin'
                )
                self.admin.set_password('password')
                db.session.add(self.admin)
                
            if not self.player:
                self.player = User(
                    username='test_player',
                    email='player@test.com', 
                    role='player'
                )
                self.player.set_password('password')
                db.session.add(self.player)
                
            if not self.director:
                self.director = User(
                    username='test_director',
                    email='director@test.com',
                    role='director'
                )
                self.director.set_password('password')
                db.session.add(self.director)
                
            db.session.commit()

    def test_player_venue_manager_request_creates_admin_notification(self, app, client):
        """Test that a player's venue manager request creates notification for admin."""
        with app.app_context():
            # Refresh objects to ensure they're bound to current session
            admin_id = self.admin.id
            player_id = self.player.id  
            venue_id = self.test_venue.id
            
            # Count initial notifications
            initial_admin_notifications = Notification.query.filter_by(
                user_id=admin_id
            ).count()
            
            # Player makes venue manager request
            request = VenueManagerRequestService.create_request(
                user_id=player_id,
                venue_id=venue_id,
                notes="I would like to manage this venue"
            )
            
            # Verify request was created
            assert request is not None
            assert request.user_id == player_id
            assert request.venue_id == venue_id
            assert request.status == "pending"
            
            # Check that admin received notification
            admin_notifications = Notification.query.filter_by(
                user_id=admin_id,
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
            ).all()
            
            # Should have one new notification
            assert len(admin_notifications) == initial_admin_notifications + 1
            
            # Get the new notification
            new_notification = admin_notifications[-1]
            
            # Verify notification content
            assert new_notification.notification_type == NotificationType.SYSTEM_ANNOUNCEMENT
            assert new_notification.status == NotificationStatus.PENDING
            assert "Test Venue Notifications" in new_notification.title
            assert "Richiesta Gestore Sala" in new_notification.title
            # Get fresh player object for username check
            player = db.session.get(User, player_id)
            assert player.username in new_notification.message
            assert new_notification.priority == NotificationPriority.NORMAL  # Non-contested

    def test_director_venue_manager_request_creates_admin_notification(self, app, client):
        """Test that a director's venue manager request creates notification for admin."""
        with app.app_context():
            # Count initial notifications
            initial_admin_notifications = Notification.query.filter_by(
                user_id=self.admin.id
            ).count()
            
            # Director makes venue manager request  
            request = VenueManagerRequestService.create_request(
                user_id=self.director.id,
                venue_id=self.test_venue.id,
                notes="As a director, I can help manage this venue"
            )
            
            # Verify request was created
            assert request is not None
            assert request.user_id == self.director.id
            assert request.venue_id == self.test_venue.id
            assert request.status == "pending"
            
            # Check that admin received notification
            admin_notifications = Notification.query.filter_by(
                user_id=self.admin.id,
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
            ).all()
            
            # Should have one new notification
            assert len(admin_notifications) == initial_admin_notifications + 1
            
            # Get the new notification
            new_notification = admin_notifications[-1]
            
            # Verify notification content
            assert new_notification.notification_type == NotificationType.SYSTEM_ANNOUNCEMENT
            assert new_notification.status == NotificationStatus.PENDING
            assert "Test Venue Notifications" in new_notification.title
            assert "Richiesta Gestore Sala" in new_notification.title
            assert self.director.username in new_notification.message
            assert new_notification.priority == NotificationPriority.NORMAL  # Non-contested

    def test_contested_venue_request_has_high_priority(self, app, client):
        """Test that contested venue requests (venue already has manager) get HIGH priority."""
        with app.app_context():
            # First, assign a manager to the venue
            from models.user.services import VenueManagementService
            
            # Create initial manager assignment
            VenueManagementService.assign_venue_manager(
                self.director.id, 
                self.test_venue.id, 
                self.admin
            )
            
            # Clear existing notifications after setup
            Notification.query.delete()
            db.session.commit()
            
            # Now player requests to manage same venue (contested)
            request = VenueManagerRequestService.create_request(
                user_id=self.player.id,
                venue_id=self.test_venue.id,
                notes="I want to replace the current manager"
            )
            
            # Verify request is marked as contested
            assert request.is_contested == True
            
            # Check that admin received HIGH priority notification
            admin_notification = Notification.query.filter_by(
                user_id=self.admin.id,
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
            ).first()
            
            assert admin_notification is not None
            assert admin_notification.priority == NotificationPriority.HIGH  # Contested
            assert "ATTENZIONE" in admin_notification.message  # Warning message
            assert "già un gestore" in admin_notification.message

    def test_multiple_admins_receive_notifications(self, app, client):
        """Test that all admins receive notifications for venue manager requests."""
        with app.app_context():
            # Create second admin
            second_admin = User(
                username='second_admin',
                email='admin2@test.com',
                role='admin'
            )
            second_admin.set_password('password')
            db.session.add(second_admin)
            db.session.commit()
            
            # Clear existing notifications
            Notification.query.delete()
            db.session.commit()
            
            # Player makes venue manager request
            request = VenueManagerRequestService.create_request(
                user_id=self.player.id,
                venue_id=self.test_venue.id,
                notes="Please consider my request"
            )
            
            # Check that both admins received notifications
            admin1_notifications = Notification.query.filter_by(
                user_id=self.admin.id,
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
            ).count()
            
            admin2_notifications = Notification.query.filter_by(
                user_id=second_admin.id,
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
            ).count()
            
            assert admin1_notifications == 1
            assert admin2_notifications == 1

    def test_admin_rejection_notifies_requester(self, app, client):
        """Test that when admin rejects a request, the requester gets notified."""
        with app.app_context():
            # Player makes venue manager request
            request = VenueManagerRequestService.create_request(
                user_id=self.player.id,
                venue_id=self.test_venue.id,
                notes="Please approve my request"
            )
            
            # Clear existing notifications to focus on rejection notification
            Notification.query.delete()
            db.session.commit()
            
            # Admin rejects the request
            VenueManagerRequestService.process_request(
                request_id=request.id,
                admin_user=self.admin,
                approve=False,
                notes="Not qualified at this time"
            )
            
            # Check that player received rejection notification
            player_notifications = Notification.query.filter_by(
                user_id=self.player.id,
                notification_type=NotificationType.ACCOUNT_UPDATE
            ).all()
            
            assert len(player_notifications) == 1
            
            rejection_notification = player_notifications[0]
            assert rejection_notification.status == NotificationStatus.PENDING
            assert "rifiutata" in rejection_notification.title.lower()
            assert "Not qualified at this time" in rejection_notification.message
            assert rejection_notification.priority == NotificationPriority.NORMAL

    def test_admin_approval_notifies_requester(self, app, client):
        """Test that when admin approves a request, the requester gets notified."""
        with app.app_context():
            # Player makes venue manager request
            request = VenueManagerRequestService.create_request(
                user_id=self.player.id,
                venue_id=self.test_venue.id,
                notes="Please approve my request"
            )
            
            # Clear existing notifications to focus on approval notification
            Notification.query.delete()
            db.session.commit()
            
            # Admin approves the request
            VenueManagerRequestService.process_request(
                request_id=request.id,
                admin_user=self.admin,
                approve=True,
                notes="Welcome to venue management!"
            )
            
            # Check that player received approval notification
            player_notifications = Notification.query.filter_by(
                user_id=self.player.id,
                notification_type=NotificationType.ACCOUNT_UPDATE
            ).all()
            
            assert len(player_notifications) == 1
            
            approval_notification = player_notifications[0]
            assert approval_notification.status == NotificationStatus.PENDING
            assert "approvata" in approval_notification.title.lower()
            assert "Welcome to venue management!" in approval_notification.message
            assert approval_notification.priority == NotificationPriority.HIGH

    def test_notification_integration_via_web_request(self, app, client):
        """Test notification creation through actual web request (integration test)."""
        with app.app_context():
            # Clear existing notifications
            Notification.query.delete()
            db.session.commit()
            
            # Login as player
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self.player.id)
                sess['_fresh'] = True
                
            # Count admin notifications before request
            initial_count = Notification.query.filter_by(
                user_id=self.admin.id
            ).count()
            
            # Make venue manager request via web form
            response = client.post('/player/request_venue_manager', data={
                'venue_id': self.test_venue.id,
                'notes': 'Web request test'
            }, follow_redirects=True)
            
            # Should redirect successfully
            assert response.status_code == 200
            
            # Check that admin received notification
            final_count = Notification.query.filter_by(
                user_id=self.admin.id
            ).count()
            
            assert final_count == initial_count + 1
            
            # Verify the notification
            new_notification = Notification.query.filter_by(
                user_id=self.admin.id,
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
            ).order_by(Notification.created_at.desc()).first()
            
            assert new_notification is not None
            assert "Test Venue Notifications" in new_notification.title
            assert self.player.username in new_notification.message

    def teardown_method(self):
        """Clean up after each test."""
        # Database cleanup is handled by test fixtures
        pass