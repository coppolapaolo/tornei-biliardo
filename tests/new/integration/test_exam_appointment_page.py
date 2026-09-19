"""L'appuntamento d'esame, la pagina (fase 3c).

Tre difetti della pagina di prima, tutti visti nelle schermate della guida:

* «Accetto lo slot» stava in fondo, sotto la storia della trattativa e — sul
  telefono — dietro la nav flottante. Ora nasce **dentro la card della
  proposta**, accanto al dato su cui si decide;
* le date erano ``20/09/2026, 23:30``: un appuntamento si dice «sab 26 set»;
* la controproposta era un solo ``datetime-local`` e non lasciava cambiare
  sala, che pure il servizio accetta da sempre.

Gli invarianti della trattativa restano dove sono, nel servizio
(`test_exam_request_flow.py`): qui si prova solo ciò che la pagina mostra e
ciò che il modulo manda.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge
from models.exam.overview import ExamOverview, RecipientStance
from models.exam.request_models import ExamRequest
from models.exam.request_service import ExamRequestService
from models.exam.services import ExamService
from models.location.models import BilliardHall
from models.status_enum import ExamRequestStatus
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService
from utils.local_time import parse_local_datetime

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


def _make_examiner() -> User:
    admin = _make_user(UserRole.ADMIN.value)
    user = _make_user()
    RoleGrantService.grant(user.id, GrantableRole.EXAMINER, admin)
    return user


def _hall(name: str) -> BilliardHall:
    hall = BilliardHall(name=f"{name} {uuid.uuid4().hex[:5]}", city="Udine")
    db.session.add(hall)
    db.session.flush()
    return hall


@pytest.fixture
def examiner(db_session):
    user = _make_examiner()
    db_session.commit()
    return user


@pytest.fixture
def second_examiner(db_session):
    user = _make_examiner()
    db_session.commit()
    return user


@pytest.fixture
def exam(db_session, examiner, second_examiner):
    exam = ExamService.create_exam(examiner, "Fondamentali — livello 2")
    challenge = Challenge(
        title="Spot Shot Rally",
        description="x",
        image_path="/static/uploads/challenges/x.png",
    )
    db.session.add(challenge)
    db.session.flush()
    ExamService.add_challenge_to_exam(exam.id, challenge.id, examiner, max_score=10)
    ExamService.add_examiner(exam.id, second_examiner.id, examiner)
    db_session.commit()
    return exam


@pytest.fixture
def player(db_session):
    user = _make_user(gamification_override=True)
    db_session.commit()
    return user


@pytest.fixture
def hall(db_session):
    hall = _hall("Biliardo Centrale")
    db_session.commit()
    return hall


@pytest.fixture
def open_request(exam, player, hall) -> ExamRequest:
    request = ExamRequestService.create_request(
        player,
        exam.id,
        scheduled_at=utc_now() + timedelta(days=5),
        billiard_hall_id=hall.id,
    )
    db.session.commit()
    return request


def _client_for(app, username: str):
    db.session.commit()
    client = app.test_client()
    client.post(
        "/auth/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=True,
    )
    return client


class TestRecipientStances:
    """Chi sta trattando, chi non ha risposto: la riga sotto la storia."""

    def test_prima_di_ogni_controproposta_nessuno_ha_risposto(self, open_request):
        stances = ExamOverview.recipient_stances(open_request)

        assert {s for _, s in stances} == {RecipientStance.SILENT}

    def test_chi_contropropone_sta_trattando_e_gli_altri_no(
        self, open_request, examiner, second_examiner
    ):
        ExamRequestService.counter_propose(
            open_request.id, examiner, scheduled_at=utc_now() + timedelta(days=6)
        )
        db.session.commit()

        stances = {
            r.examiner_id: s for r, s in ExamOverview.recipient_stances(open_request)
        }

        assert stances[examiner.id] == RecipientStance.NEGOTIATING
        assert stances[second_examiner.id] == RecipientStance.SILENT

    def test_chi_accetta_e_chi_resta_fuori(
        self, open_request, examiner, second_examiner
    ):
        ExamRequestService.accept(open_request.id, examiner)
        db.session.commit()

        stances = {
            r.examiner_id: s for r, s in ExamOverview.recipient_stances(open_request)
        }

        assert stances[examiner.id] == RecipientStance.ACCEPTED
        assert stances[second_examiner.id] == RecipientStance.CLOSED

    def test_chi_si_sfila(self, open_request, examiner):
        ExamRequestService.decline(open_request.id, examiner)
        db.session.commit()

        stances = {
            r.examiner_id: s for r, s in ExamOverview.recipient_stances(open_request)
        }

        assert stances[examiner.id] == RecipientStance.DECLINED


class TestDetailPage:
    def test_accetto_sta_nella_card_della_proposta_prima_di_tutto_il_resto(
        self, app, open_request, examiner
    ):
        html = (
            _client_for(app, examiner.username)
            .get(f"/exam/requests/{open_request.id}")
            .get_data(as_text=True)
        )

        accept = html.index(f"/exam/requests/{open_request.id}/accept")
        counter = html.index(f"/exam/requests/{open_request.id}/counter")
        story = html.index("c7-tl")
        assert accept < counter < story
        # Dentro la card, non in una barra in fondo alla pagina.
        card = html.index("c7-card--accent")
        assert card < accept
        assert "c7-actionbar" not in html[card:accept]

    def test_la_data_si_legge_come_la_si_dice(self, app, open_request, examiner):
        html = (
            _client_for(app, examiner.username)
            .get(f"/exam/requests/{open_request.id}")
            .get_data(as_text=True)
        )

        assert '<time datetime="' in html
        assert open_request.scheduled_at.strftime("%d/%m/%Y") not in html

    def test_la_controproposta_chiede_giorno_ora_e_sala(
        self, app, open_request, examiner, hall
    ):
        html = (
            _client_for(app, examiner.username)
            .get(f"/exam/requests/{open_request.id}")
            .get_data(as_text=True)
        )

        assert 'name="scheduled_date"' in html
        assert 'name="scheduled_time"' in html
        assert 'type="datetime-local"' not in html
        # La sala di adesso è già scelta: di solito è l'ora a non andare bene.
        assert f'<option value="{hall.id}" selected' in html

    def test_chi_ha_proposto_per_ultimo_non_vede_comandi_che_verrebbero_rifiutati(
        self, app, open_request, player
    ):
        html = (
            _client_for(app, player.username)
            .get(f"/exam/requests/{open_request.id}")
            .get_data(as_text=True)
        )

        assert f"/exam/requests/{open_request.id}/accept" not in html
        assert f"/exam/requests/{open_request.id}/counter" not in html
        assert f"/exam/requests/{open_request.id}/cancel" in html

    def test_a_trattativa_avviata_gli_altri_possono_solo_accettare(
        self, app, open_request, examiner, second_examiner
    ):
        ExamRequestService.counter_propose(
            open_request.id, examiner, scheduled_at=utc_now() + timedelta(days=6)
        )
        html = (
            _client_for(app, second_examiner.username)
            .get(f"/exam/requests/{open_request.id}")
            .get_data(as_text=True)
        )

        assert f"/exam/requests/{open_request.id}/accept" in html
        assert f"/exam/requests/{open_request.id}/counter" not in html

    def test_l_appuntamento_fissato_dice_con_chi(self, app, open_request, examiner):
        ExamRequestService.accept(open_request.id, examiner)
        html = (
            _client_for(app, examiner.username)
            .get(f"/exam/requests/{open_request.id}")
            .get_data(as_text=True)
        )

        assert "c7-card--ok" in html
        assert f"/exam/requests/{open_request.id}/open-session" in html


class TestSplitDateTime:
    """Giorno e ora arrivano in due campi, nell'ora di chi scrive (ADR-043)."""

    def test_la_controproposta_compone_giorno_e_ora_e_cambia_sala(
        self, app, open_request, examiner
    ):
        other_hall = _hall("Sala Nuova")
        day = (utc_now() + timedelta(days=8)).strftime("%Y-%m-%d")
        client = _client_for(app, examiner.username)

        client.post(
            f"/exam/requests/{open_request.id}/counter",
            data={
                "scheduled_date": day,
                "scheduled_time": "20:00",
                "billiard_hall_id": str(other_hall.id),
            },
        )

        request = db.session.get(ExamRequest, open_request.id)
        db.session.refresh(request)
        assert request.scheduled_at == parse_local_datetime(f"{day}T20:00")
        assert request.billiard_hall_id == other_hall.id
        assert len(request.time_proposals) == 2

    def test_la_richiesta_nuova_compone_giorno_e_ora(self, app, exam, player, hall):
        day = (utc_now() + timedelta(days=8)).strftime("%Y-%m-%d")
        client = _client_for(app, player.username)

        client.post(
            f"/exam/{exam.id}/request",
            data={
                "scheduled_date": day,
                "scheduled_time": "18:30",
                "billiard_hall_id": str(hall.id),
            },
        )

        request = ExamRequestService.get_open_request(player.id, exam.id)
        assert request is not None
        assert request.scheduled_at == parse_local_datetime(f"{day}T18:30")

    def test_un_giorno_senza_ora_non_diventa_mezzanotte(
        self, app, open_request, examiner
    ):
        day = (utc_now() + timedelta(days=8)).strftime("%Y-%m-%d")
        client = _client_for(app, examiner.username)

        client.post(
            f"/exam/requests/{open_request.id}/counter",
            data={"scheduled_date": day, "scheduled_time": ""},
        )

        request = db.session.get(ExamRequest, open_request.id)
        db.session.refresh(request)
        assert len(request.time_proposals) == 1


class TestListPage:
    def test_l_elenco_dice_lo_stato_e_il_giorno(
        self, app, open_request, player, examiner
    ):
        client = _client_for(app, player.username)
        html = client.get("/exam/requests").get_data(as_text=True)
        assert "In trattativa" in html
        assert '<time datetime="' in html

        ExamRequestService.accept(open_request.id, examiner)
        html = (
            _client_for(app, player.username)
            .get("/exam/requests")
            .get_data(as_text=True)
        )
        assert "Confermato" in html

    def test_una_trattativa_a_tempo_finito_non_risulta_in_corso(
        self, app, open_request, player
    ):
        request = db.session.get(ExamRequest, open_request.id)
        request.expires_at = utc_now() - timedelta(hours=1)
        db.session.commit()
        assert request.status == ExamRequestStatus.NEGOTIATING.value

        html = (
            _client_for(app, player.username)
            .get("/exam/requests")
            .get_data(as_text=True)
        )

        assert "In trattativa" not in html
        assert "Scaduta" in html
