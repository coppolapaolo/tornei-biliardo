"""E2E test fixtures — StaticPool for SQLite in-memory consistency.

E2E tests use Flask test client which creates its own DB connections.
With regular pooling, the fixture's session and the client's requests get
different SQLite in-memory databases (they're per-connection). StaticPool
forces all connections to share the same one.
"""

import os
import pytest
from importlib import import_module
from sqlalchemy.pool import StaticPool


@pytest.fixture(scope="session")
def app():
    """Create Flask app with StaticPool for E2E tests."""
    os.environ.setdefault("FLASK_ENV", "testing")
    app_module = import_module("app")
    try:
        flask_app = app_module.create_app("testing")
    except TypeError:
        flask_app = app_module.create_app()

    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_ENGINE_OPTIONS={
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        },
        ADMIN_USERNAME=flask_app.config.get("ADMIN_USERNAME", "admin"),
        ADMIN_EMAIL=flask_app.config.get("ADMIN_EMAIL", "admin@test.local"),
        ADMIN_PASSWORD=flask_app.config.get("ADMIN_PASSWORD", "admin123"),
        SERVER_NAME="localhost",
        APPLICATION_ROOT="/",
        PREFERRED_URL_SCHEME="http",
    )

    # Disable rate limiter
    from utils.rate_limiter import limiter

    limiter.enabled = False

    ctx = flask_app.app_context()
    ctx.push()
    from models import db

    db.create_all()
    try:
        yield flask_app
    finally:
        db.session.remove()
        db.drop_all()
        ctx.pop()


@pytest.fixture
def driver(client):
    """Guida una gara parlando solo HTTP (vedi `gara_driver.py`)."""
    from gara_driver import GaraDriver

    return GaraDriver(client)


@pytest.fixture
def campionato(client):
    """Guida un campionato intero, gare e playoff (`campionato_driver.py`)."""
    from campionato_driver import CampionatoDriver

    return CampionatoDriver(client)


@pytest.fixture
def sfida(client):
    """Guida una sfida individuale parlando solo HTTP (`sfida_driver.py`)."""
    from sfida_driver import SfidaDriver

    return SfidaDriver(client)
