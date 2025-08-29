"""
PyTest configuration - Transaction-per-Test Pattern
Implements proper session management for SQLAlchemy testing
"""

import sys
import pytest
from pathlib import Path
from sqlalchemy.orm import scoped_session, sessionmaker
import datetime as _dt

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app  # noqa: E402
from models import db as _db  # noqa: E402
from models import User  # noqa: E402
from models.tournament.models import Tournament  # noqa: E402
from models.competition.models import Prova  # noqa: E402
from models.caching import cache_manager  # noqa: E402


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
    try:
        Session.remove()
        if transaction.is_active:
            transaction.rollback()
    except Exception:
        # Transaction may already be rolled back due to exceptions in tests
        pass
    finally:
        connection.close()


@pytest.fixture(scope="function", autouse=True)
def db_session(session):
    """Auto-use fixture to ensure session is available"""
    yield session


@pytest.fixture(scope="function", autouse=True)
def clear_cache():
    """Clear cache before each test to avoid caching issues"""
    cache_manager.clear_all()
    yield
    cache_manager.clear_all()


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


@pytest.fixture
def tournament(db_session):
    """
    Crea un torneo minimale tramite il service di dominio.
    Usa db_session per essere dentro la transazione del test.
    """
    from models.tournament.services import TournamentService

    # Qui non servono kwargs: il modello ha default sensati (tournament_type="Amalfi")
    t = TournamentService.create_tournament(name="Unit Test Tournament")

    # Garantisce che l'ID sia assegnato anche se il service cambiasse in futuro
    _db.session.flush()
    return t


@pytest.fixture
def started_prova(db_session):
    """
    Crea un Tournament e una Prova in stato 'playing' (prova avviata)
    aderente ai modelli attuali.
    """
    # Torneo minimo (tournament_type è non-nullable, ma ha default "Amalfi")
    t = Tournament(
        name="Tournament Fixture",
        tournament_type="Amalfi",
    )
    _db.session.add(t)
    _db.session.flush()  # ci serve t.id senza committare ancora

    # Prova 'avviata' con i campi obbligatori della codebase
    p = Prova(
        tournament_id=t.id,  # puoi ometterlo se vuoi una prova standalone
        number=1,
        name="Prova started",
        date=_dt.date.today(),
        discipline="palla 9",  # ammessi: palla 8/9/10
        distance=7,  # numero rack da giocare
        status="playing",  # nomenclatura attuale (non 'started')
        current_round=1,  # round corrente
    )
    _db.session.add(p)
    _db.session.commit()
    _db.session.refresh(p)
    return p


@pytest.fixture
def assign_director(db_session):
    """Factory per assegnare un director a un torneo con assigned_by valorizzato.
    Idempotente: se esiste già, restituisce quello.
    """
    from models.user.models import TournamentDirector

    def _assign(director_user, tournament, assigned_by_user):
        # get_or_create per evitare UNIQUE violation in caso di doppio uso
        existing = TournamentDirector.query.filter_by(
            user_id=director_user.id,
            tournament_id=tournament.id,
        ).one_or_none()
        if existing:
            return existing

        assoc = TournamentDirector(
            user_id=director_user.id,
            tournament_id=tournament.id,
            assigned_by_id=assigned_by_user.id,
        )
        _db.session.add(assoc)
        _db.session.commit()
        return assoc

    return _assign
