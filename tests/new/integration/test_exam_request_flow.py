"""Integration test dell'appuntamento d'esame (UJ-3, Fase 3).

Il journey portante: il candidato chiede a **due** esaminatori, uno
contropropone, il candidato rilancia, l'esaminatore accetta — e in quel momento
la richiesta si chiude per l'altro, che ne riceve notifica.

Quel che va davvero presidiato sono i due invarianti della negoziazione, perché
sono l'unica cosa che tiene insieme un ciclo altrimenti aperto:

1. **può accettare solo chi non ha fatto l'ultima proposta** — altrimenti si
   accetterebbe la propria;
2. **la prima controproposta fissa l'interlocutore** — altrimenti N esaminatori
   controproporrebbero in parallelo sullo stesso slot e l'ultimo a scrivere
   sovrascriverebbe gli altri in silenzio.

Copre US-P4, US-P5, US-P5b, US-E3, US-E4, US-E4b, US-E5.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge
from models.exam.request_models import ExamRequest, ExamTimeProposal
from models.exam.request_service import ExamRequestService
from models.exam.services import ExamService
from models.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ValidationError,
)
from models.individual_match.availability_service import AvailabilityService
from models.location.models import BilliardHall
from models.notification.models import Notification, NotificationType
from models.status_enum import ExamRequestRecipientStatus, ExamRequestStatus
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


def _make_hall() -> BilliardHall:
    hall = BilliardHall(name=f"Biliardo {uuid.uuid4().hex[:6]}", is_active=True)
    db.session.add(hall)
    db.session.flush()
    return hall


def _make_challenge() -> Challenge:
    challenge = Challenge(
        description=f"Drill {uuid.uuid4().hex[:6]}",
        image_path="/static/uploads/challenges/x.png",
        pass_fail_only=False,
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
def examiner_one(db_session, admin):
    user = _make_user()
    RoleGrantService.grant(user.id, EXAMINER, admin)
    db_session.commit()
    return user


@pytest.fixture
def examiner_two(db_session, admin):
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
    venue = _make_hall()
    db_session.commit()
    return venue


@pytest.fixture
def exam(db_session, examiner_one, examiner_two):
    """«Fondamentali — livello 1», somministrato da entrambi gli esaminatori."""
    created = ExamService.create_exam(examiner_one, "Fondamentali — livello 1")
    ExamService.add_challenge_to_exam(
        created.id, _make_challenge().id, examiner_one, max_score=10
    )
    ExamService.add_examiner(created.id, examiner_two.id, examiner_one)
    db_session.commit()
    return created


def _thursday_at(hour: int, minute: int = 0):
    """Uno slot futuro qualsiasi: le date reali le sceglie l'utente."""
    return utc_now().replace(minute=minute, second=0, microsecond=0) + timedelta(
        days=3, hours=hour
    )


@pytest.fixture
def request_to_both(db_session, exam, player, hall):
    """Il candidato chiede a entrambi gli esaminatori: giovedì alle 20:00."""
    created = ExamRequestService.create_request(
        player,
        exam.id,
        scheduled_at=_thursday_at(20),
        billiard_hall_id=hall.id,
    )
    db_session.commit()
    return created


