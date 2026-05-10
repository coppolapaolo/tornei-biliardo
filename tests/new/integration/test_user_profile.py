# import pytest


def _register(username="dave", email=None, password="pass123"):
    from models.user.services import UserService  # type: ignore

    return UserService.create_user(
        username, email or f"{username}@test.local", password
    )


def test_soft_delete_non_admin(db_session):
    from models.user.services import UserService  # type: ignore
    from models.user.models import User
    from sqlalchemy import select

    u = _register("eve", "eve@test.local", "pass123")
    UserService.soft_delete_user(u.id)

    # non autenticabile
    assert UserService.authenticate_user("eve", "pass123") is None

    # flag di soft delete presente (o equivalente)
    deleted = db_session.execute(
        select(User).where(User.id == u.id).execution_options(include_deleted=True)
    ).scalar_one()
    assert getattr(deleted, "deleted_at", None) is not None


# @pytest.mark.xfail(reason="TDD: implementare update_profile")
def test_update_profile_email_and_fields(db_session):
    from models.user.services import UserService  # type: ignore

    u = _register("frank", "frank@test.local")
    updated = UserService.update_user(u.id, email="new@test.local")
    assert updated.email == "new@test.local"


def test_changing_email_revokes_verification_and_queues_token(db_session):
    """Regression: a verified user that changes email must lose verification
    and receive a fresh verification token. Otherwise the old `is_verified=True`
    flag would falsely guarantee that an unconfirmed address is reachable —
    breaking the password recovery contract."""
    from models.user.services import UserService  # type: ignore
    from models.user.tokens import UserToken

    u = _register("hank", "hank@test.local")
    u.is_verified = True
    db_session.flush()

    updated = UserService.update_user(u.id, email="hank2@test.local")

    assert updated.email == "hank2@test.local"
    assert updated.is_verified is False
    # A new verification token was created and queued for post-commit send.
    assert hasattr(updated, "_pending_verification_email")
    pending = updated._pending_verification_email
    assert pending["token"] is not None
    # The token row exists in the DB.
    db_token = UserToken.query.filter_by(
        user_id=updated.id, token_type="verification"
    ).first()
    assert db_token is not None


def _simulate_post_register_cleanup(user):
    """Drop the registration-time pending token attr — mirrors the route flow
    where send_pending_verification_email() deletes it after sending."""
    if hasattr(user, "_pending_verification_email"):
        delattr(user, "_pending_verification_email")


def test_updating_other_fields_keeps_verification(db_session):
    """Username/phone changes alone must NOT invalidate is_verified."""
    from models.user.services import UserService  # type: ignore

    u = _register("ivy", "ivy@test.local")
    u.is_verified = True
    db_session.flush()
    _simulate_post_register_cleanup(u)

    updated = UserService.update_user(u.id, username="ivy_new", phone="+391234567890")

    assert updated.is_verified is True
    assert not hasattr(updated, "_pending_verification_email")


def test_resubmitting_same_email_keeps_verification(db_session):
    """Saving the form without actually changing email must NOT revoke
    verification — the user just hit Save with the same address."""
    from models.user.services import UserService  # type: ignore

    u = _register("jane", "Jane@test.local")
    u.is_verified = True
    db_session.flush()
    _simulate_post_register_cleanup(u)

    # Same email, different casing + surrounding whitespace — should be a no-op
    # for verification purposes.
    updated = UserService.update_user(u.id, email="  jane@test.local  ")

    assert updated.is_verified is True
    assert not hasattr(updated, "_pending_verification_email")


# @pytest.mark.xfail(reason="TDD: implementare change_password")
def test_change_password_flow(db_session):
    from models.user.services import UserService  # type: ignore

    u = _register("gina", "gina@test.local", "old!123")
    UserService.change_password(u.id, old_password="old!123", new_password="new!123")
    assert UserService.authenticate_user("gina", "old!123") is None
    assert UserService.authenticate_user("gina", "new!123") is not None
