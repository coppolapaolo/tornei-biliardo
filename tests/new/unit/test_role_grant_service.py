"""Unit test del meccanismo generico di delega dei ruoli (ADR-038, Fase 1).

Copre US-A1 (promozione da admin), US-A2 (un titolare concede), US-A3 (revoca
e audit), US-A4 (il meccanismo è generico e la catena è una proprietà
per-ruolo) e US-D1 (auto-concessione solo in DEBUG_MODE).
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from models.status_enum import RoleRequestRecipientStatus, RoleRequestStatus
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant import RoleGrant
from models.user.role_grant_service import GRANT_POLICY, RoleGrantService

EXAMINER = GrantableRole.EXAMINER


def _make_user(role: str = UserRole.PLAYER.value) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"{role}_{suffix}",
        email=f"{role}_{suffix}@test.local",
        role=role,
    )
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.flush()
    return user


@pytest.fixture
def admin(db_session):
    return _make_user(UserRole.ADMIN.value)


@pytest.fixture
def player(db_session):
    return _make_user()


# ────────────────────────────────────────────────────────────────────────────────
# Matrice di autorizzazione (US-A4)
# ────────────────────────────────────────────────────────────────────────────────
def test_policy_declares_examiner_as_self_propagating(app):
    """La catena è una proprietà del ruolo, non del meccanismo."""
    with app.app_context():
        policy = RoleGrantService.get_policy(EXAMINER)
        assert policy.self_propagating is True
        assert policy.request_feature_code == "request_examiner"


def test_get_policy_rejects_unknown_role(app):
    with app.app_context():

        class _Fake(str):
            pass

        with pytest.raises(ValidationError):
            RoleGrantService.get_policy(_Fake("nope"))  # type: ignore[arg-type]


def test_parse_role_rejects_unknown_string(app):
    with app.app_context():
        with pytest.raises(ValidationError):
            RoleGrantService.parse_role("venue_manager")


def test_admin_can_grant_and_player_cannot(app, admin, player):
    with app.app_context():
        assert RoleGrantService.can_grant(admin, EXAMINER) is True
        assert RoleGrantService.can_grant(player, EXAMINER) is False
        assert RoleGrantService.can_grant(None, EXAMINER) is False


def test_examiner_can_grant_because_role_is_self_propagating(app, admin, player):
    """US-A2: è questo che scarica admin a regime."""
    with app.app_context():
        RoleGrantService.grant(player.id, EXAMINER, admin)
        assert RoleGrantService.can_grant(player, EXAMINER) is True


def test_non_propagating_role_never_grants(app, admin, player, monkeypatch):
    """Con self_propagating=False il titolare non concede: solo admin."""
    with app.app_context():
        RoleGrantService.grant(player.id, EXAMINER, admin)
        policy = GRANT_POLICY[EXAMINER]
        monkeypatch.setitem(
            GRANT_POLICY,
            EXAMINER,
            type(policy)(
                self_propagating=False,
                request_feature_code=policy.request_feature_code,
            ),
        )
        assert RoleGrantService.can_grant(player, EXAMINER) is False
        assert RoleGrantService.can_grant(admin, EXAMINER) is True


def test_only_admin_can_revoke(app, admin, player):
    """La revoca resta l'unico punto di contenimento della catena (US-A3)."""
    with app.app_context():
        RoleGrantService.grant(player.id, EXAMINER, admin)
        assert RoleGrantService.can_revoke(admin, EXAMINER) is True
        assert RoleGrantService.can_revoke(player, EXAMINER) is False

        with pytest.raises(PermissionDeniedError):
            RoleGrantService.revoke(player.id, EXAMINER, player)


# ────────────────────────────────────────────────────────────────────────────────
# Grant / revoca
# ────────────────────────────────────────────────────────────────────────────────
def test_grant_makes_user_examiner_without_touching_primary_role(app, admin, player):
    """Il ruolo è ortogonale: un player che diventa esaminatore resta player."""
    with app.app_context():
        grant = RoleGrantService.grant(player.id, EXAMINER, admin)

        assert grant.granted_by_id == admin.id
        assert grant.is_active is True
        assert RoleGrantService.has_role(player.id, EXAMINER) is True
        assert player.is_examiner is True
        assert player.role == UserRole.PLAYER.value
        assert player.is_player is True


