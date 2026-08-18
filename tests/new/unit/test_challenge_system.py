"""
Unit tests for Challenge system implementation
"""

import pytest
import uuid
from models import db, Challenge, ChallengeAttempt, ChallengeFavorite, User
from models.challenge.services import ChallengeService


class TestChallengeService:
    """Test ChallengeService methods."""

    @pytest.fixture
    def test_user(self, app):
        """Create a test user."""
        with app.app_context():
            unique_id = str(uuid.uuid4())[:8]
            user = User(
                username=f"testuser_{unique_id}",
                email="test@example.com",
                role="player",
            )
            user.set_password("testpass123")
            db.session.add(user)
            db.session.commit()
            yield user
            # Niente hard delete: completare un drill crea la riga `UserLevel`
            # (XP), e cancellare l'utente proverebbe ad azzerarne la chiave
            # primaria. È anche la regola del progetto — gli utenti si
            # anonimizzano, non si cancellano. La pulizia la fa comunque
            # `db_session`, che ricrea lo schema a ogni test.

    @pytest.fixture
    def test_challenge(self, app, test_user):
        """Create a test challenge."""
        with app.app_context():
            challenge = Challenge(
                description="Test challenge description for testing purposes",
                image_path="test_image.jpg",
                pass_fail_only=False,
                created_by_id=test_user.id,
                is_active=True,
            )
            db.session.add(challenge)
            db.session.commit()
            yield challenge
            db.session.delete(challenge)
            db.session.commit()

    def test_create_challenge(self, app, test_user):
        """Test challenge creation."""
        with app.app_context():
            challenge = ChallengeService.create_challenge(
                title="Progressione lungo sponda",
                description="New challenge description",
                image_path="test_create.jpg",
                pass_fail_only=False,
                created_by_id=test_user.id,
            )

            assert challenge.id is not None
            assert challenge.get_display_name() == "Progressione lungo sponda"
            assert challenge.description == "New challenge description"
            assert challenge.created_by_id == test_user.id
            assert challenge.is_active is True

            # Cleanup
            db.session.delete(challenge)
            db.session.commit()

    def test_create_challenge_without_name(self, app, test_user):
        """Senza titolo il nome è il progressivo, non le istruzioni troncate."""
        with app.app_context():
            challenge = ChallengeService.create_challenge(
                description="Challenge without name",
                image_path="test_no_name.jpg",
                created_by_id=test_user.id,
            )

            assert challenge.id is not None
            assert challenge.title is None
            assert challenge.get_display_name() == f"Esercizio {challenge.id}"
            assert challenge.description == "Challenge without name"

            # Cleanup
            db.session.delete(challenge)
            db.session.commit()

    def test_get_active_challenges(self, app, test_challenge):
        """Test retrieving active challenges."""
        with app.app_context():
            # Create an inactive challenge
            inactive_challenge = Challenge(
                description="This should not appear",
                image_path="inactive_image.jpg",
                is_active=False,
            )
            db.session.add(inactive_challenge)
            db.session.commit()

            active_challenges = ChallengeService.get_active_challenges()

            # Should only include active challenges
            active_descriptions = [c.description for c in active_challenges]
            assert test_challenge.description in active_descriptions
            assert "This should not appear" not in active_descriptions

            # Cleanup
            db.session.delete(inactive_challenge)
            db.session.commit()

    def test_get_catalog_data(self, app, test_user, test_challenge):
        """Test catalog data structure."""
        with app.app_context():
            # Create a challenge by the test user
            my_challenge = Challenge(
                description="Created by me",
                image_path="my_challenge.jpg",
                created_by_id=test_user.id,
                is_active=True,
            )
            db.session.add(my_challenge)

            # Create a favorite
            favorite = ChallengeFavorite(
                user_id=test_user.id, challenge_id=test_challenge.id
            )
            db.session.add(favorite)
            db.session.commit()

            catalog_data = ChallengeService.get_catalog_data(test_user.id)

            assert "all_challenges" in catalog_data
            assert "my_challenges" in catalog_data
            assert "favorite_challenges" in catalog_data
            assert "user_favorites" in catalog_data

            # Check my challenges
            my_challenge_descriptions = [
                c.description for c in catalog_data["my_challenges"]
            ]
            assert "Created by me" in my_challenge_descriptions

            # Check favorites
            assert test_challenge.id in catalog_data["user_favorites"]
            favorite_descriptions = [
                c.description for c in catalog_data["favorite_challenges"]
            ]
            assert test_challenge.description in favorite_descriptions

            # Cleanup
            db.session.delete(my_challenge)
            db.session.delete(favorite)
            db.session.commit()

    def test_start_challenge_attempt(self, app, test_user, test_challenge):
        """Test starting a challenge attempt."""
        with app.app_context():
            attempt = ChallengeService.start_challenge_attempt(
                user_id=test_user.id, challenge_id=test_challenge.id
            )

            assert attempt.id is not None
            assert attempt.user_id == test_user.id
            assert attempt.challenge_id == test_challenge.id
            assert attempt.completed is False
            assert attempt.attempted_at is not None

            # Cleanup
            db.session.delete(attempt)
            db.session.commit()

    def test_complete_challenge_attempt_with_score(
        self, app, test_user, test_challenge
    ):
        """Test completing a challenge attempt with score."""
        with app.app_context():
            # Start an attempt
            attempt = ChallengeService.start_challenge_attempt(
                user_id=test_user.id, challenge_id=test_challenge.id
            )

            # Complete it
            completed_attempt = ChallengeService.complete_challenge_attempt(
                attempt_id=attempt.id, score=75, notes="Good performance"
            )

            assert completed_attempt.completed is True
            assert completed_attempt.score == 75
            assert completed_attempt.notes == "Good performance"
            assert completed_attempt.attempted_at is not None

            # Cleanup
            db.session.delete(attempt)
            db.session.commit()

    def test_complete_challenge_attempt_pass_fail(self, app, test_user):
        """Test completing a pass/fail challenge."""
        with app.app_context():
            # Create pass/fail challenge
            pass_fail_challenge = Challenge(
                description="Pass or fail",
                image_path="test_pass_fail.jpg",
                pass_fail_only=True,
                is_active=True,
            )
            db.session.add(pass_fail_challenge)
            db.session.commit()

            # Start and complete attempt
            attempt = ChallengeService.start_challenge_attempt(
                user_id=test_user.id, challenge_id=pass_fail_challenge.id
            )

            completed_attempt = ChallengeService.complete_challenge_attempt(
                attempt_id=attempt.id, passed=True
            )

            assert completed_attempt.completed is True
            assert completed_attempt.passed is True

            # Cleanup
            db.session.delete(attempt)
            db.session.delete(pass_fail_challenge)
            db.session.commit()

    def test_toggle_favorite(self, app, test_user, test_challenge):
        """Test favorite toggle functionality."""
        with app.app_context():
            # Initially not favorite
            is_favorite = ChallengeService.toggle_favorite(
                test_user.id, test_challenge.id
            )
            assert is_favorite is True

            # Check it exists
            favorite = (
                db.session.query(ChallengeFavorite)
                .filter_by(user_id=test_user.id, challenge_id=test_challenge.id)
                .first()
            )
            assert favorite is not None

            # Toggle again (remove)
            is_favorite = ChallengeService.toggle_favorite(
                test_user.id, test_challenge.id
            )
            assert is_favorite is False

            # Check it's gone
            favorite = (
                db.session.query(ChallengeFavorite)
                .filter_by(user_id=test_user.id, challenge_id=test_challenge.id)
                .first()
            )
            assert favorite is None

    def test_update_challenge(self, app, test_challenge):
        """Test challenge update functionality."""
        with app.app_context():
            test_challenge.description
            original_pass_fail = test_challenge.pass_fail_only

            # Update challenge
            updated_challenge = ChallengeService.update_challenge(
                challenge_id=test_challenge.id,
                description="Updated description",
                pass_fail_only=not original_pass_fail,
                is_active=False,
            )

            # Verify updates
            assert updated_challenge.id == test_challenge.id
            assert updated_challenge.description == "Updated description"
            assert updated_challenge.pass_fail_only != original_pass_fail
            assert updated_challenge.is_active is False

            # Verify partial update (only description)
            partial_update = ChallengeService.update_challenge(
                challenge_id=test_challenge.id, description="Partially updated"
            )
            assert partial_update.description == "Partially updated"
            assert partial_update.is_active is False  # Should remain unchanged

    def test_delete_challenge_soft_delete(self, app, test_challenge):
        """Test challenge soft delete."""
        with app.app_context():
            original_active = test_challenge.is_active

            # Create a challenge attempt to force soft delete behavior
            from models.challenge.models import ChallengeAttempt

            unique_id = str(uuid.uuid4())[:8]
            test_user = User(
                username=f"testuser_attempt_{unique_id}",
                email=f"test_attempt_{unique_id}@example.com",
                role="player",
            )
            test_user.set_password("testpass123")
            db.session.add(test_user)
            db.session.flush()

            attempt = ChallengeAttempt(
                challenge_id=test_challenge.id,
                user_id=test_user.id,
                score=50,
                notes="Test attempt to force soft delete",
            )
            db.session.add(attempt)
            db.session.commit()

            ChallengeService.delete_challenge(test_challenge.id)

            # Should still exist but be inactive (soft delete)
            challenge = db.session.get(Challenge, test_challenge.id)
            assert challenge is not None
            assert challenge.is_active is False

            # Cleanup
            db.session.delete(attempt)
            db.session.delete(test_user)
            challenge.is_active = original_active
            db.session.commit()


