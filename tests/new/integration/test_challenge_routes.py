"""
Integration tests for Challenge routes
"""

import pytest
import json
from models import db, User, Challenge, ChallengeFavorite
from flask import url_for


class TestChallengeRoutes:
    """Test Challenge route endpoints."""

    @pytest.fixture
    def admin_user(self, app):
        """Create an admin user."""
        with app.app_context():
            user = User(
                username="admin",
                email="admin@example.com",
                password_hash="admin_password_hash",
                role="admin",
            )
            db.session.add(user)
            db.session.commit()
            yield user
            db.session.delete(user)
            db.session.commit()

    @pytest.fixture
    def director_user(self, app):
        """Create a director user."""
        with app.app_context():
            user = User(
                username="director",
                email="director@example.com",
                password_hash="director_password_hash",
                role="director",
            )
            db.session.add(user)
            db.session.commit()
            yield user
            db.session.delete(user)
            db.session.commit()

    @pytest.fixture
    def player_user(self, app):
        """Create a player user."""
        with app.app_context():
            user = User(
                username="player",
                email="player@example.com",
                password_hash="player_password_hash",
                role="player",
            )
            db.session.add(user)
            db.session.commit()
            yield user
            db.session.delete(user)
            db.session.commit()

    @pytest.fixture
    def test_challenge(self, app, director_user):
        """Create a test challenge."""
        with app.app_context():
            challenge = Challenge(
                name="Test Challenge",
                description="Test description for integration tests",
                min_score=0,
                max_score=100,
                created_by_id=director_user.id,
                is_active=True,
            )
            db.session.add(challenge)
            db.session.commit()
            yield challenge
            db.session.delete(challenge)
            db.session.commit()

    def test_challenge_catalog_access(self, client, admin_user):
        """Test challenge catalog access."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)

        response = client.get("/challenge/")
        assert response.status_code == 200
        assert b"Challenge" in response.data

    def test_challenge_catalog_requires_login(self, client):
        """Test that challenge catalog requires login."""
        response = client.get("/challenge/")
        assert response.status_code == 302  # Redirect to login

    def test_create_challenge_get(self, client, director_user):
        """Test GET request to create challenge form."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(director_user.id)

        response = client.get("/challenge/create")
        assert response.status_code == 200
        assert b"Crea Nuova Challenge" in response.data

    def test_create_challenge_post(self, client, director_user):
        """Test POST request to create challenge."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(director_user.id)

        response = client.post(
            "/challenge/create",
            data={
                "name": "New Test Challenge",
                "description": "Test challenge created via POST",
                "min_score": "0",
                "max_score": "100",
                "pass_fail_only": "false",
            },
        )

        # Should redirect after successful creation
        assert response.status_code == 302

        # Check challenge was created
        challenge = Challenge.query.filter_by(name="New Test Challenge").first()
        assert challenge is not None
        assert challenge.created_by_id == director_user.id

        # Cleanup
        db.session.delete(challenge)
        db.session.commit()

    def test_create_challenge_requires_director(self, client, player_user):
        """Test that creating challenges requires director role."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)

        response = client.get("/challenge/create")
        assert response.status_code == 403  # Forbidden

    def test_challenge_detail(self, client, admin_user, test_challenge):
        """Test challenge detail view."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)

        response = client.get(f"/challenge/{test_challenge.id}")
        assert response.status_code == 200
        assert test_challenge.name.encode() in response.data

    def test_challenge_detail_ajax(self, client, admin_user, test_challenge):
        """Test AJAX challenge detail request."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)

        response = client.get(
            f"/challenge/{test_challenge.id}",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        # Should return partial HTML for modal
        assert b"Dettagli Challenge" in response.data

    def test_start_attempt_get(self, client, player_user, test_challenge):
        """Test GET request to start attempt page."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)

        response = client.get(f"/challenge/{test_challenge.id}/attempt")
        assert response.status_code == 200
        assert b"Inizia Challenge" in response.data

    def test_start_attempt_post(self, client, player_user, test_challenge):
        """Test POST request to start attempt."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)

        response = client.post(f"/challenge/{test_challenge.id}/attempt")

        # Should redirect to attempt detail
        assert response.status_code == 302
        assert "/challenge/attempt/" in response.location

    def test_toggle_favorite(self, client, player_user, test_challenge):
        """Test favorite toggle functionality."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)

        # Toggle favorite on
        response = client.post(
            f"/challenge/{test_challenge.id}/favorite",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["is_favorite"] is True

        # Check favorite exists
        favorite = ChallengeFavorite.query.filter_by(
            user_id=player_user.id, challenge_id=test_challenge.id
        ).first()
        assert favorite is not None

        # Toggle favorite off
        response = client.post(
            f"/challenge/{test_challenge.id}/favorite",
            headers={"Content-Type": "application/json"},
        )

        data = json.loads(response.data)
        assert data["success"] is True
        assert data["is_favorite"] is False

    def test_edit_challenge_get(self, client, director_user, test_challenge):
        """Test GET request to edit challenge."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(director_user.id)

        response = client.get(f"/challenge/{test_challenge.id}/edit")
        assert response.status_code == 200
        assert b"Modifica Challenge" in response.data
        assert test_challenge.name.encode() in response.data

    def test_edit_challenge_post(self, client, director_user, test_challenge):
        """Test POST request to edit challenge."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(director_user.id)

        response = client.post(
            f"/challenge/{test_challenge.id}/edit",
            data={
                "name": "Updated Challenge Name",
                "description": "Updated description",
                "is_active": "true",
            },
        )

        # Should redirect after successful update
        assert response.status_code == 302

        # Check challenge was updated
        db.session.refresh(test_challenge)
        assert test_challenge.name == "Updated Challenge Name"
        assert test_challenge.description == "Updated description"

    def test_edit_challenge_requires_permission(
        self, client, player_user, test_challenge
    ):
        """Test that editing requires proper permissions."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)

        response = client.get(f"/challenge/{test_challenge.id}/edit")
        assert response.status_code == 403  # Forbidden

    def test_delete_challenge(self, client, director_user, test_challenge):
        """Test challenge deletion (soft delete)."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(director_user.id)

        response = client.post(
            f"/challenge/{test_challenge.id}/delete",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True

        # Check challenge is soft deleted (inactive)
        db.session.refresh(test_challenge)
        assert test_challenge.is_active is False

    def test_delete_challenge_requires_permission(
        self, client, player_user, test_challenge
    ):
        """Test that deletion requires proper permissions."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)

        response = client.post(f"/challenge/{test_challenge.id}/delete")
        assert response.status_code == 403  # Forbidden

    def test_challenge_not_found(self, client, admin_user):
        """Test 404 handling for non-existent challenge."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin_user.id)

        response = client.get("/challenge/99999")
        assert response.status_code == 404

    def test_inactive_challenge_attempt(self, client, player_user, test_challenge):
        """Test that inactive challenges cannot be attempted."""
        # Make challenge inactive
        test_challenge.is_active = False
        db.session.commit()

        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)

        response = client.get(f"/challenge/{test_challenge.id}/attempt")

        # Should redirect with warning
        assert response.status_code == 302
        assert "/challenge/" in response.location

        # Restore for cleanup
        test_challenge.is_active = True
        db.session.commit()


class TestChallengeAttemptRoutes:
    """Test Challenge attempt route endpoints."""

    @pytest.fixture
    def player_user(self, app):
        """Create a player user."""
        with app.app_context():
            user = User(
                username="player",
                email="player@example.com",
                password_hash="player_password_hash",
                role="player",
            )
            db.session.add(user)
            db.session.commit()
            yield user
            db.session.delete(user)
            db.session.commit()

    @pytest.fixture
    def test_challenge(self, app):
        """Create a test challenge."""
        with app.app_context():
            challenge = Challenge(
                name="Test Challenge",
                description="Test description",
                min_score=0,
                max_score=100,
                is_active=True,
            )
            db.session.add(challenge)
            db.session.commit()
            yield challenge
            db.session.delete(challenge)
            db.session.commit()

    @pytest.fixture
    def test_attempt(self, app, player_user, test_challenge):
        """Create a test challenge attempt."""
        with app.app_context():
            from models.challenge.services import ChallengeService

            attempt = ChallengeService.start_challenge_attempt(
                user_id=player_user.id, challenge_id=test_challenge.id
            )
            yield attempt
            db.session.delete(attempt)
            db.session.commit()

    def test_attempt_detail(self, client, player_user, test_attempt):
        """Test attempt detail view."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)

        response = client.get(f"/challenge/attempt/{test_attempt.id}")
        assert response.status_code == 200
        assert b"Tentativo" in response.data

    def test_complete_attempt_score(self, client, player_user, test_attempt):
        """Test completing an attempt with score."""
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player_user.id)

        response = client.post(
            f"/challenge/attempt/{test_attempt.id}/complete",
            data={"score": "85", "notes": "Good attempt"},
        )

        # Should redirect after completion
        assert response.status_code == 302

        # Check attempt was completed
        db.session.refresh(test_attempt)
        assert test_attempt.completed is True
        assert test_attempt.score == 85
        assert test_attempt.notes == "Good attempt"

    def test_complete_attempt_pass_fail(self, client, player_user, app):
        """Test completing a pass/fail attempt."""
        with app.app_context():
            # Create pass/fail challenge
            pass_fail_challenge = Challenge(
                name="Pass/Fail Challenge",
                description="Pass or fail",
                pass_fail_only=True,
                min_score=0,
                max_score=1,
                is_active=True,
            )
            db.session.add(pass_fail_challenge)
            db.session.commit()

            # Create attempt
            from models.challenge.services import ChallengeService

            attempt = ChallengeService.start_challenge_attempt(
                user_id=player_user.id, challenge_id=pass_fail_challenge.id
            )

            with client.session_transaction() as sess:
                sess["_user_id"] = str(player_user.id)

            response = client.post(
                f"/challenge/attempt/{attempt.id}/complete",
                data={"passed": "true", "notes": "Passed successfully"},
            )

            # Should redirect after completion
            assert response.status_code == 302

            # Check attempt was completed
            db.session.refresh(attempt)
            assert attempt.completed is True
            assert attempt.passed is True
            assert attempt.notes == "Passed successfully"

            # Cleanup
            db.session.delete(attempt)
            db.session.delete(pass_fail_challenge)
            db.session.commit()

    def test_complete_attempt_access_control(self, client, app, test_attempt):
        """Test that users can only complete their own attempts."""
        with app.app_context():
            # Create another user
            other_user = User(
                username="other",
                email="other@example.com",
                password_hash="other_password_hash",
                role="player",
            )
            db.session.add(other_user)
            db.session.commit()

            with client.session_transaction() as sess:
                sess["_user_id"] = str(other_user.id)

            response = client.post(
                f"/challenge/attempt/{test_attempt.id}/complete", data={"score": "50"}
            )

            # Should be forbidden
            assert response.status_code in [
                403,
                404,
            ]  # Depending on security implementation

            # Cleanup
            db.session.delete(other_user)
            db.session.commit()
