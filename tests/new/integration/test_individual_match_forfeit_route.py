"""
Integration tests for IndividualMatch forfeit route.

Tests the POST /match/matches/<match_id>/forfeit endpoint.
"""

import pytest
from datetime import datetime, timedelta

from models import db
from models.individual_match.models import IndividualMatch
from models.status_enum import MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


class TestIndividualMatchForfeitRoute:
    """Integration tests for forfeit endpoint."""

    @pytest.fixture
    def player1(self, app):
        """Create first player."""
        import uuid
        with app.app_context():
            unique_id = uuid.uuid4().hex[:8]
            user = User(
                username=f"p1_{unique_id}",
                email=f"p1_{unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            user.set_password("test123")
            db.session.add(user)
            db.session.commit()
            yield user

    @pytest.fixture
    def player2(self, app):
        """Create second player."""
        import uuid
        with app.app_context():
            unique_id = uuid.uuid4().hex[:8]
            user = User(
                username=f"p2_{unique_id}",
                email=f"p2_{unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            user.set_password("test123")
            db.session.add(user)
            db.session.commit()
            yield user

    @pytest.fixture
    def other_player(self, app):
        """Create third player (not in match)."""
        import uuid
        with app.app_context():
            unique_id = uuid.uuid4().hex[:8]
            user = User(
                username=f"other_{unique_id}",
                email=f"other_{unique_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            user.set_password("test123")
            db.session.add(user)
            db.session.commit()
            yield user

    @pytest.fixture
    def in_progress_match(self, app, player1, player2):
        """Create a match in progress."""
        with app.app_context():
            match = IndividualMatch(
                player1_id=player1.id,
                player2_id=player2.id,
                location="Test Hall",
                scheduled_at=datetime.utcnow() + timedelta(hours=1),
                status=MatchStatus.IN_PROGRESS,
                distance=5,
                is_race_to=True,
                player1_score=2,
                player2_score=3,
            )
            db.session.add(match)
            db.session.commit()
            yield match

    @pytest.fixture
    def match_with_scores(self, app, player1, player2):
        """Create a match with specific scores for forfeit test."""
        with app.app_context():
            match = IndividualMatch(
                player1_id=player1.id,
                player2_id=player2.id,
                location="Test Hall",
                scheduled_at=datetime.utcnow() + timedelta(hours=1),
                status=MatchStatus.IN_PROGRESS,
                distance=5,
                is_race_to=True,
                player1_score=3,  # Player 1 has won 3 racks
                player2_score=2,  # Player 2 has won 2 racks
            )
            db.session.add(match)
            db.session.commit()
            yield match

    @pytest.fixture
    def completed_match(self, app, player1, player2):
        """Create a completed match."""
        with app.app_context():
            match = IndividualMatch(
                player1_id=player1.id,
                player2_id=player2.id,
                location="Test Hall",
                scheduled_at=datetime.utcnow() + timedelta(hours=1),
                status=MatchStatus.COMPLETED,
                distance=5,
                is_race_to=True,
                winner_id=player1.id,
            )
            db.session.add(match)
            db.session.commit()
            yield match

    def test_forfeit_endpoint_returns_success_json(
        self, client, player1, player2, in_progress_match
    ):
        """POST /match/matches/<id>/forfeit should return success JSON."""
        # Login as player1
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player1.id)

        response = client.post(
            f"/match/matches/{in_progress_match.id}/forfeit",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["winner_id"] == player2.id
        assert "message" in data

    def test_forfeit_endpoint_updates_match_status(
        self, client, player1, player2, in_progress_match
    ):
        """Forfeit endpoint should update match to COMPLETED."""
        # Login as player1
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player1.id)

        client.post(f"/match/matches/{in_progress_match.id}/forfeit")

        # Reload from DB
        updated_match = db.session.get(IndividualMatch, in_progress_match.id)
        assert updated_match.status == MatchStatus.COMPLETED
        assert updated_match.winner_id == player2.id

    def test_forfeit_endpoint_fails_for_non_player(
        self, client, player1, player2, other_player, in_progress_match
    ):
        """Forfeit endpoint should fail for non-players."""
        # Login as other_player (not in match)
        with client.session_transaction() as sess:
            sess["_user_id"] = str(other_player.id)

        response = client.post(
            f"/match/matches/{in_progress_match.id}/forfeit",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "not a player" in data["error"].lower()

    def test_forfeit_endpoint_fails_for_completed_match(
        self, client, player1, completed_match
    ):
        """Forfeit endpoint should fail for completed matches."""
        # Login as player1
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player1.id)

        response = client.post(
            f"/match/matches/{completed_match.id}/forfeit",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_forfeit_keeps_racks_already_played(
        self, client, player1, player2, match_with_scores
    ):
        """Forfeit should preserve the forfeiting player's racks."""
        # Login as player1 (who will forfeit)
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player1.id)

        # Player 1 forfeits
        client.post(f"/match/matches/{match_with_scores.id}/forfeit")

        # Verify scores are preserved
        updated_match = db.session.get(IndividualMatch, match_with_scores.id)
        assert updated_match.player1_score == 3  # Unchanged
        assert updated_match.player2_score == 5  # Gets winning score
        assert updated_match.winner_id == player2.id

    def test_forfeit_endpoint_redirects_for_non_json(
        self, client, player1, player2, in_progress_match
    ):
        """Forfeit endpoint should redirect for non-JSON requests."""
        # Login as player1
        with client.session_transaction() as sess:
            sess["_user_id"] = str(player1.id)

        # Non-JSON request should redirect
        response = client.post(f"/match/matches/{in_progress_match.id}/forfeit")

        assert response.status_code == 302  # Redirect
