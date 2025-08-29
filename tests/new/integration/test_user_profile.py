# import pytest


def _register(username="dave", email=None, password="pass123"):
    from models.user.services import UserService  # type: ignore

    return UserService.create_user(
        username,
        email or f"{username}@test.local",
        password
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


# @pytest.mark.xfail(reason="TDD: implementare change_password")
def test_change_password_flow(db_session):
    from models.user.services import UserService  # type: ignore

    u = _register("gina", "gina@test.local", "old!123")
    UserService.change_password(u.id, old_password="old!123", new_password="new!123")
    assert UserService.authenticate_user("gina", "old!123") is None
    assert UserService.authenticate_user("gina", "new!123") is not None
