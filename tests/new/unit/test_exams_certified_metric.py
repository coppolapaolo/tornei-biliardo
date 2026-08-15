"""La metrica ``exams_certified`` per le regole ABAC.

⚠️ Il motivo per cui questo file esiste. Il dispatch delle metriche è
``getattr(UserMetricService, f"_get_{metric_name}", None)`` e poi
``value = handler(user_id, context) if handler else 0``: **una metrica
sconosciuta restituisce 0 in silenzio**, non solleva. Se si semina una regola
ABAC su ``exams_certified`` dimenticando il metodo, il gate resta chiuso per
sempre, per tutti, senza un errore da nessuna parte.

Quindi qui non basta verificare che la feature sia configurata: si verifica che
il metodo **esista** e che restituisca il valore atteso.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.exam.models import Exam, ExamAttempt
from models.kpi.user_metrics import UserMetricService
from models.status_enum import ExamAttemptMode, ExamAttemptStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


@pytest.fixture
def player(db_session) -> User:
    user = User(
        username=f"p_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def examiner(db_session) -> User:
    user = User(
        username=f"e_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


def _make_exam(examiner: User, name: str | None = None) -> Exam:
    exam = Exam(
        name=name or f"Esame {uuid.uuid4().hex[:6]}",
        description="",
        examiner_id=examiner.id,
        is_active=True,
    )
    db.session.add(exam)
    db.session.commit()
    return exam


def _attempt(
    player: User,
    exam: Exam,
    examiner: User,
    *,
    mode: str = ExamAttemptMode.CERTIFIED.value,
    status: str = ExamAttemptStatus.COMPLETED.value,
    passed: bool | None = True,
) -> ExamAttempt:
    attempt = ExamAttempt(
        exam_id=exam.id,
        user_id=player.id,
        mode=mode,
        status=status,
        passed=passed,
        examiner_id=examiner.id if mode == ExamAttemptMode.CERTIFIED.value else None,
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt


def _metric(user: User) -> int:
    return UserMetricService.get_metric(user.id, "exams_certified")


def test_the_metric_handler_exists(app):
    """Il guscio del footgun: senza questo metodo il gate resterebbe muto."""
    assert getattr(UserMetricService, "_get_exams_certified", None) is not None


def test_no_exams_no_credit(app, db_session, player):
    assert _metric(player) == 0


def test_a_passed_certified_exam_counts(app, db_session, player, examiner):
    _attempt(player, _make_exam(examiner), examiner)
    assert _metric(player) == 1


def test_a_self_practice_attempt_never_counts(app, db_session, player, examiner):
    """L'autonomia è allenamento: non certifica, nemmeno se il punteggio è pieno."""
    _attempt(
        player,
        _make_exam(examiner),
        examiner,
        mode=ExamAttemptMode.SELF_PRACTICE.value,
        passed=None,
    )
    assert _metric(player) == 0


def test_a_failed_exam_does_not_count(app, db_session, player, examiner):
    _attempt(player, _make_exam(examiner), examiner, passed=False)
    assert _metric(player) == 0


def test_a_session_still_open_does_not_count(app, db_session, player, examiner):
    """Un esame si conta quando è chiuso, non quando è in corso."""
    _attempt(
        player,
        _make_exam(examiner),
        examiner,
        status=ExamAttemptStatus.IN_PROGRESS.value,
        passed=None,
    )
    assert _metric(player) == 0


def test_an_abandoned_session_does_not_count(app, db_session, player, examiner):
    """Il candidato non si è presentato: non è una bocciatura, ma nemmeno un titolo."""
    _attempt(
        player,
        _make_exam(examiner),
        examiner,
        status=ExamAttemptStatus.ABANDONED.value,
        passed=None,
    )
    assert _metric(player) == 0


def test_repeating_the_same_exam_is_still_one_certification(
    app, db_session, player, examiner
):
    """Si contano gli esami superati, non i tentativi.

    Ripetere lo stesso esame non moltiplica il titolo: è la differenza fra
    questa metrica e ``challenges_completed``, che invece conta i tentativi.
    """
    exam = _make_exam(examiner)
    _attempt(player, exam, examiner)
    _attempt(player, exam, examiner)
    assert _metric(player) == 1


def test_two_different_exams_count_twice(app, db_session, player, examiner):
    _attempt(player, _make_exam(examiner), examiner)
    _attempt(player, _make_exam(examiner), examiner)
    assert _metric(player) == 2


def test_the_metric_is_per_user(app, db_session, player, examiner):
    other = User(
        username=f"o_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        role=UserRole.PLAYER.value,
    )
    other.set_password("x")
    db.session.add(other)
    db.session.commit()

    _attempt(player, _make_exam(examiner), examiner)
    assert _metric(other) == 0


def test_the_metric_has_a_label_everywhere_it_is_shown(app):
    """Senza label l'admin vede ``exams_certified`` grezzo nella console ABAC.

    Due posti, entrambi obbligatori: il dropdown delle metriche in
    ``routes/gamification/features.py`` e la frase «cosa ti manca» di
    ``UnlockProgressService``.
    """
    from models.gamification.unlock_progress_service import UnlockProgressService

    progress = UnlockProgressService._evaluate_condition(
        1,
        {
            "type": "METRIC",
            "metric": "exams_certified",
            "operator": "gte",
            "value": 1,
        },
    )
    assert "exams_certified" not in progress["description"]

    hint = UnlockProgressService._get_action_hint(
        {
            "type": "METRIC",
            "metric": "exams_certified",
            "current_value": 0,
            "required_value": 2,
        }
    )
    assert "exams_certified" not in hint


def test_the_challenge_metric_is_unaffected(app, db_session, player, examiner):
    """Un esame non è un drill: non deve inquinare ``challenges_completed``.

    È il gate di ``take_exam``/``request_examiner``, quindi una contaminazione
    qui sposterebbe le soglie di sblocco senza che nessuno se ne accorga.
    """
    challenge = Challenge(
        description=f"Drill {uuid.uuid4().hex[:6]}",
        image_path="challenges/placeholder.png",
        pass_fail_only=False,
    )
    db.session.add(challenge)
    db.session.commit()

    _attempt(player, _make_exam(examiner), examiner)
    assert UserMetricService.get_metric(player.id, "challenges_completed") == 0
