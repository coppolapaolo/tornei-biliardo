"""
Integration test for venue manager request flow through both UI paths.

Tests that player and director can request venue management through:
1. Venues list page (Sale Biliardo) - modal forms for each venue
2. Venue detail page - single modal form for the specific venue

Both paths should result in admin receiving notification.

Author: Venue Management UI Integration Test
Created: 2025-09-11
"""

import pytest
from models.base import db
from models.user.models import User
from models.user.services import VenueManagerRequestService  
from models.notification.models import (
    Notification,
    NotificationType,
    NotificationPriority,
    NotificationStatus
)
from models import BilliardHall
from models.location.services import LocationService


def test_player_venue_manager_request_from_venues_list_page(app, client):
    """Test that a player can request venue management from venues list page and admin receives notification."""
    with app.app_context():
        # Clear existing data
        Notification.query.delete()
        db.session.commit()
        
        # Create test users
        admin = User(username="test_admin_ui", email="admin_ui@test.com", role="admin")
        admin.set_password("password")
        db.session.add(admin)
        
        player = User(username="test_player_ui", email="player_ui@test.com", role="player")
        player.set_password("password")
        db.session.add(player)
        
        db.session.commit()
        
        # Create test venue
        test_venue = LocationService.create_billiard_hall(
            name="UI Test Venue List",
            address="123 UI List Street",
            city="UI List City"
        )
        
        # Count initial admin notifications
        initial_notifications = Notification.query.filter_by(
            user_id=admin.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).count()
        
        # Login as player
        with client.session_transaction() as sess:
            sess['_user_id'] = str(player.id)
            sess['_fresh'] = True
        
        # Navigate to venues list page to verify access
        venues_response = client.get('/admin/venues')
        assert venues_response.status_code == 200
        
        # Make venue manager request via form (simulating modal form submission from venues list)
        request_response = client.post('/player/request_venue_manager', data={
            'venue_id': test_venue.id,
            'notes': 'Request from venues list page modal'
        }, follow_redirects=True)
        
        # Should redirect successfully
        assert request_response.status_code == 200
        
        # Check that admin received notification
        final_notifications = Notification.query.filter_by(
            user_id=admin.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).count()
        
        assert final_notifications == initial_notifications + 1
        
        # Verify notification content
        new_notification = Notification.query.filter_by(
            user_id=admin.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).order_by(Notification.created_at.desc()).first()
        
        assert new_notification is not None
        assert new_notification.status == NotificationStatus.PENDING
        assert "UI Test Venue List" in new_notification.title
        assert "Richiesta Gestore Sala" in new_notification.title
        assert player.username in new_notification.message
        assert new_notification.priority == NotificationPriority.NORMAL


def test_director_venue_manager_request_from_venue_detail_page(app, client):
    """Test that a director can request venue management from venue detail page and admin receives notification."""
    with app.app_context():
        # Clear existing data
        Notification.query.delete()
        db.session.commit()
        
        # Create test users
        admin = User(username="test_admin_detail", email="admin_detail@test.com", role="admin")
        admin.set_password("password")
        db.session.add(admin)
        
        director = User(username="test_director_detail", email="director_detail@test.com", role="director")
        director.set_password("password")
        db.session.add(director)
        
        db.session.commit()
        
        # Create test venue
        test_venue = LocationService.create_billiard_hall(
            name="UI Test Venue Detail",
            address="456 UI Detail Street",
            city="UI Detail City"
        )
        
        # Count initial admin notifications
        initial_notifications = Notification.query.filter_by(
            user_id=admin.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).count()
        
        # Login as director
        with client.session_transaction() as sess:
            sess['_user_id'] = str(director.id)
            sess['_fresh'] = True
        
        # Navigate to venue detail page to verify access
        detail_response = client.get(f'/admin/venues/{test_venue.id}')
        assert detail_response.status_code == 200
        
        # Make venue manager request via form (simulating modal form submission from detail page)
        request_response = client.post('/player/request_venue_manager', data={
            'venue_id': test_venue.id,
            'notes': 'Request from venue detail page modal - director experience in tournament organization'
        }, follow_redirects=True)
        
        # Should redirect successfully
        assert request_response.status_code == 200
        
        # Check that admin received notification
        final_notifications = Notification.query.filter_by(
            user_id=admin.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).count()
        
        assert final_notifications == initial_notifications + 1
        
        # Verify notification content
        new_notification = Notification.query.filter_by(
            user_id=admin.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).order_by(Notification.created_at.desc()).first()
        
        assert new_notification is not None
        assert new_notification.status == NotificationStatus.PENDING
        assert "UI Test Venue Detail" in new_notification.title
        assert "Richiesta Gestore Sala" in new_notification.title
        assert director.username in new_notification.message
        assert new_notification.priority == NotificationPriority.NORMAL


