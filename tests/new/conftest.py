import os
import pytest
import uuid
from importlib import import_module


@pytest.fixture(scope="session", autouse=True)
def _fast_password_hashing():
    """Velocizza i test sostituendo l'hashing PBKDF2 di default (~600k iter)
    con una variante a 1 iterazione. Solo per i test: la produzione continua
    a usare il default Werkzeug. `check_password_hash` legge le iterazioni
    dall'hash salvato, quindi gli utenti creati nei test si autenticano
    correttamente. Vedi issue #47.

    Patcha il nome `generate_password_hash` nel namespace di
    `models.user.models`, unico call-site reale (tutto passa da
    `User.set_password`).
    """
    import models.user.models as um

    orig = um.generate_password_hash
    um.generate_password_hash = lambda pw, **kw: orig(pw, method="pbkdf2:sha256:1")
    try:
        yield
    finally:
        um.generate_password_hash = orig


@pytest.fixture(scope="session")
def app():
    os.environ.setdefault("FLASK_ENV", "testing")
    app_module = import_module("app")
    try:
        flask_app = app_module.create_app("testing")
    except TypeError:
        flask_app = app_module.create_app()

    # Solo configurazione; NON creiamo l'admin qui.
    # StaticPool: SQLite in-memory is per-connection. Without StaticPool,
    # db.drop_all() in fixtures gets a new connection (empty DB), leaving
    # stale data on the old connection. StaticPool forces one connection.
    from sqlalchemy.pool import StaticPool

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

    # Disable rate limiter in tests to avoid 429 errors from rapid login calls
    from utils.rate_limiter import limiter

    limiter.enabled = False

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

    # Clear all existing data before each test.
    # With StaticPool (single connection), we must ensure no pending
    # transaction before DROP TABLE, otherwise SQLite silently ignores it.
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    db.session.close()

    # Clear in-memory caches to prevent stale data between tests
    from models.caching import cache_manager

    cache_manager.clear_all()

    # Use test_request_context for setup (drop/create tables)
    # This provides session access for Flask-Babel translations during setup
    with app.test_request_context():
        # Drop and recreate all tables to ensure complete isolation
        db.drop_all()
        db.create_all()

        # Populate feature_config table with test data for ABAC
        _populate_test_features(db)

        # Configure session to NOT expire objects after commit
        # This prevents DetachedInstanceError in tests
        db.session.expire_on_commit = False

        # Clear any remaining session state
        db.session.remove()

        # Flask-Login caches the logged-in user on the app context `g`
        # (`g._login_user`). The session-scoped `app` fixture keeps a single
        # app context pushed for the whole suite, so that cache survives
        # across tests: a User logged in by one test stays referenced by the
        # next, detached after this fixture's db.session.remove()/drop_all,
        # causing DetachedInstanceError when a sibling test's request reads
        # current_user. Clear it before and after each test.
        from flask import g

        g.pop("_login_user", None)

        try:
            yield db.session
        finally:
            # Clean up after test
            g.pop("_login_user", None)
            try:
                db.session.rollback()
            except Exception:
                pass
            db.session.remove()


def _populate_test_features(db):
    """Populate feature_config table with test data."""
    import json
    from models.gamification.feature_models import FeatureConfig

    # Add essential features for tests
    test_features = [
        {
            "code": "tournament_creation",
            "name": "Creazione Tornei",
            "description": "Test feature",
            "rules": json.dumps(
                [
                    {
                        "description": "Level 10",
                        "conditions": [
                            {"type": "LEVEL", "operator": "gte", "value": 10}
                        ],
                    }
                ]
            ),
        },
        {
            "code": "create_campionato",
            "name": "Create Championship",
            "description": "Test feature",
            "rules": json.dumps(
                [
                    {
                        "description": "Director role",
                        "conditions": [{"type": "ROLE", "value": "DIRECTOR"}],
                    }
                ]
            ),
        },
        {
            "code": "create_match_direct",
            "name": "Create Direct Match",
            "description": "Test feature",
            "rules": json.dumps(
                [
                    {
                        "description": "5+ matches",
                        "conditions": [
                            {
                                "type": "METRIC",
                                "metric": "total_matches",
                                "operator": "gte",
                                "value": 5,
                            }
                        ],
                    }
                ]
            ),
        },
    ]

    for feature_data in test_features:
        feature = FeatureConfig(**feature_data, is_active=True)
        db.session.add(feature)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


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
        except Exception:
            pass
        db.session.expunge_all()

    return _clean


@pytest.fixture
def logged_in_client(app, db_session):
    """
    Create a test client with a logged-in user.

    Usage:
        def test_something(logged_in_client):
            client, user = logged_in_client(role="admin")
            response = client.get('/some/protected/route')
    """
    from models import User

    def _create_logged_in_client(role="player", username_prefix="test"):
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"{username_prefix}_{unique_id}",
            email=f"{username_prefix}_{unique_id}@test.com",
            role=role if isinstance(role, str) else role.value,
        )
        user.set_password("test123")
        db_session.add(user)
        db_session.commit()

        # Store user_id for later use
        user_id = user.id

        client = app.test_client()

        # Login using session manipulation (compatible with test client)
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user_id)
            sess["_fresh"] = True

        # Refresh user from current session to avoid DetachedInstanceError
        from models import db

        user = db.session.get(User, user_id)

        return client, user

    return _create_logged_in_client


# def pytest_runtest_logstart(nodeid, location):
#     print(f"\n>>> STARTING {nodeid}\n", flush=True)

# def pytest_runtest_logfinish(nodeid, location):
#     print(f"\n<<< FINISHED {nodeid}\n", flush=True)
