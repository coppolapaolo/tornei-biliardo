from models import (
    User,
    TournamentDirector,
    DirectorRequest,
    Tournament,          # serve per il test di retro-compatibilità
)

# --------------------------------------------------------------------
# 1) Import corretti e alias verso il nuovo dominio user
# --------------------------------------------------------------------
def test_user_imports():
    assert User.__name__ == "User"
    assert TournamentDirector.__name__ == "TournamentDirector"
    assert DirectorRequest.__name__ == "DirectorRequest"
    # lo User importato da models deve essere lo stesso della versione modulare
    from models.user.models import User as ModularUser
    assert User is ModularUser


# --------------------------------------------------------------------
# 2) Backward-compatibility: i vecchi modelli non-utente sono ancora importabili
# --------------------------------------------------------------------
def test_backward_compatibility():
    # Se arriva qui senza eccezioni l’import di Tournament funziona
    assert Tournament.__name__ == "Tournament"


# --------------------------------------------------------------------
# 3) Creazione utente di base, password hashing e proprietà di ruolo
# --------------------------------------------------------------------
def test_user_creation():
    u = User(username="test", email="t@t.com", role="player")
    u.set_password("secret123")
    assert u.role == "player"
    assert u.check_password("secret123")
    assert u.is_player
