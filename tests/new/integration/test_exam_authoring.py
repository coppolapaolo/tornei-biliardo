"""Integration test della composizione di un esame (UJ-1, Fase 2).

Percorso: admin nomina il primo esaminatore → l'esaminatore compone un esame
come sequenza ordinata di drill, con un punteggio massimo per ciascuno →
prova ad aggiungere co-esaminatori e **non può**, è l'unico titolare → admin
ne nomina un secondo e allora il creatore può aggiungerlo.

Copre US-E1 (composizione), US-E2 (co-esaminatori), US-E8 (statistiche) e i
confini di permesso di UJ-6 (modificare l'esame di un altro).
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.exam.models import ExamAttempt, ExamExaminer
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
    """Il primo esaminatore del sistema, nominato da admin (UJ-1)."""
    user = _make_user()
    RoleGrantService.grant(user.id, EXAMINER, admin)
    db_session.commit()
    return user


@pytest.fixture
def player(db_session):
    user = _make_user()
    db_session.commit()
    return user


class TestExamAuthoring:
    """UJ-1 — l'esaminatore compone «Fondamentali — livello 1»."""

    def test_examiner_composes_an_ordered_sequence_of_drills(self, examiner):
        exam = ExamService.create_exam(
            examiner, "Fondamentali — livello 1", description="Tre drill di base"
        )
        assert exam.examiner_id == examiner.id
        assert exam.is_active is True

        numeric_10 = _make_challenge()
        pass_fail = _make_challenge(pass_fail=True)
        numeric_15 = _make_challenge()

        ExamService.add_challenge_to_exam(
            exam.id, numeric_10.id, examiner, max_score=10
        )
        ExamService.add_challenge_to_exam(exam.id, pass_fail.id, examiner)
        ExamService.add_challenge_to_exam(
            exam.id, numeric_15.id, examiner, max_score=15
        )

        drills = exam.challenges.all()
        assert [d.order for d in drills] == [1, 2, 3]
        assert [d.challenge_id for d in drills] == [
            numeric_10.id,
            pass_fail.id,
            numeric_15.id,
        ]
        assert [d.effective_max_score for d in drills] == [10, 1, 15]

    def test_reorder_moves_a_drill_to_the_front(self, examiner):
        """Il riordino scambia posizioni già occupate: due passate, non una."""
        exam = ExamService.create_exam(examiner, "Riordinabile")
        first = _make_challenge()
        second = _make_challenge()
        third = _make_challenge()
        for challenge in (first, second, third):
            ExamService.add_challenge_to_exam(
                exam.id, challenge.id, examiner, max_score=10
            )

        ExamService.reorder_exam_challenges(
            exam.id, examiner, [second.id, first.id, third.id]
        )

        assert [d.challenge_id for d in exam.challenges.all()] == [
            second.id,
            first.id,
            third.id,
        ]

    def test_reorder_must_list_exactly_the_drills_of_the_exam(self, examiner):
        exam = ExamService.create_exam(examiner, "Riordino incompleto")
        first = _make_challenge()
        second = _make_challenge()
        for challenge in (first, second):
            ExamService.add_challenge_to_exam(
                exam.id, challenge.id, examiner, max_score=5
            )

        with pytest.raises(ValidationError):
            ExamService.reorder_exam_challenges(exam.id, examiner, [first.id])

        # Un duplicato copre tutti gli id ma lascia l'ordine ambiguo: va
        # rifiutato, non deduplicato in silenzio.
        with pytest.raises(ValidationError):
            ExamService.reorder_exam_challenges(
                exam.id, examiner, [first.id, first.id, second.id]
            )

        assert [d.order for d in exam.challenges.all()] == [1, 2]

    def test_an_explicit_position_must_start_from_one(self, examiner):
        """Le posizioni negative sono il parcheggio del riordino, non un ordine."""
        exam = ExamService.create_exam(examiner, "Posizione esplicita")

        with pytest.raises(ValidationError):
            ExamService.add_challenge_to_exam(
                exam.id, _make_challenge().id, examiner, max_score=5, order=0
            )
        with pytest.raises(ValidationError):
            ExamService.add_challenge_to_exam(
                exam.id, _make_challenge().id, examiner, max_score=5, order=-1
            )

        first = _make_challenge()
        ExamService.add_challenge_to_exam(
            exam.id, first.id, examiner, max_score=5, order=1
        )
        with pytest.raises(ConflictError):
            ExamService.add_challenge_to_exam(
                exam.id, _make_challenge().id, examiner, max_score=5, order=1
            )

    def test_max_score_is_required_for_numeric_and_forbidden_for_pass_fail(
        self, examiner
    ):
        exam = ExamService.create_exam(examiner, "Validazione punteggi")

        with pytest.raises(ValidationError):
            ExamService.add_challenge_to_exam(exam.id, _make_challenge().id, examiner)

        with pytest.raises(ValidationError):
            ExamService.add_challenge_to_exam(
                exam.id, _make_challenge(pass_fail=True).id, examiner, max_score=5
            )

        with pytest.raises(ValidationError):
            ExamService.add_challenge_to_exam(
                exam.id, _make_challenge().id, examiner, max_score=0
            )

    def test_the_same_drill_cannot_appear_twice(self, examiner):
        exam = ExamService.create_exam(examiner, "Doppione")
        challenge = _make_challenge()
        ExamService.add_challenge_to_exam(exam.id, challenge.id, examiner, max_score=10)

        with pytest.raises(ConflictError):
            ExamService.add_challenge_to_exam(
                exam.id, challenge.id, examiner, max_score=10
            )

    def test_removing_a_drill_leaves_the_others(self, examiner):
        exam = ExamService.create_exam(examiner, "Rimozione")
        first = _make_challenge()
        second = _make_challenge()
        for challenge in (first, second):
            ExamService.add_challenge_to_exam(
                exam.id, challenge.id, examiner, max_score=10
            )

        ExamService.remove_challenge_from_exam(exam.id, first.id, examiner)

        assert [d.challenge_id for d in exam.challenges.all()] == [second.id]
        with pytest.raises(NotFoundError):
            ExamService.remove_challenge_from_exam(exam.id, first.id, examiner)


