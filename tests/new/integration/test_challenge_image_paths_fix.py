"""Integration tests for correct challenge image paths."""

import pytest
import uuid
import os
from datetime import date, timedelta
from flask import current_app

from models import User, Gara
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus
from models.competition.services import GaraService
from models.challenge.models import Challenge
from models.competition.gara_challenge import GaraChallenge
from utils.image_paths import ImagePathManager


@pytest.mark.integration
class TestChallengeImagePathsFix:
    """Test that challenge images use correct paths and are actually servable."""

    @pytest.fixture
    def admin_user(self, db_session) -> User:
        """Create admin user for test."""
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("admin123")
        db_session.add(admin)
        db_session.commit()
        return admin

    @pytest.fixture
    def challenge_with_correct_path(self, db_session, admin_user) -> Challenge:
        """Create a challenge with the correct image path format."""
        # This simulates how the real application saves image paths (from
        # admin/competition.py:1702)
        unique_id = str(uuid.uuid4())[:8]
        filename = f"test_challenge_{unique_id}.jpg"

        # Use centralized path management for correct format
        from utils.image_paths import ImagePathManager

        image_path = ImagePathManager.get_challenge_db_path(filename)

        challenge = Challenge(
            description="Real Challenge - Test with correct path",
            image_path=image_path,  # Correct format with static/ prefix!
            pass_fail_only=False,
            created_by_id=admin_user.id,
            is_active=True,
        )
        db_session.add(challenge)
        db_session.commit()
        return challenge

    @pytest.fixture
    def gara_with_real_challenge(
        self, db_session, admin_user, challenge_with_correct_path
    ) -> Gara:
        """Create a gara with challenge using real path format."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=1,
            name="Real Random Strategy Gara",
            date=tomorrow,
            location="Real Test Venue",
            description="Test gara with correct challenge image paths",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=admin_user.id,
        )

        # Set status to inscription
        gara.status = GaraStatus.INSCRIPTION.value
        db_session.commit()

        # Add challenge to the gara
        gara_challenge = GaraChallenge(
            gara_id=gara.id,
            challenge_id=challenge_with_correct_path.id,
            round_number=1,
            max_attempts=2,
            is_active=True,
            added_by_id=admin_user.id,
        )
        db_session.add(gara_challenge)
        db_session.commit()

        return gara

    def test_challenge_has_correct_path_format(
        self, db_session, challenge_with_correct_path
    ):
        """Test that challenge uses the correct path format."""
        challenge = challenge_with_correct_path

        # Should be static/uploads/challenges/filename.jpg, not
        # static/challenges/filename.jpg
        assert challenge.image_path.startswith("static/uploads/challenges/")
        assert not challenge.image_path.startswith("static/challenges/")
        assert challenge.image_path.endswith(".jpg")

        # Filename extraction should work correctly
        expected_filename = challenge.image_path.split("/")[-1]
        assert challenge.image_filename == expected_filename

    def test_template_generates_correct_src_attribute(
        self, db_session, gara_with_real_challenge
    ):
        """Test that template generates correct src for serving images."""
        # Get challenge from gara
        gara_challenges = GaraChallenge.query.filter_by(
            gara_id=gara_with_real_challenge.id
        ).all()
        assert len(gara_challenges) == 1

        gara_challenge = gara_challenges[0]
        challenge = gara_challenge.challenge

        # Use centralized URL generation like templates do
        src_attribute = ImagePathManager.get_challenge_url_path_from_db_path(
            challenge.image_path
        )

        # Should generate proper URL using centralized constants
        expected_pattern = "/static/uploads/challenges/"
        assert src_attribute.startswith(expected_pattern)
        assert src_attribute.endswith(".jpg")

        # Should NOT contain the old incorrect pattern
        assert "/static/challenges/" not in src_attribute

        print(f"Generated src attribute: {src_attribute}")

    def test_static_folder_structure_exists(self, app):
        """Test that the static folder structure for challenges exists."""
        with app.app_context():
            # Use centralized path management to check directory structure
            static_folder = current_app.static_folder
            challenges_dir = ImagePathManager.get_challenge_upload_dir()

            assert static_folder is not None, "Static folder should be configured"
            assert challenges_dir is not None, "Challenges dir should be configured"

            assert os.path.exists(
                static_folder
            ), f"Static folder should exist: {static_folder}"
            assert os.path.exists(
                challenges_dir
            ), f"Challenges folder should exist: {challenges_dir}"

            # Verify the challenges dir is within static folder
            assert challenges_dir.startswith(
                static_folder
            ), "Challenges dir should be within static folder"

    def test_identify_path_mismatch_in_our_previous_tests(self, db_session):
        """Test to identify and document the path mismatch issue."""
        # This test documents the issue we had in our previous tests

        # WRONG path (what we used in tests before centralization)
        wrong_path = "static/challenges/spot_shot_9ball.jpg"

        # CORRECT path (what real app uses with centralized management)
        correct_path = ImagePathManager.get_challenge_db_path("spot_shot_9ball.jpg")

        # Template src generation using centralized utility
        wrong_src = f"/{wrong_path}"  # "/static/challenges/spot_shot_9ball.jpg"
        correct_src = ImagePathManager.get_challenge_url_path_from_db_path(correct_path)

        # Verify format
        assert correct_src.startswith("/static/uploads/challenges/")
        assert wrong_src == "/static/challenges/spot_shot_9ball.jpg"

        # Document the issue
        print(f"❌ Wrong path used in tests: {wrong_path}")
        print(f"✅ Correct path used by app: {correct_path}")
        print(f"❌ Wrong src attribute: {wrong_src}")
        print(f"✅ Correct src attribute: {correct_src}")

    def test_fix_needed_in_previous_tests(self, db_session):
        """Test to document what needs to be fixed in our previous tests."""
        # Our previous test files used wrong paths (before centralization):
        wrong_paths_used = [
            "static/challenges/spot_shot_9ball.jpg",
            "static/challenges/bank_shot_8ball.png",
        ]

        # Should be (using centralized path management):
        correct_paths_should_be = [
            ImagePathManager.get_challenge_db_path("spot_shot_9ball.jpg"),
            ImagePathManager.get_challenge_db_path("bank_shot_8ball.png"),
        ]

        for wrong, correct in zip(wrong_paths_used, correct_paths_should_be):
            print(f"Fix needed: '{wrong}' → '{correct}'")

            # Verify template behavior using centralized URL generation
            wrong_src = f"/{wrong}"
            correct_src = ImagePathManager.get_challenge_url_path_from_db_path(correct)

            # The correct path uses centralized constants
            assert correct_src.startswith("/static/uploads/challenges/")
            assert wrong_src.startswith(
                "/static/challenges/"
            )  # This is the old wrong pattern
            assert correct != wrong  # Verify they are actually different

    def test_actual_image_serving_simulation(
        self, app, db_session, challenge_with_correct_path
    ):
        """Test that demonstrates how Flask would serve the image."""
        with app.app_context():
            challenge = challenge_with_correct_path

            # Challenge image path in database (using centralized system)
            db_path = challenge.image_path

            # Template generates this src using centralized utility
            src_attribute = ImagePathManager.get_challenge_url_path_from_db_path(
                db_path
            )

            # Flask static file serving would look for file at:
            static_folder = current_app.static_folder
            assert static_folder is not None, "Static folder should be configured"
            # Remove the leading slash and "static/" from src to get relative path
            # within static folder
            relative_path = src_attribute.lstrip("/").replace("static/", "", 1)
            file_system_path = os.path.join(static_folder, relative_path)

            print(f"Database path: {db_path}")
            print(f"Generated src: {src_attribute}")
            print(f"Flask would serve from: {file_system_path}")

            # The file path should be within the static folder
            assert file_system_path.startswith(static_folder)
            assert "uploads" in file_system_path
            assert "challenges" in file_system_path

            # The directory should exist (using centralized directory management)
            expected_dir = ImagePathManager.get_challenge_upload_dir()
            assert os.path.exists(expected_dir)
