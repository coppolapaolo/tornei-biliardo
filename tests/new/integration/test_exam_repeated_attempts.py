"""Un drill dentro un esame può prevedere più prove (ADR-042).

Il numero di prove lo decide **chi compone l'esame**, non chi lo sostiene: è
parte della prova, come il punteggio massimo. Il drill vale poi la prova
migliore — si ripete per migliorare, quindi conta il picco; sommarle avrebbe
fatto pesare un drill a tre prove il triplo di uno a prova unica, cambiando la
taratura dell'esame senza che nessuno l'avesse deciso.

Qui si guarda il giro dal servizio: comporre, somministrare, correggere.
Lo scoring in isolamento sta in ``unit/test_exam_scoring.py``.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.exam.models import ExamChallengeResult
from models.exam.services import MAX_ATTEMPTS_PER_CHALLENGE, ExamService
from models.exceptions import ConflictError, NotFoundError, ValidationError
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
    """Un drill da 10 punti in **tre** prove, e un pass/fail in due."""
    created = ExamService.create_exam(examiner, "Ripetizioni")
    ExamService.add_challenge_to_exam(
        created.id, _make_challenge().id, examiner, max_score=10, max_attempts=3
    )
    ExamService.add_challenge_to_exam(
        created.id, _make_challenge(pass_fail=True).id, examiner, max_attempts=2
    )
    db_session.flush()
    return created


def _drills(exam):
    return exam.challenges.all()


def _slots(attempt, exam_challenge):
    return (
        ExamChallengeResult.query.filter_by(
            exam_attempt_id=attempt.id, exam_challenge_id=exam_challenge.id
        )
        .order_by(ExamChallengeResult.attempt_number)
        .all()
    )


class TestComposition:
    """Quante prove: lo si dichiara componendo l'esame."""

    def test_the_number_of_attempts_is_part_of_the_exam(self, exam):
        numeric, pass_fail = _drills(exam)
        assert numeric.max_attempts == 3
        assert pass_fail.max_attempts == 2

    def test_a_drill_prescribes_at_least_one_attempt(self, exam, examiner):
        with pytest.raises(ValidationError):
            ExamService.add_challenge_to_exam(
                exam.id, _make_challenge().id, examiner, max_score=5, max_attempts=0
            )

    def test_the_number_of_attempts_has_a_ceiling(self, exam, examiner):
        """Ogni prova è una riga per **ogni** sessione: un numero incollato si
        pagherebbe su tutti i candidati."""
        with pytest.raises(ValidationError):
            ExamService.add_challenge_to_exam(
                exam.id,
                _make_challenge().id,
                examiner,
                max_score=5,
                max_attempts=MAX_ATTEMPTS_PER_CHALLENGE + 1,
            )

    def test_updating_only_the_score_leaves_the_attempts_alone(self, exam, examiner):
        """Chi cambia il punteggio non deve rimandare l'altro campo per non
        azzerarlo — è il modo classico di perdere un dato senza accorgersene."""
        numeric = _drills(exam)[0]

        ExamService.update_exam_challenge(
            exam.id, numeric.challenge_id, examiner, max_score=12
        )
        assert (numeric.max_score, numeric.max_attempts) == (12, 3)

        ExamService.update_exam_challenge(
            exam.id, numeric.challenge_id, examiner, max_score=12, max_attempts=5
        )
        assert numeric.max_attempts == 5