class TestRequestCreation:
    """US-P4 — chiedere a tutti, o a esaminatori scelti."""

    def test_request_reaches_every_examiner_of_the_exam(
        self, request_to_both, player, examiner_one, examiner_two
    ):
        assert request_to_both.status == ExamRequestStatus.NEGOTIATING.value
        assert request_to_both.requester_id == player.id
        assert set(request_to_both.recipient_ids()) == {
            examiner_one.id,
            examiner_two.id,
        }
        # Chi ha fatto la prima proposta è il candidato, e nessun interlocutore
        # è ancora fissato: la trattativa è aperta a tutti i destinatari.
        assert request_to_both.last_proposed_by_id == player.id
        assert request_to_both.negotiating_with_id is None

        assert len(request_to_both.time_proposals) == 1
        assert request_to_both.current_proposal is request_to_both.time_proposals[0]

        for examiner in (examiner_one, examiner_two):
            assert (
                _notifications_of(examiner.id, NotificationType.EXAM_REQUEST_RECEIVED)
                == 1
            )

    def test_request_can_be_addressed_to_a_single_examiner(
        self, db_session, exam, player, hall, examiner_one, examiner_two
    ):
        created = ExamRequestService.create_request(
            player,
            exam.id,
            scheduled_at=_thursday_at(20),
            billiard_hall_id=hall.id,
            recipient_ids=[examiner_two.id],
        )
        db_session.commit()

        assert created.recipient_ids() == [examiner_two.id]
        assert (
            _notifications_of(examiner_one.id, NotificationType.EXAM_REQUEST_RECEIVED)
            == 0
        )

    def test_someone_who_does_not_examine_this_exam_is_not_addressable(
        self, db_session, exam, player, hall, admin
    ):
        with pytest.raises(ValidationError):
            ExamRequestService.create_request(
                player,
                exam.id,
                scheduled_at=_thursday_at(20),
                billiard_hall_id=hall.id,
                recipient_ids=[admin.id],
            )

    def test_an_examiner_cannot_request_his_own_exam(
        self, db_session, exam, hall, examiner_one
    ):
        """Auto-somministrazione vietata **a monte**, non solo in sessione."""
        with pytest.raises(PermissionDeniedError):
            ExamRequestService.create_request(
                examiner_one,
                exam.id,
                scheduled_at=_thursday_at(20),
                billiard_hall_id=hall.id,
            )

    def test_a_second_open_request_for_the_same_exam_is_refused(
        self, request_to_both, exam, player, hall
    ):
        with pytest.raises(ConflictError):
            ExamRequestService.create_request(
                player,
                exam.id,
                scheduled_at=_thursday_at(21),
                billiard_hall_id=hall.id,
            )

    def test_the_slot_must_be_in_the_future(self, exam, player, hall):
        with pytest.raises(ValidationError):
            ExamRequestService.create_request(
                player,
                exam.id,
                scheduled_at=utc_now() - timedelta(hours=1),
                billiard_hall_id=hall.id,
            )


