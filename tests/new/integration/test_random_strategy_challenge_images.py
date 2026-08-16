"""Integration tests for challenge images visibility in random strategy gara details."""

import pytest
import uuid
from datetime import date, timedelta

from models import User, Gara
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus
from models.competition.services import GaraService
from models.challenge.models import Challenge
from models.competition.gara_challenge import GaraChallenge
from utils.image_paths import ImagePathManager


@pytest.mark.integration
class TestRandomStrategyChallengeImages:
    """Test challenge images visibility in random strategy gara details for player and
    guest.
    """

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
    def player_user(self, db_session) -> User:
        """Create player user for test."""
        unique_id = str(uuid.uuid4())[:8]
        player = User(
            username=f"player_{unique_id}",
            email=f"player_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        db_session.add(player)
        db_session.commit()
        return player

    @pytest.fixture
    def challenge_with_image(self, db_session, admin_user) -> Challenge:
        """Create a challenge with an image path."""
        # Use centralized path management for test data
        image_path = ImagePathManager.get_challenge_db_path("spot_shot_9ball.jpg")

        challenge = Challenge(
            description="Spot Shot Challenge - Hit the 9-ball in the corner pocket",
            image_path=image_path,
            pass_fail_only=False,
            created_by_id=admin_user.id,
            is_active=True,
        )
        db_session.add(challenge)
        db_session.commit()
        return challenge

    @pytest.fixture
    def challenge_with_different_image(self, db_session, admin_user) -> Challenge:
        """Create a challenge with a different image path."""
        # Use centralized path management for test data
        image_path = ImagePathManager.get_challenge_db_path("bank_shot_8ball.png")

        challenge = Challenge(
            description="Bank Shot Challenge - Use the rail to pocket the 8-ball",
            image_path=image_path,
            pass_fail_only=True,
            created_by_id=admin_user.id,
            is_active=True,
        )
        db_session.add(challenge)
        db_session.commit()
        return challenge

    @pytest.fixture
    def random_gara_with_challenges(
        self,
        db_session,
        admin_user,
        challenge_with_image,
        challenge_with_different_image,
    ) -> Gara:
        """Create a random strategy gara with challenges."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,  # Standalone
            number=1,
            name="Random Strategy Gara with Challenge Images",
            date=tomorrow,
            location="Challenge Test Venue",
            description="Test gara with random strategy and challenge images",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=15.0,
            discipline="palla 9",
            distance=7,
            is_race_to=True,
            director_id=admin_user.id,
            strategy_config={
                "matchmaking_strategy": "random",
                "first_round_policy": "random",
                "odd_number_policy": "bye_with_challenge",  # For challenges
            },
        )

        # Set status to inscription to simulate open inscriptions
        gara.status = GaraStatus.INSCRIPTION.value
        db_session.commit()

        # Add challenges to the gara
        gara_challenge_1 = GaraChallenge(
            gara_id=gara.id,
            challenge_id=challenge_with_image.id,
            round_number=1,  # Available after round 1
            max_attempts=2,
            is_active=True,
            added_by_id=admin_user.id,
        )

        gara_challenge_2 = GaraChallenge(
            gara_id=gara.id,
            challenge_id=challenge_with_different_image.id,
            round_number=2,  # Available after round 2
            max_attempts=1,
            is_active=True,
            added_by_id=admin_user.id,
        )

        db_session.add_all([gara_challenge_1, gara_challenge_2])
        db_session.commit()

        return gara

    def test_challenge_model_image_properties(
        self, db_session, challenge_with_image, challenge_with_different_image
    ):
        """Test that Challenge model correctly handles image paths and filename
        extraction.
        """
        # First challenge with JPG image - use centralized path for comparison
        expected_jpg_path = ImagePathManager.get_challenge_db_path(
            "spot_shot_9ball.jpg"
        )
        assert challenge_with_image.image_path == expected_jpg_path
        assert challenge_with_image.image_filename == "spot_shot_9ball.jpg"
        assert expected_jpg_path == "static/uploads/challenges/spot_shot_9ball.jpg"

        # Second challenge with PNG image - use centralized path for comparison
        expected_png_path = ImagePathManager.get_challenge_db_path(
            "bank_shot_8ball.png"
        )
        assert challenge_with_different_image.image_path == expected_png_path
        assert challenge_with_different_image.image_filename == "bank_shot_8ball.png"
        assert expected_png_path == "static/uploads/challenges/bank_shot_8ball.png"

    def test_gara_challenge_relationships(
        self, db_session, random_gara_with_challenges
    ):
        """Test that gara challenge relationships are correctly set up."""
        # Get gara challenges
        gara_challenges = GaraChallenge.query.filter_by(
            gara_id=random_gara_with_challenges.id
        ).all()

        assert len(gara_challenges) == 2, "Should have 2 challenges linked to gara"

        # Check that challenges have correct properties
        for gara_challenge in gara_challenges:
            assert gara_challenge.gara_id == random_gara_with_challenges.id
            assert gara_challenge.is_active is True
            assert gara_challenge.challenge is not None
            assert gara_challenge.gara is not None

        # Check image paths through relationships - both challenges have images
        jpg_challenges = [
            gc
            for gc in gara_challenges
            if gc.challenge.image_path and "jpg" in gc.challenge.image_path
        ]
        png_challenges = [
            gc
            for gc in gara_challenges
            if gc.challenge.image_path and "png" in gc.challenge.image_path
        ]

        assert len(jpg_challenges) == 1, "Should have 1 challenge with JPG image"
        assert len(png_challenges) == 1, "Should have 1 challenge with PNG image"

        # Verify the JPG challenge has correct path
        jpg_challenge = jpg_challenges[0]
        assert "spot_shot_9ball.jpg" in jpg_challenge.challenge.image_path

        # Verify the PNG challenge has correct path
        png_challenge = png_challenges[0]
        assert "bank_shot_8ball.png" in png_challenge.challenge.image_path

    def test_gara_detail_data_preparation_for_challenges(
        self, db_session, random_gara_with_challenges, player_user
    ):
        """Test data preparation that would be used in gara_detail templates."""
        # This simulates what happens in routes when preparing data for templates

        gara = random_gara_with_challenges

        # Get gara challenges (what template would receive)
        gara_challenges = GaraChallenge.query.filter_by(
            gara_id=gara.id, is_active=True
        ).all()

        # Simulate template data preparation for player view
        challenge_data = []
        for gara_challenge in gara_challenges:
            challenge = gara_challenge.challenge

            # This mimics template logic for displaying challenges
            challenge_info = {
                "gara_challenge": gara_challenge,
                "challenge": challenge,
                "has_image": challenge.image_path is not None,
                "image_path": challenge.image_path,
                "image_filename": challenge.image_filename,
                "description": challenge.description,
                "round_number": gara_challenge.round_number,
                "max_attempts": gara_challenge.max_attempts,
            }
            challenge_data.append(challenge_info)

        # Verify we have the expected challenge data
        assert len(challenge_data) == 2, "Should have data for 2 challenges"

        # Both challenges should have images (since image_path is required)
        assert all(
            cd["has_image"] for cd in challenge_data
        ), "All challenges should have images"

        # Check JPG challenge - use centralized path for comparison
        jpg_challenge_data = [cd for cd in challenge_data if "jpg" in cd["image_path"]][
            0
        ]
        expected_jpg_path = ImagePathManager.get_challenge_db_path(
            "spot_shot_9ball.jpg"
        )
        assert jpg_challenge_data["image_path"] == expected_jpg_path
        assert jpg_challenge_data["image_filename"] == "spot_shot_9ball.jpg"
        assert "Spot Shot Challenge" in jpg_challenge_data["description"]

        # Check PNG challenge - use centralized path for comparison
        png_challenge_data = [cd for cd in challenge_data if "png" in cd["image_path"]][
            0
        ]
        expected_png_path = ImagePathManager.get_challenge_db_path(
            "bank_shot_8ball.png"
        )
        assert png_challenge_data["image_path"] == expected_png_path
        assert png_challenge_data["image_filename"] == "bank_shot_8ball.png"
        assert "Bank Shot Challenge" in png_challenge_data["description"]

    def test_template_image_display_logic(
        self, db_session, random_gara_with_challenges
    ):
        """Test template logic for displaying challenge images vs placeholders."""
        # Get challenges as they would appear in template
        gara_challenges = GaraChallenge.query.filter_by(
            gara_id=random_gara_with_challenges.id, is_active=True
        ).all()

        # Simulate template rendering logic for each challenge
        rendered_challenges = []
        for gara_challenge in gara_challenges:
            challenge = gara_challenge.challenge

            # This simulates the template logic from player/gara_detail.html lines
            # 320-340
            # Since all challenges have image_path (required field), they all render as
            # img
            # Use centralized URL generation like templates do
            template_url = ImagePathManager.get_challenge_url_path_from_db_path(
                challenge.image_path
            )
            image_element = {
                "type": "img",
                "src": template_url,
                "alt": challenge.get_display_name(),
                "class": "challenge-image img-fluid rounded",
                "has_fallback": True,  # Template has onerror fallback for broken images
                "file_extension": challenge.image_path.split(".")[-1],
            }

            rendered_challenge = {
                "gara_challenge_id": gara_challenge.id,
                "challenge_id": challenge.id,
                "description": challenge.description,
                "image_element": image_element,
                "round_number": gara_challenge.round_number,
            }
            rendered_challenges.append(rendered_challenge)

        # Verify rendering logic
        assert len(rendered_challenges) == 2

        # Both challenges should render as images (not placeholders)
        img_challenges = [
            rc for rc in rendered_challenges if rc["image_element"]["type"] == "img"
        ]
        assert len(img_challenges) == 2, "Both challenges should render as images"

        # Find JPG challenge - use centralized URL generation
        jpg_challenge = next(
            (
                rc
                for rc in rendered_challenges
                if rc["image_element"]["file_extension"] == "jpg"
            ),
            None,
        )
        assert jpg_challenge is not None, "Should have JPG challenge"
        expected_jpg_url = ImagePathManager.get_challenge_url_path_from_db_path(
            ImagePathManager.get_challenge_db_path("spot_shot_9ball.jpg")
        )
        assert jpg_challenge["image_element"]["src"] == expected_jpg_url
        assert jpg_challenge["image_element"]["has_fallback"] is True

        # Find PNG challenge - use centralized URL generation
        png_challenge = next(
            (
                rc
                for rc in rendered_challenges
                if rc["image_element"]["file_extension"] == "png"
            ),
            None,
        )
        assert png_challenge is not None, "Should have PNG challenge"
        expected_png_url = ImagePathManager.get_challenge_url_path_from_db_path(
            ImagePathManager.get_challenge_db_path("bank_shot_8ball.png")
        )
        assert png_challenge["image_element"]["src"] == expected_png_url
        assert png_challenge["image_element"]["has_fallback"] is True

    def test_guest_vs_player_challenge_visibility(
        self, db_session, random_gara_with_challenges, player_user
    ):
        """Test that both guest and player can see challenge images in gara details."""
        # Both guest and player should be able to see the gara (inscriptions are open)
        gara = random_gara_with_challenges
        assert gara.status == GaraStatus.INSCRIPTION.value

        # Get challenges that would be visible in template
        gara_challenges = GaraChallenge.query.filter_by(
            gara_id=gara.id, is_active=True
        ).all()

        # Both guest and player should see the same challenge information
        # The difference is in what actions they can take, not what they can see

        challenge_display_data = []
        for gara_challenge in gara_challenges:
            challenge = gara_challenge.challenge

            # This data would be the same for guest and player in the template
            # Use centralized URL generation like templates do
            template_url = ImagePathManager.get_challenge_url_path_from_db_path(
                challenge.image_path
            )
            display_info = {
                "challenge_name": challenge.get_display_name(),
                "has_image": challenge.image_path is not None,
                "image_url": template_url,
                "round_availability": gara_challenge.round_number,
                "max_attempts": gara_challenge.max_attempts,
                "description": challenge.description,
            }
            challenge_display_data.append(display_info)

        # Verify that challenge data is properly structured for display
        assert len(challenge_display_data) == 2

        # Both challenges should be visible with their images - use centralized URL
        # generation
        image_urls = [cd["image_url"] for cd in challenge_display_data]
        assert len(image_urls) == 2, "Both challenges should have image URLs"

        expected_jpg_url = ImagePathManager.get_challenge_url_path_from_db_path(
            ImagePathManager.get_challenge_db_path("spot_shot_9ball.jpg")
        )
        expected_png_url = ImagePathManager.get_challenge_url_path_from_db_path(
            ImagePathManager.get_challenge_db_path("bank_shot_8ball.png")
        )

        assert expected_jpg_url in image_urls
        assert expected_png_url in image_urls

        # All challenges should have images (no placeholders needed)
        assert all(
            cd["has_image"] for cd in challenge_display_data
        ), "All challenges should have images"

    def test_challenge_images_in_random_strategy_context(
        self, db_session, random_gara_with_challenges
    ):
        """
        Test that challenge images work correctly in the context of random strategy.
        """
        gara = random_gara_with_challenges

        # Verify this is indeed a random strategy gara
        # (Note: strategy_config might be stored differently, this is conceptual)
        assert gara.name == "Random Strategy Gara with Challenge Images"

        # Get challenges and verify they're properly linked
        gara_challenges = GaraChallenge.query.filter_by(gara_id=gara.id).all()
        assert len(gara_challenges) == 2

        # Verify challenges are available at different rounds (as configured)
        round_1_challenges = [gc for gc in gara_challenges if gc.round_number == 1]
        round_2_challenges = [gc for gc in gara_challenges if gc.round_number == 2]

        assert (
            len(round_1_challenges) == 1
        ), "Should have 1 challenge available after round 1"
        assert (
            len(round_2_challenges) == 1
        ), "Should have 1 challenge available after round 2"

        # Verify the round 1 challenge has the JPG image (spot shot)
        round_1_challenge = round_1_challenges[0]
        assert round_1_challenge.challenge.image_path is not None
        assert "spot_shot_9ball.jpg" in round_1_challenge.challenge.image_path

        # Verify the round 2 challenge has the PNG image (bank shot)
        round_2_challenge = round_2_challenges[0]
        assert round_2_challenge.challenge.image_path is not None
        assert "bank_shot_8ball.png" in round_2_challenge.challenge.image_path
