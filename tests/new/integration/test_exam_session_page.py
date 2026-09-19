"""La sessione d'esame, la pagina di chi somministra (fase 3d).

La sessione di prima elencava **tutti** gli esercizi, ognuno col suo campo
numerico e il suo «Registra», e il punteggio compariva due volte: la cifra già
scritta e, accanto, il campo che la ripeteva. Al tavolo se ne somministra uno
per volta: la pagina mette a fuoco quello, scrive la prova dal tastierino in
basso, e quando gli esercizi sono finiti mostra il riepilogo con i due pulsanti
dell'esito.

Le regole di chi può scrivere cosa restano nel servizio
(`test_exam_session.py`, `test_exam_repeated_attempts.py`): qui si prova dove
guarda la pagina e cosa offre.
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
from models.exam.session_view import OUTCOME, StepState, build_focus
from models.location.models import BilliardHall
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


def _make_challenge(title: str, pass_fail: bool = False) -> Challenge:
    challenge = Challenge(
        title=title,
        description=title,
        image_path="/static/uploads/challenges/x.png",
        pass_fail_only=pass_fail,
    )
    db.session.add(challenge)
    db.session.flush()
    return challenge


@pytest.fixture
def examiner(db_session):
    admin = _make_user(UserRole.ADMIN.value)
    user = _make_user()
    RoleGrantService.grant(user.id, GrantableRole.EXAMINER, admin)
    db_session.commit()
    return user


@pytest.fixture
def player(db_session):
    user = _make_user(gamification_override=True)
    db_session.commit()
    return user


@pytest.fixture
def exam(db_session, examiner):
    """Tre prove da 10, poi un superato-o-no, poi due prove da 12."""
    created = ExamService.create_exam(examiner, "Fondamentali — livello 1")
    ExamService.add_challenge_to_exam(
        created.id,
        _make_challenge("Spot Shot Rally").id,
        examiner,
        max_score=10,
        max_attempts=3,
    )
    ExamService.add_challenge_to_exam(
        created.id, _make_challenge("Serie da otto", pass_fail=True).id, examiner
    )
    ExamService.add_challenge_to_exam(
        created.id,
        _make_challenge("Ferma nel cerchio").id,
        examiner,
        max_score=12,
        max_attempts=2,
    )
    db_session.commit()
    return created


@pytest.fixture
def session(db_session, exam, examiner, player) -> ExamAttempt:
    """Sessione certificata in corso: il candidato ha già accettato l'inizio."""
    hall = BilliardHall(name=f"Sala {uuid.uuid4().hex[:5]}", city="Udine")
    db.session.add(hall)
    db.session.flush()
    request = ExamRequestService.create_request(
        player,
        exam.id,
        scheduled_at=utc_now() + timedelta(days=2),
        billiard_hall_id=hall.id,
    )
    ExamRequestService.accept(request.id, examiner)
    attempt = ExamService.open_certified_session(examiner, request.id)
    ExamService.accept_session_start(attempt.id, player)
    db_session.commit()
    return attempt


def _drills(exam):
    return exam.challenges.all()


def _record(attempt, exam_challenge, actor, **kwargs):
    ExamService.record_challenge_result(attempt.id, exam_challenge.id, actor, **kwargs)
    db.session.commit()


def _client_for(app, username: str):
    db.session.commit()
    client = app.test_client()
    client.post(
        "/auth/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=True,
    )
    return client


class TestFocus:
    def test_si_comincia_dal_primo_esercizio_e_dalla_prima_prova(self, session, exam):
        focus = build_focus(session)

        assert focus.step.exam_challenge.id == _drills(exam)[0].id
        assert focus.slot.attempt_number == 1
        assert not focus.correcting
        assert [s.state for s in focus.steps] == [
            StepState.NOW,
            StepState.TODO,
            StepState.TODO,
        ]

    def test_dopo_una_prova_si_resta_sull_esercizio_finche_ha_prove_libere(
        self, session, exam, examiner
    ):
        _record(session, _drills(exam)[0], examiner, score=7)

        focus = build_focus(session)

        assert focus.step.exam_challenge.id == _drills(exam)[0].id
        assert focus.slot.attempt_number == 2

    def test_finite_le_prove_si_passa_al_successivo(self, session, exam, examiner):
        for score in (7, 8, 6):
            _record(session, _drills(exam)[0], examiner, score=score)

        focus = build_focus(session)

        assert focus.step.exam_challenge.id == _drills(exam)[1].id
        assert focus.steps[0].state == StepState.DONE
        assert focus.steps[0].best.score == 8

    def test_rinunciare_a_una_prova_non_richiama_indietro(
        self, session, exam, examiner
    ):
        """Due prove su tre, poi si va avanti: la terza resta vuota e non è
        uno zero, e la pagina non torna a chiederla a ogni ricarica."""
        first, second, _ = _drills(exam)
        _record(session, first, examiner, score=7)
        _record(session, first, examiner, score=8)
        assert build_focus(session).next_at == str(second.id)

        _record(session, second, examiner, passed=True)
        focus = build_focus(session)

        assert focus.step.exam_challenge.id == _drills(exam)[2].id
        assert session.total_score == 8 + 1

    def test_at_porta_su_un_esercizio_preciso_e_su_una_prova_da_correggere(
        self, session, exam, examiner
    ):
        first = _drills(exam)[0]
        _record(session, first, examiner, score=7)
        _record(session, first, examiner, score=8)

        focus = build_focus(session, at=str(first.id), attempt_number=2)

        assert focus.slot.attempt_number == 2
        assert focus.correcting
        assert focus.slot.score == 8

    def test_finiti_gli_esercizi_resta_il_riepilogo(self, session, exam, examiner):
        first, second, third = _drills(exam)
        for score in (7, 8, 6):
            _record(session, first, examiner, score=score)
        _record(session, second, examiner, passed=True)
        for score in (9, 7):
            _record(session, third, examiner, score=score)

        focus = build_focus(session)

        assert focus.step is None
        assert {s.state for s in focus.steps} == {StepState.DONE}

    def test_il_riepilogo_si_raggiunge_anche_prima(self, session):
        assert build_focus(session, at=OUTCOME).step is None


