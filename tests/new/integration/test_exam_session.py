"""Integration test della sessione d'esame certificata (UJ-3/UJ-6, Fase 3).

Dall'appuntamento accettato all'esito. Il punto non è la meccanica dei
punteggi — quella è di Fase 2 — ma i tre confini che rendono la certificazione
un fatto e non un'opinione:

- **nessuno viene valutato a sua insaputa** (US-P6): finché il candidato non
  accetta l'inizio, il *servizio* rifiuta i punteggi. Non la UI: una POST
  diretta la aggira, il servizio no;
- **si certifica solo ciò per cui c'è un appuntamento**: niente sessione senza
  richiesta accettata, e una sola sessione per appuntamento;
- **un esaminatore non si esamina da solo**, in nessun punto del percorso.

Copre US-E6, US-E7, US-P6 e i divieti di UJ-6.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge
from models.exam.models import ExamAttempt
from models.exam.request_service import ExamRequestService
from models.exam.services import ExamService
from models.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ValidationError,
)
from models.location.models import BilliardHall
from models.notification.models import Notification, NotificationType
from models.status_enum import (
    ExamAttemptMode,
    ExamAttemptStatus,
    ExamRequestStatus,
)
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

EXAMINER = GrantableRole.EXAMINER


def _make_user(role: str = UserRole.PLAYER.value) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"{role}_{suffix}",
        email=f"{role}_{suffix}@test.local",
        role=role,
        is_verified=True,
    )
    user.set_password("test1234")
    db.session.add(user)
    db.session.flush()
    return user


def _make_challenge(pass_fail: bool = False) -> Challenge:
    challenge = Challenge(
        description=f"Drill {uuid.uuid4().hex[:6]}",
        image_path="/static/uploads/challenges/x.png",
        pass_fail_only=pass_fail,
    )
    db.session.add(challenge)
    db.session.flush()
    return challenge


def _notifications_of(user_id: int, notification_type: NotificationType) -> int:
    return Notification.query.filter_by(
        user_id=user_id, notification_type=notification_type
    ).count()


@pytest.fixture
def admin(db_session):
    user = _make_user(UserRole.ADMIN.value)
    db_session.commit()
    return user


@pytest.fixture
def examiner(db_session, admin):
    user = _make_user()
    RoleGrantService.grant(user.id, EXAMINER, admin)
    db_session.commit()
    return user


@pytest.fixture
def other_examiner(db_session, admin):
    user = _make_user()
    RoleGrantService.grant(user.id, EXAMINER, admin)
    db_session.commit()
    return user


@pytest.fixture
def player(db_session):
    user = _make_user()
    db_session.commit()
    return user


@pytest.fixture
def hall(db_session):
    venue = BilliardHall(name=f"Biliardo {uuid.uuid4().hex[:6]}", is_active=True)
    db_session.add(venue)
    db_session.commit()
    return venue


@pytest.fixture
def exam(db_session, examiner, other_examiner):
    created = ExamService.create_exam(examiner, "Fondamentali — livello 1")
    ExamService.add_challenge_to_exam(
        created.id, _make_challenge().id, examiner, max_score=10
    )
    ExamService.add_challenge_to_exam(
        created.id, _make_challenge(pass_fail=True).id, examiner
    )
    ExamService.add_examiner(created.id, other_examiner.id, examiner)
    db_session.commit()
    return created


@pytest.fixture
def negotiating_request(db_session, exam, player, hall):
    created = ExamRequestService.create_request(
        player,
        exam.id,
        scheduled_at=utc_now() + timedelta(days=3),
        billiard_hall_id=hall.id,
    )
    db_session.commit()
    return created


@pytest.fixture
def appointment(db_session, negotiating_request, examiner):
    """L'appuntamento fissato: l'esaminatore ha accettato."""
    ExamRequestService.accept(negotiating_request.id, examiner)
    db_session.commit()
    return negotiating_request


class TestOpeningTheSession:
    """US-E6 — la sessione nasce dall'appuntamento, non dal nulla."""

    def test_the_session_opens_awaiting_the_candidate(
        self, db_session, appointment, examiner, player, hall, exam
    ):
        attempt = ExamService.open_certified_session(examiner, appointment.id)
        db_session.commit()

        assert attempt.mode == ExamAttemptMode.CERTIFIED.value
        assert attempt.status == ExamAttemptStatus.AWAITING_PLAYER_START.value
        assert attempt.user_id == player.id
        assert attempt.examiner_id == examiner.id
        assert attempt.billiard_hall_id == hall.id
        assert attempt.exam_request_id == appointment.id
        assert attempt.exam_id == exam.id
        assert attempt.passed is None
        # I risultati vuoti ci sono già: l'esaminatore li riempie uno a uno.
        assert attempt.challenge_results.count() == exam.challenges.count()
        assert _notifications_of(player.id, NotificationType.EXAM_SESSION_OPENED) == 1

    def test_no_session_without_an_accepted_appointment(
        self, negotiating_request, examiner
    ):
        with pytest.raises(ConflictError):
            ExamService.open_certified_session(examiner, negotiating_request.id)

    def test_only_the_examiner_who_accepted_opens_the_session(
        self, appointment, other_examiner, player
    ):
        with pytest.raises(PermissionDeniedError):
            ExamService.open_certified_session(other_examiner, appointment.id)
        with pytest.raises(PermissionDeniedError):
            ExamService.open_certified_session(player, appointment.id)

    def test_one_session_per_appointment(self, db_session, appointment, examiner):
        ExamService.open_certified_session(examiner, appointment.id)
        db_session.commit()

        with pytest.raises(ConflictError):
            ExamService.open_certified_session(examiner, appointment.id)

    def test_an_examiner_cannot_examine_himself(
        self, db_session, appointment, examiner
    ):
        """Il divieto vale anche se l'appuntamento fosse arrivato storto."""
        appointment.requester_id = examiner.id
        db_session.commit()

        with pytest.raises(PermissionDeniedError):
            ExamService.open_certified_session(examiner, appointment.id)