class TestNegotiation:
    """US-E5/US-P5 — la controproposta a ciclo, con i suoi due invarianti."""

    def test_the_proposer_cannot_accept_his_own_proposal(self, request_to_both, player):
        """Invariante 1, lato candidato."""
        with pytest.raises(ConflictError):
            ExamRequestService.accept(request_to_both.id, player)

    def test_an_examiner_cannot_counter_his_own_counter_proposal(
        self, db_session, request_to_both, examiner_one
    ):
        """Invariante 1, lato esaminatore: si aspetta la risposta."""
        ExamRequestService.counter_propose(
            request_to_both.id, examiner_one, scheduled_at=_thursday_at(21, 30)
        )
        db_session.commit()

        with pytest.raises(ConflictError):
            ExamRequestService.counter_propose(
                request_to_both.id, examiner_one, scheduled_at=_thursday_at(22)
            )

    def test_the_first_counter_proposal_fixes_the_interlocutor(
        self, db_session, request_to_both, examiner_one, examiner_two, player, hall
    ):
        """Invariante 2 — da qui la trattativa è a due."""
        new_slot = _thursday_at(21, 30)
        ExamRequestService.counter_propose(
            request_to_both.id, examiner_one, scheduled_at=new_slot
        )
        db_session.commit()

        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        assert fresh.negotiating_with_id == examiner_one.id
        assert fresh.last_proposed_by_id == examiner_one.id
        assert fresh.scheduled_at == new_slot
        # La sala resta quella se non se ne propone un'altra.
        assert fresh.billiard_hall_id == hall.id

        # Lo storico è completo e una sola proposta è viva.
        proposals = ExamTimeProposal.query.filter_by(request_id=fresh.id).all()
        assert len(proposals) == 2
        assert sum(1 for p in proposals if p.superseded_at is None) == 1
        assert fresh.current_proposal is not None
        assert fresh.current_proposal.proposed_by_id == examiner_one.id

        # Il candidato è avvisato della controproposta.
        assert _notifications_of(player.id, NotificationType.EXAM_TIME_PROPOSED) == 1

        # L'altro esaminatore non può inserirsi nello scambio…
        with pytest.raises(ConflictError):
            ExamRequestService.counter_propose(
                request_to_both.id, examiner_two, scheduled_at=_thursday_at(19)
            )

    def test_a_shut_out_examiner_can_still_accept_the_slot_on_the_table(
        self, db_session, request_to_both, examiner_one, examiner_two
    ):
        """L'invariante 2 chiude lo *scambio*, non la richiesta."""
        ExamRequestService.counter_propose(
            request_to_both.id, examiner_one, scheduled_at=_thursday_at(21, 30)
        )
        db_session.commit()

        ExamRequestService.accept(request_to_both.id, examiner_two)
        db_session.commit()

        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        assert fresh.accepted_by_id == examiner_two.id

    def test_the_cycle_can_run_more_than_one_round(
        self, db_session, request_to_both, examiner_one, player
    ):
        """Giovedì 20:00 → 21:30 → 21:00: lo scambio prosegue a oltranza."""
        ExamRequestService.counter_propose(
            request_to_both.id, examiner_one, scheduled_at=_thursday_at(21, 30)
        )
        db_session.commit()

        final_slot = _thursday_at(21)
        ExamRequestService.counter_propose(
            request_to_both.id, player, scheduled_at=final_slot
        )
        db_session.commit()

        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        assert fresh.last_proposed_by_id == player.id
        assert fresh.scheduled_at == final_slot
        assert len(fresh.time_proposals) == 3
        # L'interlocutore resta quello: il rilancio non lo cambia.
        assert fresh.negotiating_with_id == examiner_one.id

    def test_a_stranger_cannot_counter_propose(
        self, request_to_both, admin, db_session
    ):
        outsider = _make_user()
        db_session.commit()
        with pytest.raises(PermissionDeniedError):
            ExamRequestService.counter_propose(
                request_to_both.id, outsider, scheduled_at=_thursday_at(19)
            )

    def test_the_counter_proposal_can_move_the_venue_too(
        self, db_session, request_to_both, examiner_one
    ):
        other_hall = _make_hall()
        db_session.commit()

        ExamRequestService.counter_propose(
            request_to_both.id,
            examiner_one,
            scheduled_at=_thursday_at(21),
            billiard_hall_id=other_hall.id,
        )
        db_session.commit()

        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        assert fresh.billiard_hall_id == other_hall.id


