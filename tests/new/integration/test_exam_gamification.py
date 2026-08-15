"""XP, streak e achievement dell'esame — e la riga che li separa.

La regola del dominio: **solo la sessione certificata e superata vale una
certificazione**. Il tentativo in autonomia è allenamento; contribuisce
all'abitudine settimanale ma non al curriculum.

Qui si verifica che quella riga sia davvero nel codice e non solo nel piano.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.events.base import EventBus
from models.exam.models import Exam, ExamAttempt
from models.gamification.models import (
    StreakTracker,
    StreakType,
    XPTransaction,
    XPTransactionType,
)
from models.status_enum import ExamAttemptMode, ExamAttemptStatus
from models.user.models import User
from models.user.role_enum import UserRole


@pytest.fixture(autouse=True)
def preserve_handlers():
    """Mai azzerare ``EventBus._handlers``: si preserva e si ripristina."""
    original = {k: list(v) for k, v in EventBus._handlers.items()}
    yield
    EventBus._handlers = original


def _user(role: str = UserRole.PLAYER.value) -> User:
    user = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        role=role,
    )
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def player(db_session) -> User:
    return _user()


@pytest.fixture
def examiner(db_session) -> User:
    return _user()


@pytest.fixture
def exam(db_session, examiner) -> Exam:
    """Un esame con un drill: senza, il service rifiuta di aprire un tentativo."""
    from models.challenge.models import Challenge
    from models.exam.models import ExamChallenge

    exam = Exam(
        name=f"Esame {uuid.uuid4().hex[:6]}",
        description="",
        examiner_id=examiner.id,
        is_active=True,
    )
    db.session.add(exam)
    db.session.flush()

    challenge = Challenge(
        description=f"Drill {uuid.uuid4().hex[:6]}",
        image_path="challenges/placeholder.png",
        pass_fail_only=True,
    )
    db.session.add(challenge)
    db.session.flush()

    db.session.add(ExamChallenge(exam_id=exam.id, challenge_id=challenge.id, order=1))
    db.session.commit()
    return exam


def _publish_completion(
    player: User,
    exam: Exam,
    examiner: User,
    *,
    mode: str = ExamAttemptMode.CERTIFIED.value,
    passed: bool | None = True,
) -> None:
    """Chiude un tentativo pubblicando l'evento, come fa ``complete_attempt``."""
    from models.exam.events import ExamAttemptCompletedEvent

    attempt = ExamAttempt(
        exam_id=exam.id,
        user_id=player.id,
        mode=mode,
        status=ExamAttemptStatus.COMPLETED.value,
        passed=passed,
        examiner_id=examiner.id if mode == ExamAttemptMode.CERTIFIED.value else None,
    )
    db.session.add(attempt)
    db.session.commit()

    EventBus.publish(
        ExamAttemptCompletedEvent(
            attempt_id=attempt.id,
            exam_id=exam.id,
            exam_name=exam.name,
            user_id=player.id,
            mode=mode,
            passed=passed,
            examiner_id=attempt.examiner_id,
        )
    )
    db.session.commit()


def _xp_rows(user: User, xp_type: XPTransactionType) -> list[XPTransaction]:
    return XPTransaction.query.filter_by(
        user_id=user.id, transaction_type=xp_type
    ).all()


def _streak(user: User, streak_type: StreakType) -> int:
    tracker = StreakTracker.query.filter_by(
        user_id=user.id, streak_type=streak_type
    ).first()
    return tracker.current_streak if tracker else 0


