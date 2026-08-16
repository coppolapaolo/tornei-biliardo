"""Un drill completato paga XP e muove la streak settimanale.

Il docstring di ``models/gamification/event_handlers.py`` prometteva questo
handler da sempre — «Challenge (drill) completion (training XP + weekly drill
streak)» — ma l'handler non esisteva: allenarsi non contava niente, e la
``WEEKLY_DRILL`` restava a zero per chiunque non facesse esami.

Le due origini non sono simmetriche di proposito, ed è la parte che questi test
presidiano: la streak scatta da entrambe (allenarsi è allenarsi), l'XP no —
in gara la stessa prova si ripete fino a ``max_attempts`` nello stesso turno, e
pagarle tutte moltiplicherebbe l'XP di un allenamento per il numero di tiri.
"""

from __future__ import annotations

import uuid

import pytest

from models import db
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.services import ChallengeService
from models.events.base import EventBus
from models.gamification.models import (
    StreakTracker,
    StreakType,
    XPTransaction,
    XPTransactionType,
)
from models.user.models import User
from models.user.role_enum import UserRole


@pytest.fixture(autouse=True)
def preserve_handlers():
    """Gli handler sono globali: si preservano, non si azzerano."""
    original = {k: list(v) for k, v in EventBus._handlers.items()}
    yield
    EventBus._handlers = original


@pytest.fixture
def player(db_session) -> User:
    user = User(
        username=f"drill_{uuid.uuid4().hex[:8]}",
        email=f"drill_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("test123")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def drill(db_session) -> Challenge:
    challenge = Challenge(
        description="Spot shot rally da dieci bilie",
        image_path="/static/challenges/spot.jpg",
        is_active=True,
    )
    db_session.add(challenge)
    db_session.commit()
    return challenge


def _drill_xp(user_id: int) -> list[XPTransaction]:
    return XPTransaction.query.filter_by(
        user_id=user_id,
        transaction_type=XPTransactionType.CHALLENGE_COMPLETION,
    ).all()


def _streak(user_id: int, streak_type: StreakType) -> int:
    tracker = StreakTracker.query.filter_by(
        user_id=user_id, streak_type=streak_type
    ).first()
    return tracker.current_streak if tracker else 0


def test_a_catalog_drill_pays_xp(player, drill, db_session):
    attempt = ChallengeService.start_challenge_attempt(
        user_id=player.id, challenge_id=drill.id
    )
    ChallengeService.complete_challenge_attempt(attempt_id=attempt.id, score=12)

    transactions = _drill_xp(player.id)
    assert len(transactions) == 1
    assert transactions[0].xp_amount > 0


def test_a_catalog_drill_moves_the_weekly_drill_streak(player, drill, db_session):
    attempt = ChallengeService.start_challenge_attempt(
        user_id=player.id, challenge_id=drill.id
    )
    ChallengeService.complete_challenge_attempt(attempt_id=attempt.id, score=12)

    assert _streak(player.id, StreakType.WEEKLY_DRILL) == 1
    # Un drill è anche attività: la streak generica non deve restare indietro.
    assert _streak(player.id, StreakType.WEEKLY_ACTIVITY) == 1


def test_a_failed_drill_pays_just_the_same(player, db_session):
    """Quello che si premia è essersi allenati, non aver azzeccato la prova."""
    pass_fail = Challenge(
        description="Prova pass/fail per il test dello sbagliato",
        image_path="/static/challenges/pf.jpg",
        pass_fail_only=True,
        is_active=True,
    )
    db_session.add(pass_fail)
    db_session.commit()

    attempt = ChallengeService.start_challenge_attempt(
        user_id=player.id, challenge_id=pass_fail.id
    )
    ChallengeService.complete_challenge_attempt(attempt_id=attempt.id, passed=False)

    assert len(_drill_xp(player.id)) == 1
    assert _streak(player.id, StreakType.WEEKLY_DRILL) == 1


def test_two_catalog_sessions_pay_twice(player, drill, db_session):
    """Dal catalogo ogni tentativo è una sessione: allenarsi di più paga di più."""
    for _ in range(2):
        attempt = ChallengeService.start_challenge_attempt(
            user_id=player.id, challenge_id=drill.id
        )
        ChallengeService.complete_challenge_attempt(attempt_id=attempt.id, score=10)

    assert len(_drill_xp(player.id)) == 2
    # La streak è settimanale: due allenamenti nella stessa settimana valgono
    # comunque una settimana sola.
    assert _streak(player.id, StreakType.WEEKLY_DRILL) == 1


def test_a_gara_drill_pays_once_no_matter_how_many_attempts(player, drill, db_session):
    """In gara i tentativi sono la stessa prova, non tre allenamenti."""
    from datetime import date, timedelta

    from models.competition.gara_challenge_service import GaraChallengeService
    from models.competition.services import GaraService

    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Gara con drill",
        date=date.today() + timedelta(days=7),
        director_id=player.id,
        discipline="8_ball",
        distance=5,
        max_participants=8,
    )
    gara_challenge = GaraChallengeService.add_challenge_to_gara(
        gara_id=gara.id,
        challenge_id=drill.id,
        round_number=1,
        max_attempts=3,
        added_by_id=player.id,
    )

    for score in (8, 11, 14):
        GaraChallengeService.record_challenge_attempt(
            gara_challenge_id=gara_challenge.id,
            user_id=player.id,
            score=score,
        )

    assert len(_drill_xp(player.id)) == 1, "i tiri ripetuti non sono drill nuovi"
    assert _streak(player.id, StreakType.WEEKLY_DRILL) == 1


def test_the_handler_never_blocks_the_drill(player, drill, db_session, monkeypatch):
    """Se la gamification esplode, il punteggio resta registrato lo stesso."""
    from models.gamification.level_service import LevelService

    def boom(*args, **kwargs):
        raise RuntimeError("gamification giù")

    monkeypatch.setattr(LevelService, "award_xp", boom)

    attempt = ChallengeService.start_challenge_attempt(
        user_id=player.id, challenge_id=drill.id
    )
    ChallengeService.complete_challenge_attempt(attempt_id=attempt.id, score=9)

    stored = db.session.get(ChallengeAttempt, attempt.id)
    assert stored.completed is True
    assert stored.score == 9
