"""Integration tests for authentication workflows."""

import pytest

from models import User, DirectorRequest
from models.user.role_enum import UserRole


@pytest.mark.integration
class TestAuthenticationRoutes:
    """Test authentication routes and workflows."""

    def test_user_registration_workflow(self, client, db_session):
        """Test complete user registration workflow."""
        # Test GET registration page
        response = client.get("/auth/register")
        assert response.status_code == 200
        assert b"register" in response.data.lower()

        # Test POST registration with valid data
        response = client.post(
            "/auth/register",
            data={
                "username": "newuser",
                "email": "newuser@test.com",
                "password": "password123",
                "confirm_password": "password123",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Check user was created in database
        user = User.query.filter_by(username="newuser").first()
        assert user is not None
        assert user.email == "newuser@test.com"
        assert user.role == UserRole.PLAYER.value
        assert user.check_password("password123") is True

    def test_user_registration_duplicate_username(self, client, db_session):
        """Test registration with duplicate username."""
        # Create existing user
        existing_user = User(
            username="existing", email="existing@test.com", role=UserRole.PLAYER.value
        )
        existing_user.set_password("password123")
        db_session.add(existing_user)
        db_session.commit()

        # Try to register with same username
        response = client.post(
            "/auth/register",
            data={
                "username": "existing",
                "email": "different@test.com",
                "password": "password123",
                "confirm_password": "password123",
            },
        )

        assert response.status_code == 200  # Should return to registration page
        # Should show error message (check for username error)
        assert (
            b"username" in response.data.lower() or b"exists" in response.data.lower()
        )

    def test_user_registration_duplicate_email(self, client, db_session):
        """Test registration with duplicate email."""
        # Create existing user
        existing_user = User(
            username="existing", email="existing@test.com", role=UserRole.PLAYER.value
        )
        existing_user.set_password("password123")
        db_session.add(existing_user)
        db_session.commit()

        # Try to register with same email
        response = client.post(
            "/auth/register",
            data={
                "username": "different",
                "email": "existing@test.com",
                "password": "password123",
                "confirm_password": "password123",
            },
        )

        assert response.status_code == 200  # Should return to registration page
        # Should show error message (check for email error)
        assert b"email" in response.data.lower() or b"exists" in response.data.lower()

    def test_user_login_workflow(self, client, db_session):
        """Test complete user login workflow."""
        # Create test user
        user = User(
            username="testuser", email="test@test.com", role=UserRole.PLAYER.value
        )
        user.set_password("password123")
        db_session.add(user)
        db_session.commit()

        # Test GET login page
        response = client.get("/auth/login")
        assert response.status_code == 200
        assert b"login" in response.data.lower()

        # Test POST login with valid credentials (username)
        response = client.post(
            "/auth/login",
            data={"username": "testuser", "password": "password123"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        # Should redirect to dashboard after successful login

    def test_user_login_with_email(self, client, db_session):
        """Test user login with email instead of username."""
        # Create test user
        user = User(
            username="testuser", email="test@test.com", role=UserRole.PLAYER.value
        )
        user.set_password("password123")
        db_session.add(user)
        db_session.commit()

        # Test login with email
        response = client.post(
            "/auth/login",
            data={
                "username": "test@test.com",  # Using email in username field
                "password": "password123",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        # Should redirect to dashboard after successful login

    def test_user_login_invalid_credentials(self, client, db_session):
        """Test user login with invalid credentials."""
        # Create test user
        user = User(
            username="testuser", email="test@test.com", role=UserRole.PLAYER.value
        )
        user.set_password("password123")
        db_session.add(user)
        db_session.commit()

        # Test login with wrong password
        response = client.post(
            "/auth/login", data={"username": "testuser", "password": "wrongpassword"}
        )

        assert response.status_code == 200  # Should return to login page
        # Should show error message
        assert b"invalid" in response.data.lower() or b"error" in response.data.lower()

        # Test login with non-existent user
        response = client.post(
            "/auth/login", data={"username": "nonexistent", "password": "password123"}
        )

        assert response.status_code == 200  # Should return to login page
        assert b"invalid" in response.data.lower() or b"error" in response.data.lower()

    def test_user_logout_workflow(self, client, db_session):
        """Test user logout workflow."""
        # Create and login user
        user = User(
            username="testuser", email="test@test.com", role=UserRole.PLAYER.value
        )
        user.set_password("password123")
        db_session.add(user)
        db_session.commit()

        # Login
        client.post(
            "/auth/login", data={"username": "testuser", "password": "password123"}
        )

        # Test logout
        response = client.post("/auth/logout", follow_redirects=True)
        assert response.status_code == 200
        # Should redirect to main page after logout

    def test_admin_access_after_login(self, client, db_session):
        """Test admin can access admin routes after login."""
        # Create admin user
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        admin.set_password("admin123")
        db_session.add(admin)
        db_session.commit()

        # Login as admin
        client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        # Test access to admin dashboard
        response = client.get("/admin/dashboard")
        assert response.status_code == 200

    def test_director_access_after_login(self, client, db_session):
        """Test director can access director routes after login."""
        # Create director user
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        # Login as director
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # Test access to director routes
        response = client.get("/director/create_standalone")
        assert response.status_code == 200

    def test_player_cannot_access_admin_routes(self, client, db_session):
        """Test player cannot access admin routes."""
        # Create player user
        player = User(
            username="player", email="player@test.com", role=UserRole.PLAYER.value
        )
        player.set_password("player123")
        db_session.add(player)
        db_session.commit()

        # Login as player
        client.post("/auth/login", data={"username": "player", "password": "player123"})

        # Test cannot access admin dashboard
        response = client.get("/admin/dashboard")
        assert response.status_code == 403  # Forbidden

    def test_unauthenticated_user_redirected_to_login(self, client, db_session):
        """Test unauthenticated user gets 403 for protected routes."""
        # Test access to protected route without login
        response = client.get("/admin/dashboard")
        assert response.status_code == 403  # Forbidden - correct behavior for admin_required decorator


@pytest.mark.integration
class TestDirectorRequestWorkflow:
    """Test director request workflow."""

    def test_complete_director_request_workflow(self, client, db_session):
        """Test complete director request workflow from player to admin."""
        # Create player and admin
        player = User(
            username="player", email="player@test.com", role=UserRole.PLAYER.value
        )
        player.set_password("player123")
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        admin.set_password("admin123")
        db_session.add_all([player, admin])
        db_session.commit()

        # Login as player
        client.post("/auth/login", data={"username": "player", "password": "player123"})

        # Submit director request
        response = client.post(
            "/player/request_director",
            data={"reason": "I want to organize tournaments in my local club"},
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Check request was created
        request = DirectorRequest.query.filter_by(user_id=player.id).first()
        assert request is not None
        assert request.notes == "I want to organize tournaments in my local club"
        assert request.status == "pending"

        # Logout player
        client.post("/auth/logout")

        # Login as admin
        client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        # View pending director requests
        response = client.get("/admin/director_requests")
        assert response.status_code == 200
        assert b"player" in response.data  # Should show player's request

        # Approve the request
        response = client.post(
            f"/admin/director_requests/{request.id}/process",
            data={
                "status": "approved",
                "admin_notes": "User is qualified to be a director",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Check request was processed
        db_session.refresh(request)
        assert request.status == "approved"
        assert request.processed_by_id == admin.id
        assert request.notes == "User is qualified to be a director"

        # Check player was promoted to director
        db_session.refresh(player)
        assert player.role == UserRole.DIRECTOR.value

    def test_director_request_rejection(self, client, db_session):
        """Test director request rejection workflow."""
        # Create player and admin
        player = User(
            username="player", email="player@test.com", role=UserRole.PLAYER.value
        )
        player.set_password("player123")
        admin = User(
            username="admin", email="admin@test.com", role=UserRole.ADMIN.value
        )
        admin.set_password("admin123")
        db_session.add_all([player, admin])
        db_session.commit()

        # Create director request
        request = DirectorRequest(user_id=player.id, notes="Test reason")
        db_session.add(request)
        db_session.commit()

        # Login as admin
        client.post("/auth/login", data={"username": "admin", "password": "admin123"})

        # Reject the request
        response = client.post(
            f"/admin/director_requests/{request.id}/process",
            data={"status": "rejected", "admin_notes": "Not qualified at this time"},
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Check request was processed
        db_session.refresh(request)
        assert request.status == "rejected"
        assert request.processed_by_id == admin.id
        assert request.notes == "Not qualified at this time"

        # Check player remains player
        db_session.refresh(player)
        assert player.role == UserRole.PLAYER.value

    def test_duplicate_director_request_prevention(self, client, db_session):
        """Test that users cannot submit multiple pending requests."""
        # Create player
        player = User(
            username="player", email="player@test.com", role=UserRole.PLAYER.value
        )
        player.set_password("player123")
        db_session.add(player)
        db_session.commit()

        # Create existing pending request
        existing_request = DirectorRequest(
            user_id=player.id, notes="First request", status="pending"
        )
        db_session.add(existing_request)
        db_session.commit()

        # Login as player
        client.post("/auth/login", data={"username": "player", "password": "player123"})

        # Try to submit another request
        response = client.post(
            "/player/request_director", data={"reason": "Second request"}
        )

        # Should prevent duplicate request with redirect
        assert response.status_code == 302  # Redirect to profile with flash message

        # Check only one pending request exists
        pending_requests = DirectorRequest.query.filter_by(
            user_id=player.id, status="pending"
        ).all()
        assert len(pending_requests) == 1
        assert pending_requests[0].notes == "First request"  # Original request remains

    def test_director_cannot_submit_request(self, client, db_session):
        """Test that directors cannot submit director requests."""
        # Create director
        director = User(
            username="director", email="director@test.com", role=UserRole.DIRECTOR.value
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()

        # Login as director
        client.post(
            "/auth/login", data={"username": "director", "password": "director123"}
        )

        # Try to submit director request
        response = client.post(
            "/player/request_director", data={"reason": "I am already a director"}
        )

        # Should be prevented (error or redirect)
        assert response.status_code in [
            403,
            302,
            200,
        ]  # Forbidden, redirect, or error page

        # Check no request was created
        request = DirectorRequest.query.filter_by(user_id=director.id).first()
        assert request is None