class TestTheCandidateAcceptsTheStart:
    """US-P6 — nessuno viene valutato a sua insaputa."""

    @pytest.fixture
    def session(self, db_session, appointment, examiner):
        attempt = ExamService.open_certified_session(examiner, appointment.id)
        db_session.commit()
        return attempt

    def test_no_score_can_be_recorded_before_the_candidate_accepts(
        self, session, examiner, exam
    ):
        first_drill = exam.challenges.first()
        with pytest.raises(ConflictError):
            ExamService.record_challenge_result(
                session.id, first_drill.id, examiner, score=8
            )

    def test_the_session_cannot_be_closed_before_it_starts(self, session, examiner):
        with pytest.raises(ConflictError):
            ExamService.complete_attempt(session.id, examiner, passed=True)

    def test_only_the_candidate_accepts_the_start(
        self, session, examiner, other_examiner
    ):
        for actor in (examiner, other_examiner):
            with pytest.raises(PermissionDeniedError):
                ExamService.accept_session_start(session.id, actor)

    def test_accepting_puts_the_session_in_progress(self, db_session, session, player):
        started = ExamService.accept_session_start(session.id, player)
        db_session.commit()

        assert started.status == ExamAttemptStatus.IN_PROGRESS.value

    def test_the_start_is_accepted_once(self, db_session, session, player):
        ExamService.accept_session_start(session.id, player)
        db_session.commit()

        with pytest.raises(ConflictError):
            ExamService.accept_session_start(session.id, player)

    def test_a_self_practice_attempt_has_nothing_to_accept(
        self, db_session, exam, player
    ):
        attempt = ExamService.start_self_practice(player, exam.id)
        db_session.commit()

        with pytest.raises(ConflictError):
            ExamService.accept_session_start(attempt.id, player)


class TestCertification:
    """US-E7 — l'esito è un fatto netto: superato o non superato."""

    @pytest.fixture
    def started(self, db_session, appointment, examiner, player):
        attempt = ExamService.open_certified_session(examiner, appointment.id)
        db_session.commit()
        ExamService.accept_session_start(attempt.id, player)
        db_session.commit()
        return attempt

    def test_the_examiner_scores_and_certifies(
        self, db_session, started, examiner, player, exam, hall
    ):
        numeric, pass_fail = exam.challenges.all()
        ExamService.record_challenge_result(started.id, numeric.id, examiner, score=8)
        ExamService.record_challenge_result(
            started.id, pass_fail.id, examiner, passed=True
        )
        db_session.commit()

        certified = ExamService.complete_attempt(started.id, examiner, passed=True)
        db_session.commit()

        fresh = db.session.get(ExamAttempt, certified.id)
        assert fresh is not None
        assert fresh.status == ExamAttemptStatus.COMPLETED.value
        assert fresh.passed is True
        assert fresh.certified_at is not None
        assert fresh.is_certified is True
        # Somma semplice: 8 su 10 al drill numerico, 1 su 1 al pass/fail.
        assert (fresh.total_score, fresh.max_possible_score) == (9, 11)
        assert fresh.billiard_hall_id == hall.id
        assert _notifications_of(player.id, NotificationType.EXAM_CERTIFIED) == 1

    def test_failing_is_certified_too(self, db_session, started, examiner):
        certified = ExamService.complete_attempt(started.id, examiner, passed=False)
        db_session.commit()

        assert certified.passed is False
        assert certified.is_certified is True

    def test_the_candidate_does_not_score_his_own_certified_session(
        self, started, player, exam
    ):
        numeric = exam.challenges.first()
        with pytest.raises(PermissionDeniedError):
            ExamService.record_challenge_result(
                started.id, numeric.id, player, score=10
            )
        with pytest.raises(PermissionDeniedError):
            ExamService.complete_attempt(started.id, player, passed=True)

    def test_a_certified_session_needs_an_outcome(self, started, examiner):
        with pytest.raises(ValidationError):
            ExamService.complete_attempt(started.id, examiner)

    def test_a_no_show_is_abandoned_and_is_not_a_failure(
        self, db_session, appointment, examiner
    ):
        attempt = ExamService.open_certified_session(examiner, appointment.id)
        db_session.commit()

        abandoned = ExamService.abandon_attempt(attempt.id, examiner)
        db_session.commit()

        assert abandoned.status == ExamAttemptStatus.ABANDONED.value
        assert abandoned.passed is None
        assert abandoned.is_certified is False

    def test_repeating_a_failed_exam_needs_a_fresh_request(
        self, db_session, started, examiner, player, exam, hall
    ):
        """UJ-6: si ripete aprendo una richiesta nuova, non riusando la vecchia."""
        ExamService.complete_attempt(started.id, examiner, passed=False)
        db_session.commit()

        again = ExamRequestService.create_request(
            player,
            exam.id,
            scheduled_at=utc_now() + timedelta(days=10),
            billiard_hall_id=hall.id,
        )
        db_session.commit()

        assert again.status == ExamRequestStatus.NEGOTIATING.value
        assert again.id != started.exam_request_id
