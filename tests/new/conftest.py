import os
import pytest
from importlib import import_module


@pytest.fixture(scope="session")
def app():
    os.environ.setdefault("FLASK_ENV", "testing")
    app_module = import_module("app")
    try:
        flask_app = app_module.create_app("testing")
    except TypeError:
        flask_app = app_module.create_app()

    # Solo configurazione; NON creiamo l'admin qui.
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        ADMIN_USERNAME=flask_app.config.get("ADMIN_USERNAME", "admin"),
        ADMIN_EMAIL=flask_app.config.get("ADMIN_EMAIL", "admin@test.local"),
        ADMIN_PASSWORD=flask_app.config.get("ADMIN_PASSWORD", "admin123"),
    )

    ctx = flask_app.app_context()
    ctx.push()
    from models import db

    db.create_all()
    try:
        yield flask_app
    finally:
        from models import db

        db.session.remove()
        db.drop_all()
        ctx.pop()


@pytest.fixture
def client(app):

    return app.test_client()


@pytest.fixture(autouse=True)
def db_session(app):
    from models import db

    conn = db.engine.connect()
    trans = conn.begin()
    old_bind = db.session.get_bind()
    db.session.bind = conn
    try:
        yield db.session
    finally:
        trans.rollback()
        conn.close()
        db.session.bind = old_bind