class TestExaminerPage:
    def test_un_esercizio_per_volta_e_il_punteggio_una_volta_sola(
        self, app, session, examiner
    ):
        html = (
            _client_for(app, examiner.username)
            .get(f"/exam/sessions/{session.id}")
            .get_data(as_text=True)
        )

        assert html.count(f"/exam/sessions/{session.id}/results") == 1
        assert 'type="number"' not in html
        assert 'inputmode="numeric"' in html
        assert "Spot Shot Rally" in html
        assert "c7-exam-dock" in html

    def test_chi_somministra_non_ha_la_nav_sotto_il_tastierino(
        self, app, session, examiner, player
    ):
        examiner_html = (
            _client_for(app, examiner.username)
            .get(f"/exam/sessions/{session.id}")
            .get_data(as_text=True)
        )
        candidate_html = (
            _client_for(app, player.username)
            .get(f"/exam/sessions/{session.id}")
            .get_data(as_text=True)
        )

        assert "c7-mobilenav" not in examiner_html
        assert "c7-mobilenav" in candidate_html

    def test_registrare_riporta_sullo_stesso_esercizio(
        self, app, session, exam, examiner
    ):
        first = _drills(exam)[0]
        response = _client_for(app, examiner.username).post(
            f"/exam/sessions/{session.id}/results",
            data={
                "exam_challenge_id": str(first.id),
                "attempt_number": "1",
                "score": "7",
            },
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith(f"/exam/sessions/{session.id}")
        html = (
            _client_for(app, examiner.username)
            .get(f"/exam/sessions/{session.id}")
            .get_data(as_text=True)
        )
        assert 'name="attempt_number" value="2"' in html

    def test_un_esercizio_superato_o_no_ha_due_tasti_e_nessun_numero(
        self, app, session, exam, examiner
    ):
        second = _drills(exam)[1]
        html = (
            _client_for(app, examiner.username)
            .get(f"/exam/sessions/{session.id}?at={second.id}")
            .get_data(as_text=True)
        )

        assert 'name="passed" value="1"' in html
        assert 'name="passed" value="0"' in html
        assert 'inputmode="numeric"' not in html

    def test_l_esito_si_decide_dal_riepilogo(self, app, session, examiner):
        html = (
            _client_for(app, examiner.username)
            .get(f"/exam/sessions/{session.id}?at={OUTCOME}")
            .get_data(as_text=True)
        )

        assert html.count(f"/exam/sessions/{session.id}/complete") == 2
        assert f"/exam/sessions/{session.id}/results" not in html
        assert "confirm(" not in html

    def test_il_candidato_segue_ma_non_scrive(self, app, session, player):
        html = (
            _client_for(app, player.username)
            .get(f"/exam/sessions/{session.id}")
            .get_data(as_text=True)
        )

        assert f"/exam/sessions/{session.id}/results" not in html
        assert f"/exam/sessions/{session.id}/complete" not in html
        assert "Spot Shot Rally" in html


class TestOutcomePage:
    def test_l_esito_dice_chi_ha_certificato_e_il_giorno(
        self, app, session, exam, examiner, player
    ):
        _record(session, _drills(exam)[0], examiner, score=8)
        ExamService.complete_attempt(session.id, examiner, passed=True)
        db.session.commit()

        html = (
            _client_for(app, player.username)
            .get(f"/exam/sessions/{session.id}")
            .get_data(as_text=True)
        )

        assert "Esame superato" in html
        assert examiner.username in html
        assert '<time datetime="' in html

    def test_l_attesa_mette_accetto_in_cima(self, app, exam, examiner, player):
        hall = BilliardHall(name=f"Sala {uuid.uuid4().hex[:5]}", city="Udine")
        db.session.add(hall)
        db.session.flush()
        request = ExamRequestService.create_request(
            player,
            exam.id,
            scheduled_at=utc_now() + timedelta(days=2),
            billiard_hall_id=hall.id,
        )
        ExamRequestService.accept(request.id, examiner)
        attempt = ExamService.open_certified_session(examiner, request.id)
        db.session.commit()

        html = (
            _client_for(app, player.username)
            .get(f"/exam/sessions/{attempt.id}")
            .get_data(as_text=True)
        )

        accept = html.index(f"/exam/sessions/{attempt.id}/accept-start")
        # Prima dell'elenco degli esercizi, non in fondo alla pagina.
        assert accept < html.index("c7-rows__row")
