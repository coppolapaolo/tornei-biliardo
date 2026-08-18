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
    """``specs``: lista di ``(pass_fail, max_score)``, o ``(…, max_attempts)``."""
    exam = Exam(name=f"Esame {uuid.uuid4().hex[:6]}", examiner_id=owner.id)
    db.session.add(exam)
    db.session.flush()

    exam_challenges = []
    for index, spec in enumerate(specs, start=1):
        pass_fail, max_score = spec[0], spec[1]
        max_attempts = spec[2] if len(spec) > 2 else 1
        exam_challenge = ExamChallenge(
            exam_id=exam.id,
            challenge_id=_challenge(pass_fail).id,
            order=index,
            max_score=max_score,
            max_attempts=max_attempts,
        )
        db.session.add(exam_challenge)
        exam_challenges.append(exam_challenge)
    db.session.flush()
    return exam, exam_challenges


def _slots(attempt: ExamAttempt, exam_challenge: ExamChallenge):
    """I risultati di un drill dentro un tentativo, in ordine di tentativo."""
    return (
        attempt.challenge_results.filter_by(exam_challenge_id=exam_challenge.id)
        .order_by(ExamChallengeResult.attempt_number)
        .all()
    )


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
    """Lo stesso esercizio vale 10 in un esame e 15 in un altro.

    Dal 2026-08-18 l'esercizio ha un ``max_score`` **suo** (facoltativo), e la
    convivenza e' voluta: le due colonne rispondono a domande diverse.

    - ``Challenge.max_score`` → *quanto vale al massimo questa prova*, che e'
      una proprieta' dell'esercizio: quindici bilie sono quindici bilie
      ovunque. Serve fuori dagli esami — mostrare «12 / 15» a chi si allena dal
      catalogo, e rifiutare un 20 su una prova che arriva a 15.
    - ``ExamChallenge.max_score`` → *quanto pesa dentro quell'esame*, che e'
      una scelta di chi l'esame lo compone.

    Quello che questo test difende e' che il secondo **non** venga derivato dal
    primo: e' il punto di ADR-042, e derivarlo renderebbe impossibile far
    pesare diversamente lo stesso esercizio in due esami.
    """
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        challenge = _challenge()
        challenge.max_score = 30
        db.session.flush()

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

        # Il massimo dell'esercizio non entra nel conto dell'esame, nemmeno
        # quando c'e' ed e' piu' alto di entrambi.
        assert in_first.effective_max_score == 10
        assert in_second.effective_max_score == 15
        assert challenge.max_score == 30


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


def test_result_is_unique_per_attempt_challenge_and_number(app):
    """Due risultati sullo **stesso** tentativo di drill restano vietati.

    Il vincolo si è allargato per reggere i tentativi ripetuti, non allentato:
    la coppia (drill, tentativo) resta una sola riga.
    """
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, (only_one,) = _exam_with_challenges(owner, [(False, 10)])
        attempt = _attempt(exam, player)

        db.session.add(
            ExamChallengeResult(
                exam_attempt_id=attempt.id,
                exam_challenge_id=only_one.id,
                attempt_number=1,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()


# ────────────────────────────────────────────────────────────────────────────────
# Tentativi ripetuti per drill: conta il migliore
# ────────────────────────────────────────────────────────────────────────────────
def test_a_drill_gets_one_slot_per_prescribed_attempt(app):
    """Tre tentativi prescritti, tre righe numerate 1-2-3."""
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, (drill,) = _exam_with_challenges(owner, [(False, 10, 3)])
        attempt = _attempt(exam, player)

        assert [s.attempt_number for s in _slots(attempt, drill)] == [1, 2, 3]


def test_the_best_attempt_is_the_one_that_counts(app):
    """6, 8, 7 su un drill da 10 fanno 8 — e il massimo resta 10, non 30.

    È la scelta di fondo: il drill si ripete per migliorare, quindi vale la
    prova migliore. Contare la somma farebbe pesare un drill a tre tentativi il
    triplo di uno a tentativo unico, cambiando l'esame senza dirlo.
    """
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, (drill,) = _exam_with_challenges(owner, [(False, 10, 3)])
        attempt = _attempt(exam, player)

        for slot, score in zip(_slots(attempt, drill), (6, 8, 7)):
            slot.record(score=score)
        db.session.flush()

        attempt.recompute_scores()
        assert attempt.total_score == 8
        assert attempt.max_possible_score == 10


def test_a_pass_fail_drill_is_passed_if_any_attempt_passed(app):
    """Sbagliare la prima e riuscire la seconda vale il punto."""
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, (drill,) = _exam_with_challenges(owner, [(True, None, 2)])
        attempt = _attempt(exam, player)

        first, second = _slots(attempt, drill)
        first.record(score=0, passed=False)
        second.record(score=1, passed=True)
        db.session.flush()

        attempt.recompute_scores()
        assert attempt.total_score == 1
        assert attempt.max_possible_score == 1


def test_slots_still_to_do_do_not_drag_the_best_down(app):
    """Un tentativo non ancora registrato non è uno zero.

    Vale mentre la sessione è in corso: il punteggio mostrato dopo la prima
    prova dev'essere quello della prima prova, non una media con dei vuoti.
    """
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, (drill,) = _exam_with_challenges(owner, [(False, 10, 3)])
        attempt = _attempt(exam, player)

        _slots(attempt, drill)[0].record(score=5)
        db.session.flush()

        attempt.recompute_scores()
        assert attempt.total_score == 5


def test_progress_counts_every_prescribed_attempt(app):
    """Un drill da tre prove non è svolto dopo la prima.

    L'esame prescrive quante prove servono: fermarsi prima è una sessione
    incompleta, e la barra deve dirlo invece di segnare 100%.
    """
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, (drill,) = _exam_with_challenges(owner, [(False, 10, 3)])
        attempt = _attempt(exam, player)
        slots = _slots(attempt, drill)

        slots[0].record(score=4)
        db.session.flush()
        progress = attempt.get_progress()
        assert progress["completed_challenges"] == 0
        assert progress["completed_attempts"] == 1
        assert progress["total_attempts"] == 3
        assert progress["is_complete"] is False

        slots[1].record(score=6)
        slots[2].record(score=5)
        db.session.flush()
        progress = attempt.get_progress()
        assert progress["completed_challenges"] == 1
        assert progress["progress_percentage"] == 100
        assert progress["is_complete"] is True


def test_a_single_attempt_per_drill_behaves_exactly_as_before(app):
    """Il default è 1, e con 1 i conti sono quelli di prima.

    L'esame già composto non cambia di significato: è la condizione perché
    questa aggiunta non sia una modifica retroattiva.
    """
    with app.app_context():
        owner = _user(UserRole.ADMIN.value)
        player = _user()
        exam, (numeric, pass_fail) = _exam_with_challenges(
            owner, [(False, 10), (True, None)]
        )
        assert numeric.max_attempts == 1

        attempt = _attempt(exam, player)
        _slots(attempt, numeric)[0].record(score=8)
        _slots(attempt, pass_fail)[0].record(score=1, passed=True)
        db.session.flush()

        attempt.recompute_scores()
        assert attempt.total_score == 9
        assert attempt.max_possible_score == 11
        assert attempt.get_progress()["is_complete"] is True