class TestExamPermissions:
    """UJ-6 — i confini: chi può creare e chi può modificare."""

    def test_a_player_without_the_role_cannot_create_an_exam(self, player):
        with pytest.raises(PermissionDeniedError):
            ExamService.create_exam(player, "Non dovrebbe nascere")

    def test_another_examiner_cannot_edit_someone_elses_exam(
        self, db_session, admin, examiner
    ):
        exam = ExamService.create_exam(examiner, "Esame del primo")
        outsider = _make_user()
        RoleGrantService.grant(outsider.id, EXAMINER, admin)
        db_session.flush()

        assert ExamService.can_edit(exam, outsider) is False
        with pytest.raises(PermissionDeniedError):
            ExamService.update_exam(exam.id, outsider, name="Rubato")

        # Aggiunto come co-esaminatore, invece, può.
        ExamService.add_examiner(exam.id, outsider.id, examiner)
        assert ExamService.can_edit(exam, outsider) is True
        ExamService.update_exam(exam.id, outsider, description="Ritoccata")
        assert exam.description == "Ritoccata"

    def test_admin_can_always_edit(self, admin, examiner):
        exam = ExamService.create_exam(examiner, "Esame vigilato")
        assert ExamService.can_edit(exam, admin) is True
        ExamService.update_exam(exam.id, admin, is_active=False)
        assert exam.is_active is False

    def test_unknown_exam_raises_not_found(self, examiner):
        with pytest.raises(NotFoundError):
            ExamService.get_exam(999_999)


class TestCoExaminers:
    """US-E2 — il creatore aggiunge altri esaminatori."""

    def test_with_a_single_role_holder_the_candidate_list_is_empty(self, examiner):
        """UJ-1: all'inizio non c'è nessun altro da aggiungere, e va bene così."""
        exam = ExamService.create_exam(examiner, "Solo io")

        assert ExamService.eligible_examiners(exam.id) == []
        assert exam.examiner_ids == {examiner.id}

    def test_a_second_holder_becomes_selectable_and_addable(
        self, db_session, admin, examiner
    ):
        exam = ExamService.create_exam(examiner, "In due")
        second = _make_user()
        RoleGrantService.grant(second.id, EXAMINER, admin)
        db_session.flush()

        assert [u.id for u in ExamService.eligible_examiners(exam.id)] == [second.id]

        link = ExamService.add_examiner(exam.id, second.id, examiner)
        assert isinstance(link, ExamExaminer)
        assert exam.examiner_ids == {examiner.id, second.id}
        assert exam.is_examined_by(second.id) is True
        # Aggiunto: non è più selezionabile.
        assert ExamService.eligible_examiners(exam.id) == []

    def test_only_role_holders_can_be_added(self, examiner, player):
        exam = ExamService.create_exam(examiner, "Non chiunque")

        with pytest.raises(ValidationError):
            ExamService.add_examiner(exam.id, player.id, examiner)

    def test_adding_twice_conflicts_and_the_creator_cannot_be_removed(
        self, db_session, admin, examiner
    ):
        exam = ExamService.create_exam(examiner, "Idempotenza")
        second = _make_user()
        RoleGrantService.grant(second.id, EXAMINER, admin)
        db_session.flush()
        ExamService.add_examiner(exam.id, second.id, examiner)

        with pytest.raises(ConflictError):
            ExamService.add_examiner(exam.id, second.id, examiner)
        with pytest.raises(ValidationError):
            ExamService.remove_examiner(exam.id, examiner.id, examiner)

        ExamService.remove_examiner(exam.id, second.id, examiner)
        assert exam.examiner_ids == {examiner.id}

    def test_exams_of_an_examiner_include_the_ones_he_was_added_to(
        self, db_session, admin, examiner
    ):
        own = ExamService.create_exam(examiner, "Creato da me")
        second = _make_user()
        RoleGrantService.grant(second.id, EXAMINER, admin)
        db_session.flush()
        shared = ExamService.create_exam(second, "Creato da un altro")
        ExamService.add_examiner(shared.id, examiner.id, second)

        mine = {e.id for e in ExamService.get_exams_for_examiner(examiner.id)}
        assert mine == {own.id, shared.id}


