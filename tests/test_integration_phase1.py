import pytest

def test_backward_compatibility_imports():
    """Test che gli import esistenti funzionano ancora dopo la modularizzazione"""
    from models import User, Tournament, Prova, Inscription, Match, Rack, Classification, MatchResult, Playoff, TournamentDirector, DirectorRequest
    from models.user.models import User as ModularUser
    assert User is ModularUser
    assert hasattr(User, 'is_admin')
    assert hasattr(User, 'set_password')
    assert hasattr(Tournament, '__tablename__')
    assert hasattr(Prova, '__tablename__')
    assert hasattr(Match, '__tablename__')
    assert hasattr(Playoff, '__tablename__')
    assert hasattr(TournamentDirector, '__tablename__')
    assert hasattr(DirectorRequest, '__tablename__')


def test_modular_imports():
    """Test che i nuovi import modulari funzionano"""
    from models.user.models import User, TournamentDirector, DirectorRequest
    from models.legacy_models import Tournament, Prova, Inscription, Match, Rack, Classification, MatchResult, Playoff
    assert hasattr(User, 'is_admin')
    assert hasattr(Tournament, 'get_status')
    assert hasattr(Prova, 'can_inscribe')
    assert hasattr(Match, 'player1_id')
    assert hasattr(Playoff, 'category')


def test_existing_functionality_smoke(app):
    """Test di smoke: le route principali rispondono senza errori (login, dashboard, ecc.)"""
    client = app.test_client()
    # Test login page (con prefisso auth)
    resp = client.get('/auth/login')
    assert resp.status_code == 200
    # Test home page
    resp = client.get('/')
    assert resp.status_code == 200
    # Test pagina dashboard (se richiede login, deve reindirizzare)
    resp = client.get('/dashboard')
    assert resp.status_code in (200, 302)