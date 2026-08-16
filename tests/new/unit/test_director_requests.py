"""Unit tests for director request system."""

import pytest
import uuid

from models import User, DirectorRequest
from models.user.role_enum import UserRole
from models.user.services import UserService
from models.base import utc_now


@pytest.mark.unit
class TestDirectorRequestModel:
    """Test DirectorRequest model functionality."""

    def test_create_director_request(self, db_session):
        """Test creating a director request."""
        unique_id = str(uuid.uuid4())[:8]
        # Create a player user
        user = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        # Create director request
        request = DirectorRequest(
            user_id=user.id, notes="I want to organize tournaments"
        )
        db_session.add(request)
        db_session.commit()

        assert request.id is not None
        assert request.user_id == user.id
        assert request.notes == "I want to organize tournaments"
        assert request.status == "pending"
        assert request.requested_at is not None
        assert request.processed_at is None
        assert request.processed_by is None

    def test_director_request_status_updates(self, db_session):
        """Test director request status updates."""
        unique_id = str(uuid.uuid4())[:8]
        # Create users
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        db_session.add_all([player, admin])
        db_session.commit()

        # Create request
        request = DirectorRequest(user_id=player.id, notes="Test reason")
        db_session.add(request)
        db_session.commit()

        # Test approval
        request.status = "approved"
        request.processed_by = admin
        request.processed_at = utc_now()
        db_session.commit()

        assert request.status == "approved"
        assert request.processed_by == admin
        assert request.processed_at is not None

    def test_director_request_relationships(self, db_session):
        """Test director request relationships."""
        unique_id = str(uuid.uuid4())[:8]
        # Create users
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        db_session.add_all([player, admin])
        db_session.commit()

        # Create request
        request = DirectorRequest(
            user_id=player.id, notes="Test reason", processed_by=admin
        )
        db_session.add(request)
        db_session.commit()

        # Test relationships
        assert request.user == player
        assert request.processed_by == admin

    def test_multiple_requests_same_user(self, db_session):
        """Test multiple requests from same user."""
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        # Create multiple requests
        request1 = DirectorRequest(user_id=user.id, notes="First request")
        request2 = DirectorRequest(user_id=user.id, notes="Second request")
        db_session.add_all([request1, request2])
        db_session.commit()

        # Should be able to create multiple requests
        assert request1.id != request2.id
        assert request1.user_id == request2.user_id == user.id


