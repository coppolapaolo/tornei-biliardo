"""
PyTest configuration - Transaction-per-Test Pattern
Implements proper session management for SQLAlchemy testing
"""

import sys
import pytest
from pathlib import Path
from sqlalchemy.orm import scoped_session, sessionmaker

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app  # noqa: E402
from models import db as _db  # noqa: E402
from models import User  # noqa: E402


@pytest.fixture(scope="session")
def app():
    """Create Flask app once per test session"""
    app = create_app("testing")

    # Establish application context for the entire test session
    ctx = app.app_context()
    ctx.push()

    yield app

    ctx.pop()


@pytest.fixture(scope="session")
def _database(app):
    """Create database schema once per test session"""
    _db.create_all()
    yield _db
    _db.drop_all()


@pytest.fixture(scope="function")
def session(_database):
    """Create a transactional database session for each test"""
    connection = _database.engine.connect()
    transaction = connection.begin()

    # Configure session with transaction
    session_factory = sessionmaker(bind=connection)
    Session = scoped_session(session_factory)

    # Monkey-patch Flask-SQLAlchemy to use our session
    _database.session = Session

    yield Session

    # Rollback transaction and cleanup
    Session.remove()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function", autouse=True)
def db_session(session):
    """Auto-use fixture to ensure session is available"""
    yield session


@pytest.fixture
def client(app, db_session):
    """Test client with proper session management"""
    return app.test_client()


# User fixtures centralized for reusability
@pytest.fixture
def director_user(db_session):
    """Create a director user for testing"""
    user = User(username="testdirector", email="director@test.com", role="director")
    user.set_password("password")
    db_session.add(user)
    db_session.commit()
    # Ensure object remains attached
    db_session.refresh(user)
    return user


@pytest.fixture
def player_user(db_session):
    """Create a player user for testing"""
    user = User(username="testplayer", email="player@test.com", role="player")
    user.set_password("password")
    db_session.add(user)
    db_session.commit()
    # Ensure object remains attached
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session):
    """Create an admin user for testing"""
    user = User(username="testadmin", email="admin@test.com", role="admin")
    user.set_password("password")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
