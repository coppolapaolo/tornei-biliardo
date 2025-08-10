import pytest


def test_backward_compatibility_imports():
    """Test che gli import esistenti funzionano ancora dopo la modularizzazione"""
    from models import (
        User,
        Tournament,
        Prova,
        Match,
        Playoff,
        TournamentDirector,
        DirectorRequest,
    )
    from models.user.models import User as ModularUser

    assert User is ModularUser
    assert hasattr(User, "is_admin")
    assert hasattr(User, "set_password")
    assert hasattr(Tournament, "__tablename__")
    assert hasattr(Prova, "__tablename__")
    assert hasattr(Match, "__tablename__")
    assert hasattr(Playoff, "__tablename__")
    assert hasattr(TournamentDirector, "__tablename__")
    assert hasattr(DirectorRequest, "__tablename__")


def test_models_metadata_present():
    from models import Tournament, Prova, Match, Classification, MatchResult, Playoff

    # Check alcune colonne chiave ancora esistenti
    assert hasattr(Tournament, "name")
    assert hasattr(Prova, "number")
    assert hasattr(Match, "round_number")
    assert hasattr(Classification, "position")
    assert hasattr(MatchResult, "winner_id")
    assert hasattr(Playoff, "category")


@pytest.mark.usefixtures("client")
def test_existing_functionality_smoke(client):
    """Smoke test: route principali rispondono senza errori.
    Usa la *client fixture* (function-scope) e forza logout per
    evitare dipendenze dallo stato di altri test.
    """
    # Assicurati di non essere autenticato (alcuni test precedenti loggano admin)
    client.get("/auth/logout", follow_redirects=True)

    # Login page (prefisso /auth)
    resp = client.get("/auth/login")
    assert resp.status_code == 200

    # Home page: può essere 200 (pubblica) oppure
    # 302 (auto-redirect admin se autenticato)
    resp = client.get("/")
    assert resp.status_code in (200, 302)

    # Dashboard generica: alcune app reindirizzano al login
    resp = client.get("/dashboard")
    assert resp.status_code in (200, 302)
