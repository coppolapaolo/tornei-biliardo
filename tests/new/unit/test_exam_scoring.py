"""Unit test dello scoring d'esame (ADR-042, Fase 2).

Tre cose che il modello precedente sbagliava e che qui sono presidiate:

1. il punteggio massimo si legge da ``ExamChallenge.max_score``, **non** da
   ``Challenge.max_score`` — colonna che su ``Challenge`` non esiste e la cui
   lettura rendeva il dominio non funzionante;
2. ``get_progress()`` conta come svolto anche un drill pass/fail: prima
   guardava il solo ``score``, quindi un esame di soli pass/fail restava
   eternamente allo 0%;
3. il totale è una **somma semplice**: niente ``weight``, niente moltiplicatori.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.exam.models import Exam, ExamAttempt, ExamChallenge, ExamChallengeResult
from models.status_enum import ExamAttemptMode, ExamAttemptStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _user(role: str = UserRole.PLAYER.value) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"{role}_{suffix}", email=f"{role}_{suffix}@test.local", role=role
    )
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.flush()
    return user


def _challenge(pass_fail: bool = False) -> Challenge:
    challenge = Challenge(
        description=f"Drill {uuid.uuid4().hex[:6]}",
        image_path="/static/uploads/challenges/x.png",
        pass_fail_only=pass_fail,
    )
    db.session.add(challenge)
    db.session.flush()
    return challenge


def _exam_with_challenges(owner: User, specs) -> tuple[Exam, list[ExamChallenge]]:
    """``specs``: lista di ``(pass_fail, max_score)`` nell'ordine voluto."""
    exam = Exam(name=f"Esame {uuid.uuid4().hex[:6]}", examiner_id=owner.id)
    db.session.add(exam)
    db.session.flush()

    exam_challenges = []
    for index, (pass_fail, max_score) in enumerate(specs, start=1):
        exam_challenge = ExamChallenge(
            exam_id=exam.id,
            challenge_id=_challenge(pass_fail).id,
            order=index,
            max_score=max_score,
        )
        db.session.add(exam_challenge)
        exam_challenges.append(exam_challenge)
    db.session.flush()
    return exam, exam_challenges


def _attempt(exam: Exam, user: User) -> ExamAttempt:
    attempt = ExamAttempt(
        exam_id=exam.id,
        user_id=user.id,
        mode=ExamAttemptMode.SELF_PRACTICE.value,
        status=ExamAttemptStatus.IN_PROGRESS.value,
    )
    db.session.add(attempt)
    db.session.flush()
    attempt.create_placeholder_results()
    db.session.flush()
    return attempt


# ────────────────────────────────────────────────────────────────────────────────
# max_score per-esame
# ────────────────────────────────────────────────────────────────────────────────
def test_max_score_is_per_exam_not_per_challenge(app):
    """Lo stesso drill vale 10 in un esame e 15 in un altro."""
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        challenge = _challenge()

        first = Exam(name="Primo", examiner_id=owner.id)
        second = Exam(name="Secondo", examiner_id=owner.id)
        db.session.add_all([first, second])
        db.session.flush()

        in_first = ExamChallenge(
            exam_id=first.id, challenge_id=challenge.id, order=1, max_score=10
        )
        in_second = ExamChallenge(
            exam_id=second.id, challenge_id=challenge.id, order=1, max_score=15
        )
        db.session.add_all([in_first, in_second])
        db.session.flush()

        assert in_first.effective_max_score == 10
        assert in_second.effective_max_score == 15
        # Challenge non ha (e non deve avere) un max_score proprio.
        assert not hasattr(challenge, "max_score")


def test_pass_fail_challenge_has_null_max_score_and_counts_one_point(app):
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        _, (pass_fail,) = _exam_with_challenges(owner, [(True, None)])

        assert pass_fail.is_pass_fail is True
        assert pass_fail.effective_max_score == 1
        assert pass_fail.score_of(None, True) == 1
        assert pass_fail.score_of(None, False) == 0


def test_numeric_challenge_scores_are_not_weighted(app):
    """Il ``weight`` non esiste più: il punteggio entra tale e quale."""
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        _, (numeric,) = _exam_with_challenges(owner, [(False, 10)])

        assert numeric.is_pass_fail is False
        assert numeric.score_of(8, None) == 8
        assert not hasattr(numeric, "weight")


