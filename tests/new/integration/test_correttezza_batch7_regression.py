"""Regression (review 2026-06, batch 7): bug di correttezza nelle route.

Triage 2026-06-10 della sezione "Da ri-verificare a mano" del report
docs/_archive/2026-06-09-codebase-review-uncovered.md.
"""

import uuid
from datetime import date, time, timedelta

import pytest

from models import Challenge, db
from models.base import utc_now
from models.competition.gara_challenge import GaraChallenge
from models.competition.models import Gara
from models.status_enum import GaraStatus
from models.user.models import User


def _make_user(db_session, role):
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"b7_{role}_{uid}", email=f"b7_{role}_{uid}@t.com", role=role)
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return db_session.get(User, user.id)


def _login(client, user):
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=True,
    )


@pytest.fixture
def director_user(db_session):
    return _make_user(db_session, "director")


@pytest.fixture
def player_user(db_session):
    return _make_user(db_session, "player")


@pytest.fixture
def random_gara_with_challenge(db_session, director_user, player_user):
    """Gara Random gestita dal director, con una GaraChallenge attiva."""
    uid = uuid.uuid4().hex[:8]
    gara = Gara(
        name=f"B7 Random {uid}",
        number=1,
        date=date.today() + timedelta(days=7),
        time=time(18, 0),
        discipline="palla_8",
        distance=5,
        rounds_count=3,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="random",
        director_id=director_user.id,
        status=GaraStatus.PLAYING.value,
        inscription_start=utc_now() - timedelta(days=1),
        inscription_end=utc_now() - timedelta(hours=1),
    )
    db_session.add(gara)
    db_session.flush()

    challenge = Challenge(
        description="Challenge batch 7",
        image_path="b7.jpg",
        pass_fail_only=True,
        created_by_id=director_user.id,
        is_active=True,
    )
    db_session.add(challenge)
    db_session.flush()

    gara_challenge = GaraChallenge(
        gara_id=gara.id,
        challenge_id=challenge.id,
        round_number=1,
        max_attempts=3,
        is_active=True,
        added_by_id=director_user.id,
    )
    db_session.add(gara_challenge)
    db_session.commit()
    return gara, gara_challenge


class TestRecordChallengeAttemptRoutes:
    """Bug 1: @match_manager_required su route senza <match_id> → 400 sempre.

    Le route /admin/match/record_challenge_attempt(s) non hanno match_id
    nell'URL: il decorator abortiva ogni richiesta con 400 e la registrazione
    challenge da pannello admin era morta. L'autorizzazione corretta e' sulla
    GARA della challenge.
    """

    def test_director_can_record_attempt(
        self, client, db_session, director_user, player_user, random_gara_with_challenge
    ):
        _, gara_challenge = random_gara_with_challenge
        _login(client, director_user)

        response = client.post(
            "/admin/match/record_challenge_attempt",
            json={
                "gara_challenge_id": gara_challenge.id,
                "user_id": player_user.id,
                "passed": True,
            },
        )

        assert response.status_code == 200
        assert response.get_json()["success"] is True

    def test_director_can_record_attempts_bulk(
        self, client, db_session, director_user, player_user, random_gara_with_challenge
    ):
        _, gara_challenge = random_gara_with_challenge
        _login(client, director_user)

        response = client.post(
            "/admin/match/record_challenge_attempts",
            json={
                "attempts": [
                    {
                        "gara_challenge_id": gara_challenge.id,
                        "user_id": player_user.id,
                        "passed": True,
                    }
                ]
            },
        )

        assert response.status_code == 200
        assert response.get_json()["success"] is True

    def test_unrelated_player_gets_403(
        self, client, db_session, player_user, random_gara_with_challenge
    ):
        """Un player che NON gestisce la gara non puo' registrare tentativi."""
        _, gara_challenge = random_gara_with_challenge
        _login(client, player_user)

        response = client.post(
            "/admin/match/record_challenge_attempt",
            json={
                "gara_challenge_id": gara_challenge.id,
                "user_id": player_user.id,
                "passed": True,
            },
        )

        assert response.status_code == 403
