"""Integration test del tentativo in autonomia (UJ-2, Fase 2).

Il punto della modalità non è che esista: è che **non certifichi mai**. Il
player si allena, registra i punteggi, chiude — e il tentativo resta un
allenamento, senza esito, senza esaminatore, senza data di certificazione.
Nessun percorso lo trasforma in certificato, nemmeno a posteriori.

Copre US-P3 e la variante «abbandona a metà e riprende lo stesso tentativo».
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.exam.models import ExamAttempt
from models.exam.services import ExamService
from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from models.status_enum import ExamAttemptMode, ExamAttemptStatus
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
def player(db_session):
    user = _make_user()
    db_session.commit()
    return user


@pytest.fixture
def exam(db_session, examiner):
    """«Fondamentali — livello 1»: 10 punti, pass/fail, 15 punti."""
    created = ExamService.create_exam(examiner, "Fondamentali — livello 1")
    ExamService.add_challenge_to_exam(
        created.id, _make_challenge().id, examiner, max_score=10
    )
    ExamService.add_challenge_to_exam(
        created.id, _make_challenge(pass_fail=True).id, examiner
    )
    ExamService.add_challenge_to_exam(
        created.id, _make_challenge().id, examiner, max_score=15
    )
    db_session.flush()
    return created


def _drills(exam):
    return exam.challenges.all()


class TestSelfPracticeRun:
    """UJ-2 — il player prova l'esame da solo."""

    def test_a_full_run_records_scores_and_stays_uncertified(self, exam, player):
        attempt = ExamService.start_self_practice(player, exam.id)
        assert attempt.mode == ExamAttemptMode.SELF_PRACTICE.value
        assert attempt.status == ExamAttemptStatus.IN_PROGRESS.value
        assert attempt.challenge_results.count() == 3

        first, second, third = _drills(exam)
        ExamService.record_challenge_result(attempt.id, first.id, player, score=8)
        ExamService.record_challenge_result(attempt.id, second.id, player, passed=True)
        ExamService.record_challenge_result(attempt.id, third.id, player, score=7)

        assert attempt.get_progress()["is_complete"] is True

        ExamService.complete_attempt(attempt.id, player)

        assert attempt.status == ExamAttemptStatus.COMPLETED.value
        assert attempt.total_score == 16
        assert attempt.max_possible_score == 26
        # Il cuore della storia: nessuna certificazione.
        assert attempt.passed is None
        assert attempt.examiner_id is None
        assert attempt.certified_at is None
        assert attempt.is_certified is False

    def test_completing_with_an_outcome_is_refused(self, exam, player):
        """«Superato» non si autoassegna: l'esito esiste solo se certificato."""
        attempt = ExamService.start_self_practice(player, exam.id)

        with pytest.raises(ValidationError):
            ExamService.complete_attempt(attempt.id, player, passed=True)

        assert attempt.status == ExamAttemptStatus.IN_PROGRESS.value
        assert attempt.passed is None

    def test_self_practice_never_appears_among_certified_attempts(self, exam, player):
        attempt = ExamService.start_self_practice(player, exam.id)
        ExamService.complete_attempt(attempt.id, player)

        assert [a.id for a in ExamService.get_user_exam_attempts(player.id)] == [
            attempt.id
        ]
        assert ExamService.get_user_exam_attempts(player.id, certified_only=True) == []