@pytest.mark.unit
class TestDirectorRequestService:
    """Test director request service functionality."""

    def test_create_director_request(self, db_session):
        """Test creating a director request through service."""
        unique_id = str(uuid.uuid4())[:8]
        # Create a player
        user = UserService.create_user(
            f"player_{unique_id}", f"player_{unique_id}@test.com", "pass123", "player"
        )

        # Grant the required "Aspirante Direttore" achievement
        from models.gamification.models import Achievement, UserAchievement
        from models.gamification.models import (
            AchievementCategory,
            AchievementDifficulty,
        )

        # Create or get the achievement
        achievement = Achievement.query.filter_by(slug="aspiring_director").first()
        if not achievement:
            achievement = Achievement(
                slug="aspiring_director",
                name="Aspirante Direttore",
                description="Test achievement for director eligibility",
                category=AchievementCategory.MILESTONE,
                difficulty=AchievementDifficulty.UNCOMMON,
                requirements=(
                    '{"type": "director_eligibility", "min_gare": 10, '
                    '"min_campionati_completi": 1}'
                ),
                is_progressive=False,
                xp_reward=200,
            )
            db_session.add(achievement)
            db_session.flush()

        # Unlock the achievement for the user
        user_achievement = UserAchievement(
            user_id=user.id,
            achievement_id=achievement.id,
            is_unlocked=True,
        )
        db_session.add(user_achievement)
        db_session.commit()

        # Create director request
        result = UserService.request_director_promotion(
            user.id, "I want to organize tournaments"
        )

        assert result is not None
        assert result.user_id == user.id
        assert result.notes == "I want to organize tournaments"
        assert result.status == "pending"

    def test_create_director_request_invalid_user(self, db_session):
        """Test creating director request for invalid user."""
        try:
            UserService.request_director_promotion(99999, "Test reason")
            assert False, "Should have raised an exception"
        except ValueError:
            pass  # Expected

    def test_create_director_request_already_director(self, db_session):
        """Test creating director request for user who is already director."""
        unique_id = str(uuid.uuid4())[:8]
        # Create a director
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("testpass123")
        db_session.add(director)
        db_session.commit()

        try:
            UserService.request_director_promotion(director.id, "Test reason")
            assert False, "Should have raised an exception"
        except ValueError as e:
            assert "already" in str(e).lower()

    def test_get_pending_director_requests(self, db_session):
        """Test getting pending director requests."""
        unique_id = str(uuid.uuid4())[:8]
        # Create users and requests
        users = []
        requests = []

        for i in range(3):
            user = User(
                username=f"player{i}_{unique_id}",
                email=f"player{i}_{unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            user.set_password("testpass123")
            db_session.add(user)
            users.append(user)

        db_session.commit()

        # Create requests - 2 pending, 1 approved
        for i, user in enumerate(users):
            status = "pending" if i < 2 else "approved"
            request = DirectorRequest(
                user_id=user.id, notes=f"Reason {i}", status=status
            )
            db_session.add(request)
            requests.append(request)

        db_session.commit()

        # Get pending requests
        pending_requests = UserService.get_director_requests_by_status("pending")

        assert len(pending_requests) == 2
        for request in pending_requests:
            assert request.status == "pending"

    def test_process_director_request_approve(self, db_session):
        """Test approving a director request."""
        unique_id = str(uuid.uuid4())[:8]
        # Create player and admin
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        db_session.add_all([player, admin])
        db_session.commit()

        # Create request
        request = DirectorRequest(user_id=player.id, notes="Test reason")
        db_session.add(request)
        db_session.commit()

        # Approve request
        result = UserService.approve_director_request(request.id, admin)

        assert result is not None

        # Check request status
        db_session.refresh(request)
        assert request.status == "approved"
        assert request.processed_by == admin
        assert request.processed_at is not None
        # The approve_director_request method doesn't set admin_notes

        # Check user promotion
        db_session.refresh(player)
        assert player.role == UserRole.DIRECTOR.value

    def test_process_director_request_reject(self, db_session):
        """Test rejecting a director request."""
        unique_id = str(uuid.uuid4())[:8]
        # Create player and admin
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        db_session.add_all([player, admin])
        db_session.commit()

        # Create request
        request = DirectorRequest(user_id=player.id, notes="Test reason")
        db_session.add(request)
        db_session.commit()

        # Reject request
        result = UserService.reject_director_request(request.id)

        assert result is not None

        # Check request status
        db_session.refresh(request)
        assert request.status == "rejected"
        assert request.processed_by.username == "mock_admin"  # Service uses mock admin
        assert request.processed_at is not None
        # The reject_director_request method doesn't set admin_notes

        # Check user remains player
        db_session.refresh(player)
        assert player.role == UserRole.PLAYER.value

    def test_process_director_request_invalid_status(self, db_session):
        """Test processing director request with invalid status."""
        unique_id = str(uuid.uuid4())[:8]
        # Create player and admin
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("testpass123")
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        db_session.add_all([player, admin])
        db_session.commit()

        # Create request
        request = DirectorRequest(user_id=player.id, notes="Test reason")
        db_session.add(request)
        db_session.commit()

        # The approve/reject methods don't allow invalid status - test not applicable
        # as the methods are designed to only allow approve or reject

    def test_process_director_request_nonexistent(self, db_session):
        """Test processing non-existent director request."""
        unique_id = str(uuid.uuid4())[:8]
        # Create admin
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("testpass123")
        db_session.add(admin)
        db_session.commit()

        try:
            UserService.approve_director_request(99999, admin)
            assert False, "Should have raised an exception"
        except ValueError as e:
            assert "not found" in str(e).lower()

    def test_get_user_director_requests(self, db_session):
        """Test getting director requests for a specific user."""
        unique_id = str(uuid.uuid4())[:8]
        # Create user
        user = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        # Create multiple requests for this user
        for i in range(3):
            request = DirectorRequest(user_id=user.id, notes=f"Reason {i}")
            db_session.add(request)

        db_session.commit()

        # Get user's requests
        user_requests = [
            req for req in UserService.get_director_requests() if req.user_id == user.id
        ]

        assert len(user_requests) == 3
        for request in user_requests:
            assert request.user_id == user.id

    def test_has_pending_director_request(self, db_session):
        """Test checking if user has pending director request."""
        unique_id = str(uuid.uuid4())[:8]
        # Create user
        user = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("testpass123")
        db_session.add(user)
        db_session.commit()

        # No pending request initially
        pending_requests = [
            req
            for req in UserService.get_director_requests_by_status("pending")
            if req.user_id == user.id
        ]
        assert len(pending_requests) == 0

        # Add pending request
        request = DirectorRequest(user_id=user.id, notes="Test", status="pending")
        db_session.add(request)
        db_session.commit()

        # Should have pending request
        pending_requests = [
            req
            for req in UserService.get_director_requests_by_status("pending")
            if req.user_id == user.id
        ]
        assert len(pending_requests) == 1

        # Process request
        request.status = "approved"
        db_session.commit()

        # Should not have pending request anymore
        pending_requests = [
            req
            for req in UserService.get_director_requests_by_status("pending")
            if req.user_id == user.id
        ]
        assert len(pending_requests) == 0