def test_admin_is_examiner_without_any_grant(app, admin):
    with app.app_context():
        assert admin.is_examiner is True
        assert RoleGrantService.has_role(admin.id, EXAMINER) is False


def test_grant_by_unauthorized_actor_is_denied(app, player):
    with app.app_context():
        other = _make_user()
        with pytest.raises(PermissionDeniedError):
            RoleGrantService.grant(other.id, EXAMINER, player)


def test_grant_to_missing_user_raises_not_found(app, admin):
    with app.app_context():
        with pytest.raises(NotFoundError):
            RoleGrantService.grant(999999, EXAMINER, admin)


def test_double_grant_conflicts(app, admin, player):
    """L'indice UNIQUE parziale ammette un solo grant attivo per (utente, ruolo)."""
    with app.app_context():
        RoleGrantService.grant(player.id, EXAMINER, admin)
        with pytest.raises(ConflictError):
            RoleGrantService.grant(player.id, EXAMINER, admin)


def test_revoke_then_regrant_keeps_the_audit_chain(app, admin, player):
    """La revoca è soft: la storia delle deleghe resta leggibile (US-A3)."""
    with app.app_context():
        RoleGrantService.grant(player.id, EXAMINER, admin)
        revoked = RoleGrantService.revoke(player.id, EXAMINER, admin)

        assert revoked.is_active is False
        assert revoked.revoked_by_id == admin.id
        assert player.is_examiner is False

        RoleGrantService.grant(player.id, EXAMINER, admin)
        assert player.is_examiner is True

        history = RoleGrantService.list_grants_history(EXAMINER)
        assert len(history) == 2
        assert sum(1 for g in history if g.is_active) == 1


def test_double_revoke_is_rejected_not_silently_duplicated(app, admin, player):
    """Regressione del bug latente di VenueManagement (UniqueConstraint su
    colonna booleana): con l'indice parziale la seconda revoca è possibile
    dopo un nuovo grant, e senza grant attivo dà NotFoundError."""
    with app.app_context():
        RoleGrantService.grant(player.id, EXAMINER, admin)
        RoleGrantService.revoke(player.id, EXAMINER, admin)

        with pytest.raises(NotFoundError):
            RoleGrantService.revoke(player.id, EXAMINER, admin)

        RoleGrantService.grant(player.id, EXAMINER, admin)
        RoleGrantService.revoke(player.id, EXAMINER, admin)
        assert RoleGrant.query.filter_by(user_id=player.id).count() == 2


def test_list_holders_returns_only_active_grants(app, admin, player):
    with app.app_context():
        other = _make_user()
        RoleGrantService.grant(player.id, EXAMINER, admin)
        RoleGrantService.grant(other.id, EXAMINER, admin)
        RoleGrantService.revoke(other.id, EXAMINER, admin)

        holders = RoleGrantService.list_holders(EXAMINER)
        assert [g.user_id for g in holders] == [player.id]


# ────────────────────────────────────────────────────────────────────────────────
# Richieste (US-P8, US-A2)
# ────────────────────────────────────────────────────────────────────────────────
def test_request_defaults_to_all_holders(app, admin, player):
    with app.app_context():
        ex1 = _make_user()
        ex2 = _make_user()
        RoleGrantService.grant(ex1.id, EXAMINER, admin)
        RoleGrantService.grant(ex2.id, EXAMINER, admin)

        req = RoleGrantService.create_request(player.id, EXAMINER)

        assert req.status == RoleRequestStatus.PENDING.value
        assert {r.recipient_id for r in req.recipients} == {ex1.id, ex2.id}