class TestAcceptance:
    """US-E4/US-E4b/US-P5b — il primo che accetta vince, gli altri lo sanno."""

    def test_the_examiner_accepts_and_the_appointment_is_fixed(
        self, db_session, request_to_both, examiner_one, examiner_two, player, hall
    ):
        ExamRequestService.counter_propose(
            request_to_both.id, examiner_one, scheduled_at=_thursday_at(21, 30)
        )
        db_session.commit()
        final_slot = _thursday_at(21)
        ExamRequestService.counter_propose(
            request_to_both.id, player, scheduled_at=final_slot
        )
        db_session.commit()

        ExamRequestService.accept(request_to_both.id, examiner_one)
        db_session.commit()

        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        assert fresh.status == ExamRequestStatus.ACCEPTED.value
        assert fresh.accepted_by_id == examiner_one.id
        assert fresh.accepted_at is not None
        assert fresh.scheduled_at == final_slot
        assert fresh.billiard_hall_id == hall.id

        by_examiner = {r.examiner_id: r.status for r in fresh.recipients}
        assert by_examiner[examiner_one.id] == ExamRequestRecipientStatus.ACCEPTED.value
        # Il secondo non ha rifiutato: non ha fatto in tempo. La differenza si
        # vede nello stato **e** nella notifica (US-E4b).
        assert by_examiner[examiner_two.id] == ExamRequestRecipientStatus.CLOSED.value
        assert (
            _notifications_of(examiner_two.id, NotificationType.EXAM_REQUEST_CLOSED)
            == 1
        )
        # Conferma al candidato con data, ora e sala (US-P5b).
        assert _notifications_of(player.id, NotificationType.EXAM_REQUEST_ACCEPTED) == 1

    def test_the_candidate_can_accept_the_counter_proposal(
        self, db_session, request_to_both, examiner_one, player
    ):
        """Senza questo, la trattativa non convergerebbe mai dal lato candidato."""
        ExamRequestService.counter_propose(
            request_to_both.id, examiner_one, scheduled_at=_thursday_at(21, 30)
        )
        db_session.commit()

        ExamRequestService.accept(request_to_both.id, player)
        db_session.commit()

        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        # Accetta il candidato, ma l'appuntamento è con chi ha proposto.
        assert fresh.accepted_by_id == examiner_one.id
        assert fresh.is_accepted
        assert (
            _notifications_of(examiner_one.id, NotificationType.EXAM_REQUEST_ACCEPTED)
            == 1
        )

    def test_an_examiner_cannot_accept_his_own_counter_proposal(
        self, db_session, request_to_both, examiner_one
    ):
        ExamRequestService.counter_propose(
            request_to_both.id, examiner_one, scheduled_at=_thursday_at(21, 30)
        )
        db_session.commit()

        with pytest.raises(ConflictError):
            ExamRequestService.accept(request_to_both.id, examiner_one)

    def test_a_stranger_cannot_accept(self, db_session, request_to_both):
        outsider = _make_user()
        db_session.commit()
        with pytest.raises(PermissionDeniedError):
            ExamRequestService.accept(request_to_both.id, outsider)

    def test_an_expired_request_cannot_be_accepted(
        self, db_session, request_to_both, examiner_one
    ):
        request_to_both.expires_at = utc_now() - timedelta(minutes=1)
        db_session.commit()

        with pytest.raises(ConflictError):
            ExamRequestService.accept(request_to_both.id, examiner_one)


class TestClosingWithoutAppointment:
    """Le uscite che non producono un appuntamento."""

    def test_the_last_decline_closes_the_request(
        self, db_session, request_to_both, examiner_one, examiner_two, player
    ):
        ExamRequestService.decline(request_to_both.id, examiner_one)
        db_session.commit()

        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        # Un rifiuto solo non chiude niente: resta l'altro esaminatore.
        assert fresh.status == ExamRequestStatus.NEGOTIATING.value

        ExamRequestService.decline(request_to_both.id, examiner_two)
        db_session.commit()

        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        assert fresh.status == ExamRequestStatus.EXPIRED.value
        assert _notifications_of(player.id, NotificationType.EXAM_REQUEST_CLOSED) == 1

    def test_who_pulls_out_frees_the_negotiation(
        self, db_session, request_to_both, examiner_one, examiner_two, player
    ):
        """L'invariante 2 non deve lasciare la richiesta ostaggio di chi si sfila."""
        ExamRequestService.counter_propose(
            request_to_both.id, examiner_one, scheduled_at=_thursday_at(21, 30)
        )
        db_session.commit()

        ExamRequestService.decline(request_to_both.id, examiner_one)
        db_session.commit()

        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        assert fresh.negotiating_with_id is None

        # Il secondo esaminatore può ora prendere in mano la trattativa.
        ExamRequestService.counter_propose(
            request_to_both.id, examiner_two, scheduled_at=_thursday_at(19)
        )
        db_session.commit()

        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        assert fresh.negotiating_with_id == examiner_two.id

    def test_the_candidate_cannot_accept_a_proposal_of_who_pulled_out(
        self, db_session, request_to_both, examiner_one, player
    ):
        ExamRequestService.counter_propose(
            request_to_both.id, examiner_one, scheduled_at=_thursday_at(21, 30)
        )
        ExamRequestService.decline(request_to_both.id, examiner_one)
        db_session.commit()

        with pytest.raises(ConflictError):
            ExamRequestService.accept(request_to_both.id, player)

    def test_the_candidate_can_withdraw(
        self, db_session, request_to_both, player, examiner_one, examiner_two
    ):
        ExamRequestService.cancel(request_to_both.id, player)
        db_session.commit()

        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        assert fresh.status == ExamRequestStatus.CANCELLED.value
        assert all(
            r.status == ExamRequestRecipientStatus.CLOSED.value
            for r in fresh.recipients
        )
        for examiner in (examiner_one, examiner_two):
            assert (
                _notifications_of(examiner.id, NotificationType.EXAM_REQUEST_CLOSED)
                == 1
            )

    def test_an_examiner_cannot_withdraw_the_request(
        self, request_to_both, examiner_one
    ):
        with pytest.raises(PermissionDeniedError):
            ExamRequestService.cancel(request_to_both.id, examiner_one)

    def test_expired_requests_are_swept_and_the_candidate_is_told(
        self, db_session, request_to_both, player
    ):
        request_to_both.expires_at = utc_now() - timedelta(minutes=1)
        db_session.commit()

        assert ExamRequestService.expire_pending_requests() == 1
        db_session.commit()

        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        assert fresh.status == ExamRequestStatus.EXPIRED.value
        assert all(
            r.status == ExamRequestRecipientStatus.CLOSED.value
            for r in fresh.recipients
        )
        assert _notifications_of(player.id, NotificationType.EXAM_REQUEST_CLOSED) == 1

        # Idempotente: una richiesta già scaduta non si conta due volte.
        assert ExamRequestService.expire_pending_requests() == 0

    def test_an_accepted_request_never_expires(
        self, db_session, request_to_both, examiner_one
    ):
        ExamRequestService.accept(request_to_both.id, examiner_one)
        request_to_both.expires_at = utc_now() - timedelta(minutes=1)
        db_session.commit()

        assert ExamRequestService.expire_pending_requests() == 0
        fresh = db.session.get(ExamRequest, request_to_both.id)
        assert fresh is not None
        assert fresh.status == ExamRequestStatus.ACCEPTED.value