class TestCertifiedExam:
    def test_passing_pays_the_certification_xp(
        self, db_session, player, exam, examiner
    ):
        _publish_completion(player, exam, examiner)
        assert len(_xp_rows(player, XPTransactionType.EXAM_CERTIFIED)) == 1

    def test_failing_pays_nothing(self, db_session, player, exam, examiner):
        """Non è una punizione: il tentativo si ripete, e pagare le bocciature
        renderebbe conveniente collezionarle."""
        _publish_completion(player, exam, examiner, passed=False)
        assert _xp_rows(player, XPTransactionType.EXAM_CERTIFIED) == []
        assert _xp_rows(player, XPTransactionType.EXAM_PRACTICE) == []

    def test_showing_up_counts_for_the_weekly_habit_even_if_failed(
        self, db_session, player, exam, examiner
    ):
        _publish_completion(player, exam, examiner, passed=False)
        assert _streak(player, StreakType.WEEKLY_DRILL) >= 1


class TestSelfPractice:
    def test_practising_pays_the_training_xp_only(
        self, db_session, player, exam, examiner
    ):
        _publish_completion(
            player,
            exam,
            examiner,
            mode=ExamAttemptMode.SELF_PRACTICE.value,
            passed=None,
        )
        assert len(_xp_rows(player, XPTransactionType.EXAM_PRACTICE)) == 1
        assert _xp_rows(player, XPTransactionType.EXAM_CERTIFIED) == []

    def test_the_training_xp_is_worth_less_than_the_certification(self):
        """Se le due tariffe si pareggiassero, allenarsi da soli varrebbe
        quanto farsi certificare — e il dominio perderebbe il suo centro."""
        from models.gamification.config_service import (
            GamificationConfigService as ConfigService,
        )

        practice = ConfigService.get_xp_rate(XPTransactionType.EXAM_PRACTICE)
        certified = ConfigService.get_xp_rate(XPTransactionType.EXAM_CERTIFIED)
        assert 0 < practice < certified

    def test_practising_still_feeds_the_weekly_drill_streak(
        self, db_session, player, exam, examiner
    ):
        _publish_completion(
            player,
            exam,
            examiner,
            mode=ExamAttemptMode.SELF_PRACTICE.value,
            passed=None,
        )
        assert _streak(player, StreakType.WEEKLY_DRILL) >= 1


class TestTheServiceEmitsTheEvent:
    def test_completing_an_attempt_publishes_it(self, db_session, player, exam):
        """L'aggancio vero: senza questo, l'handler resterebbe teoria."""
        from models.exam.events import ExamAttemptCompletedEvent
        from models.exam.services import ExamService

        received = []
        EventBus.register_handler(
            ExamAttemptCompletedEvent, lambda e: received.append(e)
        )

        attempt = ExamService.start_self_practice(player, exam.id)
        ExamService.complete_attempt(attempt.id, player)
        db.session.commit()

        assert len(received) == 1
        assert received[0].user_id == player.id
        assert received[0].mode == ExamAttemptMode.SELF_PRACTICE.value
        assert received[0].is_certification is False

    def test_an_abandoned_attempt_publishes_nothing(self, db_session, player, exam):
        """Chi non si presenta non ha completato niente: niente XP, niente streak."""
        from models.exam.events import ExamAttemptCompletedEvent
        from models.exam.services import ExamService

        received = []
        EventBus.register_handler(
            ExamAttemptCompletedEvent, lambda e: received.append(e)
        )

        attempt = ExamService.start_self_practice(player, exam.id)
        ExamService.abandon_attempt(attempt.id, player)
        db.session.commit()

        assert received == []

    def test_a_broken_handler_does_not_lose_the_certification(
        self, db_session, player, exam
    ):
        """La gamification è un di più: se esplode, l'esame resta registrato."""
        from models.exam.events import ExamAttemptCompletedEvent
        from models.exam.services import ExamService

        def _explode(event):
            raise RuntimeError("boom")

        EventBus.register_handler(ExamAttemptCompletedEvent, _explode)

        attempt = ExamService.start_self_practice(player, exam.id)
        ExamService.complete_attempt(attempt.id, player)
        db.session.commit()

        reloaded = db.session.get(ExamAttempt, attempt.id)
        assert reloaded is not None
        assert reloaded.status == ExamAttemptStatus.COMPLETED.value