def test_request_can_target_specific_recipients(app, admin, player):
    with app.app_context():
        ex1 = _make_user()
        ex2 = _make_user()
        RoleGrantService.grant(ex1.id, EXAMINER, admin)
        RoleGrantService.grant(ex2.id, EXAMINER, admin)

        req = RoleGrantService.create_request(
            player.id, EXAMINER, recipient_ids=[ex2.id]
        )
        assert {r.recipient_id for r in req.recipients} == {ex2.id}


def test_request_falls_back_to_admins_when_no_holder_exists(app, admin, player):
    """UJ-4 variante 2: senza titolari la richiesta può andare solo ad admin."""
    with app.app_context():
        req = RoleGrantService.create_request(player.id, EXAMINER)
        assert {r.recipient_id for r in req.recipients} == {admin.id}


def test_request_rejects_recipients_that_are_not_holders(app, admin, player):
    with app.app_context():
        ex1 = _make_user()
        RoleGrantService.grant(ex1.id, EXAMINER, admin)
        outsider = _make_user()

        with pytest.raises(ValidationError):
            RoleGrantService.create_request(
                player.id, EXAMINER, recipient_ids=[outsider.id]
            )


def test_second_pending_request_conflicts(app, admin, player):
    with app.app_context():
        RoleGrantService.create_request(player.id, EXAMINER)
        with pytest.raises(ConflictError):
            RoleGrantService.create_request(player.id, EXAMINER)


def test_request_from_someone_who_already_has_the_role_conflicts(app, admin, player):
    with app.app_context():
        RoleGrantService.grant(player.id, EXAMINER, admin)
        with pytest.raises(ConflictError):
            RoleGrantService.create_request(player.id, EXAMINER)


def test_first_approval_grants_and_closes_the_others(app, admin, player):
    """US-A2 / UJ-4: nessun quorum, nessun secondo assenso."""
    with app.app_context():
        ex1 = _make_user()
        ex2 = _make_user()
        RoleGrantService.grant(ex1.id, EXAMINER, admin)
        RoleGrantService.grant(ex2.id, EXAMINER, admin)

        req = RoleGrantService.create_request(player.id, EXAMINER)
        RoleGrantService.process_request(req.id, ex1, approve=True)

        assert req.status == RoleRequestStatus.APPROVED.value
        assert req.processed_by_id == ex1.id
        assert player.is_examiner is True

        by_recipient = {r.recipient_id: r.status for r in req.recipients}
        assert by_recipient[ex1.id] == RoleRequestRecipientStatus.APPROVED.value
        assert by_recipient[ex2.id] == RoleRequestRecipientStatus.CLOSED.value


def test_second_examiner_cannot_process_a_closed_request(app, admin, player):
    with app.app_context():
        ex1 = _make_user()
        ex2 = _make_user()
        RoleGrantService.grant(ex1.id, EXAMINER, admin)
        RoleGrantService.grant(ex2.id, EXAMINER, admin)

        req = RoleGrantService.create_request(player.id, EXAMINER)
        RoleGrantService.process_request(req.id, ex1, approve=True)

        with pytest.raises(ConflictError):
            RoleGrantService.process_request(req.id, ex2, approve=True)


def test_single_rejection_leaves_the_request_open_for_the_others(app, admin, player):
    """Un rifiuto vale per chi lo esprime, non chiude la richiesta per tutti."""
    with app.app_context():
        ex1 = _make_user()
        ex2 = _make_user()
        RoleGrantService.grant(ex1.id, EXAMINER, admin)
        RoleGrantService.grant(ex2.id, EXAMINER, admin)

        req = RoleGrantService.create_request(
            player.id, EXAMINER, recipient_ids=[ex1.id, ex2.id]
        )
        RoleGrantService.process_request(req.id, ex1, approve=False)

        assert req.status == RoleRequestStatus.PENDING.value
        assert player.is_examiner is False

        RoleGrantService.process_request(req.id, ex2, approve=True)
        assert req.status == RoleRequestStatus.APPROVED.value
        assert player.is_examiner is True