class TestAdministration:
    """Somministrare: le prove si riempiono in ordine, e si possono correggere."""

    def test_a_session_opens_with_one_slot_per_prescribed_attempt(self, exam, player):
        attempt = ExamService.start_self_practice(player, exam.id)
        numeric, pass_fail = _drills(exam)

        assert [s.attempt_number for s in _slots(attempt, numeric)] == [1, 2, 3]
        assert [s.attempt_number for s in _slots(attempt, pass_fail)] == [1, 2]
        assert attempt.challenge_results.count() == 5

    def test_recording_without_a_number_fills_the_next_free_attempt(self, exam, player):
        attempt = ExamService.start_self_practice(player, exam.id)
        numeric = _drills(exam)[0]

        for expected, score in enumerate((6, 8, 7), start=1):
            result = ExamService.record_challenge_result(
                attempt.id, numeric.id, player, score=score
            )
            assert result.attempt_number == expected

        assert [s.score for s in _slots(attempt, numeric)] == [6, 8, 7]

    def test_the_drill_is_worth_its_best_attempt(self, exam, player):
        """6, 8, 7 fanno 8 — e il massimo del drill resta 10, non 30."""
        attempt = ExamService.start_self_practice(player, exam.id)
        numeric, pass_fail = _drills(exam)

        for score in (6, 8, 7):
            ExamService.record_challenge_result(
                attempt.id, numeric.id, player, score=score
            )
        ExamService.record_challenge_result(
            attempt.id, pass_fail.id, player, passed=False
        )
        ExamService.record_challenge_result(
            attempt.id, pass_fail.id, player, passed=True
        )

        assert attempt.total_score == 9  # 8 sul numerico + 1 sul pass/fail
        assert attempt.max_possible_score == 11

    def test_an_explicit_number_corrects_that_attempt(self, exam, player):
        """Il numero serve proprio a dire *quale* prova si sta rifacendo."""
        attempt = ExamService.start_self_practice(player, exam.id)
        numeric = _drills(exam)[0]

        for score in (6, 8, 7):
            ExamService.record_challenge_result(
                attempt.id, numeric.id, player, score=score
            )

        ExamService.record_challenge_result(
            attempt.id, numeric.id, player, score=3, attempt_number=2
        )
        assert [s.score for s in _slots(attempt, numeric)] == [6, 3, 7]
        # Il migliore ora è il terzo, e il totale lo segue.
        assert attempt.total_score == 7 + 0

    def test_a_fourth_attempt_is_refused_and_says_why(self, exam, player):
        attempt = ExamService.start_self_practice(player, exam.id)
        numeric = _drills(exam)[0]

        for score in (6, 8, 7):
            ExamService.record_challenge_result(
                attempt.id, numeric.id, player, score=score
            )

        with pytest.raises(ConflictError):
            ExamService.record_challenge_result(attempt.id, numeric.id, player, score=9)

    def test_an_attempt_the_exam_does_not_prescribe_is_not_found(self, exam, player):
        attempt = ExamService.start_self_practice(player, exam.id)
        numeric = _drills(exam)[0]

        with pytest.raises(NotFoundError):
            ExamService.record_challenge_result(
                attempt.id, numeric.id, player, score=5, attempt_number=4
            )

    def test_the_session_is_complete_only_when_every_attempt_is_recorded(
        self, exam, player
    ):
        """Fermarsi alla prima prova di un drill da tre è una sessione a metà."""
        attempt = ExamService.start_self_practice(player, exam.id)
        numeric, pass_fail = _drills(exam)

        ExamService.record_challenge_result(attempt.id, numeric.id, player, score=6)
        ExamService.record_challenge_result(
            attempt.id, pass_fail.id, player, passed=True
        )
        progress = attempt.get_progress()
        assert (progress["completed_attempts"], progress["total_attempts"]) == (2, 5)
        assert progress["is_complete"] is False

        ExamService.record_challenge_result(attempt.id, numeric.id, player, score=8)
        ExamService.record_challenge_result(attempt.id, numeric.id, player, score=7)
        ExamService.record_challenge_result(
            attempt.id, pass_fail.id, player, passed=False
        )
        assert attempt.get_progress()["is_complete"] is True


class TestSingleAttemptIsUnchanged:
    """Il default è 1, e con 1 nulla si comporta diversamente da prima."""

    def test_re_recording_a_single_attempt_drill_still_corrects_it(
        self, db_session, examiner, player
    ):
        exam = ExamService.create_exam(examiner, "Prova unica")
        ExamService.add_challenge_to_exam(
            exam.id, _make_challenge().id, examiner, max_score=10
        )
        db_session.flush()
        drill = exam.challenges.all()[0]
        assert drill.max_attempts == 1

        attempt = ExamService.start_self_practice(player, exam.id)
        ExamService.record_challenge_result(attempt.id, drill.id, player, score=4)
        ExamService.record_challenge_result(attempt.id, drill.id, player, score=9)

        assert [s.score for s in _slots(attempt, drill)] == [9]
        assert attempt.total_score == 9
