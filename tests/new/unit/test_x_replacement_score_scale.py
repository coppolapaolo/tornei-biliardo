"""Regression: il bye da X-replacement usa la distanza del round, non lo score.

Bug (code review 2026-06-09, HIGH correttezza) —
`models/challenge/services.py:414`:

_create_x_replacement_match_result impostava
`match.player1_score = max(1, attempt.score or 0)`, cioè lo score grezzo della
challenge (scala arbitraria, es. 0-15) usato come numero di rack vinti sul
bye match. I bye normali usano invece `round_distance` (= gara.distance).
Risultato: un bye via X-replacement con score 12 in una gara "race to 5"
gonfiava racks_won a 12 in classifica rispetto agli altri bye (che valgono 5).
Inoltre violava ADR-027 (lo score non passava per effective_distance).
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models.competition.models import Gara
from models.challenge.models import Challenge, ChallengeAttempt
from models.match.models import Match
from models.user.models import User
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus
from models.challenge.services import ChallengeService


def _user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    u = User(
        username=f"x_{uid}", email=f"x_{uid}@test.local", role=UserRole.PLAYER.value
    )
    u.set_password("p")
    db_session.add(u)
    db_session.flush()
    return u


@pytest.mark.unit
def test_x_replacement_bye_uses_round_distance_not_raw_score(db_session):
    count = db_session.query(Gara).count()
    gara = Gara(
        name=f"X-repl gara {count + 1}",
        number=count + 1,
        date=date.today(),
        distance=5,  # race to 5
        discipline="palla_9",
        status=GaraStatus.PLAYING.value,
        is_race_to=True,
        rounds_count=3,
        current_round=1,
    )
    db_session.add(gara)
    db_session.flush()

    player = _user(db_session)
    challenge = Challenge(
        description="Spot shot",
        image_path="x.png",
        pass_fail_only=False,
        created_by_id=player.id,
    )
    db_session.add(challenge)
    db_session.flush()

    attempt = ChallengeAttempt(
        challenge_id=challenge.id,
        user_id=player.id,
        gara_id=gara.id,
        round_number=1,
        score=12,  # scala arbitraria, ben oltre i 5 rack della gara
        completed=True,
    )
    db_session.add(attempt)
    db_session.flush()

    ChallengeService._create_x_replacement_match_result(attempt)

    match = Match.query.filter_by(
        gara_id=gara.id, round_number=1, player1_id=player.id, is_bye=True
    ).first()
    assert match is not None
    # Prima del fix: player1_score == 12 (score grezzo). Dopo: 5 (gara.distance).
    assert match.player1_score == 5
    assert match.player2_score == 0