class TestExaminerStatistics:
    """US-E8 — quanti sostenuti, quanti superati, quanti candidati distinti."""

    def _certified(self, exam, user, examiner, passed):
        attempt = ExamAttempt(
            exam_id=exam.id,
            user_id=user.id,
            examiner_id=examiner.id,
            mode=ExamAttemptMode.CERTIFIED.value,
            status=ExamAttemptStatus.COMPLETED.value,
            passed=passed,
        )
        db.session.add(attempt)
        db.session.flush()
        return attempt

    def test_fresh_examiner_has_zero_everything(self, examiner):
        ExamService.create_exam(examiner, "Appena creato")

        stats = ExamService.get_examiner_statistics(examiner.id)
        assert stats["total_exams"] == 1
        assert stats["certified_attempts"] == 0
        assert stats["pass_rate"] is None
        assert stats["unique_candidates"] == 0

    def test_counts_only_certified_completed_attempts(self, examiner, player):
        exam = ExamService.create_exam(examiner, "Con tentativi")
        self._certified(exam, player, examiner, passed=True)
        self._certified(exam, player, examiner, passed=False)
        other = _make_user()
        self._certified(exam, other, examiner, passed=True)
        # Allenamento e abbandoni non contano.
        db.session.add(
            ExamAttempt(
                exam_id=exam.id,
                user_id=other.id,
                mode=ExamAttemptMode.SELF_PRACTICE.value,
                status=ExamAttemptStatus.COMPLETED.value,
            )
        )
        db.session.add(
            ExamAttempt(
                exam_id=exam.id,
                user_id=other.id,
                examiner_id=examiner.id,
                mode=ExamAttemptMode.CERTIFIED.value,
                status=ExamAttemptStatus.ABANDONED.value,
            )
        )
        db.session.flush()

        stats = ExamService.get_examiner_statistics(examiner.id)
        assert stats["certified_attempts"] == 3
        assert stats["passed"] == 2
        assert stats["failed"] == 1
        assert stats["unique_candidates"] == 2
        assert stats["pass_rate"] == pytest.approx(66.7)

        per_exam = stats["exams"][0]
        assert per_exam["exam"].id == exam.id
        assert per_exam["certified_attempts"] == 3

        exam_stats = ExamService.get_exam_statistics(exam.id)
        assert exam_stats["certified_attempts"] == 3
        assert exam_stats["passed"] == 2
        assert exam_stats["self_practice_attempts"] == 1

    def test_unique_candidates_are_not_the_sum_across_exams(self, examiner, player):
        first = ExamService.create_exam(examiner, "Primo")
        second = ExamService.create_exam(examiner, "Secondo")
        self._certified(first, player, examiner, passed=True)
        self._certified(second, player, examiner, passed=True)

        stats = ExamService.get_examiner_statistics(examiner.id)
        assert stats["certified_attempts"] == 2
        assert stats["unique_candidates"] == 1

    def test_statistics_do_not_grow_queries_with_the_number_of_exams(self, examiner):
        """Regressione sull'N+1: gli aggregati escono da un GROUP BY.

        Non si conta un numero assoluto di query — dipenderebbe da dettagli
        estranei — ma si verifica che **non cambi** aggiungendo esami: era
        proprio questo a crescere quando le statistiche iteravano
        ``exam.get_statistics()`` su una relazione ``lazy="dynamic"``.
        """
        from sqlalchemy import event

        def _count_selects() -> int:
            statements: list[str] = []

            def _record(conn, cursor, statement, parameters, context, executemany):
                statements.append(statement)

            engine = db.session.get_bind()
            event.listen(engine, "before_cursor_execute", _record)
            try:
                ExamService.get_examiner_statistics(examiner.id)
            finally:
                event.remove(engine, "before_cursor_execute", _record)
            return len(
                [s for s in statements if s.strip().upper().startswith("SELECT")]
            )

        ExamService.create_exam(examiner, "Esame 1")
        with_one = _count_selects()

        for index in range(2, 8):
            ExamService.create_exam(examiner, f"Esame {index}")
        with_seven = _count_selects()

        assert with_seven == with_one