class TestChallengeModel:
    """Test Challenge model methods."""

    @pytest.fixture
    def test_challenge_with_attempts(self, app):
        """Create a challenge with some attempts for testing."""
        with app.app_context():
            # Create user
            unique_id = str(uuid.uuid4())[:8]
            user = User(
                username=f"testuser_{unique_id}",
                email="test@example.com",
                role="player",
            )
            user.set_password("testpass123")
            db.session.add(user)
            db.session.flush()

            # Create challenge
            challenge = Challenge(
                description="Test description for statistics",
                image_path="test_stats.jpg",
                is_active=True,
            )
            db.session.add(challenge)
            db.session.flush()

            # Create attempts
            attempt1 = ChallengeAttempt(
                user_id=user.id, challenge_id=challenge.id, score=80, completed=True
            )
            attempt2 = ChallengeAttempt(
                user_id=user.id, challenge_id=challenge.id, score=60, completed=True
            )
            db.session.add(attempt1)
            db.session.add(attempt2)
            db.session.commit()

            yield challenge

            # Cleanup
            db.session.delete(attempt1)
            db.session.delete(attempt2)
            db.session.delete(challenge)
            db.session.delete(user)
            db.session.commit()

    def test_get_display_name(self, app):
        """Il nome è il titolo; senza titolo, il progressivo.

        La descrizione non c'entra più: due drill che cominciano allo stesso
        modo — ed è la norma, «Disponi le bilie…» — mostravano lo stesso nome.
        """
        with app.app_context():
            challenge_with_title = Challenge(
                title="Progressione lungo sponda",
                description="Test challenge",
                image_path="test_display.jpg",
            )
            assert (
                challenge_with_title.get_display_name() == "Progressione lungo sponda"
            )

            # Titolo di soli spazi: non è un titolo.
            challenge_blank_title = Challenge(
                title="   ", description="Test challenge", image_path="test_blank.jpg"
            )
            db.session.add(challenge_blank_title)
            db.session.flush()
            assert challenge_blank_title.get_display_name() == (
                f"Esercizio {challenge_blank_title.id}"
            )

            # Senza titolo la descrizione non finisce nel nome, per quanto lunga.
            challenge_without_title = Challenge(
                description=(
                    "Test challenge description that is quite long and needs truncation"
                ),
                image_path="test_long.jpg",
            )
            db.session.add(challenge_without_title)
            db.session.flush()
            assert challenge_without_title.get_display_name() == (
                f"Esercizio {challenge_without_title.id}"
            )
            assert "Test challenge description" not in (
                challenge_without_title.get_display_name()
            )

            db.session.rollback()

    def test_get_statistics(self, app, test_challenge_with_attempts):
        """Test challenge statistics calculation."""
        with app.app_context():
            stats = test_challenge_with_attempts.get_statistics()

            assert stats["total_attempts"] == 2
            assert stats["unique_players"] == 1
            assert stats["average_score"] == 70  # (80 + 60) / 2
            assert stats["pass_rate"] is None  # Numeric challenges don't have pass_rate

    def test_image_filename_property(self, app):
        """Test image filename property."""
        with app.app_context():
            # Challenge without image
            challenge_no_image = Challenge(
                description="Test challenge without image", image_path=""
            )
            assert challenge_no_image.image_filename is None

            # Challenge with image path
            challenge_with_image = Challenge(
                description="Test challenge with image", image_path="path/to/image.jpg"
            )
            assert challenge_with_image.image_filename == "image.jpg"
