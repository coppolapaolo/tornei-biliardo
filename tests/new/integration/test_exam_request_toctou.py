"""Due esaminatori accettano insieme: uno solo vince (Fase 3).

Modello: ``test_unique_constraints_toctou.py``. Ma il presidio **non** è lo
stesso dei match individuali, e la differenza è la ragione di questo file.

Là accettare crea subito l'``IndividualMatch``, quindi a far vincere un solo
accettante è l'indice UNIQUE su ``individual_match.proposal_id``. Qui accettare
fissa **solo** l'appuntamento: l'``ExamAttempt`` nasce molto dopo, all'apertura
della sessione, e un indice su ``exam_attempt.exam_request_id`` proteggerebbe
un'altra corsa — due sessioni per lo stesso appuntamento — non questa.

Servono quindi due presidi distinti, e qui si verifica che entrambi tengano:

1. l'indice UNIQUE parziale ``(request_id) WHERE status='accepted'`` su
   ``exam_request_recipient``;
2. l'accettazione come UPDATE condizionato su ``accepted_by_id IS NULL``, con
   controllo del rowcount — così il perdente riceve un ``ConflictError`` invece
   di sovrascrivere il vincitore in silenzio.

Come nel test dei match, la concorrenza si simula scrivendo a mano lo stato che
un vincitore concorrente avrebbe lasciato: il controllo in Python passa, ed è
il presidio a dover fermare la seconda accettazione.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from models.base import db, utc_now
from models.challenge.models import Challenge
from models.exam.models import ExamAttempt
from models.exam.request_models import ExamRequest, ExamRequestRecipient
from models.exam.request_service import ExamRequestService
from models.exam.services import ExamService
from models.exceptions import ConflictError
from models.location.models import BilliardHall
from models.status_enum import (
    ExamAttemptMode,
    ExamAttemptStatus,
    ExamRequestRecipientStatus,
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


@pytest.fixture
def scenario(db_session):
    """Un esame con due esaminatori e una richiesta rivolta a entrambi."""
    admin = _make_user(UserRole.ADMIN.value)
    first = _make_user()
    second = _make_user()
    player = _make_user()
    RoleGrantService.grant(first.id, EXAMINER, admin)
    RoleGrantService.grant(second.id, EXAMINER, admin)

    hall = BilliardHall(name=f"Biliardo {uuid.uuid4().hex[:6]}", is_active=True)
    db.session.add(hall)
    challenge = Challenge(
        description=f"Drill {uuid.uuid4().hex[:6]}",
        image_path="/static/uploads/challenges/x.png",
    )
    db.session.add(challenge)
    db_session.commit()

    exam = ExamService.create_exam(first, "Fondamentali — livello 1")
    ExamService.add_challenge_to_exam(exam.id, challenge.id, first, max_score=10)
    ExamService.add_examiner(exam.id, second.id, first)
    db_session.commit()

    request = ExamRequestService.create_request(
        player,
        exam.id,
        scheduled_at=utc_now() + timedelta(days=3),
        billiard_hall_id=hall.id,
    )
    db_session.commit()

    return {
        "exam": exam,
        "request": request,
        "first": first,
        "second": second,
        "player": player,
        "hall": hall,
    }


class TestOnlyOneExaminerWins:
    def test_partial_unique_index_allows_a_single_accepted_recipient(
        self, db_session, scenario
    ):
        """Presidio 1, a livello DB."""
        request = scenario["request"]
        recipients = ExamRequestRecipient.query.filter_by(request_id=request.id).all()
        assert len(recipients) == 2

        recipients[0].status = ExamRequestRecipientStatus.ACCEPTED.value
        db_session.commit()

        recipients[1].status = ExamRequestRecipientStatus.ACCEPTED.value
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_the_index_does_not_block_the_other_outcomes(self, db_session, scenario):
        """Parziale sul serio: `closed` e `rejected` restano quanti servono."""
        request = scenario["request"]
        recipients = ExamRequestRecipient.query.filter_by(request_id=request.id).all()
        recipients[0].status = ExamRequestRecipientStatus.CLOSED.value
        recipients[1].status = ExamRequestRecipientStatus.CLOSED.value
        db_session.commit()  # nessun conflitto

        assert (
            ExamRequestRecipient.query.filter_by(
                request_id=request.id,
                status=ExamRequestRecipientStatus.CLOSED.value,
            ).count()
            == 2
        )

    def test_the_loser_gets_a_conflict_not_a_silent_overwrite(
        self, db_session, scenario
    ):
        """Presidio 1, dal servizio: il perdente riceve un ConflictError."""
        request = scenario["request"]
        winner_row = ExamRequestRecipient.query.filter_by(
            request_id=request.id, examiner_id=scenario["first"].id
        ).one()

        # Stato lasciato da un vincitore concorrente che ha già scritto la
        # propria riga: la richiesta risulta ancora in trattativa, quindi il
        # controllo in Python passa e tocca all'indice fermare il secondo.
        winner_row.status = ExamRequestRecipientStatus.ACCEPTED.value
        db_session.commit()

        with pytest.raises(ConflictError):
            ExamRequestService.accept(request.id, scenario["second"])
        db_session.rollback()

        # E il vincitore resta il primo: nessuna sovrascrittura.
        rows = ExamRequestRecipient.query.filter_by(
            request_id=request.id, status=ExamRequestRecipientStatus.ACCEPTED.value
        ).all()
        assert [r.examiner_id for r in rows] == [scenario["first"].id]

    def test_the_conditional_update_catches_an_already_taken_request(
        self, db_session, scenario
    ):
        """Presidio 2: rowcount 0 → ConflictError, invece di rubare l'appuntamento."""
        request = scenario["request"]
        # Il vincitore ha scritto ``accepted_by_id`` ma la riga del destinatario
        # non è ancora visibile: è la finestra che l'UPDATE condizionato copre.
        request.accepted_by_id = scenario["first"].id
        request.accepted_at = utc_now()
        db_session.commit()

        with pytest.raises(ConflictError):
            ExamRequestService.accept(request.id, scenario["second"])
        db_session.rollback()

        fresh = db.session.get(ExamRequest, request.id)
        assert fresh is not None
        assert fresh.accepted_by_id == scenario["first"].id


class TestOneSessionPerAppointment:
    """La corsa che l'indice su ``exam_attempt.exam_request_id`` protegge davvero."""

    def test_two_attempts_on_the_same_appointment_collide(self, db_session, scenario):
        request = scenario["request"]
        ExamRequestService.accept(request.id, scenario["first"])
        db_session.commit()

        ExamService.open_certified_session(scenario["first"], request.id)
        db_session.commit()

        duplicate = ExamAttempt(
            exam_id=scenario["exam"].id,
            user_id=scenario["player"].id,
            mode=ExamAttemptMode.CERTIFIED.value,
            status=ExamAttemptStatus.AWAITING_PLAYER_START.value,
            examiner_id=scenario["first"].id,
            exam_request_id=request.id,
        )
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_self_practice_attempts_are_not_affected(self, db_session, scenario):
        """Tutti con ``exam_request_id`` NULL: l'indice parziale li ignora."""
        exam = scenario["exam"]
        first_player = scenario["player"]
        second_player = _make_user()
        db_session.commit()

        ExamService.start_self_practice(first_player, exam.id)
        ExamService.start_self_practice(second_player, exam.id)
        db_session.commit()

        assert (
            ExamAttempt.query.filter_by(exam_id=exam.id, exam_request_id=None).count()
            == 2
        )
