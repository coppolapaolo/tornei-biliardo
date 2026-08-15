"""Chi arriva dove, nelle route dell'esame (Fase 5).

I due gate sono **ortogonali** e vanno tenuti distinti:

- ``take_exam`` (progressione, L2) dice se puoi *sostenere* un esame;
- il ruolo esaminatore (L1) dice se puoi *somministrarlo*.

Il caso che li mette alla prova è l'esaminatore che non ha ancora macinato i
suoi drill: non può sostenere esami, ma deve raggiungere i propri. Gattando il
catalogo sul solo ``take_exam`` si otteneva un esaminatore che non raggiungeva
niente — trovato provando il percorso a mano, non dai test.

⚠️ Due note di harness, entrambe imparate a caro prezzo:

1. **Si autentica con una POST vera a ``/auth/login``**, non falsificando la
   sessione: dopo una fixture che passa da un servizio ``@transactional``, una
   sessione scritta a mano non viene riconosciuta e la route risponde con un
   redirect al login — il test fallisce per una ragione che non c'entra niente
   con ciò che verifica. È lo stesso approccio di ``test_role_request_flow.py``.
2. **La feature va seminata.** ``UnlockEngine`` è fail-open sui codici non
   configurati: senza seminare ``take_exam`` il gate lascia passare tutti, e il
   test verificherebbe il nulla credendo di verificare una porta chiusa.
"""

from __future__ import annotations

import json
import uuid

import pytest

from models.base import db
from models.exam.models import Exam
from models.gamification.feature_models import FeatureConfig
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

PASSWORD = "prova123"


def _make_user(role: str = UserRole.PLAYER.value, **kwargs) -> User:
    user = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        role=role,
        onboarding_completed=True,
        **kwargs,
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


def _seed_take_exam() -> None:
    """Semina la regola ABAC di ``take_exam``: 3 drill completati."""
    if db.session.get(FeatureConfig, "take_exam") is not None:
        return
    db.session.add(
        FeatureConfig(
            code="take_exam",
            name="Sostieni un esame",
            description="",
            rules=json.dumps(
                [
                    {
                        "description": "3+ drill completati",
                        "conditions": [
                            {
                                "type": "METRIC",
                                "metric": "challenges_completed",
                                "operator": "gte",
                                "value": 3,
                            }
                        ],
                    }
                ]
            ),
            is_active=True,
        )
    )
    db.session.commit()


def _client_for(app, username: str):
    """Un client fresco, autenticato con una POST vera al login."""
    db.session.commit()

    client = app.test_client()
    client.post(
        "/auth/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=True,
    )
    return client


@pytest.fixture
def examiner(db_session) -> User:
    """Ha il ruolo, **non** ha sbloccato ``take_exam``: zero drill."""
    admin = _make_user(role=UserRole.ADMIN.value)
    user = _make_user()
    RoleGrantService.grant(user.id, GrantableRole.EXAMINER, granted_by=admin)
    db.session.commit()
    return user


@pytest.fixture
def exam(db_session, examiner) -> Exam:
    exam = Exam(
        name=f"Esame {uuid.uuid4().hex[:6]}",
        description="",
        examiner_id=examiner.id,
        is_active=True,
    )
    db.session.add(exam)
    db.session.commit()
    return exam


class TestTheTwoGatesAreOrthogonal:
    def test_an_examiner_without_drills_reaches_the_catalog(
        self, app, db_session, examiner
    ):
        """Altrimenti chi ha il ruolo non raggiunge nessuna porta."""
        _seed_take_exam()
        client = _client_for(app, examiner.username)
        assert client.get("/exam/").status_code == 200

    def test_an_examiner_without_drills_reaches_his_management_area(
        self, app, db_session, examiner
    ):
        _seed_take_exam()
        client = _client_for(app, examiner.username)
        assert client.get("/exam/manage").status_code == 200

    def test_but_he_still_cannot_sit_an_exam(self, app, db_session, examiner, exam):
        """Il ruolo apre la porta della gestione, non quella dell'esame."""
        _seed_take_exam()
        client = _client_for(app, examiner.username)
        assert client.post(f"/exam/{exam.id}/practice").status_code == 403

    def test_a_player_without_drills_is_refused_at_the_door(self, app, db_session):
        _seed_take_exam()
        client = _client_for(app, _make_user().username)
        assert client.get("/exam/").status_code == 403

    def test_a_player_with_the_override_gets_in(self, app, db_session):
        """È la via di debug prevista (US-D1), e deve continuare a funzionare."""
        _seed_take_exam()
        client = _client_for(app, _make_user(gamification_override=True).username)
        assert client.get("/exam/").status_code == 200

    def test_a_plain_player_cannot_manage_exams(self, app, db_session):
        """L'override apre la progressione, non concede il ruolo."""
        _seed_take_exam()
        client = _client_for(app, _make_user(gamification_override=True).username)
        assert client.get("/exam/manage").status_code == 403


