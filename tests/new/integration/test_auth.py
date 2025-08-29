import pytest


def test_register_new_user(db_session):
    from models.user.services import UserService  # type: ignore

    u = UserService.create_user("alice1", "alice@test.local", "pass123")
    assert u.id is not None
    assert u.username == "alice1"
    assert getattr(u, "role", "player") == "player"


def test_register_duplicate_username_fails(db_session):
    from models.user.services import UserService  # type: ignore

    UserService.create_user("alice", "a1@test.local", "pass123")
    with pytest.raises(ValueError):
        UserService.create_user("alice", "a2@test.local", "pass456")


def test_login_success_and_wrong_password(db_session):
    from models.user.services import UserService  # type: ignore

    UserService.create_user("bob", "bob@test.local", "secret")
    assert UserService.authenticate_user("bob", "secret") is not None
    assert UserService.authenticate_user("bob", "WRONG") is None
    assert UserService.authenticate_user("unknown", "secret") is None


def test_login_logout_routes_flow(client, db_session):
    # Arrange
    from models.user.services import UserService  # type: ignore

    UserService.create_user("carol", "carol@test.local", "p@ss123")

    # Act: login route (i nomi dei campi potranno essere adeguati in implementazione)
    resp = client.post("/auth/login", data={"username": "carol", "password": "p@ss123"})
    assert resp.status_code in (200, 302)

    # Act: logout
    resp = client.get("/auth/logout")
    assert resp.status_code in (200, 302)
