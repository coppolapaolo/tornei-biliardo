"""Integration tests for reset blocked by active tiebreaker.

Source: ADR-026 residual (2026-04-19). Spec:
`_bmad-output/implementation-artifacts/spec-reset-blocked-by-tiebreaker.md`.
"""

from __future__ import annotations

from datetime import date
import uuid

import pytest

from models import User
from models.competition.models import Gara, Inscription
from models.competition.round_manager import AdvancedRoundManager
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.tiebreaker.models import Tiebreaker, TiebreakerStatus, TiebreakerType
from models.user.role_enum import UserRole


@pytest.fixture
def director_user(db_session):
    suffix = str(uuid.uuid4())[:8]
    u = User(
        username=f"director_{suffix}",
        email=f"director_{suffix}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def players_pair(db_session):
    suffix = str(uuid.uuid4())[:8]
    players = []
    for i in range(2):
        p = User(
            username=f"tb_player_{i}_{suffix}",
            email=f"tb_player_{i}_{suffix}@test.com",
            role=UserRole.PLAYER.value,
        )
        p.set_password("test1234")
        players.append(p)
    db_session.add_all(players)
    db_session.commit()
    return players


@pytest.fixture
def gara_with_completed_match(director_user, players_pair, db_session):
    """Gara PLAYING con 1 match completato, pronta per riceversi un tiebreaker."""
    existing_count = db_session.query(Gara).count()
    gara = Gara(
        name=f"TB-reset gara {existing_count + 1}",
        number=existing_count + 1,
        date=date.today(),
        distance=5,
        discipline="9_ball",
        matchmaking_strategy="random",
        status=GaraStatus.PLAYING.value,
        is_race_to=True,
        director_id=director_user.id,
    )
    db_session.add(gara)
    db_session.flush()

    p1, p2 = players_pair
    db_session.add(Inscription(gara_id=gara.id, user_id=p1.id))
    db_session.add(Inscription(gara_id=gara.id, user_id=p2.id))

    match = Match(
        gara_id=gara.id,
        player1_id=p1.id,
        player2_id=p2.id,
        round_number=1,
        status=MatchStatus.COMPLETED.value,
        player1_score=5,
        player2_score=3,
        winner_id=p1.id,
    )
    db_session.add(match)
    db_session.commit()
    return gara, match, p1, p2


def _add_tiebreaker(db_session, gara, match, p1, p2, status_value):
    tb = Tiebreaker(
        match_id=match.id,
        gara_id=gara.id,
        tiebreaker_type=TiebreakerType.SPOT_SHOT.value,
        status=status_value,
        player1_id=p1.id,
        player2_id=p2.id,
    )
    db_session.add(tb)
    db_session.commit()
    return tb


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "test1234"},
        follow_redirects=True,
    )


@pytest.mark.integration
class TestResetWithTiebreakerService:
    def test_reset_with_validation_rejects_when_tiebreaker_active(
        self, gara_with_completed_match, db_session
    ):
        gara, match, p1, p2 = gara_with_completed_match
        _add_tiebreaker(
            db_session, gara, match, p1, p2, TiebreakerStatus.COMPLETED.value
        )

        success, message = AdvancedRoundManager.reset_match_with_validation(match.id)

        assert success is False
        assert "spareggio" in message.lower()

        # Verify match was NOT reset (scores preserved)
        db_session.refresh(match)
        assert match.player1_score == 5
        assert match.player2_score == 3
        assert match.winner_id == p1.id
        assert match.status == MatchStatus.COMPLETED.value

    def test_reset_succeeds_after_tiebreaker_cancellation(
        self, gara_with_completed_match, db_session
    ):
        """Director scenario: tiebreaker cancelled → reset unblocked."""
        gara, match, p1, p2 = gara_with_completed_match
        tb = _add_tiebreaker(
            db_session, gara, match, p1, p2, TiebreakerStatus.PENDING.value
        )

        # First attempt blocked
        success, _ = AdvancedRoundManager.reset_match_with_validation(match.id)
        assert success is False

        # Director cancels the tiebreaker
        tb.status = TiebreakerStatus.CANCELLED.value
        db_session.commit()

        # Second attempt succeeds
        success, message = AdvancedRoundManager.reset_match_with_validation(match.id)
        assert success is True, f"Reset should succeed after TB cancel: {message}"


@pytest.mark.integration
class TestResetWithTiebreakerHttp:
    def test_reset_endpoint_flashes_error_when_tiebreaker_active(
        self, client, gara_with_completed_match, director_user, db_session
    ):
        gara, match, p1, p2 = gara_with_completed_match
        _add_tiebreaker(db_session, gara, match, p1, p2, TiebreakerStatus.PENDING.value)
        _login(client, director_user)

        resp = client.post(f"/admin/match/{match.id}/reset", follow_redirects=True)

        assert resp.status_code == 200
        # Flash message must carry the tiebreaker reason (defense-in-depth
        # would be silently undetectable without this assertion)
        body = resp.get_data(as_text=True).lower()
        assert "spareggio" in body
        # Match state must be intact — no reset happened
        db_session.refresh(match)
        assert match.winner_id == p1.id
        assert match.player1_score == 5
        assert match.player2_score == 3