class TestResumeAndAbandon:
    """La variante di UJ-2: si lascia a metà e si riprende **lo stesso** tentativo."""

    def test_starting_again_resumes_the_open_attempt(self, exam, player):
        attempt = ExamService.start_self_practice(player, exam.id)
        first = _drills(exam)[0]
        ExamService.record_challenge_result(attempt.id, first.id, player, score=6)

        resumed = ExamService.start_self_practice(player, exam.id)

        assert resumed.id == attempt.id
        assert resumed.get_progress()["completed_challenges"] == 1
        assert (
            ExamAttempt.query.filter_by(user_id=player.id, exam_id=exam.id).count() == 1
        )

    def test_a_second_open_attempt_is_refused_by_the_database(self, exam, player):
        """Indice UNIQUE parziale: un solo allenamento aperto per esame."""
        from sqlalchemy.exc import IntegrityError

        ExamService.start_self_practice(player, exam.id)

        db.session.add(
            ExamAttempt(
                exam_id=exam.id,
                user_id=player.id,
                mode=ExamAttemptMode.SELF_PRACTICE.value,
                status=ExamAttemptStatus.IN_PROGRESS.value,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()

    def test_after_completing_a_new_attempt_can_start(self, exam, player):
        first = ExamService.start_self_practice(player, exam.id)
        ExamService.complete_attempt(first.id, player)

        second = ExamService.start_self_practice(player, exam.id)

        assert second.id != first.id
        assert second.status == ExamAttemptStatus.IN_PROGRESS.value

    def test_abandoning_leaves_no_outcome(self, exam, player):
        attempt = ExamService.start_self_practice(player, exam.id)

        ExamService.abandon_attempt(attempt.id, player)

        assert attempt.status == ExamAttemptStatus.ABANDONED.value
        assert attempt.passed is None
        assert attempt.is_certified is False
        with pytest.raises(ConflictError):
            ExamService.abandon_attempt(attempt.id, player)


class TestSelfPracticeGuards:
    """Chi scrive, su cosa, e quando."""

    def test_only_the_owner_records_his_own_scores(self, exam, player, examiner):
        attempt = ExamService.start_self_practice(player, exam.id)
        first = _drills(exam)[0]

        with pytest.raises(PermissionDeniedError):
            ExamService.record_challenge_result(attempt.id, first.id, examiner, score=9)

    def test_scores_must_match_the_kind_of_drill(self, exam, player):
        attempt = ExamService.start_self_practice(player, exam.id)
        numeric, pass_fail, _ = _drills(exam)

        with pytest.raises(ValidationError):
            ExamService.record_challenge_result(
                attempt.id, numeric.id, player, passed=True
            )
        with pytest.raises(ValidationError):
            ExamService.record_challenge_result(
                attempt.id, pass_fail.id, player, score=1
            )

    def test_score_out_of_range_is_refused(self, exam, player):
        attempt = ExamService.start_self_practice(player, exam.id)
        numeric = _drills(exam)[0]

        with pytest.raises(ValidationError):
            ExamService.record_challenge_result(
                attempt.id, numeric.id, player, score=11
            )
        with pytest.raises(ValidationError):
            ExamService.record_challenge_result(
                attempt.id, numeric.id, player, score=-1
            )

    def test_a_pass_fail_result_scores_one_and_zero(self, exam, player):
        attempt = ExamService.start_self_practice(player, exam.id)
        pass_fail = _drills(exam)[1]

        result = ExamService.record_challenge_result(
            attempt.id, pass_fail.id, player, passed=False
        )
        assert (result.score, result.passed) == (0, False)

        result = ExamService.record_challenge_result(
            attempt.id, pass_fail.id, player, passed=True
        )
        assert (result.score, result.passed) == (1, True)

    def test_nothing_can_be_recorded_on_a_closed_attempt(self, exam, player):
        attempt = ExamService.start_self_practice(player, exam.id)
        first = _drills(exam)[0]
        ExamService.complete_attempt(attempt.id, player)

        with pytest.raises(ConflictError):
            ExamService.record_challenge_result(attempt.id, first.id, player, score=5)

    def test_scores_cannot_be_recorded_before_the_player_accepts_the_start(
        self, exam, player, examiner
    ):
        """US-P6, presidiato dal servizio e non dalla sola UI.

        La sessione certificata arriva in Fase 3, ma l'invariante è del
        tentativo: in ``awaiting_player_start`` non si registra nulla.
        """
        attempt = ExamAttempt(
            exam_id=exam.id,
            user_id=player.id,
            examiner_id=examiner.id,
            mode=ExamAttemptMode.CERTIFIED.value,
            status=ExamAttemptStatus.AWAITING_PLAYER_START.value,
        )
        db.session.add(attempt)
        db.session.flush()
        attempt.create_placeholder_results()
        db.session.flush()

        first = _drills(exam)[0]
        with pytest.raises(ConflictError):
            ExamService.record_challenge_result(attempt.id, first.id, examiner, score=9)

    def test_an_examiner_cannot_administer_an_exam_to_himself(self, exam, examiner):
        """UJ-6: auto-somministrazione vietata."""
        attempt = ExamAttempt(
            exam_id=exam.id,
            user_id=examiner.id,
            examiner_id=examiner.id,
            mode=ExamAttemptMode.CERTIFIED.value,
            status=ExamAttemptStatus.IN_PROGRESS.value,
        )
        db.session.add(attempt)
        db.session.flush()
        attempt.create_placeholder_results()
        db.session.flush()

        first = _drills(exam)[0]
        with pytest.raises(PermissionDeniedError):
            ExamService.record_challenge_result(attempt.id, first.id, examiner, score=9)

    def test_an_inactive_or_empty_exam_cannot_be_attempted(
        self, db_session, exam, examiner, player
    ):
        empty = ExamService.create_exam(examiner, "Senza drill")
        with pytest.raises(ValidationError):
            ExamService.start_self_practice(player, empty.id)

        ExamService.deactivate_exam(exam.id, examiner)
        with pytest.raises(ConflictError):
            ExamService.start_self_practice(player, exam.id)

        assert exam.id not in {e.id for e in ExamService.get_available_exams()}

    def test_unknown_attempt_and_drill_raise_not_found(self, exam, player):
        with pytest.raises(NotFoundError):
            ExamService.record_challenge_result(999_999, 1, player, score=1)

        attempt = ExamService.start_self_practice(player, exam.id)
        with pytest.raises(NotFoundError):
            ExamService.record_challenge_result(attempt.id, 999_999, player, score=1)
