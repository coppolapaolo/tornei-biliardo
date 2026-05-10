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


def test_unverified_login_flash_renders_resend_link_as_html(client, db_session):
    """Regression: the "non è ancora verificato" warning embeds an inline
    link via Markup. A previous version concatenated `Markup + str` which
    silently escaped the `<a>` tag, leaving raw HTML visible in the page."""
    from models.user.services import UserService  # type: ignore

    UserService.create_user("dave", "dave@test.local", "p@ss123")
    # Default is_verified=False — login must redirect AND set the warning flash.

    resp = client.post(
        "/auth/login",
        data={"username": "dave", "password": "p@ss123"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # The link must appear rendered, not escaped.
    assert 'class="alert-link"' in body
    assert "&lt;a href=" not in body
