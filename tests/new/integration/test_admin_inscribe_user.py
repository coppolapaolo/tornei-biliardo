"""
Integration tests for admin/director user inscription functionality.

Tests the ability for directors/admins to inscribe users to competitions
and the notification system that accompanies it.
"""

import pytest
from datetime import datetime, timedelta
import uuid

from models import db
from models.user.models import User
from models.competition.models import Gara, Inscription
from models.notification.models import Notification, NotificationType
from models.status_enum import GaraStatus
from models.base import utc_now


@pytest.fixture
def director_user(db_session):
    """Create a director user."""
    unique_id = str(uuid.uuid4())[:8]
    user = User(
        username=f"director_{unique_id}",
        email=f"director_{unique_id}@test.com",
        role="director",
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return db_session.get(User, user.id)


@pytest.fixture
def player_user(db_session):
    """Create a player user."""
    unique_id = str(uuid.uuid4())[:8]
    user = User(
        username=f"player_{unique_id}",
        email=f"player_{unique_id}@test.com",
        role="player",
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return db_session.get(User, user.id)


@pytest.fixture
def second_player_user(db_session):
    """Create a second player user."""
    unique_id = str(uuid.uuid4())[:8]
    user = User(
        username=f"player2_{unique_id}",
        email=f"player2_{unique_id}@test.com",
        role="player",
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return db_session.get(User, user.id)


@pytest.fixture
def gara_in_inscription(db_session, director_user):
    """Create a gara in inscription phase."""
    from datetime import date, time

    unique_id = str(uuid.uuid4())[:8]
    gara = Gara(
        name=f"Test Gara {unique_id}",
        number=1,
        date=date.today() + timedelta(days=7),
        time=time(18, 0),
        discipline="palla_8",
        distance=5,
        rounds_count=3,
        min_participants=2,
        max_participants=10,
        director_id=director_user.id,
        status=GaraStatus.INSCRIPTION.value,
        inscription_start=utc_now() - timedelta(hours=1),
        inscription_end=utc_now() + timedelta(days=1),
    )
    db_session.add(gara)
    db_session.commit()
    return db_session.get(Gara, gara.id)


class TestAdminInscribeUser:
    """Tests for admin/director user inscription."""

    def test_director_can_inscribe_user(
        self, client, db_session, director_user, player_user, gara_in_inscription
    ):
        """Director can inscribe a user to a gara."""
        # Login as director
        client.post(
            "/auth/login",
            data={"username": director_user.username, "password": "password123"},
            follow_redirects=True,
        )

        # Inscribe the player
        response = client.post(
            f"/admin/gara/{gara_in_inscription.id}/admin_inscribe",
            data={"user_id": str(player_user.id)},
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Verify inscription was created
        inscription = (
            db_session.query(Inscription)
            .filter_by(user_id=player_user.id, gara_id=gara_in_inscription.id)
            .first()
        )
        assert inscription is not None
        assert inscription.is_waitlist is False
        assert inscription.is_withdrawn is False

    def test_notification_created_on_inscription(
        self, client, db_session, director_user, player_user, gara_in_inscription
    ):
        """Notification is created when director inscribes a user."""
        # Login as director
        client.post(
            "/auth/login",
            data={"username": director_user.username, "password": "password123"},
            follow_redirects=True,
        )

        # Delete any existing notifications for the player
        db_session.query(Notification).filter_by(user_id=player_user.id).delete()
        db_session.commit()

        # Store IDs for later verification (in case objects get detached)
        player_id = player_user.id
        gara_id = gara_in_inscription.id
        gara_name = gara_in_inscription.name
        director_name = director_user.username

        # Inscribe the player
        response = client.post(
            f"/admin/gara/{gara_id}/admin_inscribe",
            data={"user_id": str(player_id)},
            follow_redirects=True,
        )

        # Check that inscription was successful (flash message in page)
        html = response.data.decode("utf-8")
        assert (
            "iscritto" in html.lower()
            or "successo" in html.lower()
            or "aggiunt" in html.lower()
        ), f"Inscription may have failed. Page content includes: {html[:500]}"

        # Expire the session to force a fresh query from the database
        db_session.expire_all()

        # Verify notification was created
        # Note: notification_type is stored as Enum, not string
        notification = (
            db_session.query(Notification)
            .filter_by(
                user_id=player_id,
                notification_type=NotificationType.TOURNAMENT_REGISTRATION,
            )
            .first()
        )
        assert notification is not None
        assert director_name in notification.message
        assert gara_name in notification.message
        # Message format: "%(enrolled_by)s ti ha iscritto alla gara %(gara_name)s del %(gara_date)s"
        assert "iscritto" in notification.message
        # action_url may be None if set via related_entities instead

    def test_user_goes_to_waitlist_when_gara_full(
        self,
        client,
        db_session,
        director_user,
        player_user,
        second_player_user,
    ):
        """User goes to waitlist when gara is at capacity."""
        from datetime import date, time

        # Create a gara with max 1 participant
        unique_id = str(uuid.uuid4())[:8]
        gara = Gara(
            name=f"Small Gara {unique_id}",
            number=1,
            date=date.today() + timedelta(days=7),
            time=time(18, 0),
            discipline="palla_8",
            distance=5,
            rounds_count=3,
            min_participants=1,
            max_participants=1,
            director_id=director_user.id,
            status=GaraStatus.INSCRIPTION.value,
            inscription_start=utc_now() - timedelta(hours=1),
            inscription_end=utc_now() + timedelta(days=1),
        )
        db_session.add(gara)
        db_session.commit()
        gara = db_session.get(Gara, gara.id)

        # Login as director
        client.post(
            "/auth/login",
            data={"username": director_user.username, "password": "password123"},
            follow_redirects=True,
        )

        # Inscribe first player (should be active)
        client.post(
            f"/admin/gara/{gara.id}/admin_inscribe",
            data={"user_id": str(player_user.id)},
            follow_redirects=True,
        )

        # Inscribe second player (should go to waitlist)
        response = client.post(
            f"/admin/gara/{gara.id}/admin_inscribe",
            data={"user_id": str(second_player_user.id)},
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Verify first player is active
        first_inscription = (
            db_session.query(Inscription)
            .filter_by(user_id=player_user.id, gara_id=gara.id)
            .first()
        )
        assert first_inscription is not None
        assert first_inscription.is_waitlist is False

        # Verify second player is in waitlist
        second_inscription = (
            db_session.query(Inscription)
            .filter_by(user_id=second_player_user.id, gara_id=gara.id)
            .first()
        )
        assert second_inscription is not None
        assert second_inscription.is_waitlist is True
        assert second_inscription.waitlist_position == 1

    def test_non_director_cannot_inscribe(
        self, client, db_session, player_user, second_player_user, gara_in_inscription
    ):
        """Non-director cannot inscribe users."""
        # Login as regular player
        client.post(
            "/auth/login",
            data={"username": player_user.username, "password": "password123"},
            follow_redirects=True,
        )

        # Try to inscribe another player
        response = client.post(
            f"/admin/gara/{gara_in_inscription.id}/admin_inscribe",
            data={"user_id": str(second_player_user.id)},
            follow_redirects=True,
        )

        # Should be forbidden (403) since player is not a manager
        assert response.status_code == 403

        # Verify inscription was NOT created
        inscription = (
            db_session.query(Inscription)
            .filter_by(user_id=second_player_user.id, gara_id=gara_in_inscription.id)
            .first()
        )
        assert inscription is None

    def test_cannot_inscribe_when_not_in_inscription_phase(
        self, client, db_session, director_user, player_user
    ):
        """Cannot inscribe users when gara is not in inscription phase."""
        from datetime import date, time

        # Create a gara in SETUP phase
        unique_id = str(uuid.uuid4())[:8]
        gara = Gara(
            name=f"Setup Gara {unique_id}",
            number=1,
            date=date.today() + timedelta(days=7),
            time=time(18, 0),
            discipline="palla_8",
            distance=5,
            rounds_count=3,
            min_participants=2,
            director_id=director_user.id,
            status=GaraStatus.SETUP.value,
        )
        db_session.add(gara)
        db_session.commit()
        gara = db_session.get(Gara, gara.id)

        # Login as director
        client.post(
            "/auth/login",
            data={"username": director_user.username, "password": "password123"},
            follow_redirects=True,
        )

        # Try to inscribe player
        response = client.post(
            f"/admin/gara/{gara.id}/admin_inscribe",
            data={"user_id": str(player_user.id)},
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Verify inscription was NOT created
        inscription = (
            db_session.query(Inscription)
            .filter_by(user_id=player_user.id, gara_id=gara.id)
            .first()
        )
        assert inscription is None


class TestAdminInscribeFormVisibility:
    """Tests for the admin inscription form visibility in templates."""

    def test_form_visible_for_director_in_inscription_phase(
        self, client, db_session, director_user, player_user, gara_in_inscription
    ):
        """Form should be visible for director when gara is in inscription phase."""
        # Login as director
        client.post(
            "/auth/login",
            data={"username": director_user.username, "password": "password123"},
            follow_redirects=True,
        )

        # Get gara detail page
        response = client.get(f"/admin/gara/{gara_in_inscription.id}")
        assert response.status_code == 200

        # Check that the add user form is present
        html = response.data.decode("utf-8")
        assert "admin_inscribe" in html
        assert "Seleziona utente" in html or "fa-user-plus" in html

    def test_form_not_visible_when_at_max_capacity(
        self, client, db_session, director_user, player_user
    ):
        """Form should not be visible when gara is at max capacity."""
        from datetime import date, time

        # Create gara at max capacity
        unique_id = str(uuid.uuid4())[:8]
        gara = Gara(
            name=f"Full Gara {unique_id}",
            number=1,
            date=date.today() + timedelta(days=7),
            time=time(18, 0),
            discipline="palla_8",
            distance=5,
            rounds_count=3,
            min_participants=1,
            max_participants=1,
            director_id=director_user.id,
            status=GaraStatus.INSCRIPTION.value,
            inscription_start=utc_now() - timedelta(hours=1),
            inscription_end=utc_now() + timedelta(days=1),
        )
        db_session.add(gara)
        db_session.commit()
        gara = db_session.get(Gara, gara.id)

        # Add one inscription to reach max
        inscription = Inscription(
            user_id=player_user.id,
            gara_id=gara.id,
            is_waitlist=False,
        )
        db_session.add(inscription)
        db_session.commit()

        # Login as director
        client.post(
            "/auth/login",
            data={"username": director_user.username, "password": "password123"},
            follow_redirects=True,
        )

        # Get gara detail page
        response = client.get(f"/admin/gara/{gara.id}")
        assert response.status_code == 200

        # Check that the add user form is NOT present
        # (The select dropdown with admin_inscribe action should not be shown)
        html = response.data.decode("utf-8")
        # The form should not appear because max capacity is reached
        # and available_users should be None
        assert "Limite massimo raggiunto" in html
