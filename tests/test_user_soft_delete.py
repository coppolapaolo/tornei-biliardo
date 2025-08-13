import pytest
from models import db
from models.user.services import UserDeletionService


@pytest.mark.usefixtures("app")
def test_user_soft_delete_anonymizes_and_blocks_login(player_user, admin_user, app):
    uid = player_user.id
    # Flask-Login ha bisogno di un request context per usare session/cookie
    with app.test_request_context("/"):
        UserDeletionService.delete_user(player_user)

    db.session.refresh(player_user)
    assert player_user.is_deleted is True
    assert player_user.email is None and player_user.phone is None
    assert player_user.previous_username is not None
    assert player_user.username.startswith(f"deleted-{uid}-")
    assert player_user.is_active is False
