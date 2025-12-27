import os
import pytest
import uuid
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
        SERVER_NAME="localhost",
        APPLICATION_ROOT="/",
        PREFERRED_URL_SCHEME="http",
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

    # Clear all existing data before each test
    db.session.remove()

    # Use test_request_context for setup (drop/create tables)
    # This provides session access for Flask-Babel translations during setup
    with app.test_request_context():
        # Drop and recreate all tables to ensure complete isolation
        db.drop_all()
        db.create_all()

        # Clear any remaining session state
        db.session.remove()

        try:
            yield db.session
        finally:
            # Clean up after test
            try:
                db.session.rollback()
            except:
                pass
            db.session.remove()


@pytest.fixture
def isolated_admin_user(db_session):
    """Create isolated admin user for each test."""
    from models import User
    from models.user.role_enum import UserRole

    unique_id = str(uuid.uuid4())[:8]
    admin = User(
        username=f"admin_{unique_id}",
        email=f"admin_{unique_id}@test.com",
        role=UserRole.ADMIN.value,
    )
    admin.set_password("admin123")
    db_session.add(admin)
    db_session.commit()
    return admin


@pytest.fixture
def isolated_director_user(db_session):
    """Create isolated director user for each test."""
    from models import User
    from models.user.role_enum import UserRole

    unique_id = str(uuid.uuid4())[:8]
    director = User(
        username=f"director_{unique_id}",
        email=f"director_{unique_id}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("director123")
    db_session.add(director)
    db_session.commit()
    return director


@pytest.fixture
def isolated_players(db_session):
    """Create isolated players for each test."""
    from models import User
    from models.user.role_enum import UserRole

    batch_id = str(uuid.uuid4())[:8]
    players = []
    for i in range(12):  # Create 12 players
        player = User(
            username=f"player_{i}_{batch_id}",
            email=f"player_{i}_{batch_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        players.append(player)

    db_session.add_all(players)
    db_session.commit()
    return players


@pytest.fixture
def clean_session():
    """Clean session fixture that handles transaction state properly."""
    from models import db

    def _clean():
        try:
            db.session.rollback()
        except:
            pass
        db.session.expunge_all()

    return _clean

# def pytest_runtest_logstart(nodeid, location):
#     print(f"\n>>> STARTING {nodeid}\n", flush=True)

# def pytest_runtest_logfinish(nodeid, location):
#     print(f"\n<<< FINISHED {nodeid}\n", flush=True)