# ────────────────────────────────────────────────────────────────────────────────
# Somma dei punteggi
# ────────────────────────────────────────────────────────────────────────────────
def test_recompute_scores_sums_numeric_and_pass_fail(app):
    """8/10 + pass (1/1) + 7/15 = 16 su 26."""
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, (first, second, third) = _exam_with_challenges(
            owner, [(False, 10), (True, None), (False, 15)]
        )
        attempt = _attempt(exam, player)

        results = {r.exam_challenge_id: r for r in attempt.challenge_results.all()}
        results[first.id].record(score=8)
        results[second.id].record(score=1, passed=True)
        results[third.id].record(score=7)
        db.session.flush()

        attempt.recompute_scores()

        assert attempt.total_score == 16
        assert attempt.max_possible_score == 26


def test_failed_pass_fail_contributes_zero_but_still_counts_in_the_maximum(app):
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, (numeric, pass_fail) = _exam_with_challenges(
            owner, [(False, 10), (True, None)]
        )
        attempt = _attempt(exam, player)

        results = {r.exam_challenge_id: r for r in attempt.challenge_results.all()}
        results[numeric.id].record(score=10)
        results[pass_fail.id].record(score=0, passed=False)
        db.session.flush()

        attempt.recompute_scores()

        assert attempt.total_score == 10
        assert attempt.max_possible_score == 11


# ────────────────────────────────────────────────────────────────────────────────
# get_progress — regressione: i pass/fail non venivano mai contati
# ────────────────────────────────────────────────────────────────────────────────
def test_progress_counts_pass_fail_results(app):
    """Un esame di soli pass/fail arriva al 100%: prima restava a 0."""
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, (first, second) = _exam_with_challenges(
            owner, [(True, None), (True, None)]
        )
        attempt = _attempt(exam, player)

        results = {r.exam_challenge_id: r for r in attempt.challenge_results.all()}
        results[first.id].record(score=1, passed=True)
        db.session.flush()

        progress = attempt.get_progress()
        assert progress["completed_challenges"] == 1
        assert progress["is_complete"] is False

        results[second.id].record(score=0, passed=False)
        db.session.flush()

        progress = attempt.get_progress()
        assert progress["completed_challenges"] == 2
        assert progress["progress_percentage"] == 100
        assert progress["is_complete"] is True


def test_progress_of_an_exam_without_challenges_is_not_complete(app):
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, _ = _exam_with_challenges(owner, [])
        attempt = _attempt(exam, player)

        progress = attempt.get_progress()
        assert progress["total_challenges"] == 0
        assert progress["is_complete"] is False


# ────────────────────────────────────────────────────────────────────────────────
# Esito booleano
# ────────────────────────────────────────────────────────────────────────────────
def test_exam_has_no_grading_api_left(app):
    """Niente griglia, niente voto: l'esito è booleano."""
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        exam, _ = _exam_with_challenges(owner, [(False, 10)])

        for gone in (
            "grading_criteria",
            "calculate_grade",
            "get_max_possible_score",
            "set_grading_criteria",
        ):
            assert not hasattr(exam, gone), f"{gone} doveva sparire"


def test_is_certified_only_for_completed_certified_attempts(app):
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, _ = _exam_with_challenges(owner, [(False, 10)])

        practice = _attempt(exam, player)
        practice.status = ExamAttemptStatus.COMPLETED.value
        assert practice.is_certified is False

        certified = ExamAttempt(
            exam_id=exam.id,
            user_id=player.id,
            mode=ExamAttemptMode.CERTIFIED.value,
            status=ExamAttemptStatus.IN_PROGRESS.value,
            examiner_id=owner.id,
        )
        db.session.add(certified)
        db.session.flush()
        assert certified.is_certified is False

        certified.status = ExamAttemptStatus.COMPLETED.value
        certified.passed = False
        assert certified.is_certified is True  # bocciato è comunque certificato

        abandoned = ExamAttempt(
            exam_id=exam.id,
            user_id=player.id,
            mode=ExamAttemptMode.CERTIFIED.value,
            status=ExamAttemptStatus.ABANDONED.value,
            examiner_id=owner.id,
        )
        db.session.add(abandoned)
        db.session.flush()
        assert abandoned.is_certified is False
        assert abandoned.passed is None


def test_result_is_unique_per_attempt_and_challenge(app):
    """Un drill non può avere due risultati nello stesso tentativo."""
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, (only_one,) = _exam_with_challenges(owner, [(False, 10)])
        attempt = _attempt(exam, player)

        db.session.add(
            ExamChallengeResult(
                exam_attempt_id=attempt.id, exam_challenge_id=only_one.id
            )
        )
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()