def test_last_rejection_closes_the_request(app, admin, player):
    with app.app_context():
        ex1 = _make_user()
        RoleGrantService.grant(ex1.id, EXAMINER, admin)

        req = RoleGrantService.create_request(player.id, EXAMINER)
        RoleGrantService.process_request(req.id, ex1, approve=False)

        assert req.status == RoleRequestStatus.REJECTED.value
        assert player.is_examiner is False


def test_admin_can_process_a_request_addressed_to_others(app, admin, player):
    """UJ-4 variante: la processa l'admin dalla propria coda."""
    with app.app_context():
        ex1 = _make_user()
        RoleGrantService.grant(ex1.id, EXAMINER, admin)

        req = RoleGrantService.create_request(
            player.id, EXAMINER, recipient_ids=[ex1.id]
        )
        RoleGrantService.process_request(req.id, admin, approve=True)

        assert req.status == RoleRequestStatus.APPROVED.value
        assert player.is_examiner is True


def test_non_recipient_examiner_cannot_process(app, admin, player):
    with app.app_context():
        ex1 = _make_user()
        ex2 = _make_user()
        RoleGrantService.grant(ex1.id, EXAMINER, admin)
        RoleGrantService.grant(ex2.id, EXAMINER, admin)

        req = RoleGrantService.create_request(
            player.id, EXAMINER, recipient_ids=[ex1.id]
        )
        with pytest.raises(PermissionDeniedError):
            RoleGrantService.process_request(req.id, ex2, approve=True)


def test_player_cannot_process_any_request(app, admin, player):
    with app.app_context():
        other = _make_user()
        req = RoleGrantService.create_request(player.id, EXAMINER)
        with pytest.raises(PermissionDeniedError):
            RoleGrantService.process_request(req.id, other, approve=True)


def test_process_missing_request_raises_not_found(app, admin):
    with app.app_context():
        with pytest.raises(NotFoundError):
            RoleGrantService.process_request(999999, admin, approve=True)


def test_pending_queue_is_scoped_to_the_actor(app, admin, player):
    with app.app_context():
        ex1 = _make_user()
        ex2 = _make_user()
        RoleGrantService.grant(ex1.id, EXAMINER, admin)
        RoleGrantService.grant(ex2.id, EXAMINER, admin)

        req = RoleGrantService.create_request(
            player.id, EXAMINER, recipient_ids=[ex1.id]
        )

        assert [r.id for r in RoleGrantService.get_pending_requests_for(ex1)] == [
            req.id
        ]
        assert RoleGrantService.get_pending_requests_for(ex2) == []
        # Admin vede tutto: è la coda di ultima istanza.
        assert [r.id for r in RoleGrantService.get_pending_requests_for(admin)] == [
            req.id
        ]


# ────────────────────────────────────────────────────────────────────────────────
# Override di debug (US-D1)
# ────────────────────────────────────────────────────────────────────────────────
def test_debug_self_grant_requires_debug_mode(app, player):
    with app.app_context():
        original = app.config.get("DEBUG_MODE")
        app.config["DEBUG_MODE"] = False
        try:
            with pytest.raises(PermissionDeniedError):
                RoleGrantService.debug_self_grant(player, EXAMINER)
        finally:
            app.config["DEBUG_MODE"] = original


def test_debug_self_grant_creates_a_normal_revocable_grant(app, admin, player):
    with app.app_context():
        original = app.config.get("DEBUG_MODE")
        app.config["DEBUG_MODE"] = True
        try:
            grant = RoleGrantService.debug_self_grant(player, EXAMINER)
        finally:
            app.config["DEBUG_MODE"] = original

        assert grant.notes == "debug self-grant"
        assert grant.granted_by_id == player.id
        assert player.is_examiner is True

        # Normale = revocabile e visibile nell'audit come ogni altro.
        RoleGrantService.revoke(player.id, EXAMINER, admin)
        assert player.is_examiner is False
        assert len(RoleGrantService.list_grants_history(EXAMINER)) == 1