def test_venues_list_page_request_path(app, client):
    """Test that venue manager request from venues list page works and notifies admin."""
    with app.app_context():
        # Clear existing data
        Notification.query.delete()
        db.session.commit()
        
        # Create test users
        admin = User(username="test_admin_list_path", email="admin_list_path@test.com", role="admin")
        admin.set_password("password")
        db.session.add(admin)
        
        player = User(username="test_player_list_path", email="player_list_path@test.com", role="player")
        player.set_password("password")
        db.session.add(player)
        
        db.session.commit()
        
        # Create venue
        venue = LocationService.create_billiard_hall(
            name="Venues List Path Test",
            address="List Path Street",
            city="List Path City"
        )
        
        # Login as player
        with client.session_transaction() as sess:
            sess['_user_id'] = str(player.id)
            sess['_fresh'] = True
        
        # Simulate request from venues list page modal
        response = client.post('/player/request_venue_manager', data={
            'venue_id': venue.id,
            'notes': 'Request from venues list page modal form'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify admin received notification
        notifications = Notification.query.filter_by(
            user_id=admin.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).count()
        assert notifications == 1
        
        # Verify request was created
        from models.user.models import VenueManagerRequest
        request = VenueManagerRequest.query.filter_by(
            user_id=player.id,
            venue_id=venue.id
        ).first()
        assert request is not None
        assert request.status == "pending"
        assert "venues list page modal" in request.notes


def test_venue_detail_page_request_path(app, client):
    """Test that venue manager request from venue detail page works and notifies admin."""
    with app.app_context():
        # Clear existing data
        Notification.query.delete()
        db.session.commit()
        
        # Create test users
        admin = User(username="test_admin_detail_path", email="admin_detail_path@test.com", role="admin")
        admin.set_password("password")
        db.session.add(admin)
        
        director = User(username="test_director_detail_path", email="director_detail_path@test.com", role="director")
        director.set_password("password")
        db.session.add(director)
        
        db.session.commit()
        
        # Create venue
        venue = LocationService.create_billiard_hall(
            name="Venue Detail Path Test",
            address="Detail Path Street", 
            city="Detail Path City"
        )
        
        # Login as director
        with client.session_transaction() as sess:
            sess['_user_id'] = str(director.id)
            sess['_fresh'] = True
        
        # Simulate request from venue detail page modal 
        response = client.post('/player/request_venue_manager', data={
            'venue_id': venue.id,
            'notes': 'Request from venue detail page modal form with director experience'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify admin received notification
        notifications = Notification.query.filter_by(
            user_id=admin.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).count()
        assert notifications == 1
        
        # Verify request was created
        from models.user.models import VenueManagerRequest
        request = VenueManagerRequest.query.filter_by(
            user_id=director.id,
            venue_id=venue.id
        ).first()
        assert request is not None
        assert request.status == "pending"
        assert "venue detail page modal" in request.notes


def test_duplicate_request_handling_through_ui(app, client):
    """Test that duplicate requests are handled gracefully with user-friendly error messages."""
    with app.app_context():
        # Clear existing data
        Notification.query.delete()
        db.session.commit()
        
        # Create test users
        admin = User(username="test_admin_duplicate", email="admin_duplicate@test.com", role="admin")
        admin.set_password("password")
        db.session.add(admin)
        
        player = User(username="test_player_duplicate", email="player_duplicate@test.com", role="player")
        player.set_password("password")
        db.session.add(player)
        
        db.session.commit()
        
        # Create venue
        venue = LocationService.create_billiard_hall(
            name="Duplicate Request Test Venue",
            address="Duplicate Street",
            city="Duplicate City"
        )
        
        # Login as player
        with client.session_transaction() as sess:
            sess['_user_id'] = str(player.id)
            sess['_fresh'] = True
        
        # First request should succeed
        response1 = client.post('/player/request_venue_manager', data={
            'venue_id': venue.id,
            'notes': 'First request should work'
        }, follow_redirects=True)
        
        assert response1.status_code == 200
        # Should contain success message
        assert 'inviata con successo' in response1.get_data(as_text=True).lower()
        
        # Second request should fail gracefully
        response2 = client.post('/player/request_venue_manager', data={
            'venue_id': venue.id,
            'notes': 'Second request should fail'
        }, follow_redirects=True)
        
        assert response2.status_code == 200
        # Should contain error message about pending request
        response_text = response2.get_data(as_text=True).lower()
        assert 'pending request' in response_text or 'richiesta' in response_text
        
        # Verify only one request was created
        from models.user.models import VenueManagerRequest
        requests = VenueManagerRequest.query.filter_by(
            user_id=player.id,
            venue_id=venue.id
        ).all()
        assert len(requests) == 1
        assert requests[0].status == "pending"


def test_admin_cannot_request_venue_management_through_ui(app, client):
    """Test that admin users are properly excluded from venue management requests."""
    with app.app_context():
        # Create test admin
        admin = User(username="test_admin_excluded", email="admin_excluded@test.com", role="admin")
        admin.set_password("password")
        db.session.add(admin)
        db.session.commit()
        
        # Create test venue
        test_venue = LocationService.create_billiard_hall(
            name="Admin Excluded Venue",
            address="Admin Excluded Street",
            city="Admin Excluded City"
        )
        
        # Login as admin
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin.id)
            sess['_fresh'] = True
        
        # Try to make venue manager request
        response = client.post('/player/request_venue_manager', data={
            'venue_id': test_venue.id,
            'notes': 'Admin should not be able to make this request'
        }, follow_redirects=True)
        
        # Should redirect successfully with info message
        assert response.status_code == 200
        
        # Verify no request was created
        from models.user.models import VenueManagerRequest
        requests = VenueManagerRequest.query.filter_by(
            venue_id=test_venue.id,
            user_id=admin.id
        ).all()
        
        assert len(requests) == 0


def test_ui_request_includes_form_notes(app, client):
    """Test that notes from UI forms are properly captured in requests."""
    with app.app_context():
        # Clear existing data
        Notification.query.delete()
        db.session.commit()
        
        # Create test users
        admin = User(username="test_admin_notes", email="admin_notes@test.com", role="admin")
        admin.set_password("password")
        db.session.add(admin)
        
        player = User(username="test_player_notes", email="player_notes@test.com", role="player")
        player.set_password("password")
        db.session.add(player)
        
        db.session.commit()
        
        # Create test venue
        test_venue = LocationService.create_billiard_hall(
            name="UI Notes Venue",
            address="UI Notes Street",
            city="UI Notes City"
        )
        
        # Login as player
        with client.session_transaction() as sess:
            sess['_user_id'] = str(player.id)
            sess['_fresh'] = True
        
        test_notes = "I have 10 years of experience managing billiard halls and tournaments"
        
        # Make request with detailed notes
        client.post('/player/request_venue_manager', data={
            'venue_id': test_venue.id,
            'notes': test_notes
        }, follow_redirects=True)
        
        # Verify request includes notes
        from models.user.models import VenueManagerRequest
        request = VenueManagerRequest.query.filter_by(
            venue_id=test_venue.id,
            user_id=player.id
        ).first()
        
        assert request is not None
        assert request.notes == test_notes
        
        # Verify notification includes user notes context
        notification = Notification.query.filter_by(
            user_id=admin.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT
        ).first()
        
        assert notification is not None
        assert player.username in notification.message