class TestExaminerAvailability:
    """US-E3/3.4 — le disponibilità si riusano, non si duplicano."""

    def test_available_examiners_at_venue_is_an_intersection(
        self, db_session, exam, hall, examiner_one, examiner_two, player
    ):
        # L'esaminatore uno è disponibile in sala, il due no; il candidato sì
        # ma non è esaminatore di questo esame.
        AvailabilityService.set_venue_availability(
            examiner_one.id, hall.id, available_days=[3], preferred_times="18:00-22:00"
        )
        AvailabilityService.set_venue_availability(player.id, hall.id)
        db_session.commit()

        available = ExamRequestService.available_examiners_at_venue(exam.id, hall.id)
        assert [a["user_id"] for a in available] == [examiner_one.id]
        assert available[0]["preferred_times"] == "18:00-22:00"
        assert available[0]["available_days"] == [3]

    def test_an_examiner_marked_unavailable_drops_out(
        self, db_session, exam, hall, examiner_one
    ):
        AvailabilityService.set_venue_availability(
            examiner_one.id, hall.id, is_available=False
        )
        db_session.commit()

        assert ExamRequestService.available_examiners_at_venue(exam.id, hall.id) == []


class TestQueries:
    """Le letture su cui si appoggeranno le schermate (Fase 5)."""

    def test_each_side_sees_its_own_requests(
        self, request_to_both, player, examiner_one, examiner_two
    ):
        assert [
            r.id for r in ExamRequestService.get_requests_for_requester(player.id)
        ] == [request_to_both.id]
        for examiner in (examiner_one, examiner_two):
            assert [
                r.id for r in ExamRequestService.get_requests_for_examiner(examiner.id)
            ] == [request_to_both.id]

    def test_a_closed_request_leaves_the_open_list(
        self, db_session, request_to_both, player, examiner_one, examiner_two
    ):
        ExamRequestService.accept(request_to_both.id, examiner_one)
        db_session.commit()

        assert ExamRequestService.get_requests_for_examiner(examiner_two.id) == []
        # Per chi l'ha accettata resta: è il suo appuntamento.
        assert [
            r.id for r in ExamRequestService.get_requests_for_examiner(examiner_one.id)
        ] == [request_to_both.id]
        assert (
            ExamRequestService.get_requests_for_requester(
                player.id, only_negotiating=True
            )
            == []
        )
