# tests/new/integration/test_admin_user_actions.py
"""Azioni admin sulla schermata utenti: anonimizza, verifica email, reinvio.

Testa i metodi REALI del service layer (UserService) e la visibilità endpoint
(ADR-028) delle nuove azioni admin-only.
"""

import uuid

import pytest
from sqlalchemy import select


def _make_player(verified=False):
    from models.user.services import UserService

    suffix = uuid.uuid4().hex[:8]
    user = UserService.create_user(
        username=f"player_{suffix}",
        email=f"player_{suffix}@example.com",
        password="secret123",
        role="player",
        send_verification_email=False,
    )
    if verified:
        user.is_verified = True
    from models import db

    db.session.commit()
    return user


def test_anonymize_user_scrubs_pii(app, db_session):
    from models.user.services import UserService
    from models.user.models import User

    user = _make_player()
    user_id = user.id

    UserService.anonymize_user(user_id, performed_by_id=None)

    reloaded = db_session.execute(
        select(User).where(User.id == user_id).execution_options(include_deleted=True)
    ).scalar_one()
    assert reloaded.deleted_at is not None
    assert reloaded.email is None
    assert reloaded.phone is None
    assert reloaded.username.startswith(f"deleted-{user_id}-")


def test_anonymize_user_rejects_admin(app, db_session):
    from models.user.services import UserService
    from models.user.models import User
    from utils.reset_data import reset_database_enhanced

    reset_database_enhanced()
    admin_username = app.config.get("ADMIN_USERNAME", "admin")
    admin = db_session.execute(
        select(User).where(User.username == admin_username)
    ).scalar_one()

    with pytest.raises(ValueError):
        UserService.anonymize_user(admin.id, performed_by_id=None)

    reloaded = db_session.execute(select(User).where(User.id == admin.id)).scalar_one()
    assert reloaded.deleted_at is None


def test_anonymize_user_rejects_self(app, db_session):
    from models.user.services import UserService

    user = _make_player()
    with pytest.raises(ValueError):
        UserService.anonymize_user(user.id, performed_by_id=user.id)


def test_set_email_verified(app, db_session):
    from models.user.services import UserService
    from models.user.models import User

    user = _make_player(verified=False)
    assert user.is_verified is False

    UserService.set_email_verified(user.id)

    reloaded = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
    assert reloaded.is_verified is True


def test_resend_verification_returns_false_when_already_verified(app, db_session):
    from models.user.services import UserService

    user = _make_player(verified=True)
    assert UserService.resend_verification_email(user.id) is False


class _FakeUser:
    def __init__(self, *, is_authenticated=True, is_director=False, is_admin=False):
        self.is_authenticated = is_authenticated
        self.is_director = is_director
        self.is_admin = is_admin


def test_user_management_actions_hidden_from_director(app, monkeypatch):
    """Le azioni di gestione utenti sono admin-only (ADR-028)."""
    from utils.feature_flags import is_endpoint_visible

    with app.test_request_context():
        # Forza il path "produzione" (in test l'allowlist è pass-through).
        monkeypatch.setitem(app.config, "TESTING", False)
        monkeypatch.setitem(app.config, "DEBUG_MODE", False)

        director = _FakeUser(is_director=True)
        admin = _FakeUser(is_admin=True)

        for endpoint in (
            "admin.user.anonymize_user",
            "admin.user.verify_user_email",
            "admin.user.resend_verification",
        ):
            assert not is_endpoint_visible(endpoint, director)
            assert is_endpoint_visible(endpoint, admin)
