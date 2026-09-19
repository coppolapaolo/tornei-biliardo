"""Cosa sei tu per ogni esame: catalogo e dettaglio (fase 3b).

Il catalogo era un elenco di nomi e il dettaglio chiudeva con quattro
statistiche globali — sostenuti, superati, candidati, in autonomia — che su un
esame appena composto sono quattro zeri, e che al candidato non dicono niente.
Al loro posto va ciò che lo riguarda: l'appuntamento più vicino, e per ogni
esame «superato e da chi», «provato da solo», «mai provato». Sono tutti dati
che esistono già: qui si prova la lettura, senza scritture nuove.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge
from models.exam.models import ExamAttempt
from models.exam.overview import ExamOverview, StandingKind
from models.exam.request_models import ExamRequest, ExamRequestRecipient
from models.exam.services import ExamService
from models.location.models import BilliardHall
from models.status_enum import (
    ExamAttemptMode,
    ExamAttemptStatus,
    ExamRequestRecipientStatus,
    ExamRequestStatus,
)
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

PASSWORD = "prova123"


def _make_user(role: str = UserRole.PLAYER.value, **kwargs) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"u_{suffix}",
        email=f"{suffix}@example.com",
        role=role,
        is_verified=True,
        onboarding_completed=True,
        **kwargs,
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


@pytest.fixture
def examiner(db_session):
    admin = _make_user(UserRole.ADMIN.value)
    user = _make_user()
    RoleGrantService.grant(user.id, GrantableRole.EXAMINER, admin)
    db_session.commit()
    return user


@pytest.fixture
def exam(db_session, examiner):
    exam = ExamService.create_exam(examiner, "Fondamentali — livello 1")
    challenge = Challenge(
        title="Spot Shot Rally",
        description="x",
        image_path="/static/uploads/challenges/x.png",
    )
    db.session.add(challenge)
    db.session.flush()
    ExamService.add_challenge_to_exam(exam.id, challenge.id, examiner, max_score=22)
    db_session.commit()
    return exam


@pytest.fixture
def player(db_session):
    # Con l'override il gate `take_exam` non c'entra: qui si prova la lettura.
    user = _make_user(gamification_override=True)
    db_session.commit()
    return user


def _attempt(exam, user, *, mode, score, passed=None, examiner=None, days_ago=1):
    when = utc_now() - timedelta(days=days_ago)
    attempt = ExamAttempt(
        exam_id=exam.id,
        user_id=user.id,
        mode=mode,
        status=ExamAttemptStatus.COMPLETED.value,
        total_score=score,
        max_possible_score=22,
        passed=passed,
        examiner_id=examiner.id if examiner else None,
        certified_at=when if examiner else None,
        started_at=when,
        completed_at=when,
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt


def _hall() -> BilliardHall:
    hall = BilliardHall(name=f"Sala {uuid.uuid4().hex[:5]}", city="Udine")
    db.session.add(hall)
    db.session.flush()
    return hall


def _request(exam, requester, examiner, *, status, in_days=3) -> ExamRequest:
    accepted = status == ExamRequestStatus.ACCEPTED.value
    request = ExamRequest(
        exam_id=exam.id,
        requester_id=requester.id,
        status=status,
        billiard_hall_id=_hall().id,
        scheduled_at=utc_now() + timedelta(days=in_days),
        expires_at=utc_now() + timedelta(days=in_days),
        last_proposed_by_id=requester.id,
        accepted_by_id=examiner.id if accepted else None,
        accepted_at=utc_now() if accepted else None,
    )
    db.session.add(request)
    db.session.flush()
    db.session.add(
        ExamRequestRecipient(
            request_id=request.id,
            examiner_id=examiner.id,
            status=(
                ExamRequestRecipientStatus.ACCEPTED.value
                if accepted
                else ExamRequestRecipientStatus.PENDING.value
            ),
        )
    )
    db.session.commit()
    return request


class TestStanding:
    def test_mai_provato(self, exam, player):
        standing = ExamOverview.standings(player.id, [exam.id])[exam.id]
        assert standing.kind == StandingKind.NEVER

    def test_provato_da_solo_conta_le_volte_e_tiene_il_meglio(self, exam, player):
        self_practice = ExamAttemptMode.SELF_PRACTICE.value
        _attempt(exam, player, mode=self_practice, score=11, days_ago=5)
        _attempt(exam, player, mode=self_practice, score=14, days_ago=2)

        standing = ExamOverview.standings(player.id, [exam.id])[exam.id]

        assert standing.kind == StandingKind.PRACTICED
        assert standing.practice_count == 2
        assert (standing.best_score, standing.best_max) == (14, 22)
        assert (standing.first_score, standing.last_score) == (11, 14)

    def test_superato_dice_quando_e_da_chi(self, exam, player, examiner):
        _attempt(
            exam, player, mode=ExamAttemptMode.SELF_PRACTICE.value, score=20, days_ago=9
        )
        _attempt(
            exam,
            player,
            mode=ExamAttemptMode.CERTIFIED.value,
            score=18,
            passed=True,
            examiner=examiner,
            days_ago=4,
        )

        standing = ExamOverview.standings(player.id, [exam.id])[exam.id]

        assert standing.kind == StandingKind.PASSED
        assert standing.certified_by == examiner.username
        assert standing.certified_at is not None
        assert standing.practice_count == 1

    def test_un_superato_non_si_perde_con_un_non_superato_successivo(
        self, exam, player, examiner
    ):
        certified = ExamAttemptMode.CERTIFIED.value
        _attempt(exam, player, mode=certified, score=18, passed=True, examiner=examiner)
        _attempt(
            exam,
            player,
            mode=certified,
            score=9,
            passed=False,
            examiner=examiner,
            days_ago=0,
        )

        standing = ExamOverview.standings(player.id, [exam.id])[exam.id]
        assert standing.kind == StandingKind.PASSED
        assert standing.certified_count == 2

    def test_un_tentativo_abbandonato_non_conta(self, exam, player):
        attempt = _attempt(
            exam, player, mode=ExamAttemptMode.SELF_PRACTICE.value, score=3
        )
        attempt.status = ExamAttemptStatus.ABANDONED.value
        db.session.commit()

        standing = ExamOverview.standings(player.id, [exam.id])[exam.id]
        assert standing.kind == StandingKind.NEVER


class TestAppointmentsAndWaiting:
    def test_il_prossimo_appuntamento_e_il_piu_vicino_fra_quelli_confermati(
        self, exam, player, examiner
    ):
        accepted = ExamRequestStatus.ACCEPTED.value
        _request(exam, player, examiner, status=accepted, in_days=9)
        near = _request(exam, player, examiner, status=accepted, in_days=2)
        _request(
            exam,
            player,
            examiner,
            status=ExamRequestStatus.NEGOTIATING.value,
            in_days=1,
        )

        upcoming = ExamOverview.upcoming_appointments(player.id)

        assert [r.id for r in upcoming][0] == near.id
        assert len(upcoming) == 2
        # Lo stesso appuntamento lo vede anche chi esamina.
        assert ExamOverview.upcoming_appointments(examiner.id)[0].id == near.id

    def test_un_appuntamento_gia_sostenuto_non_e_piu_prossimo(
        self, exam, player, examiner
    ):
        request = _request(
            exam, player, examiner, status=ExamRequestStatus.ACCEPTED.value
        )
        attempt = _attempt(
            exam,
            player,
            mode=ExamAttemptMode.CERTIFIED.value,
            score=18,
            passed=True,
            examiner=examiner,
        )
        attempt.exam_request_id = request.id
        db.session.commit()

        assert ExamOverview.upcoming_appointments(player.id) == []

    def test_le_richieste_che_aspettano_l_esaminatore(self, exam, player, examiner):
        _request(exam, player, examiner, status=ExamRequestStatus.NEGOTIATING.value)

        waiting = ExamOverview.requests_waiting_for(examiner.id)

        assert [r.requester_id for r in waiting] == [player.id]
        assert ExamOverview.requests_waiting_for(player.id) == []


def _client_for(app, username: str):
    db.session.commit()
    client = app.test_client()
    client.post(
        "/auth/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=True,
    )
    return client


class TestPages:
    def test_il_catalogo_dice_cosa_sei_per_ogni_esame(
        self, app, exam, player, examiner
    ):
        _attempt(
            exam,
            player,
            mode=ExamAttemptMode.CERTIFIED.value,
            score=18,
            passed=True,
            examiner=examiner,
        )
        _request(exam, player, examiner, status=ExamRequestStatus.ACCEPTED.value)

        html = _client_for(app, player.username).get("/exam/").get_data(as_text=True)

        assert "Il tuo prossimo appuntamento" in html
        assert "Superato" in html
        assert examiner.username in html

    def test_il_dettaglio_non_ha_piu_le_statistiche_globali(self, app, exam, player):
        _attempt(exam, player, mode=ExamAttemptMode.SELF_PRACTICE.value, score=14)

        html = (
            _client_for(app, player.username)
            .get(f"/exam/{exam.id}")
            .get_data(as_text=True)
        )

        assert "Le tue volte" in html
        assert "14 su 22" in html
        assert "Candidati" not in html
        assert "In autonomia" not in html

    def test_chi_somministra_vede_le_richieste_che_lo_aspettano(
        self, app, exam, player, examiner
    ):
        _request(exam, player, examiner, status=ExamRequestStatus.NEGOTIATING.value)

        html = _client_for(app, examiner.username).get("/exam/").get_data(as_text=True)

        assert "aspetta te" in html or "aspettano te" in html
        assert player.username in html
