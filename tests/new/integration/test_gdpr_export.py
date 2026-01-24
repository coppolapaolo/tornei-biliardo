"""Integration tests for GDPR data export functionality."""

from datetime import date

import pytest
from flask import url_for

from models import User
from models.competition.models import Gara, Inscription
from models.gamification.models import UserLevel, XPTransaction, XPTransactionType


@pytest.fixture
def player_with_data(db_session):
    """Create a player with some test data."""
    # Create user
    user = User(username="gdpr_test_user", email="gdpr@test.com", role="player")
    user.set_password("password123")
    db_session.add(user)
    db_session.flush()

    # Create a standalone gara
    gara = Gara(
        name="Test Gara",
        number=1,
        date=date(2026, 1, 15),
        discipline="palla 8",
        status="completed",
        max_participants=16,
        distance=5,
    )
    db_session.add(gara)
    db_session.flush()

    # Create inscription
    inscription = Inscription(user_id=user.id, gara_id=gara.id)
    db_session.add(inscription)

    # Create gamification data
    user_level = UserLevel(user_id=user.id, current_level=5, total_xp=1500)
    db_session.add(user_level)

    xp_tx = XPTransaction(
        user_id=user.id,
        transaction_type=XPTransactionType.MATCH_WIN,
        xp_amount=100,
        reason="Test XP",
        level_before=4,
        level_after=5,
    )
    db_session.add(xp_tx)

    db_session.commit()
    return user


class TestGDPRExport:
    """Tests for GDPR export functionality."""

    def test_collect_user_data_returns_all_categories(self, app, player_with_data):
        """Test that _collect_user_data returns all expected data categories."""
        with app.app_context():
            from routes.player.profile import _collect_user_data

            data = _collect_user_data(player_with_data.id)

            assert "export_date" in data
            assert "export_version" in data
            assert data["export_version"] == "1.0"

            # Check all categories exist
            assert "account" in data
            assert "privacy_settings" in data
            assert "inscriptions" in data
            assert "matches" in data
            assert "classifications" in data
            assert "challenges" in data
            assert "gamification" in data

    def test_collect_user_data_account_info(self, app, player_with_data):
        """Test that account data is correctly collected."""
        with app.app_context():
            from routes.player.profile import _collect_user_data

            data = _collect_user_data(player_with_data.id)

            assert data["account"]["username"] == "gdpr_test_user"
            assert data["account"]["email"] == "gdpr@test.com"
            assert data["account"]["role"] == "player"

    def test_collect_user_data_inscriptions(self, app, player_with_data):
        """Test that inscriptions are correctly collected."""
        with app.app_context():
            from routes.player.profile import _collect_user_data

            data = _collect_user_data(player_with_data.id)

            assert len(data["inscriptions"]) == 1
            assert data["inscriptions"][0]["gara_name"] == "Test Gara"

    def test_collect_user_data_gamification(self, app, player_with_data):
        """Test that gamification data is correctly collected."""
        with app.app_context():
            from routes.player.profile import _collect_user_data

            data = _collect_user_data(player_with_data.id)

            assert data["gamification"]["level"]["current_level"] == 5
            assert data["gamification"]["level"]["total_xp"] == 1500
            assert len(data["gamification"]["xp_transactions"]) == 1

    def test_request_export_requires_login(self, client, app):
        """Test that export request requires authentication."""
        with app.app_context():
            response = client.post(url_for("player.request_gdpr_export"))
            # Should redirect to login
            assert response.status_code in [302, 401]

    def test_request_export_starts_background_task(
        self, client, app, player_with_data
    ):
        """Test that export request starts a background task."""
        with app.app_context():
            # Login as the player
            client.post(
                url_for("auth.login"),
                data={"username": "gdpr_test_user", "password": "password123"},
                follow_redirects=True,
            )

            response = client.post(
                url_for("player.request_gdpr_export"), follow_redirects=True
            )

            assert response.status_code == 200
            # Should show info message about export starting
            assert b"Export avviato" in response.data or b"in corso" in response.data

    def test_download_export_wrong_user_forbidden(
        self, client, app, db_session, player_with_data
    ):
        """Test that users cannot download other users' exports."""
        # Create another user
        other_user = User(username="other_user", email="other@test.com", role="player")
        other_user.set_password("password123")
        db_session.add(other_user)
        db_session.commit()

        with app.app_context():
            # Login as other user
            client.post(
                url_for("auth.login"),
                data={"username": "other_user", "password": "password123"},
                follow_redirects=True,
            )

            # Try to download player_with_data's export
            response = client.get(
                url_for(
                    "player.download_gdpr_export",
                    filename=f"{player_with_data.id}_20260124_120000.zip",
                )
            )

            assert response.status_code == 403

    def test_download_nonexistent_file_redirects(
        self, client, app, player_with_data
    ):
        """Test that downloading a nonexistent file shows warning."""
        with app.app_context():
            # Login as the player
            client.post(
                url_for("auth.login"),
                data={"username": "gdpr_test_user", "password": "password123"},
                follow_redirects=True,
            )

            response = client.get(
                url_for(
                    "player.download_gdpr_export",
                    filename=f"{player_with_data.id}_nonexistent.zip",
                ),
                follow_redirects=True,
            )

            assert response.status_code == 200
            # Should show warning about missing/expired file
            assert b"non esiste" in response.data or b"scaduto" in response.data

    def test_path_traversal_blocked(self, client, app, player_with_data):
        """Test that path traversal attempts are blocked."""
        with app.app_context():
            # Login as the player
            client.post(
                url_for("auth.login"),
                data={"username": "gdpr_test_user", "password": "password123"},
                follow_redirects=True,
            )

            # Try path traversal - should be blocked by either 400 (bad request)
            # or 404 (Flask routing rejects slashes in filename)
            response = client.get(
                f"/player/gdpr-export/download/{player_with_data.id}_../../../etc/passwd"
            )

            assert response.status_code in [400, 404]