class TestTheDebugSelfGrant:
    def test_it_grants_the_role_in_debug_mode(self, app, db_session):
        """US-D1: lo sviluppatore si concede il ruolo senza costruire una catena."""
        user = _make_user()
        user_id = user.id
        client = _client_for(app, user.username)

        app.config["DEBUG_MODE"] = True
        try:
            response = client.post("/roles/debug/self-grant/examiner")
        finally:
            app.config["DEBUG_MODE"] = False

        assert response.status_code in (302, 200)
        assert db.session.get(User, user_id).is_examiner is True

    def test_it_does_not_exist_outside_debug_mode(self, app, db_session):
        """404, non 403: in produzione l'endpoint non deve nemmeno esistere."""
        user = _make_user()
        user_id = user.id
        client = _client_for(app, user.username)

        app.config["DEBUG_MODE"] = False
        response = client.post("/roles/debug/self-grant/examiner")

        assert response.status_code == 404
        assert db.session.get(User, user_id).is_examiner is False

    def test_the_grant_is_a_normal_one(self, app, db_session):
        """Revocabile e visibile nell'audit: una scorciatoia, non un privilegio."""
        from models.user.role_grant import RoleGrant

        user = _make_user()
        user_id = user.id
        client = _client_for(app, user.username)

        app.config["DEBUG_MODE"] = True
        try:
            client.post("/roles/debug/self-grant/examiner")
        finally:
            app.config["DEBUG_MODE"] = False

        grant = RoleGrant.query.filter_by(user_id=user_id).first()
        assert grant is not None
        assert grant.revoked_at is None
        assert "debug" in (grant.notes or "")


class TestTheAppointmentSlotKeepsTheHourTheUserTyped:
    """Il fuso: l'utente digita l'ora italiana, il DB tiene naive-UTC.

    Salvando il valore com'è, un appuntamento fissato per le 21:00 verrebbe
    mostrato a entrambe le parti come le 23:00 — e qualcuno si presenterebbe
    alla sala all'ora sbagliata.
    """

    def test_a_typed_slot_is_shown_back_unchanged(self, app):
        from routes.exam.requests import _parse_slot
        from utils.jinja import format_datetime_local_text

        with app.app_context():
            stored = _parse_slot("2026-06-12T21:00")
            assert stored is not None
            assert stored.tzinfo is None, "in DB si tengono i naive"
            assert "21:00" in format_datetime_local_text(stored)

    def test_it_also_holds_in_winter_time(self, app):
        """L'ora legale sposta l'offset: la conversione deve seguirlo."""
        from routes.exam.requests import _parse_slot
        from utils.jinja import format_datetime_local_text

        with app.app_context():
            stored = _parse_slot("2026-01-15T21:00")
            assert "21:00" in format_datetime_local_text(stored)

    def test_a_malformed_slot_is_none_not_an_exception(self, app):
        """Il servizio dirà che manca la data: meglio di uno strptime che esplode."""
        from routes.exam.requests import _parse_slot

        assert _parse_slot("non-una-data") is None
        assert _parse_slot("") is None
        assert _parse_slot(None) is None


class TestTheDebugRedirectIsNotAnOpenDoor:
    def test_an_external_next_is_refused(self, app, db_session):
        """``next`` arriva da un form: grezzo sarebbe un open redirect."""
        user = _make_user()
        client = _client_for(app, user.username)

        app.config["DEBUG_MODE"] = True
        try:
            response = client.post(
                "/roles/debug/self-grant/examiner",
                data={"next": "https://evil.example.com/phish"},
            )
        finally:
            app.config["DEBUG_MODE"] = False

        assert "evil.example.com" not in response.headers.get("Location", "")

    def test_an_internal_next_is_honoured(self, app, db_session):
        user = _make_user()
        client = _client_for(app, user.username)

        app.config["DEBUG_MODE"] = True
        try:
            response = client.post(
                "/roles/debug/self-grant/examiner",
                data={"next": "/exam/"},
            )
        finally:
            app.config["DEBUG_MODE"] = False

        assert response.headers.get("Location", "").endswith("/exam/")
