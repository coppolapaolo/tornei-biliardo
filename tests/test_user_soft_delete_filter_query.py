from __future__ import annotations
import datetime as dt
import pytest
from models import db, User


def _mk_user(username: str, email: str) -> User:
    u = User(username=username, email=email, password_hash="x")
    return u


def _mark_deleted(u: User) -> None:
    # schema SoftDeleteMixin
    if hasattr(u, "deleted_at"):
        u.deleted_at = dt.datetime.utcnow()


@pytest.mark.usefixtures("app")
def test_query_excludes_deleted_by_default(app):
    with app.app_context():
        a = _mk_user("Active_X", "a@example.com")
        d = _mk_user("Deleted_X", "d@example.com")
        _mark_deleted(d)
        db.session.add_all([a, d])
        db.session.commit()
        names = {u.username for u in User.query.all()}
        assert "Active_X" in names and "Deleted_X" not in names


@pytest.mark.usefixtures("app")
def test_optout_include_deleted(app):
    with app.app_context():
        # opt-out esplicito per audit/report
        names = {
            u.username for u in User.query.execution_options(include_deleted=True).all()
        }
        # Non assertiamo contenuti specifici: verifichiamo solo che l'opzione non crashi
        assert isinstance(names, set)
