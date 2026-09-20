"""Integration test del flusso di delega dei ruoli via HTTP (UJ-4, Fase 1).

Percorso: un player chiede il ruolo dalle pagine dei drill → più esaminatori
lo ricevono → il primo che approva concede e chiude le altre richieste, con
notifica agli scartati → admin vede la catena e revoca.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.notification.models import Notification, NotificationType
from models.status_enum import RoleRequestRecipientStatus, RoleRequestStatus
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant import RoleRequest
from models.user.role_grant_service import RoleGrantService

EXAMINER = GrantableRole.EXAMINER
PASSWORD = "test1234"


def _make_user(role: str = UserRole.PLAYER.value) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"{role}_{suffix}",
        email=f"{role}_{suffix}@test.local",
        role=role,
        is_verified=True,
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def _login(client, user):
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": PASSWORD},
        follow_redirects=True,
    )


def _logout(client):
    client.get("/auth/logout", follow_redirects=True)


@pytest.fixture
def admin(db_session):
    user = _make_user(UserRole.ADMIN.value)
    db_session.commit()
    return user


@pytest.fixture
def player(db_session):
    user = _make_user()
    db_session.commit()
    return user


def _notifications_of(user_id: int, ntype: NotificationType):
    return Notification.query.filter_by(user_id=user_id, notification_type=ntype).all()


class TestRoleRequestFlow:
    def test_full_delegation_journey(self, client, db_session, admin, player):
        """UJ-4 end-to-end: richiesta a due esaminatori, il primo approva."""
        examiner_a = _make_user()
        examiner_b = _make_user()
        db_session.commit()

        # Bootstrap: admin promuove i due esaminatori dalla scheda utente.
        _login(client, admin)
        for examiner in (examiner_a, examiner_b):
            resp = client.post(
                f"/roles/grant/examiner/{examiner.id}",
                data={"next": "/"},
                follow_redirects=True,
            )
            assert resp.status_code == 200
        _logout(client)

        assert db_session.get(User, examiner_a.id).is_examiner is True
        assert db_session.get(User, examiner_b.id).is_examiner is True

        # Il player chiede il ruolo a entrambi.
        _login(client, player)
        form = client.get("/roles/request/examiner")
        assert form.status_code == 200

        resp = client.post(
            "/roles/request/examiner",
            data={"recipient_ids": [str(examiner_a.id), str(examiner_b.id)]},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _logout(client)

        request_obj = RoleRequest.query.filter_by(user_id=player.id).one()
        assert request_obj.status == RoleRequestStatus.PENDING.value
        assert len(request_obj.recipients) == 2
        for examiner in (examiner_a, examiner_b):
            assert _notifications_of(
                examiner.id, NotificationType.ROLE_REQUEST_RECEIVED
            )

        # Il primo esaminatore vede la richiesta in coda e approva.
        _login(client, examiner_a)
        queue = client.get("/roles/requests")
        assert queue.status_code == 200
        assert player.username.encode() in queue.data

        resp = client.post(
            f"/roles/requests/{request_obj.id}/process",
            data={"decision": "approve"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _logout(client)

        db_session.expire_all()
        request_obj = db_session.get(RoleRequest, request_obj.id)
        assert request_obj.status == RoleRequestStatus.APPROVED.value
        assert db_session.get(User, player.id).is_examiner is True

        by_recipient = {r.recipient_id: r.status for r in request_obj.recipients}
        assert by_recipient[examiner_a.id] == RoleRequestRecipientStatus.APPROVED.value
        assert by_recipient[examiner_b.id] == RoleRequestRecipientStatus.CLOSED.value

        # US-A2 lato scartato: la richiesta non sparisce in silenzio.
        assert _notifications_of(examiner_b.id, NotificationType.ROLE_REQUEST_CLOSED)
        assert _notifications_of(player.id, NotificationType.ROLE_REQUEST_PROCESSED)

        # Il secondo esaminatore non ha più nulla in coda.
        _login(client, examiner_b)
        queue = client.get("/roles/requests")
        assert queue.status_code == 200
        resp = client.post(
            f"/roles/requests/{request_obj.id}/process",
            data={"decision": "approve"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _logout(client)

        # US-A3: admin legge la catena e revoca.
        _login(client, admin)
        holders = client.get("/roles/holders/examiner")
        assert holders.status_code == 200
        assert player.username.encode() in holders.data

        resp = client.post(
            f"/roles/revoke/examiner/{examiner_a.id}",
            data={"next": "/roles/holders/examiner"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        db_session.expire_all()
        assert db_session.get(User, examiner_a.id).is_examiner is False
        # Il ruolo revocato non cancella le concessioni che aveva rilasciato.
        assert db_session.get(User, player.id).is_examiner is True

    def test_player_queue_is_forbidden(self, client, db_session, player):
        """Un player senza ruolo non accede alla coda delle richieste."""
        _login(client, player)
        assert client.get("/roles/requests").status_code == 403

    def test_player_cannot_grant_the_role(self, client, db_session, player):
        other = _make_user()
        db_session.commit()

        _login(client, player)
        client.post(f"/roles/grant/examiner/{other.id}", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(User, other.id).is_examiner is False

    def test_examiner_cannot_revoke(self, client, db_session, admin, player):
        """La revoca è riservata ad admin, anche fra pari (US-A3)."""
        examiner = _make_user()
        db_session.commit()
        RoleGrantService.grant(examiner.id, EXAMINER, admin)
        RoleGrantService.grant(player.id, EXAMINER, admin)
        db_session.commit()

        _login(client, examiner)
        client.post(f"/roles/revoke/examiner/{player.id}", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(User, player.id).is_examiner is True

    def test_holders_audit_is_for_admin_and_holders(
        self, client, db_session, admin, player
    ):
        """Emendamento ADR-041 del 20/09: chi può nominare vede la catena.

        Prima era admin-only. Il ruolo si propaga a catena, quindi un titolare
        che non può vedere da dove arriva un collega delega al buio. La
        **revoca** invece resta dell'admin, e il test qui sopra la difende.
        """
        RoleGrantService.grant(player.id, EXAMINER, admin)
        db_session.commit()

        _login(client, player)
        assert client.get("/roles/holders/examiner").status_code == 200

    def test_holders_audit_is_closed_to_who_has_not_the_role(
        self, client, db_session, player
    ):
        _login(client, player)
        assert client.get("/roles/holders/examiner").status_code == 403

    def test_unknown_role_is_404(self, client, db_session, admin):
        _login(client, admin)
        assert client.get("/roles/request/venue_manager").status_code == 404
        assert client.get("/roles/holders/wizard").status_code == 404

    def test_request_without_holders_goes_to_admin(
        self, client, db_session, admin, player
    ):
        """UJ-4 variante 2: nessun esaminatore ancora, la richiesta va ad admin."""
        _login(client, player)
        resp = client.post("/roles/request/examiner", follow_redirects=True)
        assert resp.status_code == 200
        _logout(client)

        request_obj = RoleRequest.query.filter_by(user_id=player.id).one()
        assert {r.recipient_id for r in request_obj.recipients} == {admin.id}

        _login(client, admin)
        resp = client.post(
            f"/roles/requests/{request_obj.id}/process",
            data={"decision": "approve"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        db_session.expire_all()
        assert db_session.get(User, player.id).is_examiner is True
