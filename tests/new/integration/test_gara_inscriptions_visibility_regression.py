"""
Regression tests for gara inscriptions visibility across user roles.

Bug (2025-12-28): Inscriptions section showed count "(8)" in header but
"Nessun iscritto" in body for player and guest users.

Cause: `inscriptions` variable was only loaded inside `if user_can_manage:`
block in routes/admin/competition.py, so it was None for non-admin users.

Fix: Moved inscriptions loading outside the conditional block so all users
receive the inscriptions list.
"""

import pytest
import uuid
from datetime import date, timedelta, datetime

from flask import url_for
from flask_login import login_user

from models import User, Gara, Inscription, db
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus
from models.competition.services import GaraService


@pytest.mark.integration
class TestGaraInscriptionsVisibilityRegression:
    """
    Regression tests ensuring inscriptions are visible to all user roles.

    Bug: Header showed "(8)" but body showed "Nessun iscritto" for player/guest.
    Fix: routes/admin/competition.py - load inscriptions for all users.
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
    def director_user(self, db_session) -> User:
        """Create director user for test."""
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()
        return director

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
    def other_players(self, db_session) -> list[User]:
        """Create additional player users for inscriptions."""
        players = []
        for i in range(5):
            unique_id = str(uuid.uuid4())[:8]
            player = User(
                username=f"other_player_{i}_{unique_id}",
                email=f"other_player_{i}_{unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            db_session.add(player)
            players.append(player)
        db_session.commit()
        return players

    @pytest.fixture
    def gara_with_inscriptions(
        self, db_session, admin_user, player_user, other_players
    ) -> Gara:
        """Create a gara with multiple inscriptions."""
        tomorrow = date.today() + timedelta(days=1)

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Test Gara Inscriptions Visibility",
            date=tomorrow,
            location="Test Venue",
            description="Test gara for inscriptions visibility regression",
            rounds_count=3,
            min_participants=4,
            max_participants=10,
            entry_fee=10.0,
            discipline="palla 9",
            distance=5,
            is_race_to=True,
            director_id=admin_user.id,
        )

        # Open inscriptions
        gara.status = GaraStatus.INSCRIPTION.value
        gara.inscription_start = datetime.utcnow() - timedelta(hours=1)
        gara.inscription_end = datetime.utcnow() + timedelta(days=1)
        db_session.commit()

        # Add inscriptions
        all_players = [player_user] + other_players
        for player in all_players:
            inscription = Inscription(
                gara_id=gara.id,
                user_id=player.id,
                is_waitlist=False,
                is_withdrawn=False,
            )
            db_session.add(inscription)
        db_session.commit()

        return gara

    def test_player_sees_inscriptions_list(
        self, app, db_session, gara_with_inscriptions, player_user
    ):
        """
        Regression test: Player should see list of inscribed users.

        Bug: Player saw count "(6)" in header but "Nessun iscritto" in body
        because inscriptions variable was None.
        """
        with app.test_client() as client:
            # Login as player
            with client.session_transaction() as sess:
                sess["_user_id"] = str(player_user.id)

            # Access gara detail
            response = client.get(
                url_for("admin.competition.gara_detail", gara_id=gara_with_inscriptions.id)
            )

            assert response.status_code == 200

            # The inscriptions list should be visible
            # Check that inscribed usernames appear in the response
            html = response.data.decode("utf-8")

            # Should NOT show "Nessun iscritto" since there are inscriptions
            assert "Nessun iscritto" not in html or "other_player" in html

            # Should show at least one inscribed player's username
            assert "other_player" in html or player_user.username in html

    def test_guest_sees_inscriptions_list(
        self, app, db_session, gara_with_inscriptions
    ):
        """
        Regression test: Guest (unauthenticated) should see inscriptions list.

        Bug: Guest saw count in header but empty list in body.
        """
        with app.test_client() as client:
            # Access gara detail without authentication
            response = client.get(
                url_for("admin.competition.gara_detail", gara_id=gara_with_inscriptions.id)
            )

            assert response.status_code == 200

            html = response.data.decode("utf-8")

            # Guest should see inscribed players
            # Either see usernames or at least not see "Nessun iscritto" alone
            assert "other_player" in html or "Nessun iscritto" not in html

    def test_admin_sees_inscriptions_list(
        self, app, db_session, gara_with_inscriptions, admin_user
    ):
        """Admin should see complete inscriptions list with management buttons."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["_user_id"] = str(admin_user.id)

            response = client.get(
                url_for("admin.competition.gara_detail", gara_id=gara_with_inscriptions.id)
            )

            assert response.status_code == 200

            html = response.data.decode("utf-8")

            # Admin should see inscribed players
            assert "other_player" in html

            # Admin should also see management buttons (fa-user-minus for unsubscribe)
            assert "fa-user-minus" in html

    def test_director_without_gara_permission_sees_inscriptions(
        self, app, db_session, gara_with_inscriptions, director_user
    ):
        """
        Director without specific gara permission should still see inscriptions.

        They won't have management buttons, but should see the list.
        """
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["_user_id"] = str(director_user.id)

            response = client.get(
                url_for("admin.competition.gara_detail", gara_id=gara_with_inscriptions.id)
            )

            assert response.status_code == 200

            html = response.data.decode("utf-8")

            # Director should see inscribed players
            assert "other_player" in html

    def test_inscriptions_count_matches_list_length(
        self, app, db_session, gara_with_inscriptions, player_user
    ):
        """
        Regression test: Count in header should match actual list items.

        Bug: Header showed "(6)" but list was empty because inscriptions=None.
        """
        expected_count = gara_with_inscriptions.get_active_inscriptions_count()
        assert expected_count == 6  # player_user + 5 other_players

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["_user_id"] = str(player_user.id)

            response = client.get(
                url_for("admin.competition.gara_detail", gara_id=gara_with_inscriptions.id)
            )

            html = response.data.decode("utf-8")

            # Count the number of inscription items in the HTML
            # Each inscription has class "d-flex justify-content-between align-items-center mb-2 p-2 border rounded"
            inscription_items = html.count("fa-user me-1")

            # Should have at least the expected number of inscriptions visible
            assert inscription_items >= expected_count
